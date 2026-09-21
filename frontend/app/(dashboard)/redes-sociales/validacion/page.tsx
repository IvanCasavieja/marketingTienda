"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Loader2, Plus } from "lucide-react";
import { clsx } from "clsx";
import { toast } from "sonner";
import { rrssApi, type RrssConfig, type RrssImagen, type RrssValidacion } from "@/lib/api";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { hasPermission } from "@/lib/permissions";
import CatTiBadge from "@/components/rrss/CatTiBadge";
import Historial from "@/components/rrss/Historial";
import ReviewStep, { type ItemPendiente, type Progreso } from "@/components/rrss/ReviewStep";
import UploadStep, { type PlacaLocal } from "@/components/rrss/UploadStep";
import { conReintentos, esTransitorio } from "@/components/rrss/reintentos";

const PARALELO = 3; // placas validándose a la vez

function mensajeDeError(e: unknown, porDefecto: string): string {
  const detalle = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detalle === "string" ? detalle : porDefecto;
}

// Sin respuesta = el servidor no contestó (caído, reiniciándose, cortado por el proxy).
const sinRespuesta = (e: unknown): boolean => !(e as { response?: unknown } | null)?.response;

export default function ValidacionRrssPage() {
  const { t } = useTranslation();
  const { user } = useCurrentUser();
  const puedeValidar = hasPermission(user, "rrss.validate");

  const [tabElegida, setTab] = useState<"nueva" | "historial">("nueva");
  // Sin permiso para validar solo se ve el historial.
  const tab = user && !puedeValidar ? "historial" : tabElegida;
  const [fase, setFase] = useState<"cargar" | "revisar">("cargar");

  const [placas, setPlacas] = useState<PlacaLocal[]>([]);
  const [mailing, setMailing] = useState<File | null>(null);
  const [config, setConfig] = useState<RrssConfig>({ legal_bases: "", legal_alcohol: "" });
  const [errorCarga, setErrorCarga] = useState<string | null>(null);
  const [creando, setCreando] = useState(false);

  const [validacion, setValidacion] = useState<RrssValidacion | null>(null);
  const [pendientes, setPendientes] = useState<ItemPendiente[]>([]);
  const [progreso, setProgreso] = useState<Progreso | null>(null);
  const [abriendoId, setAbriendoId] = useState<number | null>(null);
  const placasRef = useRef<PlacaLocal[]>([]);
  useEffect(() => { placasRef.current = placas; }, [placas]);

  useEffect(() => {
    rrssApi.config().then(({ data }) => setConfig(data)).catch(() => {});
  }, []);
  // Las URLs de las miniaturas viven mientras viva la página.
  useEffect(() => () => placasRef.current.forEach((p) => URL.revokeObjectURL(p.url)), []);

  const archivosRef = useRef<PlacaLocal[]>([]);

  // Valida las placas `ordenes` (posiciones en archivosRef) de la validación `validacionId`
  // y, cuando no queda ninguna, la cierra. Sirve para la primera pasada y para reintentar.
  const ejecutar = useCallback(async (validacionId: number, ordenes: number[], total: number) => {
    let siguiente = 0;
    let hechas = total - ordenes.length;
    let caido = false;
    setProgreso({ fase: "validando", hechas, total });

    // Un pool de PARALELO trabajadores: cada placa se valida en su propia request,
    // y a medida que termina aparece en pantalla.
    const trabajador = async () => {
      while (!caido && siguiente < ordenes.length) {
        const i = ordenes[siguiente++];
        const placa = archivosRef.current[i];
        setPendientes((prev) => prev.map((p) => (p.orden === i ? { ...p, analizando: true } : p)));
        let img: RrssImagen;
        try {
          img = (await conReintentos(() => rrssApi.validarImagen(validacionId, placa.file, i))).data;
        } catch (e) {
          if (esTransitorio(e)) {
            // El servidor no responde ni después de reintentar: se frena todo en vez de
            // marcar esta placa y las que faltan como error. Quedan pendientes, y con
            // "Reintentar" se retoma justo donde se cortó.
            caido = true;
            setPendientes((prev) => prev.map((p) => (p.orden === i ? { ...p, analizando: false } : p)));
            return;
          }
          // Una placa que falla por su cuenta (no es una imagen, etc.) no frena a las demás.
          img = {
            id: -(i + 1), orden: i, nombre_archivo: placa.file.name, ancho: 0, alto: 0, formato: "",
            estado: "error", match: null, filas: [], error: mensajeDeError(e, t("rrss.errorPlaca")), vista: placa.url,
          };
        }
        setValidacion((prev) => (prev ? { ...prev, imagenes: [...prev.imagenes, img] } : prev));
        setPendientes((prev) => prev.filter((p) => p.orden !== i));
        hechas += 1;
        setProgreso({ fase: "validando", hechas, total });
      }
    };
    await Promise.all(Array.from({ length: Math.min(PARALELO, ordenes.length) }, trabajador));

    if (caido) {
      setProgreso({ fase: "pausada", hechas, total });
      return;
    }
    setProgreso({ fase: "cerrando", hechas: total, total });
    try {
      const { data } = await conReintentos(() => rrssApi.cerrar(validacionId));
      setValidacion((prev) => (prev ? { ...prev, resumen: data.resumen, estado: "completada" } : prev));
      setProgreso({ fase: "listo", hechas: total, total });
    } catch (e) {
      // Sin cerrar no hay resumen del lote: queda pausada y "Reintentar" vuelve a cerrar.
      toast.error(sinRespuesta(e) ? t("rrss.errorServidor") : mensajeDeError(e, t("rrss.errorCerrar")));
      setProgreso({ fase: "pausada", hechas: total, total });
    }
  }, [t]);

  const iniciar = useCallback(async () => {
    if (!mailing || placas.length === 0) return;
    setErrorCarga(null);
    setCreando(true);
    let v: RrssValidacion;
    try {
      v = (await rrssApi.crear(mailing, config)).data;
    } catch (e) {
      setErrorCarga(sinRespuesta(e) ? t("rrss.errorServidor") : mensajeDeError(e, t("rrss.errorMailing")));
      setCreando(false);
      return;
    }
    setCreando(false);

    archivosRef.current = [...placas];
    setValidacion({ ...v, imagenes: [] });
    setPendientes(placas.map((p, i) => ({ orden: i, nombre: p.file.name, url: p.url, analizando: false })));
    setFase("revisar");
    await ejecutar(v.id, placas.map((_, i) => i), placas.length);
  }, [mailing, placas, config, t, ejecutar]);

  // Retoma una validación cortada: las placas que faltaban y las que dieron error.
  const reintentar = useCallback(async () => {
    if (!validacion) return;
    const archivos = archivosRef.current;
    const ordenes = Array.from(new Set([
      ...pendientes.map((p) => p.orden),
      ...validacion.imagenes.filter((i) => i.estado === "error").map((i) => i.orden),
    ])).sort((a, b) => a - b);
    // Las que dieron error salen de la lista y vuelven a la cola (el servidor
    // reemplaza la anterior por su `orden`, no la duplica).
    setValidacion({ ...validacion, imagenes: validacion.imagenes.filter((i) => i.estado !== "error") });
    setPendientes(ordenes.map((o) => ({ orden: o, nombre: archivos[o].file.name, url: archivos[o].url, analizando: false })));
    await ejecutar(validacion.id, ordenes, archivos.length);
  }, [validacion, pendientes, ejecutar]);

  async function abrirDelHistorial(id: number) {
    setAbriendoId(id);
    try {
      const { data } = await rrssApi.obtener(id);
      setValidacion(data);
      setPendientes([]);
      setProgreso(null);
      setFase("revisar");
    } catch (e) {
      toast.error(sinRespuesta(e) ? t("rrss.errorServidor") : mensajeDeError(e, t("rrss.errorAbrir")));
    } finally {
      setAbriendoId(null);
    }
  }

  function volver() {
    setFase("cargar");
    setValidacion(null);
    setPendientes([]);
    setProgreso(null);
  }
  function nueva() {
    placas.forEach((p) => URL.revokeObjectURL(p.url));
    setPlacas([]);
    setMailing(null);
    setErrorCarga(null);
    volver();
    setTab("nueva");
  }

  // "pausada" (el servidor no respondió) no cuenta como corriendo: no hay nada en marcha
  // y hay que poder empezar otra validación o reintentar.
  const corriendo = progreso !== null && (progreso.fase === "validando" || progreso.fase === "cerrando");

  return (
    <div className="animate-fade-in w-full space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-4">
          <CatTiBadge trabajando={corriendo || creando} size={48} />
          <div>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">{t("rrss.title")}</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{t("rrss.subtitle")}</p>
          </div>
        </div>

        {fase === "revisar" ? (
          <div className="flex items-center gap-2">
            {tab === "historial" && (
              <button onClick={volver} className="btn-secondary text-sm flex items-center gap-2">
                <ArrowLeft size={15} /> {t("rrss.volverHistorial")}
              </button>
            )}
            {puedeValidar && (
              <button onClick={nueva} disabled={corriendo} className="btn-primary text-sm disabled:opacity-40">
                <Plus size={15} /> {t("rrss.nuevaValidacion")}
              </button>
            )}
          </div>
        ) : (
          <div className="flex gap-1 p-1 rounded-xl bg-slate-100 dark:bg-slate-800">
            {puedeValidar && (
              <button onClick={() => setTab("nueva")}
                className={clsx("px-4 py-1.5 rounded-lg text-sm font-medium transition-colors",
                  tab === "nueva" ? "bg-white dark:bg-slate-700 shadow-sm text-slate-900 dark:text-slate-100" : "text-slate-500")}>
                {t("rrss.tabNueva")}
              </button>
            )}
            <button onClick={() => setTab("historial")}
              className={clsx("px-4 py-1.5 rounded-lg text-sm font-medium transition-colors",
                tab === "historial" ? "bg-white dark:bg-slate-700 shadow-sm text-slate-900 dark:text-slate-100" : "text-slate-500")}>
              {t("rrss.tabHistorial")}
            </button>
          </div>
        )}
      </div>

      {creando && (
        <div className="card p-6 flex items-center gap-4">
          <CatTiBadge trabajando />
          <div>
            <p className="text-sm font-medium text-slate-800 dark:text-slate-100 flex items-center gap-2">
              <Loader2 size={14} className="animate-spin text-brand-500" /> {t("rrss.leyendoMailing")}
            </p>
            <p className="text-xs text-slate-500 mt-0.5">{t("rrss.leyendoMailingHint")}</p>
          </div>
        </div>
      )}

      {!creando && fase === "cargar" && tab === "nueva" && puedeValidar && (
        <UploadStep
          placas={placas} onPlacas={setPlacas} mailing={mailing} onMailing={setMailing}
          config={config} onConfig={setConfig} onValidar={iniciar} error={errorCarga}
        />
      )}

      {!creando && fase === "cargar" && tab === "historial" && (
        <Historial puedeBorrar={puedeValidar} onAbrir={abrirDelHistorial} abriendoId={abriendoId} />
      )}

      {fase === "revisar" && validacion && (
        <ReviewStep
          validacion={validacion} pendientes={pendientes} progreso={progreso}
          onReintentar={progreso ? reintentar : undefined}
        />
      )}
    </div>
  );
}

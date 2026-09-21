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

const PARALELO = 3; // placas validándose a la vez

function mensajeDeError(e: unknown, porDefecto: string): string {
  const detalle = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detalle === "string" ? detalle : porDefecto;
}

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

  const iniciar = useCallback(async () => {
    if (!mailing || placas.length === 0) return;
    setErrorCarga(null);
    setCreando(true);
    let v: RrssValidacion;
    try {
      v = (await rrssApi.crear(mailing, config)).data;
    } catch (e) {
      setErrorCarga(mensajeDeError(e, t("rrss.errorMailing")));
      setCreando(false);
      return;
    }
    setCreando(false);

    const archivos = [...placas];
    const total = archivos.length;
    setValidacion({ ...v, imagenes: [] });
    setPendientes(archivos.map((p, i) => ({ orden: i, nombre: p.file.name, url: p.url, analizando: false })));
    setProgreso({ fase: "validando", hechas: 0, total });
    setFase("revisar");

    // Un pool de PARALELO trabajadores: cada placa se valida en su propia request,
    // y a medida que termina aparece en pantalla.
    let siguiente = 0;
    let hechas = 0;
    const trabajador = async () => {
      while (siguiente < total) {
        const i = siguiente++;
        setPendientes((prev) => prev.map((p) => (p.orden === i ? { ...p, analizando: true } : p)));
        let img: RrssImagen;
        try {
          img = (await rrssApi.validarImagen(v.id, archivos[i].file, i)).data;
        } catch (e) {
          // Una placa que falla no frena a las demás: queda marcada con su motivo.
          img = {
            id: -(i + 1), orden: i, nombre_archivo: archivos[i].file.name, ancho: 0, alto: 0, formato: "",
            estado: "error", match: null, filas: [], error: mensajeDeError(e, t("rrss.errorPlaca")), vista: archivos[i].url,
          };
        }
        setValidacion((prev) => (prev ? { ...prev, imagenes: [...prev.imagenes, img] } : prev));
        setPendientes((prev) => prev.filter((p) => p.orden !== i));
        hechas += 1;
        setProgreso({ fase: "validando", hechas, total });
      }
    };
    await Promise.all(Array.from({ length: Math.min(PARALELO, total) }, trabajador));

    setProgreso({ fase: "cerrando", hechas: total, total });
    try {
      const { data } = await rrssApi.cerrar(v.id);
      setValidacion((prev) => (prev ? { ...prev, resumen: data.resumen, estado: "completada" } : prev));
    } catch (e) {
      toast.error(mensajeDeError(e, t("rrss.errorCerrar")));
    }
    setProgreso({ fase: "listo", hechas: total, total });
  }, [mailing, placas, config, t]);

  async function abrirDelHistorial(id: number) {
    setAbriendoId(id);
    try {
      const { data } = await rrssApi.obtener(id);
      setValidacion(data);
      setPendientes([]);
      setProgreso(null);
      setFase("revisar");
    } catch (e) {
      toast.error(mensajeDeError(e, t("rrss.errorAbrir")));
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

  const corriendo = progreso !== null && progreso.fase !== "listo";

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
        <ReviewStep validacion={validacion} pendientes={pendientes} progreso={progreso} />
      )}
    </div>
  );
}

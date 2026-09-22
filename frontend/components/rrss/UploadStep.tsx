"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { FileSpreadsheet, FileText, FolderOpen, ImagePlus, Play, Trash2, UploadCloud, X } from "lucide-react";
import { clsx } from "clsx";
import type { RrssConfig, RrssTipoArchivo, RrssTipos } from "@/lib/api";

export interface PlacaLocal {
  key: string;
  file: File;
  url: string;
}

/**
 * Qué archivos se aceptan NO se escribe acá. Viene del backend (GET /rrss/config),
 * que lo lee de app/data/rrss_archivos.json — el mismo archivo con el que después
 * acepta o rechaza lo que se sube. Estaba escrito tres veces (acá dos y en
 * routes/rrss.py una) y el backend ni miraba el tipo del mailing.
 */
function acepta(tipo: RrssTipoArchivo, file: File): boolean {
  const nombre = file.name.toLowerCase();
  return tipo.extensiones.some((e) => nombre.endsWith(e)) || tipo.content_types.includes(file.type);
}

/** Lo que va en el `accept` de un <input type=file>: extensiones y tipos juntos. */
function acceptDe(tipo: RrssTipoArchivo): string {
  return [...tipo.extensiones, ...tipo.content_types].join(",");
}

/** ¿Este archivo sirve como fuente, sea mailing o planilla? Mismo criterio que
 *  el backend (archivos.acepta_fuente). Antes la zona de arrastre no preguntaba
 *  nada: se arrastraba un .docx, entraba, se habilitaba Validar y el backend
 *  contestaba "No pude abrir el archivo como imagen" — un mensaje sobre
 *  imágenes, para un Word, en un panel que se llama "Mailing o planilla". La
 *  zona de las placas sí filtraba: este era el único lugar donde la lista única
 *  de tipos no se aplicaba. */
export function aceptaFuente(tipos: RrssTipos, file: File): boolean {
  return acepta(tipos.fuentes.mailing, file) || acepta(tipos.fuentes.planilla, file);
}

/** Planilla o mailing, con el mismo criterio que el backend (archivos.origen_de):
 *  manda la extensión, porque el navegador manda cualquier cosa como tipo de un
 *  .xlsx y a veces nada para un .csv. */
export function esPlanilla(tipos: RrssTipos, file: File): boolean {
  const nombre = file.name.toLowerCase();
  if (tipos.fuentes.planilla.extensiones.some((e) => nombre.endsWith(e))) return true;
  if (tipos.fuentes.mailing.extensiones.some((e) => nombre.endsWith(e))) return false;
  return tipos.fuentes.planilla.content_types.includes(file.type);
}

/** Proporción → nombre de formato, igual que el backend (imagenes.clasificar_formato). */
export function formatoDe(ancho: number, alto: number): string {
  if (!alto) return "";
  const r = ancho / alto;
  if (Math.abs(r - 1) <= 0.03) return "1:1";
  if (Math.abs(r - 0.8) <= 0.03) return "4:5";
  if (Math.abs(r - 9 / 16) <= 0.03) return "9:16";
  return `${ancho}×${alto}`;
}

/** Lo que entró y lo que quedó afuera por pesar de más. Las dos cosas juntas
 *  porque la regla es UNA: si la función que filtra no dice a quién dejó
 *  afuera, el que arrastra una carpeta de 40 placas ve 38 y no se entera. */
export interface PlacasElegidas {
  placas: PlacaLocal[];
  /** Nombres de las placas que superan `max_mb`. */
  pesadas: string[];
}

export function crearPlacasLocales(archivos: File[], existentes: PlacaLocal[], tipo: RrssTipoArchivo): PlacasElegidas {
  const vistas = new Set(existentes.map((p) => p.key));
  const nuevas: PlacaLocal[] = [];
  const pesadas: string[] = [];
  for (const file of archivos) {
    if (!acepta(tipo, file)) continue;
    // El tamaño máximo sale del MISMO archivo que usa el backend para rechazar
    // (app/data/rrss_archivos.json, vía GET /rrss/config), igual que los tipos.
    // Acá no se miraba: la pantalla dejaba empezar a subir una carpeta entera
    // de placas pasadas de tamaño para que el servidor las tirara de a una, con
    // la barra de progreso corriendo. La regla del archivo único, a medias.
    if (file.size > tipo.max_mb * 1024 * 1024) {
      pesadas.push(file.name);
      continue;
    }
    const key = `${file.name}|${file.size}|${file.lastModified}`;
    if (vistas.has(key)) continue;
    vistas.add(key);
    nuevas.push({ key, file, url: URL.createObjectURL(file) });
  }
  return {
    placas: [...existentes, ...nuevas].sort((a, b) =>
      a.file.name.localeCompare(b.file.name, undefined, { numeric: true, sensitivity: "base" }),
    ),
    pesadas,
  };
}

// Arrastrar una CARPETA entera: el navegador entrega una entrada de directorio,
// no los archivos, y hay que recorrerla. `dataTransfer.files` solo trae la carpeta.
async function archivosDeUnDrop(dt: DataTransfer): Promise<File[]> {
  const entradas = Array.from(dt.items ?? [])
    .map((i) => (i.kind === "file" ? i.webkitGetAsEntry?.() : null))
    .filter((e): e is FileSystemEntry => !!e);
  if (!entradas.length) return Array.from(dt.files);

  const leer = async (entrada: FileSystemEntry): Promise<File[]> => {
    if (entrada.isFile) {
      return new Promise((ok) => (entrada as FileSystemFileEntry).file((f) => ok([f]), () => ok([])));
    }
    const lector = (entrada as FileSystemDirectoryEntry).createReader();
    const hijos: FileSystemEntry[] = [];
    // readEntries devuelve de a tandas: hay que llamarlo hasta que venga vacío
    for (;;) {
      const tanda = await new Promise<FileSystemEntry[]>((ok) => lector.readEntries(ok, () => ok([])));
      if (!tanda.length) break;
      hijos.push(...tanda);
    }
    return (await Promise.all(hijos.map(leer))).flat();
  };
  return (await Promise.all(entradas.map(leer))).flat();
}

function Miniatura({ placa, onQuitar }: { placa: PlacaLocal; onQuitar: () => void }) {
  const [formato, setFormato] = useState("");
  return (
    <div className="group relative rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden bg-white dark:bg-slate-800">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={placa.url}
        alt={placa.file.name}
        loading="lazy"
        onLoad={(e) => setFormato(formatoDe(e.currentTarget.naturalWidth, e.currentTarget.naturalHeight))}
        className="w-full h-32 object-contain bg-slate-100 dark:bg-slate-900"
      />
      <div className="px-2 py-1.5 flex items-center gap-1.5">
        <p className="text-[11px] text-slate-600 dark:text-slate-300 truncate flex-1" title={placa.file.name}>
          {placa.file.name.replace(/^.*?_(\d+(?: copia)?)\.\w+$/i, "$1")}
        </p>
        {formato && <span className="badge-slate shrink-0">{formato}</span>}
      </div>
      <button
        onClick={onQuitar}
        className="absolute top-1 right-1 p-1 rounded-full bg-black/55 text-white opacity-0 group-hover:opacity-100 transition-opacity"
        aria-label="quitar"
      >
        <X size={12} />
      </button>
    </div>
  );
}

interface Props {
  placas: PlacaLocal[];
  onPlacas: (siguiente: PlacaLocal[]) => void;
  mailing: File | null;
  onMailing: (f: File | null) => void;
  config: RrssConfig;
  onConfig: (c: RrssConfig) => void;
  onValidar: () => void;
  error: string | null;
  /** Qué archivos se aceptan, tal como los declara el backend. */
  tipos: RrssTipos;
}

/**
 * Pantalla de carga, en vista comparativa: las placas a la izquierda y la fuente
 * a la derecha, ya visible. Así quien carga confirma de un vistazo que subió la
 * fuente correcta para esas placas.
 *
 * La fuente es UNA sola y puede ser de dos clases: el mailing original (PDF o
 * imagen, que CatTi mira y transcribe) o la PLANILLA de la campaña (.xlsx/.csv,
 * que se lee como datos). Se cargan por el mismo lugar a propósito --pedido de
 * Ivan: "en esta misma pantallita que tenemos para arrastrar el archivo"-- y
 * cargar una reemplaza a la otra: no se valida contra las dos a la vez.
 */
export default function UploadStep({ placas, onPlacas, mailing, onMailing, config, onConfig, onValidar, error, tipos }: Props) {
  const { t } = useTranslation();
  const inputImagenes = useRef<HTMLInputElement>(null);
  const inputCarpeta = useRef<HTMLInputElement>(null);
  const inputMailing = useRef<HTMLInputElement>(null);
  const [arrastrando, setArrastrando] = useState<"placas" | "mailing" | null>(null);
  // El motivo por el que un archivo no entró como fuente. Vive acá y no en el
  // error general de la pantalla porque se contesta acá mismo, al lado del
  // panel donde se soltó.
  const [errorFuente, setErrorFuente] = useState<string | null>(null);
  // Lo mismo del lado de las placas: las que no entraron por pesar de más se
  // dicen al lado de su panel, con nombre y apellido.
  const [errorPlacas, setErrorPlacas] = useState<string | null>(null);
  const planilla = mailing ? esPlanilla(tipos, mailing) : false;
  // La vista previa solo tiene sentido para el mailing: una planilla no se mira,
  // se lee. Además crear un object URL de un .xlsx no sirve para nada.
  const mailingUrl = useMemo(
    () => (mailing && !esPlanilla(tipos, mailing) ? URL.createObjectURL(mailing) : null),
    [mailing, tipos],
  );
  useEffect(() => () => { if (mailingUrl) URL.revokeObjectURL(mailingUrl); }, [mailingUrl]);

  const agregar = (archivos: File[]) => {
    const { placas: siguiente, pesadas } = crearPlacasLocales(archivos, placas, tipos.placas);
    setErrorPlacas(pesadas.length
      ? t("rrss.placasMuyPesadas", { count: pesadas.length, max: tipos.placas.max_mb, nombres: pesadas.join(", ") })
      : null);
    onPlacas(siguiente);
  };

  /** La única puerta por la que entra la fuente: la arrastren o la elijan. Si
   *  no sirve se dice por qué acá, con los mismos tipos y el mismo tamaño que
   *  usa el backend (app/data/rrss_archivos.json), en vez de dejar que se suba
   *  para que la rechacen del otro lado. */
  const elegirFuente = (f: File | null | undefined) => {
    if (!f) return;
    if (!aceptaFuente(tipos, f)) {
      setErrorFuente(t("rrss.fuenteNoAceptada", {
        nombre: f.name,
        mailing: tipos.fuentes.mailing.etiqueta,
        planilla: tipos.fuentes.planilla.etiqueta,
      }));
      return;
    }
    const tipo = esPlanilla(tipos, f) ? tipos.fuentes.planilla : tipos.fuentes.mailing;
    if (f.size > tipo.max_mb * 1024 * 1024) {
      setErrorFuente(t("rrss.fuenteMuyPesada", {
        nombre: f.name, mb: Math.round(f.size / (1024 * 1024)), max: tipo.max_mb,
      }));
      return;
    }
    setErrorFuente(null);
    onMailing(f);
  };

  const esPdf = mailing ? mailing.type === "application/pdf" || /\.pdf$/i.test(mailing.name) : false;
  const listo = placas.length > 0 && !!mailing;

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5 items-start">
        {/* ── Izquierda: las placas ─────────────────────────────────────── */}
        <section
          className={clsx("card p-5 space-y-4 transition-colors", arrastrando === "placas" && "ring-2 ring-brand-500/50")}
          onDragOver={(e) => { e.preventDefault(); setArrastrando("placas"); }}
          onDragLeave={() => setArrastrando(null)}
          onDrop={async (e) => {
            e.preventDefault();
            setArrastrando(null);
            agregar(await archivosDeUnDrop(e.dataTransfer));
          }}
        >
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                {t("rrss.placas")} {placas.length > 0 && <span className="text-slate-400 font-normal">· {placas.length}</span>}
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{t("rrss.placasHint", { tipos: tipos.placas.etiqueta })}</p>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={() => inputImagenes.current?.click()} className="btn-secondary text-xs flex items-center gap-1.5">
                <ImagePlus size={14} /> {t("rrss.elegirImagenes")}
              </button>
              <button onClick={() => inputCarpeta.current?.click()} className="btn-secondary text-xs flex items-center gap-1.5">
                <FolderOpen size={14} /> {t("rrss.elegirCarpeta")}
              </button>
              {placas.length > 0 && (
                <button
                  onClick={() => { placas.forEach((p) => URL.revokeObjectURL(p.url)); onPlacas([]); }}
                  className="btn-ghost text-xs flex items-center gap-1.5"
                >
                  <Trash2 size={14} /> {t("rrss.quitarTodas")}
                </button>
              )}
            </div>
          </div>
          <input ref={inputImagenes} type="file" multiple accept={acceptDe(tipos.placas)} className="hidden"
            onChange={(e) => { agregar(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
          <input ref={inputCarpeta} type="file" multiple className="hidden"
            {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
            onChange={(e) => { agregar(Array.from(e.target.files ?? [])); e.target.value = ""; }} />

          {errorPlacas && (
            <p className="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2">
              {errorPlacas}
            </p>
          )}

          {placas.length === 0 ? (
            <button
              onClick={() => inputImagenes.current?.click()}
              className="w-full h-72 rounded-2xl border-2 border-dashed border-slate-200 dark:border-slate-700 flex flex-col items-center justify-center gap-2 text-slate-400 hover:border-brand-400 hover:text-brand-500 transition-colors"
            >
              <UploadCloud size={30} />
              <span className="text-sm">{t("rrss.arrastraPlacas")}</span>
            </button>
          ) : (
            <div className="grid grid-cols-3 sm:grid-cols-4 gap-3 max-h-[68vh] overflow-y-auto pr-1">
              {placas.map((p) => (
                <Miniatura
                  key={p.key}
                  placa={p}
                  onQuitar={() => { URL.revokeObjectURL(p.url); onPlacas(placas.filter((x) => x.key !== p.key)); }}
                />
              ))}
            </div>
          )}
        </section>

        {/* ── Derecha: el mailing original ──────────────────────────────── */}
        <section
          className={clsx("card p-5 space-y-4 transition-colors", arrastrando === "mailing" && "ring-2 ring-brand-500/50")}
          onDragOver={(e) => { e.preventDefault(); setArrastrando("mailing"); }}
          onDragLeave={() => setArrastrando(null)}
          onDrop={(e) => {
            e.preventDefault();
            setArrastrando(null);
            elegirFuente(e.dataTransfer.files?.[0]);
          }}
        >
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{t("rrss.fuente")}</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 truncate max-w-[26rem]" title={mailing?.name}>
                {mailing ? mailing.name : t("rrss.fuenteHint", {
                  mailing: tipos.fuentes.mailing.etiqueta, planilla: tipos.fuentes.planilla.etiqueta,
                })}
              </p>
            </div>
            <button onClick={() => inputMailing.current?.click()} className="btn-secondary text-xs flex items-center gap-1.5">
              <FileText size={14} /> {mailing ? t("rrss.cambiarFuente") : t("rrss.elegirFuente")}
            </button>
          </div>
          <input ref={inputMailing} type="file"
            accept={[acceptDe(tipos.fuentes.mailing), acceptDe(tipos.fuentes.planilla)].join(",")} className="hidden"
            onChange={(e) => { elegirFuente(e.target.files?.[0]); e.target.value = ""; }} />

          {/* Es UNA sola: cargar una reemplaza a la otra. Se dice acá, y no
              después de que alguien suba las dos y se pregunte cuál ganó. */}
          <p className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-800/60 rounded-lg px-3 py-2">
            {t("rrss.fuenteUnaUOtra")}
          </p>

          {errorFuente && (
            <p className="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2">
              {errorFuente}
            </p>
          )}

          {!mailing ? (
            <button
              onClick={() => inputMailing.current?.click()}
              className="w-full h-72 rounded-2xl border-2 border-dashed border-slate-200 dark:border-slate-700 flex flex-col items-center justify-center gap-2 text-slate-400 hover:border-brand-400 hover:text-brand-500 transition-colors"
            >
              <UploadCloud size={30} />
              <span className="text-sm">{t("rrss.arrastraFuente")}</span>
            </button>
          ) : planilla ? (
            // Una planilla no se mira, se lee: no hay vista previa que mostrar
            // (y por eso mismo este camino no gasta una sola llamada a la IA).
            <div className="w-full rounded-2xl border border-emerald-200 dark:border-emerald-500/30 bg-emerald-50/60 dark:bg-emerald-500/5 p-6 flex flex-col items-center justify-center gap-3 text-center">
              <FileSpreadsheet size={34} className="text-emerald-600 dark:text-emerald-400" />
              <p className="text-sm font-medium text-slate-800 dark:text-slate-100 break-all">{mailing.name}</p>
              <p className="text-xs text-slate-600 dark:text-slate-300 max-w-sm">{t("rrss.planillaComoSeLee")}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400 max-w-sm">{t("rrss.planillaColumnas")}</p>
              {/* El tope de filas sale del mismo JSON que el backend usa para
                  rechazar (max_filas): decirlo acá es la diferencia entre
                  enterarse ahora y enterarse después de subir el catálogo. */}
              <p className="text-xs text-slate-500 dark:text-slate-400 max-w-sm">
                {t("rrss.planillaTope", { max: tipos.fuentes.planilla.max_filas })}
              </p>
            </div>
          ) : !mailingUrl ? null : esPdf ? (
            // <iframe> y no <object>: la CSP del sitio tiene object-src 'none' pero frame-src permite blob:
            // (mismo criterio que el visor de PDF de FacturaUploadModal).
            <iframe src={mailingUrl} title={mailing.name} className="w-full h-[68vh] rounded-xl border border-slate-200 dark:border-slate-700" />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={mailingUrl} alt={mailing.name} className="w-full max-h-[68vh] object-contain rounded-xl bg-slate-100 dark:bg-slate-900" />
          )}
        </section>
      </div>

      {/* ── Legales que se exigen ─────────────────────────────────────────── */}
      <section className="card p-5">
        <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{t("rrss.legales")}</h2>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 mb-3">{t("rrss.legalesHint")}</p>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <label className="block space-y-1">
            <span className="text-xs font-medium text-slate-600 dark:text-slate-300">{t("rrss.legalBases")}</span>
            <input className="input" value={config.legal_bases} onChange={(e) => onConfig({ ...config, legal_bases: e.target.value })} />
          </label>
          <label className="block space-y-1">
            <span className="text-xs font-medium text-slate-600 dark:text-slate-300">{t("rrss.legalAlcohol")}</span>
            <input
              className="input"
              value={config.legal_alcohol}
              placeholder={t("rrss.legalAlcoholVacio")}
              onChange={(e) => onConfig({ ...config, legal_alcohol: e.target.value })}
            />
          </label>
          {/* La fecha se escribe acá porque una planilla trae dos fechas sueltas
              y no el texto como va impreso. Componerlo sería inventarle una
              forma; vacío = no se valida. Con un mailing sigue mandando el que
              trae el mailing, salvo que se escriba algo. */}
          <label className="block space-y-1 lg:col-span-2">
            <span className="text-xs font-medium text-slate-600 dark:text-slate-300">{t("rrss.fechaCampana")}</span>
            <input
              className="input"
              value={config.fecha}
              placeholder={t("rrss.fechaCampanaVacio")}
              onChange={(e) => onConfig({ ...config, fecha: e.target.value })}
            />
          </label>
        </div>
      </section>

      {error && (
        <p className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded-xl px-4 py-3">{error}</p>
      )}

      <div className="flex items-center justify-end gap-4">
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {listo ? t("rrss.resumenCarga", { count: placas.length }) : t("rrss.faltaCargar")}
        </p>
        <button onClick={onValidar} disabled={!listo} className="btn-primary disabled:opacity-40 disabled:cursor-not-allowed">
          <Play size={15} /> {t("rrss.validar", { count: placas.length })}
        </button>
      </div>
    </div>
  );
}

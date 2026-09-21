"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { FileText, FolderOpen, ImagePlus, Play, Trash2, UploadCloud, X } from "lucide-react";
import { clsx } from "clsx";
import type { RrssConfig } from "@/lib/api";

export interface PlacaLocal {
  key: string;
  file: File;
  url: string;
}

const TIPOS_PLACA = ["image/jpeg", "image/png", "image/webp"];

/** Proporción → nombre de formato, igual que el backend (imagenes.clasificar_formato). */
export function formatoDe(ancho: number, alto: number): string {
  if (!alto) return "";
  const r = ancho / alto;
  if (Math.abs(r - 1) <= 0.03) return "1:1";
  if (Math.abs(r - 0.8) <= 0.03) return "4:5";
  if (Math.abs(r - 9 / 16) <= 0.03) return "9:16";
  return `${ancho}×${alto}`;
}

export function crearPlacasLocales(archivos: File[], existentes: PlacaLocal[]): PlacaLocal[] {
  const vistas = new Set(existentes.map((p) => p.key));
  const nuevas: PlacaLocal[] = [];
  for (const file of archivos) {
    if (!TIPOS_PLACA.includes(file.type)) continue;
    const key = `${file.name}|${file.size}|${file.lastModified}`;
    if (vistas.has(key)) continue;
    vistas.add(key);
    nuevas.push({ key, file, url: URL.createObjectURL(file) });
  }
  return [...existentes, ...nuevas].sort((a, b) =>
    a.file.name.localeCompare(b.file.name, undefined, { numeric: true, sensitivity: "base" }),
  );
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
}

/**
 * Pantalla de carga, en vista comparativa: las placas a la izquierda y el
 * mailing original a la derecha, ya visible. Así quien carga confirma de un
 * vistazo que subió el mailing correcto para esas placas.
 */
export default function UploadStep({ placas, onPlacas, mailing, onMailing, config, onConfig, onValidar, error }: Props) {
  const { t } = useTranslation();
  const inputImagenes = useRef<HTMLInputElement>(null);
  const inputCarpeta = useRef<HTMLInputElement>(null);
  const inputMailing = useRef<HTMLInputElement>(null);
  const [arrastrando, setArrastrando] = useState<"placas" | "mailing" | null>(null);
  // La URL del mailing se deriva del archivo; el efecto solo libera la anterior.
  const mailingUrl = useMemo(() => (mailing ? URL.createObjectURL(mailing) : null), [mailing]);
  useEffect(() => () => { if (mailingUrl) URL.revokeObjectURL(mailingUrl); }, [mailingUrl]);

  const agregar = (archivos: File[]) => onPlacas(crearPlacasLocales(archivos, placas));
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
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{t("rrss.placasHint")}</p>
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
          <input ref={inputImagenes} type="file" multiple accept={TIPOS_PLACA.join(",")} className="hidden"
            onChange={(e) => { agregar(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
          <input ref={inputCarpeta} type="file" multiple className="hidden"
            {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
            onChange={(e) => { agregar(Array.from(e.target.files ?? [])); e.target.value = ""; }} />

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
            const f = e.dataTransfer.files?.[0];
            if (f) onMailing(f);
          }}
        >
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{t("rrss.mailing")}</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 truncate max-w-[26rem]" title={mailing?.name}>
                {mailing ? mailing.name : t("rrss.mailingHint")}
              </p>
            </div>
            <button onClick={() => inputMailing.current?.click()} className="btn-secondary text-xs flex items-center gap-1.5">
              <FileText size={14} /> {mailing ? t("rrss.cambiarMailing") : t("rrss.elegirMailing")}
            </button>
          </div>
          <input ref={inputMailing} type="file" accept="application/pdf,image/jpeg,image/png" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) onMailing(f); e.target.value = ""; }} />

          {!mailing || !mailingUrl ? (
            <button
              onClick={() => inputMailing.current?.click()}
              className="w-full h-72 rounded-2xl border-2 border-dashed border-slate-200 dark:border-slate-700 flex flex-col items-center justify-center gap-2 text-slate-400 hover:border-brand-400 hover:text-brand-500 transition-colors"
            >
              <UploadCloud size={30} />
              <span className="text-sm">{t("rrss.arrastraMailing")}</span>
            </button>
          ) : esPdf ? (
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

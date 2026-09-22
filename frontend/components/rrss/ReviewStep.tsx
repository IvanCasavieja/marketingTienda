"use client";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, ArrowLeft, ArrowRight, Check, ChevronDown, FileSpreadsheet, Loader2, Radio, SkipForward } from "lucide-react";
import { clsx } from "clsx";
import type { RrssFila, RrssGrupo, RrssImagen, RrssPagina, RrssValidacion } from "@/lib/api";
import CatTiBadge from "./CatTiBadge";
import { CatTiMascota } from "./CatTiMascota";
import { BarraCatTi, FraseCatTi } from "./CatTiProgreso";
import DescargarExcel from "./DescargarExcel";
import { diferenciar, ESTILO_ESTADO, etiquetaImagen, filasConProblema, ordenFormato } from "./rrssUtils";

export interface ItemPendiente {
  orden: number;
  nombre: string;
  url: string;
  analizando: boolean;
}

export interface Progreso {
  fase: "validando" | "cerrando" | "pausada" | "listo";
  hechas: number;
  total: number;
}

interface Props {
  validacion: RrssValidacion;
  pendientes: ItemPendiente[];
  progreso: Progreso | null;
  /** Retoma lo que quedó cortado o con error. Solo existe en una sesión en vivo, no al abrir del historial. */
  onReintentar?: () => void;
}

type Seleccion = { tipo: "imagen"; id: number } | { tipo: "pendiente"; orden: number } | null;

// ── Texto con lo que difiere resaltado ─────────────────────────────────────

function TextoComparado({ texto, contra, vacio }: { texto: string; contra: string; vacio: string }) {
  if (!texto) return <span className="italic text-slate-400">{vacio}</span>;
  const segmentos = contra ? diferenciar(texto, contra).placa : [{ texto, distinto: true }];
  return (
    <span className="whitespace-pre-wrap break-words">
      {segmentos.map((s, i) =>
        s.distinto ? (
          <mark key={i} className="bg-red-200 dark:bg-red-500/40 text-red-900 dark:text-red-100 rounded px-0.5 [box-decoration-break:clone]">
            {s.texto}
          </mark>
        ) : (
          <span key={i}>{s.texto}</span>
        ),
      )}
    </span>
  );
}

// Lo mismo pero para el lado del mailing: se resalta contra lo que dice la placa.
function TextoMailing({ texto, contra, vacio }: { texto: string; contra: string; vacio: string }) {
  if (!texto) return <span className="italic text-slate-400">{vacio}</span>;
  const segmentos = contra ? diferenciar(contra, texto).mailing : [{ texto, distinto: true }];
  return (
    <span className="whitespace-pre-wrap break-words">
      {segmentos.map((s, i) =>
        s.distinto ? (
          <mark key={i} className="bg-emerald-200 dark:bg-emerald-500/40 text-emerald-900 dark:text-emerald-100 rounded px-0.5 [box-decoration-break:clone]">
            {s.texto}
          </mark>
        ) : (
          <span key={i}>{s.texto}</span>
        ),
      )}
    </span>
  );
}

// ── La página del mailing, con el producto marcado ─────────────────────────

function PaginaMarcada({ pagina, caja }: { pagina: RrssPagina; caja?: [number, number, number, number] }) {
  return (
    <div className="relative inline-block max-w-full">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={pagina.imagen} alt={`página ${pagina.numero + 1}`} className="max-w-full rounded-lg" />
      {caja && (
        <div
          className="absolute border-[3px] border-red-500 rounded-md shadow-[0_0_0_9999px_rgba(0,0,0,0.35)] pointer-events-none"
          style={{
            left: `${caja[0] * 100}%`,
            top: `${caja[1] * 100}%`,
            width: `${(caja[2] - caja[0]) * 100}%`,
            height: `${(caja[3] - caja[1]) * 100}%`,
          }}
        />
      )}
    </div>
  );
}

/** ¿La fuente de esta validación es una planilla? Las validaciones viejas no
 *  traen `origen`: son mailings. (UploadStep tiene una `esPlanilla` que mira un
 *  File, que es otra pregunta: acá el archivo ya está subido y leído.) */
function fuenteEsPlanilla(v: RrssValidacion): boolean {
  return v.mailing.origen === "planilla";
}

/** El nombre de la fuente ADENTRO de una frase, con el artículo contraído: "del
 *  mailing", "en la planilla". Antes se interpolaba el título de la columna
 *  ("El mailing") y salía "Hay más de una fila de El mailing" (22/09/2026). Las
 *  tres formas viven en los JSON de idioma porque cada idioma contrae distinto
 *  ("do mailing", "na planilha"). */
function nombreFuente(t: (k: string) => string, v: RrssValidacion, forma: "nombre" | "de" | "en"): string {
  const clave = { nombre: "rrss.fuenteNombre", de: "rrss.fuenteDe", en: "rrss.fuenteEn" }[forma];
  return t(`${clave}.${fuenteEsPlanilla(v) ? "planilla" : "mailing"}`);
}

/** "LISTADO.xlsx · hoja «Alemania 2026» · fila 24": la coordenada que permite
 *  ir a chequearlo a mano, que es la diferencia entre creerle al sistema y
 *  poder auditarlo. */
function citaDeLaFila(v: RrssValidacion, indice: number): string {
  const pl = v.mailing.planilla;
  const prod = v.mailing.productos[indice];
  if (!pl || !prod?.fila) return "";
  return [pl.archivo, pl.hoja ? `hoja «${pl.hoja}»` : "", `fila ${prod.fila.numero}`]
    .filter(Boolean)
    .join(" · ");
}

/**
 * Placa que no encontró su fila. Los dos casos que pidió Ivan que se vieran
 * --que no se parezca NINGUNA y que se parezcan DOS-- se veían igual hasta
 * ahora. Acá se dicen por separado y se muestra contra qué se pareció, con el
 * puntaje: un "sin pareja" sin pruebas no le sirve a nadie.
 */
function SinPareja({ v, img }: { v: RrssValidacion; img: RrssImagen }) {
  const { t } = useTranslation();
  const [navegar, setNavegar] = useState(0);
  const candidatos = img.candidatos ?? [];
  const pagina = v.paginas[navegar];
  return (
    <div className="space-y-3">
      <p className="text-sm text-violet-700 dark:text-violet-300 bg-violet-50 dark:bg-violet-900/20 rounded-xl px-3 py-2">
        {img.sin_pareja === "ambiguo"
          ? t("rrss.sinParejaAmbiguo", { fuente: nombreFuente(t, v, "de") })
          : t("rrss.sinParejaNinguna", { fuente: nombreFuente(t, v, "en") })}
      </p>
      {candidatos.length > 0 && (
        <div className="rounded-xl border border-slate-200 dark:border-slate-700 divide-y divide-slate-100 dark:divide-slate-800">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 px-3 py-2">
            {t("rrss.loQueMasSeParecio")}
          </p>
          {candidatos.map((k) => (
            <div key={k.indice} className="px-3 py-2 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm text-slate-700 dark:text-slate-200 break-words">{k.descripcion}</p>
                {fuenteEsPlanilla(v) && <p className="text-xs text-slate-400 mt-0.5">{citaDeLaFila(v, k.indice)}</p>}
              </div>
              <span className="badge-slate shrink-0">{k.puntaje}</span>
            </div>
          ))}
        </div>
      )}
      {!fuenteEsPlanilla(v) && v.paginas.length > 1 && (
        <div className="flex gap-1.5">
          {v.paginas.map((p, i) => (
            <button key={p.numero} onClick={() => setNavegar(i)}
              className={clsx("badge", i === navegar ? "badge-blue" : "badge-slate")}>
              {t("rrss.pagina", { n: p.numero + 1 })}
            </button>
          ))}
        </div>
      )}
      {!fuenteEsPlanilla(v) && pagina && <PaginaMarcada pagina={pagina} />}
    </div>
  );
}

/**
 * La emparejó, pero no está segura. Es la otra mitad de la decisión de
 * emparejar igual en vez de encogerse de hombros: con el margen único de antes,
 * una placa de la botella que decía "lata" se quedaba SIN PAREJA y el
 * diagnóstico ("tiene que decir botella") se perdía justo en el caso en que la
 * descripción es lo que está mal. Ahora se empareja y la duda se ve, con la
 * segunda candidata y su puntaje.
 */
function Duda({ v, img }: { v: RrssValidacion; img: RrssImagen }) {
  const { t } = useTranslation();
  const candidatos = img.candidatos ?? [];
  if (!img.match?.duda) return null;
  return (
    <div className="rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50/70 dark:bg-amber-500/5 px-3 py-2 space-y-1.5">
      <p className="text-xs text-amber-900 dark:text-amber-200">
        {img.match.motivo_duda === "otra_parecida"
          ? t("rrss.dudaOtraParecida", { puntaje: img.match.puntaje, segundo: img.match.segundo ?? 0 })
          : t("rrss.dudaNoLaCalza", { puntaje: img.match.puntaje })}
      </p>
      {candidatos.length > 1 && (
        <ul className="space-y-0.5">
          {candidatos.map((k) => (
            <li key={k.indice} className="flex items-start justify-between gap-2 text-xs text-slate-600 dark:text-slate-300">
              <span className="break-words">
                {k.indice === img.match?.indice && <span className="font-semibold">→ </span>}
                {k.descripcion}
                {fuenteEsPlanilla(v) && <span className="text-slate-400"> · {citaDeLaFila(v, k.indice)}</span>}
              </span>
              <span className="badge-slate shrink-0">{k.puntaje}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function LadoMailing({ v, img }: { v: RrssValidacion; img: RrssImagen }) {
  const { t } = useTranslation();
  const [paginaCompleta, setPaginaCompleta] = useState(false);
  const item = img.match ? v.mailing.productos[img.match.indice] : null;

  if (!item) return <SinPareja v={v} img={img} />;

  // Con planilla la evidencia es la fila dibujada (la misma imagen que se pega
  // en el Excel): la fila con una vecina arriba y otra abajo, para que se vea
  // que el emparejamiento no salió de la nada. No hay página que abrir.
  // La tira viaja con la PLACA (`recorte_fuente`): se dibuja al emparejar, no
  // al leer el archivo. `item.recorte` es el camino de las validaciones viejas,
  // que la traían guardada en cada fila de la planilla.
  if (fuenteEsPlanilla(v)) {
    const tira = img.recorte_fuente ?? item.recorte;
    return (
      <div className="space-y-2">
        {tira ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={tira} alt={item.descripcion}
            className="max-w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white" />
        ) : (
          // Que no se haya podido dibujar no se esconde: la cita de abajo es la
          // coordenada para ir a mirar la fila a mano.
          <p className="text-xs text-slate-400 italic">{t("rrss.sinTira")}</p>
        )}
        <p className="text-xs text-slate-500 dark:text-slate-400 font-mono break-all">{citaDeLaFila(v, img.match!.indice)}</p>
        <Duda v={v} img={img} />
      </div>
    );
  }

  const pagina = v.paginas.find((p) => p.numero === item.pagina);
  return (
    <div className="space-y-3">
      <Duda v={v} img={img} />
      {paginaCompleta && pagina ? (
        <PaginaMarcada pagina={pagina} caja={item.cajas.producto} />
      ) : item.recorte ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={item.recorte} alt={item.descripcion} className="max-h-[52vh] max-w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white" />
      ) : (
        <p className="text-xs text-slate-400 italic">{t("rrss.sinRecorte")}</p>
      )}
      {pagina && (
        <button onClick={() => setPaginaCompleta((x) => !x)} className="text-xs text-brand-600 dark:text-brand-400 hover:underline">
          {paginaCompleta ? t("rrss.verRecorte") : t("rrss.verPaginaCompleta", { n: pagina.numero + 1 })}
        </button>
      )}
    </div>
  );
}

// ── Una diferencia: placa a la izquierda, mailing a la derecha ─────────────

/** Los campos del producto que una fuente puede exigir, en el orden en que se
 *  muestran. Mismo orden y mismos nombres que comparador.CAMPOS_PRODUCTO. */
const ETIQUETA_CAMPO_PRODUCTO = new Map<string, string>([
  ["descripcion", "rrss.campoDescripcion"],
  ["precio_anterior", "rrss.campoPrecioAnterior"],
  ["precio_anterior_tachado", "rrss.campoTachado"],
  ["mecanica", "rrss.campoMecanica"],
  ["oferta_encabezado", "rrss.campoArriba"],
  ["oferta_precio", "rrss.campoPrecioOferta"],
  ["oferta_pie", "rrss.campoAbajo"],
]);

const ETIQUETA_ESTADO: Record<RrssFila["estado"], string> = {
  ok: "rrss.coincide",
  diferente: "rrss.diferente",
  falta_en_placa: "rrss.faltaEnPlaca",
  sobra_en_placa: "rrss.sobraEnPlaca",
  revisar: "rrss.revisar",
  info: "rrss.info",
};

function FilaProblema({ fila, fuente }: { fila: RrssFila; fuente: string }) {
  const { t } = useTranslation();
  const esAviso = fila.severidad === "aviso";
  const placa = fila.placa ?? "";
  const mailing = fila.mailing ?? "";
  return (
    <div className={clsx("rounded-xl border p-4 space-y-3", esAviso
      ? "border-amber-200 dark:border-amber-500/30 bg-amber-50/50 dark:bg-amber-500/5"
      : "border-red-200 dark:border-red-500/30 bg-red-50/40 dark:bg-red-500/5")}>
      <div className="flex items-center gap-2">
        <AlertTriangle size={15} className={esAviso ? "text-amber-500" : "text-red-500"} />
        <h4 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{fila.etiqueta}</h4>
        <span className={esAviso ? "badge-yellow" : "badge-red"}>{t(ETIQUETA_ESTADO[fila.estado])}</span>
      </div>
      {fila.nota && <p className="text-xs text-slate-600 dark:text-slate-300">{fila.nota}</p>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-2 min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{t("rrss.laPlaca")}</p>
          {fila.recorte_placa && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={fila.recorte_placa} alt="" className="max-h-64 max-w-full rounded-lg border border-slate-200 dark:border-slate-700" />
          )}
          <p className="text-sm font-mono bg-white dark:bg-slate-900 rounded-lg px-3 py-2 border border-slate-200 dark:border-slate-700">
            <TextoComparado texto={placa} contra={mailing} vacio={t("rrss.noEsta")} />
          </p>
        </div>
        <div className="space-y-2 min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{fuente}</p>
          {fila.recorte_mailing && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={fila.recorte_mailing} alt="" className="max-h-64 max-w-full rounded-lg border border-slate-200 dark:border-slate-700" />
          )}
          <p className="text-sm font-mono bg-white dark:bg-slate-900 rounded-lg px-3 py-2 border border-slate-200 dark:border-slate-700">
            <TextoMailing texto={mailing} contra={placa} vacio={t("rrss.noDebeEstar")} />
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Panel comparativo de una placa ─────────────────────────────────────────

function PanelPlaca({
  v, img, anterior, siguiente, siguienteConProblema,
}: {
  v: RrssValidacion;
  img: RrssImagen;
  anterior: (() => void) | null;
  siguiente: (() => void) | null;
  siguienteConProblema: (() => void) | null;
}) {
  const { t } = useTranslation();
  const [verOk, setVerOk] = useState(false);
  // `fuente` es el TÍTULO de la columna ("El mailing"); `fuenteEnFrase` es
  // cómo se la nombra adentro de una oración ("el mailing").
  const fuente = t(fuenteEsPlanilla(v) ? "rrss.laPlanilla" : "rrss.elMailing");
  const fuenteEnFrase = nombreFuente(t, v, "nombre");
  const problemas = filasConProblema(img);
  const ok = img.filas.filter((f) => f.estado === "ok");
  const info = img.filas.filter((f) => f.estado === "info" && f.placa && f.placa !== "sin CTA");
  const item = img.match ? v.mailing.productos[img.match.indice] : null;

  return (
    <div className="card p-5 space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100 truncate">{etiquetaImagen(img)}</h3>
            <span className="badge-slate">{img.formato}</span>
            <span className={ESTILO_ESTADO[img.estado].badge}>{t(`rrss.estado.${img.estado}`)}</span>
          </div>
          {item && <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 truncate">{item.descripcion}</p>}
        </div>
        <div className="flex items-center gap-1.5">
          <button disabled={!anterior} onClick={() => anterior?.()} className="btn-secondary text-xs disabled:opacity-40" title={t("rrss.anterior")}>
            <ArrowLeft size={14} />
          </button>
          <button disabled={!siguiente} onClick={() => siguiente?.()} className="btn-secondary text-xs disabled:opacity-40" title={t("rrss.siguiente")}>
            <ArrowRight size={14} />
          </button>
          <button disabled={!siguienteConProblema} onClick={() => siguienteConProblema?.()} className="btn-secondary text-xs flex items-center gap-1.5 disabled:opacity-40">
            <SkipForward size={14} /> {t("rrss.siguienteConProblema")}
          </button>
        </div>
      </div>

      {img.error ? (
        <p className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded-xl px-4 py-3">{img.error}</p>
      ) : null}

      {/* placa a la izquierda, mailing a la derecha */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
        <div className="space-y-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{t("rrss.laPlaca")}</p>
          {img.vista && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={img.vista} alt={img.nombre_archivo} className="max-h-[52vh] max-w-full rounded-lg border border-slate-200 dark:border-slate-700" />
          )}
        </div>
        <div className="space-y-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{fuente}</p>
          <LadoMailing key={img.id} v={v} img={img} />
        </div>
      </div>

      {!img.error && problemas.length === 0 && img.estado === "ok" && (
        // "Todo coincide" es una palabra que el motor no siempre puede
        // sostener: contra una planilla que no trae mecánica ni encabezado ni
        // pie, "todo" son 2 de 7 campos. Se dice lo que se miró.
        <p className="flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 rounded-xl px-4 py-3">
          <Check size={16} />
          {fuenteEsPlanilla(v)
            ? t("rrss.coincideLoQueDicta", {
                fuente: fuenteEnFrase, dictados: (v.mailing.campos ?? []).length, total: ETIQUETA_CAMPO_PRODUCTO.size,
              })
            : t("rrss.todoCoincide", { fuente: fuenteEnFrase })}
        </p>
      )}

      {problemas.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{t("rrss.loEncontrado", { count: problemas.length })}</h4>
          {problemas.map((f) => <FilaProblema key={f.campo} fila={f} fuente={fuente} />)}
        </div>
      )}

      {ok.length > 0 && (
        <div>
          <button onClick={() => setVerOk((x) => !x)} className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300">
            <ChevronDown size={14} className={clsx("transition-transform", verOk && "rotate-180")} />
            {t("rrss.camposCoinciden", { count: ok.length })}
          </button>
          {verOk && (
            <ul className="mt-2 space-y-1">
              {ok.map((f) => (
                <li key={f.campo} className="flex items-start gap-2 text-xs text-slate-600 dark:text-slate-300">
                  <Check size={13} className="text-emerald-500 mt-0.5 shrink-0" />
                  <span className="font-medium shrink-0">{f.etiqueta}:</span>
                  <span className="font-mono break-words">{f.placa}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {info.length > 0 && (
        <div className="flex flex-wrap gap-2 text-xs text-slate-500 dark:text-slate-400">
          {info.map((f) => (
            <span key={f.campo} className="badge-slate">{f.etiqueta}: {f.placa}</span>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Lista de productos con sus adaptaciones ────────────────────────────────

interface GrupoLocal {
  clave: string;
  titulo: string;
  imagenes: RrssImagen[];
  faltan: string[];
}

function armarGrupos(v: RrssValidacion): GrupoLocal[] {
  const resumenPorIndice = new Map<number, RrssGrupo>();
  (v.resumen?.grupos ?? []).forEach((g) => { if (g.match_indice !== null) resumenPorIndice.set(g.match_indice, g); });

  const porClave = new Map<string, GrupoLocal>();
  const ordenadas = [...v.imagenes].sort((a, b) => a.orden - b.orden);
  for (const img of ordenadas) {
    const idx = img.match?.indice ?? null;
    const clave = idx !== null ? `m${idx}` : img.estado === "error" ? "error" : "sin";
    if (!porClave.has(clave)) {
      porClave.set(clave, {
        clave,
        titulo: idx !== null ? v.mailing.productos[idx].descripcion : "",
        imagenes: [],
        faltan: (resumenPorIndice.get(idx ?? -1)?.avisos ?? []).filter((a) => a.tipo === "falta_formato").map((a) => a.formato ?? ""),
      });
    }
    porClave.get(clave)!.imagenes.push(img);
  }
  porClave.forEach((g) => g.imagenes.sort((a, b) => ordenFormato(a.formato) - ordenFormato(b.formato) || a.orden - b.orden));
  return [...porClave.values()];
}

function Miniatura({ src, estado, activa, onClick, etiqueta }: {
  src: string | null; estado: keyof typeof ESTILO_ESTADO; activa: boolean; onClick: () => void; etiqueta: string;
}) {
  return (
    <button onClick={onClick} title={etiqueta}
      className={clsx("relative rounded-lg overflow-hidden border-2 transition-all bg-slate-100 dark:bg-slate-800 shrink-0",
        activa ? "border-brand-500 ring-2 ring-brand-500/30" : "border-transparent hover:border-slate-300 dark:hover:border-slate-600")}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {src ? <img src={src} alt="" className="h-20 w-auto object-contain" /> : <div className="h-20 w-14" />}
      <span className={clsx("absolute top-1 left-1 w-2.5 h-2.5 rounded-full ring-2 ring-white dark:ring-slate-900", ESTILO_ESTADO[estado].punto)} />
      <span className="absolute bottom-0 inset-x-0 text-[9px] font-semibold text-white bg-black/55 text-center py-px">{etiqueta}</span>
    </button>
  );
}

// ── Componente principal ───────────────────────────────────────────────────

export default function ReviewStep({ validacion: v, pendientes, progreso, onReintentar }: Props) {
  const { t } = useTranslation();
  // `elegida` es lo que la persona clickeó; sin nada elegido la selección la decide el
  // momento: en vivo, acompaña a la placa que acaba de terminar; ya terminado (o
  // abierta del historial), arranca por la primera placa con algo para mirar.
  const [elegida, setElegida] = useState<Seleccion>(null);
  const [soloProblemas, setSoloProblemas] = useState(false);

  const enVivo = progreso !== null && (progreso.fase === "validando" || progreso.fase === "cerrando");
  const pausada = progreso?.fase === "pausada";
  // Cuántas placas están efectivamente en el aire ahora mismo (el pool de
  // page.tsx corre PARALELO a la vez).
  const enVuelo = pendientes.filter((p) => p.analizando).length;
  // El lote tiene un paso MÁS que las placas: el cierre, que es el que revisa
  // las adaptaciones y el CTA del conjunto. Contarlo evita que la barra marque
  // 100% mientras /cerrar todavía no contestó — decir que terminó algo que
  // todavía puede fallar es la clase de mentira que hace desconfiar del resto.
  const pasosTotales = progreso ? progreso.total + 1 : 1;
  const pasosHechos = progreso ? progreso.hechas : 0;
  const porOrden = useMemo(() => [...v.imagenes].sort((a, b) => a.orden - b.orden), [v.imagenes]);
  const grupos = useMemo(() => armarGrupos(v), [v]);
  const conProblema = (i: RrssImagen) => i.estado !== "ok";

  const ultima = v.imagenes.length ? v.imagenes[v.imagenes.length - 1] : null;
  const inicial = enVivo ? ultima : porOrden.find(conProblema) ?? porOrden[0] ?? null;
  const seleccion: Seleccion = elegida ?? (inicial ? { tipo: "imagen", id: inicial.id } : null);
  const seguir = elegida === null;

  const actual = seleccion?.tipo === "imagen" ? porOrden.find((i) => i.id === seleccion.id) ?? null : null;
  const pendienteActual = seleccion?.tipo === "pendiente" ? pendientes.find((p) => p.orden === seleccion.orden) ?? null : null;
  const pos = actual ? porOrden.findIndex((i) => i.id === actual.id) : -1;
  const ir = (i: RrssImagen | undefined) => i && setElegida({ tipo: "imagen", id: i.id });
  const siguienteProblema = pos >= 0 ? porOrden.slice(pos + 1).find(conProblema) ?? porOrden.find((i, k) => k < pos && conProblema(i)) : undefined;

  const cuenta = (e: RrssImagen["estado"]) => v.imagenes.filter((i) => i.estado === e).length;
  const resumen = v.resumen;
  const sinPlaca = resumen?.productos_sin_placa ?? [];
  // Cuándo hay Excel. No alcanza con "hay placas para corregir": a una campaña
  // a la que le faltan 3 de 4 placas no hay NINGUNA placa mal, y es la que más
  // necesita el archivo (la hoja "La planilla" muestra las filas que nadie
  // reclamó). Mismo criterio que excel.hay_algo_que_decir, del otro lado.
  // Solo las que quedaron guardadas (id > 0): una placa que falló en el navegador no está en el servidor.
  const hayParaCorregir =
    v.imagenes.some((i) => i.estado !== "ok" && i.id > 0) ||
    (fuenteEsPlanilla(v) && (sinPlaca.length > 0 || (v.mailing.planilla?.avisos ?? []).length > 0));
  // Los campos del producto que la planilla NO trae, y que por lo tanto NO se
  // validaron. Se calcula acá, del mismo `campos` que usó el backend para
  // comparar: si se escribiera una lista a mano, un día diría que se validó
  // algo que no se miró.
  // La fecha y la leyenda de alcohol entran también: se comparan solo si la
  // planilla trae la columna (VIGENCIA, LEYENDA ALCOHOL) o la persona las
  // escribió en la carga. Mismo criterio que planilla.campos_que_no_dicta del
  // otro lado; hasta el 22/09/2026 acá no se decían.
  const camposSinValidar = fuenteEsPlanilla(v)
    ? [
        ...[...ETIQUETA_CAMPO_PRODUCTO.entries()]
          .filter(([campo]) => !(v.mailing.campos ?? []).includes(campo))
          .map(([, clave]) => t(clave)),
        ...(!(v.config?.fecha?.trim() || v.mailing.fecha) ? [t("rrss.campoFecha")] : []),
        ...(!(v.config?.legal_alcohol?.trim() || v.mailing.legal_alcohol) ? [t("rrss.legalAlcohol")] : []),
      ]
    : [];
  const alertas = resumen
    ? [
        ...resumen.grupos.flatMap((g) => g.avisos.map((a) => ({ g, a }))),
      ]
    : [];

  return (
    <div className="space-y-4">
      {/* ── Barra: CatTi + progreso + contadores ─────────────────────────── */}
      <div className="card p-4 space-y-3">
        <div className="flex items-center gap-3 flex-wrap">
          <CatTiBadge trabajando={enVivo} />
          <div className="flex-1 min-w-[14rem]">
            {pausada ? (
              <>
                <p className="text-sm font-medium text-amber-700 dark:text-amber-400 flex items-center gap-2">
                  <AlertTriangle size={14} /> {t("rrss.pausada", { count: pendientes.length })}
                </p>
                <p className="text-xs text-slate-500 mt-0.5">{t("rrss.pausadaHint")}</p>
              </>
            ) : progreso && progreso.fase !== "listo" ? (
              <>
                <p className="text-sm font-medium text-slate-800 dark:text-slate-100 flex items-center gap-2">
                  <Loader2 size={14} className="animate-spin text-brand-500" />
                  {/* El número que se dice es el MISMO que marca la barra: las
                      que YA terminaron. Antes decía "revisando la placa 4 de 10"
                      con la barra en 3/10, y encima con PARALELO=3 estaba
                      revisando la 4, la 5 y la 6 al mismo tiempo. Cuántas hay en
                      vuelo ahora se dice aparte, y sale del dato real. */}
                  {progreso.fase === "cerrando"
                    ? t("rrss.cerrando")
                    : t("rrss.revisando", { hechas: progreso.hechas, total: progreso.total })}
                  {progreso.fase === "validando" && enVuelo > 0 && (
                    <span className="font-normal text-slate-500">{t("rrss.revisandoAhora", { count: enVuelo })}</span>
                  )}
                </p>
                <BarraCatTi hechas={pasosHechos} total={pasosTotales} enVivo={enVivo} />
                <FraseCatTi paso={progreso.hechas} className="text-xs text-slate-500 dark:text-slate-400 mt-1.5" />
              </>
            ) : (
              <p className="text-sm font-medium text-slate-800 dark:text-slate-100">{t("rrss.terminado", { count: v.imagenes.length })}</p>
            )}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {(["ok", "avisos", "diferencias", "sin_match", "error"] as const).map((e) => cuenta(e) > 0 && (
              <span key={e} className={ESTILO_ESTADO[e].badge}>{cuenta(e)} · {t(`rrss.estado.${e}`)}</span>
            ))}
            {pendientes.length > 0 && <span className="badge-slate">{pendientes.length} · {t("rrss.estado.pendiente")}</span>}
            {!enVivo && hayParaCorregir && <DescargarExcel validacionId={v.id} nombreMailing={v.nombre_mailing} />}
            {onReintentar && (pausada || (!enVivo && cuenta("error") > 0)) && (
              <button onClick={onReintentar} className="btn-primary text-xs">
                {pausada ? t("rrss.reintentar") : t("rrss.reintentarConError", { count: cuenta("error") })}
              </button>
            )}
          </div>
        </div>

        {fuenteEsPlanilla(v) && (
          <div className="space-y-2 pt-1">
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
              <span className="badge-blue flex items-center gap-1"><FileSpreadsheet size={12} /> {t("rrss.validadoConPlanilla")}</span>
              <span className="font-mono break-all">{v.mailing.planilla?.archivo}{v.mailing.planilla?.hoja ? ` · ${v.mailing.planilla.hoja}` : ""}</span>
              {/* Qué se leyó, en números. Estaba tipado en api.ts y no se
                  mostraba en ningún lado, y es justo el dato que delata que el
                  motor contó de más: "6 filas" en un archivo de 5 productos. */}
              {v.mailing.planilla && (
                <span>
                  {t("rrss.planillaLeidas", {
                    leidas: v.mailing.planilla.filas_leidas,
                    encabezado: v.mailing.planilla.fila_encabezado,
                  })}
                  {v.mailing.planilla.filas_ignoradas > 0 &&
                    ` · ${t("rrss.planillaIgnoradas", { count: v.mailing.planilla.filas_ignoradas })}`}
                  {/* El tercer contador: cuántas filas del archivo se juntaron
                      en esos productos. Viajaba en la API y no se mostraba, y es
                      el que delata que el motor entendió el archivo de otra
                      manera que la persona ("30 filas" en un archivo de 90). */}
                  {(v.mailing.planilla.filas_juntadas ?? 0) > 0 &&
                    ` · ${t("rrss.planillaJuntadas", { count: v.mailing.planilla.filas_juntadas })}`}
                </span>
              )}
              {camposSinValidar.length > 0 && (
                <span className="text-amber-700 dark:text-amber-400">
                  {t("rrss.planillaNoDice", { campos: camposSinValidar.join(", ") })}
                </span>
              )}
            </div>
            {/* Qué entendió CatTi de la planilla. La planilla puede venir de
                cualquier forma y qué columna es cada dato lo decide él: antes de
                creerle a una sola corrección, la persona tiene que poder ver de
                qué columna salió la descripción y de cuál los precios. */}
            {v.mailing.planilla?.interpretacion && (
              <div className="rounded-xl bg-violet-50 dark:bg-violet-500/10 border border-violet-200 dark:border-violet-500/30 px-3 py-2 text-xs text-violet-900 dark:text-violet-200 space-y-1.5">
                <p className="font-semibold">{t("rrss.planillaEntendio")}</p>
                {v.mailing.planilla.interpretacion.explicacion && (
                  <p>{v.mailing.planilla.interpretacion.explicacion}</p>
                )}
                <div className="flex flex-wrap gap-1.5">
                  {v.mailing.planilla.interpretacion.columnas.map((c) => (
                    <span key={c.letra} className="rounded-md bg-white/70 dark:bg-slate-900/40 border border-violet-200 dark:border-violet-500/30 px-1.5 py-0.5">
                      {c.dato} <span className="opacity-60">←</span> <span className="font-mono">{c.titulo}</span>{" "}
                      <span className="opacity-60">({c.letra})</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
            {/* Lo que la lectura tuvo para decir. Se armaba y moría en un campo
                que nadie leía; son los avisos que delatan que el motor entendió
                mal el archivo, así que van arriba de todo y no escondidos. */}
            {(v.mailing.planilla?.avisos ?? []).length > 0 && (
              <ul className="rounded-xl bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 px-3 py-2 text-xs text-amber-900 dark:text-amber-200 space-y-1">
                {(v.mailing.planilla?.avisos ?? []).map((a, k) => (
                  <li key={k} className="flex items-start gap-1.5">
                    <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                    <span>{a}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {sinPlaca.length > 0 && (
          // El tercer caso que pidió Ivan: las filas que ninguna placa reclamó.
          // Se venían contando y no se decía nunca cuáles.
          <div className="rounded-xl bg-violet-50 dark:bg-violet-500/10 border border-violet-200 dark:border-violet-500/30 px-3 py-2 text-xs text-violet-900 dark:text-violet-200 space-y-1">
            <p className="font-semibold">{t("rrss.sinPlaca", { count: sinPlaca.length })}</p>
            <ul className="space-y-0.5">
              {sinPlaca.slice(0, 20).map((k) => (
                <li key={k.indice}>
                  {k.fila !== null && k.fila !== undefined && <span className="font-mono mr-1">fila {k.fila}</span>}
                  {k.descripcion}
                </li>
              ))}
            </ul>
            {sinPlaca.length > 20 && <p className="italic">{t("rrss.sinPlacaMas", { count: sinPlaca.length - 20 })}</p>}
          </div>
        )}

        {(resumen?.cta.hay_mezcla || alertas.length > 0) && (
          <div className="space-y-2 pt-1">
            {resumen?.cta.hay_mezcla && (
              <div className="rounded-xl bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 px-3 py-2 text-xs text-amber-900 dark:text-amber-200">
                <p className="font-semibold">{t("rrss.ctaMezclado")}</p>
                <div className="flex flex-wrap gap-2 mt-1.5">
                  {resumen.cta.variantes.map((va) => (
                    <button key={va.cta ?? "sin"} onClick={() => ir(porOrden.find((i) => i.id === va.imagenes[0]))}
                      className="badge-yellow hover:opacity-80">
                      {va.cta ?? t("rrss.sinCta")} · {va.cantidad}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {alertas.length > 0 && (
              <div className="rounded-xl bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 px-3 py-2 text-xs text-amber-900 dark:text-amber-200 space-y-1">
                {alertas.map(({ g, a }, k) => (
                  <button key={k} className="block text-left hover:underline"
                    onClick={() => ir(porOrden.find((i) => i.id === (a.imagenes[0] ?? g.imagenes[0])))}>
                    <span className="font-semibold">{g.titulo.slice(0, 48)}:</span> {a.texto}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[320px_minmax(0,1fr)] gap-5 items-start">
        {/* ── Lista por producto ─────────────────────────────────────────── */}
        <aside className="card p-3 space-y-3 lg:sticky lg:top-4 lg:max-h-[86vh] overflow-y-auto">
          <div className="flex items-center justify-between gap-2 px-1">
            <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300 cursor-pointer">
              <input type="checkbox" checked={soloProblemas} onChange={(e) => setSoloProblemas(e.target.checked)} />
              {t("rrss.soloProblemas")}
            </label>
            {enVivo && !seguir && (
              <button onClick={() => setElegida(null)} className="flex items-center gap-1 text-[11px] text-brand-600 dark:text-brand-400 hover:underline">
                <Radio size={12} /> {t("rrss.seguirEnVivo")}
              </button>
            )}
          </div>

          {grupos
            .filter((g) => !soloProblemas || g.imagenes.some(conProblema) || g.faltan.length > 0)
            .map((g) => (
              <div key={g.clave} className="rounded-xl border border-slate-100 dark:border-slate-800 p-2.5 space-y-2">
                <p className="text-xs font-semibold text-slate-700 dark:text-slate-200 leading-snug line-clamp-2">
                  {g.clave === "sin" ? t("rrss.sinProductoTitulo") : g.clave === "error" ? t("rrss.estado.error") : g.titulo}
                </p>
                <div className="flex gap-1.5 flex-wrap">
                  {g.imagenes.map((img) => (
                    <Miniatura key={img.id} src={img.vista} estado={img.estado}
                      activa={seleccion?.tipo === "imagen" && seleccion.id === img.id}
                      etiqueta={img.formato} onClick={() => setElegida({ tipo: "imagen", id: img.id })} />
                  ))}
                  {g.faltan.map((f) => (
                    <div key={f} title={t("rrss.faltaFormato", { formato: f })}
                      className="h-20 w-14 rounded-lg border-2 border-dashed border-amber-400/70 text-amber-600 dark:text-amber-400 flex flex-col items-center justify-center text-[10px] font-semibold leading-tight text-center">
                      {t("rrss.falta")}<br />{f}
                    </div>
                  ))}
                </div>
              </div>
            ))}

          {pendientes.length > 0 && !soloProblemas && (
            <div className="rounded-xl border border-dashed border-slate-200 dark:border-slate-700 p-2.5 space-y-2">
              <p className="text-xs font-semibold text-slate-500">{t("rrss.pendientes")}</p>
              <div className="flex gap-1.5 flex-wrap">
                {pendientes.map((p) => (
                  <Miniatura key={p.orden} src={p.url} estado={p.analizando ? "analizando" : "pendiente"}
                    activa={seleccion?.tipo === "pendiente" && seleccion.orden === p.orden}
                    etiqueta={p.nombre.replace(/^.*?_(\d+(?: copia)?)\.\w+$/i, "$1")}
                    onClick={() => setElegida({ tipo: "pendiente", orden: p.orden })} />
                ))}
              </div>
            </div>
          )}
        </aside>

        {/* ── Comparación de la placa elegida ───────────────────────────── */}
        <main className="min-w-0">
          {actual ? (
            <PanelPlaca
              key={actual.id}
              v={v} img={actual}
              anterior={pos > 0 ? () => ir(porOrden[pos - 1]) : null}
              siguiente={pos < porOrden.length - 1 ? () => ir(porOrden[pos + 1]) : null}
              siguienteConProblema={siguienteProblema ? () => ir(siguienteProblema) : null}
            />
          ) : pendienteActual ? (
            <div className="card p-5 grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
              <div className="space-y-2">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{t("rrss.laPlaca")}</p>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={pendienteActual.url} alt="" className="max-h-[52vh] max-w-full rounded-lg border border-slate-200 dark:border-slate-700" />
              </div>
              <div className="space-y-2">
                {/* La columna se llama como la fuente de ESTA validación: decir
                    "El mailing" cuando se validó con una planilla es mandar a
                    buscar un archivo que no existe. */}
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                  {t(fuenteEsPlanilla(v) ? "rrss.laPlanilla" : "rrss.elMailing")}
                </p>
                {/* Mientras esta placa se está revisando no hay nada de la
                    fuente que mostrar todavía, así que el lugar lo ocupa CatTi
                    con la lupa: es el momento exacto en el que está trabajando. */}
                {pendienteActual.analizando ? (
                  <div className="flex flex-col items-center gap-2 py-6">
                    <CatTiMascota size={72} trabajando />
                    <p className="text-sm text-slate-500">{t("rrss.estado.analizando")}</p>
                    <FraseCatTi className="text-xs text-slate-400 text-center" />
                  </div>
                ) : (
                  <p className="text-sm text-slate-500">{t("rrss.enEspera")}</p>
                )}
              </div>
            </div>
          ) : (
            <div className="card p-10 flex flex-col items-center justify-center gap-2 text-center">
              <CatTiMascota size={88} trabajando />
              <p className="text-sm text-slate-500">{t("rrss.esperandoPrimera")}</p>
              <FraseCatTi className="text-xs text-slate-400" />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

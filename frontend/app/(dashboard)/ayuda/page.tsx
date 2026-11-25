"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight, BarChart2, CalendarDays, Camera, ClipboardCheck, ClipboardList, Compass, FileSpreadsheet,
  HelpCircle, Layers, ListChecks, ListPlus, Loader2, MessageCircle, PanelRight, Presentation, Receipt,
  ScanSearch, Search, SquareStack, Tag, Users,
} from "lucide-react";
import { RobotMascot } from "@/components/RobotMascot";
import { guiaApi } from "@/lib/api";
import { filtrarGuia, trozos, type SeccionDeGuia } from "@/lib/guia";

/**
 * La guía de uso (/ayuda).
 *
 * Desde el 25/11/2026 el texto viene del servidor (GET /guia, que sale de
 * backend/app/services/guia.py): es el mismo que sabe Don Tino, así no se
 * desactualizan por separado. El servidor manda solo lo que la persona puede
 * usar: el equipo ve sus herramientas, una agencia su tablero y un local de
 * Redexpres su pedido y sus fotos. Antes la guía vivía en los archivos de
 * idioma y se había quedado en septiembre, sin el calendario, las tareas ni el
 * tablero; ahora va solo en castellano, como el resto del núcleo.
 */

const ICONOS: Record<string, React.ElementType> = {
  BarChart2, CalendarDays, Camera, ClipboardCheck, ClipboardList, Compass, FileSpreadsheet, Layers, ListChecks,
  ListPlus, MessageCircle, PanelRight, Presentation, Receipt, ScanSearch, SquareStack, Tag, Users,
};

/** Un renglón con su **negrita**. */
function Texto({ texto }: { texto: string }) {
  return (
    <>
      {trozos(texto).map((t, i) =>
        t.negrita
          ? <strong key={i} className="font-semibold text-slate-900 dark:text-slate-100">{t.texto}</strong>
          : <span key={i}>{t.texto}</span>)}
    </>
  );
}

function Seccion({ s }: { s: SeccionDeGuia }) {
  const Icono = ICONOS[s.icono] ?? HelpCircle;
  return (
    <section id={s.clave} className="scroll-mt-20 rounded-2xl border border-slate-300 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900 sm:p-5">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200">
          <Icono className="h-5 w-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-bold leading-snug text-slate-900 dark:text-slate-100">{s.titulo}</h2>
          <p className="mt-0.5 text-sm leading-relaxed text-slate-700 dark:text-slate-300">{s.resumen}</p>
        </div>
      </div>

      <div className="mt-4 space-y-4">
        {s.partes.map((p, i) => {
          const Lista = p.numerada ? "ol" : "ul";
          return (
            <div key={`${p.titulo}-${i}`}>
              <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">{p.titulo}</h3>
              <Lista className="mt-1.5 space-y-1.5">
                {p.puntos.map((punto, j) => (
                  <li key={j} className="flex gap-2.5 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
                    {p.numerada ? (
                      <span className="mt-0.5 flex h-5 min-w-[1.25rem] shrink-0 items-center justify-center rounded-full bg-brand-600 px-1 text-[11px] font-bold text-white">
                        {j + 1}
                      </span>
                    ) : (
                      <span className="mt-[0.55rem] h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400 dark:bg-slate-500" aria-hidden />
                    )}
                    <span className="min-w-0"><Texto texto={punto} /></span>
                  </li>
                ))}
              </Lista>
            </div>
          );
        })}
      </div>

      {s.ruta && (
        <Link
          href={s.ruta}
          className="mt-4 inline-flex min-h-[40px] items-center gap-1.5 rounded-xl px-2 text-sm font-semibold text-brand-700 transition hover:bg-brand-50 dark:text-brand-200 dark:hover:bg-brand-500/10"
        >
          Ir a {s.titulo.replace(/ \(.*\)$/, "")} <ArrowRight className="h-4 w-4" aria-hidden />
        </Link>
      )}
    </section>
  );
}

export default function AyudaPage() {
  const [secciones, setSecciones] = useState<SeccionDeGuia[] | null>(null);
  const [error, setError] = useState(false);
  const [intento, setIntento] = useState(0);
  const [busqueda, setBusqueda] = useState("");

  useEffect(() => {
    let vivo = true;
    guiaApi.ver()
      .then(({ data }) => { if (vivo) { setSecciones(data.secciones); setError(false); } })
      .catch(() => { if (vivo) setError(true); });
    return () => { vivo = false; };
  }, [intento]);

  // Un link a una sección (/ayuda#revisar): la guía llega después de que el
  // navegador intentó bajar, así que se baja cuando ya está.
  useEffect(() => {
    if (!secciones) return;
    const id = decodeURIComponent(window.location.hash.slice(1));
    if (id) document.getElementById(id)?.scrollIntoView();
  }, [secciones]);

  const vistas = secciones ? filtrarGuia(secciones, busqueda) : [];

  return (
    <div className="mx-auto max-w-3xl space-y-6 py-4 sm:py-6">
      <div className="flex flex-col items-center gap-2 text-center">
        <RobotMascot size={90} />
        <p className="text-xs font-semibold uppercase tracking-widest text-brand-700 dark:text-brand-300">Guía de uso</p>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 sm:text-3xl">Cómo se usa Core Tienda</h1>
        <p className="max-w-lg text-sm leading-relaxed text-slate-700 dark:text-slate-300">
          Cada parte de la plataforma, contada simple. Ves solo lo que podés usar.
        </p>
      </div>

      {!secciones && !error && (
        <div className="flex h-40 items-center justify-center" role="status">
          <Loader2 className="h-6 w-6 animate-spin text-slate-500" aria-hidden />
          <span className="sr-only">Cargando la guía…</span>
        </div>
      )}

      {error && !secciones && (
        <div className="flex flex-col items-center gap-2 rounded-2xl border border-slate-300 p-6 text-center dark:border-slate-700">
          <p className="text-sm text-slate-800 dark:text-slate-200">No se pudo traer la guía.</p>
          <button
            type="button"
            onClick={() => setIntento(n => n + 1)}
            className="min-h-[40px] rounded-xl px-3 text-sm font-semibold text-brand-700 hover:bg-brand-50 dark:text-brand-200 dark:hover:bg-brand-500/10"
          >
            Probar de nuevo
          </button>
        </div>
      )}

      {secciones && (
        <>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" aria-hidden />
            <input
              type="search"
              value={busqueda}
              onChange={e => setBusqueda(e.target.value)}
              placeholder="Buscar en la guía: «entregar», «Excel», «contraseña»…"
              aria-label="Buscar en la guía"
              className="campo pl-9"
            />
          </div>

          {!busqueda.trim() && secciones.length > 1 && (
            <nav aria-label="Temas de la guía" className="flex flex-wrap gap-2">
              {secciones.map(s => (
                <a
                  key={s.clave}
                  href={`#${s.clave}`}
                  className="min-h-[36px] rounded-full border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 transition hover:border-brand-400 hover:text-brand-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:text-brand-200"
                >
                  {s.titulo}
                </a>
              ))}
            </nav>
          )}

          {vistas.length === 0 ? (
            <p className="rounded-2xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-700 dark:border-slate-700 dark:text-slate-300">
              No hay nada de «{busqueda.trim()}» en la guía. Probá con otra palabra.
            </p>
          ) : (
            <div className="space-y-4">
              {vistas.map(s => <Seccion key={s.clave} s={s} />)}
            </div>
          )}
        </>
      )}
    </div>
  );
}

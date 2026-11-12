"use client";

import Link from "next/link";
import { ArrowRight, Globe2 } from "lucide-react";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { herramientaDe, inicioDe, mundosDe, useMundoElegido, type Mundo } from "@/lib/mundos";

/**
 * Lo que se ve al abrir una herramienta que no es del mundo en el que se está:
 * la planilla de pedidos estando en Tienda Inglesa, los medios estando en
 * Redexpres. Pasa con un link guardado o con un aviso de la campanita.
 *
 * No se cambia de mundo solo: los mundos están separados a propósito, y pasar
 * de uno a otro sin darse cuenta es justo lo que se quiere evitar. Se dice
 * dónde está esa herramienta y se ofrece ir, si la persona puede entrar.
 */
export default function FueraDeMundo({ pathname, mundo }: { pathname: string; mundo: Mundo }) {
  const { user } = useCurrentUser();
  const elegir = useMundoElegido((s) => s.elegir);
  const herramienta = herramientaDe(pathname);
  if (!herramienta) return null;

  const dondeEsta = mundosDe(user).filter((m) => herramienta.mundos.includes(m.clave));

  return (
    <div className="mx-auto flex max-w-lg flex-col items-center gap-4 px-2 py-16 text-center animate-fade-in">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-100 text-slate-400 dark:bg-slate-800">
        <Globe2 className="h-7 w-7" />
      </span>
      <div>
        <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
          {herramienta.nombre} no {/^(Las|Los) /.test(herramienta.nombre) ? "son" : "es"} de {mundo.nombre}
        </h1>
        <p className="mt-1.5 text-sm text-slate-600 dark:text-slate-400">
          Estás en el mundo <strong>{mundo.nombre}</strong>, y acá solo se ve lo de {mundo.nombre}.
          {dondeEsta.length === 0 && " Tu cuenta no entra al mundo donde está esta herramienta."}
        </p>
      </div>

      <div className="flex w-full flex-col gap-2">
        {dondeEsta.map((m) => (
          <button
            key={m.clave}
            type="button"
            onClick={() => elegir(m.clave)}
            className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-left shadow-card transition hover:border-slate-300 hover:shadow-card-hover dark:border-slate-700 dark:bg-slate-900"
          >
            <span className="h-3 w-3 shrink-0 rounded-full" style={{ backgroundColor: m.color }} />
            <span className="flex-1 text-sm font-semibold text-slate-800 dark:text-slate-100">Pasar a {m.nombre}</span>
            <ArrowRight className="h-4 w-4 text-slate-400" />
          </button>
        ))}
        <Link
          href={inicioDe(user)}
          className="rounded-xl px-4 py-3 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Volver al inicio de {mundo.nombre}
        </Link>
      </div>
    </div>
  );
}

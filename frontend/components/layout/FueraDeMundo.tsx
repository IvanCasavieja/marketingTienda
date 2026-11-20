"use client";

import Link from "next/link";
import { ArrowRight, Globe2 } from "lucide-react";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { herramientaDe, inicioDe, mundosDe, useMundoElegido, type Mundo } from "@/lib/mundos";

/**
 * Lo que se ve al abrir una herramienta que no es del mundo en el que se está:
 * la planilla de pedidos estando en Tienda Inglesa, los precios estando en
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
    <div className="mx-auto flex max-w-md flex-col items-center gap-5 px-2 py-14 text-center animate-rise sm:py-20">
      {/* El mundo en el que se está, con su color: lo que hay que entender primero */}
      <span className="relative flex h-16 w-16 items-center justify-center rounded-2xl bg-white text-slate-500 shadow-card ring-1 ring-slate-300 dark:bg-slate-900 dark:text-slate-400 dark:ring-slate-800">
        <Globe2 className="h-7 w-7" />
        <span
          className="absolute -right-1 -top-1 h-4 w-4 rounded-full ring-4 ring-slate-50 dark:ring-slate-950"
          style={{ backgroundColor: mundo.color }}
          aria-hidden
        />
      </span>
      <div>
        <h1 className="text-xl font-bold text-balance text-slate-900 dark:text-slate-100 sm:text-2xl">
          {herramienta.nombre} no {/^(Las|Los) /.test(herramienta.nombre) ? "son" : "es"} de {mundo.nombre}
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
          Estás en el mundo <strong className="text-slate-900 dark:text-slate-100">{mundo.nombre}</strong>, y acá solo se ve lo de {mundo.nombre}.
          {dondeEsta.length === 0 && " Tu cuenta no entra al mundo donde está esta herramienta."}
        </p>
      </div>

      <div className="flex w-full flex-col gap-2">
        {dondeEsta.map((m) => (
          <button
            key={m.clave}
            type="button"
            onClick={() => elegir(m.clave)}
            className="group relative flex min-h-[52px] items-center gap-3 overflow-hidden rounded-xl border border-slate-300 bg-white py-3 pl-5 pr-4 text-left shadow-card transition hover:-translate-y-px hover:border-slate-300 hover:shadow-card-hover active:translate-y-0 active:scale-[.99] dark:border-slate-700 dark:bg-slate-900 dark:hover:border-slate-700"
          >
            <span className="absolute inset-y-0 left-0 w-1.5" style={{ backgroundColor: m.color }} aria-hidden />
            <span className="flex-1 text-sm font-semibold text-slate-800 dark:text-slate-100">Pasar a {m.nombre}</span>
            <ArrowRight className="h-4 w-4 text-slate-500 transition group-hover:translate-x-0.5 group-hover:text-slate-700 dark:group-hover:text-slate-200" />
          </button>
        ))}
        <Link
          href={inicioDe(user)}
          className="flex min-h-[48px] items-center justify-center rounded-xl px-4 py-3 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
        >
          Volver al inicio de {mundo.nombre}
        </Link>
      </div>
    </div>
  );
}

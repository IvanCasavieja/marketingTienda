"use client";

import Link from "next/link";
import { Lock } from "lucide-react";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { aLaHerramienta, requisitoDe } from "@/lib/acceso";
import { MARCA, inicioDe } from "@/lib/mundos";

/**
 * Lo que se ve al abrir una herramienta sin tener el permiso (lib/acceso.ts):
 * con un link guardado, un aviso o escribiendo la dirección. Antes se veían
 * errores sueltos en cada recuadro (Ivan, 20/11/2026).
 */
export default function SinAcceso({ pathname }: { pathname: string }) {
  const { user } = useCurrentUser();
  const req = requisitoDe(pathname);
  if (!req) return null;

  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-5 px-2 py-14 text-center animate-rise sm:py-20">
      <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-white text-slate-500 shadow-card ring-1 ring-slate-300 dark:bg-slate-900 dark:text-slate-400 dark:ring-slate-800">
        <Lock className="h-7 w-7" />
      </span>
      <div>
        <h1 className="text-xl font-bold text-balance text-slate-900 dark:text-slate-100 sm:text-2xl">
          No tenés acceso {aLaHerramienta(req.nombre)}
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
          Tu cuenta no tiene ese permiso. Si lo necesitás, pedíselo a quien administra {MARCA}.
        </p>
      </div>
      <Link
        href={inicioDe(user)}
        className="flex min-h-[48px] w-full items-center justify-center rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-slate-800 shadow-card transition hover:-translate-y-px hover:shadow-card-hover active:translate-y-0 active:scale-[.99] dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      >
        Volver al inicio
      </Link>
    </div>
  );
}

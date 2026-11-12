"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Check } from "lucide-react";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { MARCA, mundosDe, useMundoElegido, type Mundo } from "@/lib/mundos";

/**
 * El selector de mundos.
 *
 * Pedido de Ivan (12/11/2026): "una persona cuando vaya a entrar, que pueda
 * elegir el calendario de Redexpres o el de Tienda Inglesa... Una persona que
 * tenga solo acceso a un mundo no va a pasar por esa selección".
 *
 * Por eso quien tiene un solo mundo nunca ve esta pantalla: se lo manda derecho
 * a su calendario. Y quien no tiene ninguno, también: el calendario le explica
 * que le falta el acceso.
 */
export default function MundosPage() {
  const router = useRouter();
  const { user, loading } = useCurrentUser();
  const elegido = useMundoElegido(s => s.elegido);
  const elegir = useMundoElegido(s => s.elegir);
  const mundos = mundosDe(user);

  useEffect(() => {
    if (loading || !user) return;
    if (mundos.length <= 1) router.replace("/calendario");
  }, [loading, user, mundos.length, router]);

  if (loading || mundos.length <= 1) return null;

  function entrar(m: Mundo) {
    elegir(m.clave);
    router.push("/calendario");
  }

  const nombre = user?.full_name?.split(" ")[0];

  return (
    <div className="mx-auto flex min-h-full max-w-4xl flex-col justify-center px-1 py-8 sm:py-14">
      <p className="text-sm font-semibold text-brand-600">{MARCA}</p>
      <h1 className="mt-1 text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100 sm:text-4xl">
        {nombre ? `Hola, ${nombre}.` : "Hola."} ¿En qué mundo vas a trabajar?
      </h1>
      <p className="mt-2 text-base text-slate-600 dark:text-slate-400">
        Cada mundo tiene su propio calendario y sus propias tareas. Podés cambiar cuando quieras desde el menú.
      </p>

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        {mundos.map(m => (
          <button
            key={m.clave}
            type="button"
            onClick={() => entrar(m)}
            className="group relative flex items-center gap-4 overflow-hidden rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-card transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-card-hover focus:outline-none focus-visible:ring-4 focus-visible:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900"
          >
            <span className="absolute inset-y-0 left-0 w-1.5" style={{ backgroundColor: m.color }} />
            <span
              className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl text-xl font-bold text-white"
              style={{ backgroundColor: m.color }}
            >
              {m.nombre.split(" ").map(p => p[0]).join("").slice(0, 2)}
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-2">
                <span className="text-xl font-bold text-slate-900 dark:text-slate-100">{m.nombre}</span>
                {elegido === m.clave && (
                  <span className="flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                    <Check className="h-3 w-3" /> el último que usaste
                  </span>
                )}
              </span>
              <span className="mt-1 block text-sm text-slate-600 dark:text-slate-400">{m.bajada}</span>
            </span>
            <ArrowRight className="h-5 w-5 shrink-0 text-slate-300 transition group-hover:translate-x-1 group-hover:text-slate-600" />
          </button>
        ))}
      </div>
    </div>
  );
}

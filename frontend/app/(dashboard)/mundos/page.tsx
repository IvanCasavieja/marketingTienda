"use client";

import { useEffect, type CSSProperties } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, CalendarDays, History } from "lucide-react";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { MARCA, inicioDe, mundosDe, useMundoElegido, type Mundo } from "@/lib/mundos";
import { volverDeLaBusqueda } from "@/lib/volver";

/**
 * El selector de mundos.
 *
 * Pedido de Ivan (12/11/2026): "una persona cuando vaya a entrar, que pueda
 * elegir el calendario de Redexpres o el de Tienda Inglesa... Una persona que
 * tenga solo acceso a un mundo no va a pasar por esa selección".
 *
 * Por eso quien tiene un solo mundo nunca ve esta pantalla: se lo manda derecho
 * a su inicio. Lo que se elige acá vale para toda la plataforma, no solo para
 * el calendario: el menú, las cenefas y las tareas pasan a ser las de ese mundo.
 *
 * Cada tarjeta lleva el color de su mundo (el mismo del punto del menú), así
 * se aprende a reconocerlo antes de entrar.
 */
export default function MundosPage() {
  const router = useRouter();
  const { user, loading } = useCurrentUser();
  const elegido = useMundoElegido(s => s.elegido);
  const elegir = useMundoElegido(s => s.elegir);
  const mundos = mundosDe(user);

  useEffect(() => {
    if (loading || !user) return;
    if (mundos.length <= 1) router.replace(volverDeLaBusqueda(window.location.search) ?? inicioDe(user));
  }, [loading, user, mundos.length, router]);

  // Mientras se sabe quién es, el esqueleto de las tarjetas; con uno solo (o
  // ninguno), nada: el efecto de arriba ya lo está mandando a su inicio.
  const esperando = loading && !user;
  if (!esperando && mundos.length <= 1) return null;

  function entrar(m: Mundo) {
    elegir(m.clave);
    // Si venía de un link (el del mail), elegido el mundo sigue ahí (H-040).
    router.push(volverDeLaBusqueda(window.location.search) ?? inicioDe(user, m.clave));
  }

  const nombre = user?.full_name?.split(" ")[0];

  return (
    <div className="relative mx-auto flex min-h-[100dvh] max-w-4xl flex-col justify-center px-1 py-10 sm:py-14">
      {/* Un resplandor apenas, del color de la marca: la pantalla de entrada
          no es una página más. */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-24 left-1/2 h-72 w-[min(42rem,100%)] -translate-x-1/2 rounded-full bg-brand-400/20 blur-3xl dark:bg-brand-500/10"
      />

      <div className="relative flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 shadow-sm shadow-brand-600/30">
          <CalendarDays className="h-[18px] w-[18px] text-white" />
        </span>
        <span className="text-sm font-bold text-slate-900 dark:text-slate-100">{MARCA}</span>
      </div>

      <h1 className="relative mt-8 text-3xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-4xl">
        <span className="block text-lg font-semibold tracking-normal text-slate-500 dark:text-slate-400 sm:text-xl">
          {nombre ? `Hola, ${nombre}.` : "Hola."}
        </span>
        ¿En qué mundo vas a trabajar?
      </h1>
      <p className="relative mt-3 max-w-2xl text-base leading-relaxed text-slate-600 dark:text-slate-400">
        Cada mundo es la plataforma entera para ese negocio: su calendario, sus tareas y sus herramientas.
        Podés cambiar cuando quieras desde el menú.
      </p>

      <div className="relative mt-8 grid gap-3 sm:grid-cols-2 sm:gap-4">
        {esperando && [0, 1].map(i => (
          <div key={i} className="flex items-center gap-4 rounded-2xl border border-slate-300 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
            <div className="skeleton h-14 w-14 shrink-0 rounded-2xl" />
            <div className="flex-1 space-y-2.5">
              <div className="skeleton h-4 w-1/2 rounded-md" />
              <div className="skeleton h-3 w-5/6 rounded-md" />
            </div>
          </div>
        ))}

        {mundos.map((m, i) => {
          const ultimo = elegido === m.clave;
          return (
            <button
              key={m.clave}
              type="button"
              onClick={() => entrar(m)}
              style={{ "--mundo": m.color, animationDelay: `${i * 60}ms` } as CSSProperties}
              className="group relative flex animate-rise items-center gap-4 overflow-hidden rounded-2xl border border-slate-300 bg-white p-4 text-left shadow-card transition duration-200 ease-suave hover:-translate-y-0.5 hover:border-[color:var(--mundo)] hover:shadow-card-hover active:translate-y-0 active:scale-[.99] dark:border-slate-700 dark:bg-slate-900 dark:hover:border-[color:var(--mundo)] sm:p-5"
            >
              {/* La franja del color del mundo, que se ensancha al pasar */}
              <span className="absolute inset-y-0 left-0 w-1.5 transition-all duration-200 group-hover:w-2" style={{ backgroundColor: m.color }} aria-hidden />
              <span
                className="relative flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-2xl text-xl font-bold text-white shadow-sm"
                style={{ backgroundColor: m.color }}
                aria-hidden
              >
                <span className="absolute inset-0 bg-gradient-to-br from-white/25 to-transparent" />
                <span className="relative">{m.nombre.split(" ").map(p => p[0]).join("").slice(0, 2)}</span>
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="text-lg font-bold text-slate-900 dark:text-slate-100 sm:text-xl">{m.nombre}</span>
                  {ultimo && (
                    <span className="flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                      <History className="h-3 w-3" /> el último que usaste
                    </span>
                  )}
                </span>
                <span className="mt-1 block text-sm leading-snug text-slate-600 dark:text-slate-400">{m.bajada}</span>
              </span>
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-50 text-slate-500 transition duration-200 group-hover:translate-x-0.5 group-hover:bg-[color:var(--mundo)] group-hover:text-white dark:bg-slate-800 dark:text-slate-400">
                <ArrowRight className="h-[18px] w-[18px]" />
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

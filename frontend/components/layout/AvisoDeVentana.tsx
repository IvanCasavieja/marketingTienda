"use client";

import { CalendarRange } from "lucide-react";
import type { CurrentUser } from "@/types";
import { ventanaEnPalabras } from "@/lib/externos";

/**
 * El aviso de arriba para una cuenta externa (la agencia): qué parte del
 * calendario está viendo y por qué no ve lo que viene más adelante. Sin él,
 * "no hay nada en enero" parecería un error. Las fechas las manda el servidor
 * (/auth/me), que es el que de verdad recorta lo que se ve.
 */
export default function AvisoDeVentana({ user }: { user: CurrentUser }) {
  const cuando = ventanaEnPalabras(user.ventana);
  return (
    <div
      role="note"
      className="mx-auto mb-4 flex max-w-7xl items-start gap-2.5 rounded-2xl border border-sky-200 bg-sky-50 px-3 py-2.5 text-[13px] text-sky-950 dark:border-sky-500/25 dark:bg-sky-500/10 dark:text-sky-100 sm:gap-3 sm:px-4 sm:py-3 sm:text-sm"
    >
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-sky-100 text-sky-700 dark:bg-sky-500/20 dark:text-sky-200 sm:mt-0.5 sm:h-8 sm:w-8 sm:rounded-xl">
        <CalendarRange size={16} aria-hidden />
      </span>
      <p className="min-w-0 leading-snug">
        <span className="font-semibold">
          Ves el calendario del mes actual{cuando ? ` (${cuando})` : ""}.
        </span>{" "}
        {/* En el teléfono, corto: lo de abajo lo dice el menú (la empresa) y la pantalla. */}
        <span className="hidden text-sky-900/80 dark:text-sky-100/80 sm:inline">
          {user.empresa ? `Cuenta de ${user.empresa}: ` : ""}solo tus tareas y tus entregas. Lo que viene más
          adelante aparece a medida que se acerca.
        </span>
      </p>
    </div>
  );
}

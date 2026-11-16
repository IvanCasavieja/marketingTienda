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
      className="mx-auto mb-4 flex max-w-7xl items-start gap-3 rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-950 dark:border-sky-500/25 dark:bg-sky-500/10 dark:text-sky-100"
    >
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-sky-100 text-sky-700 dark:bg-sky-500/20 dark:text-sky-200">
        <CalendarRange size={17} aria-hidden />
      </span>
      <p className="min-w-0 leading-snug">
        <span className="font-semibold">
          {user.empresa ? `Cuenta de ${user.empresa}. ` : ""}Ves el calendario del mes actual
          {cuando ? ` (${cuando})` : ""}.
        </span>{" "}
        <span className="text-sky-900/80 dark:text-sky-100/80">
          Solo tus tareas y tus entregas: lo que viene más adelante aparece a medida que se acerca.
        </span>
      </p>
    </div>
  );
}

"use client";

import { CalendarRange } from "lucide-react";
import type { CurrentUser } from "@/types";
import { ventanaEnPalabras } from "@/lib/externos";
import { alcanceDe } from "@/lib/alcance";

/**
 * El aviso de arriba del calendario para quien lo ve limitado (su alcance,
 * 16/11/2026: 1 mes, 2 meses o 12 meses): qué parte está viendo y por qué no
 * ve lo que viene más adelante. Sin él, "no hay nada en marzo" parecería un
 * error. Las fechas las manda el servidor (/auth/me), que es el que de verdad
 * recorta lo que se ve.
 */
export default function AvisoDeVentana({ user }: { user: CurrentUser }) {
  const cuando = ventanaEnPalabras(user.ventana);
  const alcance = alcanceDe(user);
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
          Ves {alcance === "1m" ? "el calendario del mes actual" : alcance === "12m" ? "12 meses del calendario" : "2 meses del calendario"}
          {cuando ? ` (${cuando})` : ""}.
        </span>{" "}
        {/* En el teléfono, corto: lo de abajo lo dice la pantalla. */}
        <span className="hidden text-sky-900/80 dark:text-sky-100/80 sm:inline">
          {user.es_externo ? "Solo tus tareas. " : ""}Lo que viene más adelante aparece a medida que se acerca. Tus
          tarjetas las ves siempre en el tablero.
        </span>
      </p>
    </div>
  );
}

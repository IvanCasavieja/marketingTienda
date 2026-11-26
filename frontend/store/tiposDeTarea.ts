"use client";
import { useEffect, useState } from "react";
import { create } from "zustand";
import { calendarioApi } from "@/lib/api";
import type { TipoDeTarea } from "@/lib/calendario/tipos-de-tarea";

/**
 * El catálogo de tipos de tarea, pedido una sola vez por sesión: no cambia
 * mientras se usa la pantalla (se cambia en el backend, en un solo lugar:
 * app/services/tipos_de_tarea.py).
 */
interface EstadoTipos {
  tipos: TipoDeTarea[] | null;
  error: boolean;
  pedido: boolean;
  traer: () => void;
}

export const useTiposDeTarea = create<EstadoTipos>((set, get) => ({
  tipos: null,
  error: false,
  pedido: false,
  traer: () => {
    if (get().pedido && !get().error) return;
    set({ pedido: true, error: false });
    calendarioApi.tiposDeTarea()
      .then(({ data }) => set({ tipos: data }))
      .catch(() => set({ error: true, pedido: false }));
  },
}));

/** Los tipos de tarea (los pide la primera vez que se necesitan). */
export function useCatalogoDeTipos(): { tipos: TipoDeTarea[] | null; error: boolean; reintentar: () => void } {
  const tipos = useTiposDeTarea((s) => s.tipos);
  const error = useTiposDeTarea((s) => s.error);
  const traer = useTiposDeTarea((s) => s.traer);
  useEffect(() => { traer(); }, [traer]);
  return { tipos, error, reintentar: traer };
}

/** Una agencia a la que se le puede pedir trabajo, cada una con su tablero:
 *  los tres de siempre (Publicis, Another Monday y Diseñadores, aunque no
 *  tengan cuentas) y, desde el 26/11/2026, cualquier otra con cuentas. Con
 *  cuántas cuentas tiene en el mundo (0 = todavía no entra nadie; la pieza
 *  espera ahí igual). Las define el servidor (GET /calendario/tableros). */
export type Tablero = { nombre: string; cuentas: number };

/** La última lista que llegó de cada mundo, y el pedido que está en camino. */
const ultimosTableros = new Map<string, Tablero[]>();
const pidiendoTableros = new Map<string, Promise<Tablero[]>>();

/**
 * Las agencias del mundo. Se ve al toque la última lista que llegó y se pide
 * de nuevo cada vez que una pantalla la necesita (es una consulta chica; dos
 * pantallas a la vez comparten el pedido). Antes se pedía una sola vez por
 * sesión, y una agencia dada de alta mientras tanto no aparecía en «¿Quién la
 * hace?» hasta recargar la página (H-018, 26/11/2026).
 */
export function useTableros(mundo: string | null | undefined): { tableros: Tablero[] | null } {
  const [llegada, setLlegada] = useState<{ mundo: string; tableros: Tablero[] } | null>(null);
  useEffect(() => {
    if (!mundo) return;
    let vivo = true;
    let pedido = pidiendoTableros.get(mundo);
    if (!pedido) {
      pedido = calendarioApi.tableros(mundo)
        .then(({ data }) => { ultimosTableros.set(mundo, data); return data; })
        .finally(() => pidiendoTableros.delete(mundo));
      pidiendoTableros.set(mundo, pedido);
    }
    pedido.then((tableros) => { if (vivo) setLlegada({ mundo, tableros }); }).catch(() => {});
    return () => { vivo = false; };
  }, [mundo]);
  if (!mundo) return { tableros: null };
  return { tableros: llegada?.mundo === mundo ? llegada.tableros : ultimosTableros.get(mundo) ?? null };
}

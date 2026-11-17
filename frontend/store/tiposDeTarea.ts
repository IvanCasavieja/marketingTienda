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

/** Un tablero al que va una pieza (17/11/2026): Publicis, Another Monday o
 *  Diseñadores, con cuántas cuentas tiene en el mundo (0 = todavía no entra
 *  nadie; la pieza espera ahí igual). Los define el servidor
 *  (app/core/tableros.py). */
export type Tablero = { nombre: string; cuentas: number };

const tablerosPorMundo = new Map<string, Promise<Tablero[]>>();

/** Los tableros del mundo, pedidos una vez por sesión y mundo. */
export function useTableros(mundo: string | null | undefined): { tableros: Tablero[] | null } {
  const [tableros, setTableros] = useState<Tablero[] | null>(null);
  useEffect(() => {
    if (!mundo) return;
    let vivo = true;
    let pedido = tablerosPorMundo.get(mundo);
    if (!pedido) {
      pedido = calendarioApi.tableros(mundo).then(({ data }) => data);
      tablerosPorMundo.set(mundo, pedido);
      pedido.catch(() => tablerosPorMundo.delete(mundo));
    }
    pedido.then((t) => { if (vivo) setTableros(t); }).catch(() => {});
    return () => { vivo = false; };
  }, [mundo]);
  return { tableros };
}

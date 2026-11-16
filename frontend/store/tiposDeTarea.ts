"use client";
import { useEffect } from "react";
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

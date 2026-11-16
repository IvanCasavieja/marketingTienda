"use client";
import { create } from "zustand";

/**
 * Qué tarea tiene abiertas sus entregas. La vista (VistaEntregas) vive una
 * sola vez en el layout: la abren la ficha de la acción, el tablero, "Mis
 * tareas" y un aviso de la campanita, y todos ven lo mismo.
 *
 * `cambios` sube cada vez que desde la vista se entregó o se decidió algo:
 * el tablero y "Mis tareas" lo escuchan para traer lo nuevo enseguida, sin
 * esperar a su próxima pregunta.
 */
export type ModoEntregas = "ver" | "entregar" | "revisar" | "configurar";

interface EstadoVistaEntregas {
  tareaId: string | null;
  modo: ModoEntregas;
  /** Para "configurar" una tarea que todavía no lleva entregas. */
  mundo: string | null;
  cambios: number;
  abrir: (tareaId: string, modo?: ModoEntregas, mundo?: string | null) => void;
  setModo: (modo: ModoEntregas) => void;
  cerrar: () => void;
  huboCambios: () => void;
}

export const useVistaEntregas = create<EstadoVistaEntregas>((set) => ({
  tareaId: null,
  modo: "ver",
  mundo: null,
  cambios: 0,
  abrir: (tareaId, modo = "ver", mundo = null) => set({ tareaId, modo, mundo }),
  setModo: (modo) => set({ modo }),
  cerrar: () => set({ tareaId: null, modo: "ver", mundo: null }),
  huboCambios: () => set((s) => ({ cambios: s.cambios + 1 })),
}));

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
 *
 * `soloEsto`: se abrió para una sola cosa (soltar la tarjeta en "Esperando
 * feedback" abre "Entregar"; soltarla en "En proceso" con "Ver la revisión
 * completa", el revisor). Al terminar o cancelar, se cierra y se vuelve al
 * tablero: si se canceló, la tarjeta quedó donde estaba.
 */
export type ModoEntregas = "ver" | "entregar" | "revisar" | "configurar";

interface EstadoVistaEntregas {
  tareaId: string | null;
  modo: ModoEntregas;
  /** Para "configurar" una tarea que todavía no lleva entregas. */
  mundo: string | null;
  soloEsto: boolean;
  cambios: number;
  abrir: (tareaId: string, modo?: ModoEntregas, mundo?: string | null, soloEsto?: boolean) => void;
  setModo: (modo: ModoEntregas) => void;
  cerrar: () => void;
  huboCambios: () => void;
}

export const useVistaEntregas = create<EstadoVistaEntregas>((set) => ({
  tareaId: null,
  modo: "ver",
  mundo: null,
  soloEsto: false,
  cambios: 0,
  abrir: (tareaId, modo = "ver", mundo = null, soloEsto = false) => set({ tareaId, modo, mundo, soloEsto }),
  setModo: (modo) => set({ modo }),
  cerrar: () => set({ tareaId: null, modo: "ver", mundo: null, soloEsto: false }),
  huboCambios: () => set((s) => ({ cambios: s.cambios + 1 })),
}));

"use client";
import { create } from "zustand";

/**
 * Los avisos de la campanita que comparten el menú lateral y la barra de
 * abajo del teléfono. El menú es el que los pregunta al servidor (cada minuto
 * y al volver a la pestaña); la barra de abajo muestra el número y puede
 * pedir que se abra la lista, que vive en el menú.
 */
interface EstadoDeAvisos {
  noLeidos: number;
  /** Sube cada vez que alguien pide abrir la lista (la barra de abajo). */
  pedidoDeAbrir: number;
  setNoLeidos: (n: number | ((antes: number) => number)) => void;
  pedirAbrir: () => void;
}

export const useAvisos = create<EstadoDeAvisos>((set) => ({
  noLeidos: 0,
  pedidoDeAbrir: 0,
  setNoLeidos: (n) => set((s) => ({ noLeidos: typeof n === "function" ? n(s.noLeidos) : n })),
  pedirAbrir: () => set((s) => ({ pedidoDeAbrir: s.pedidoDeAbrir + 1 })),
}));

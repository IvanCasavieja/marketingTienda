"use client";
import { create } from "zustand";
import type { TFunction } from "i18next";
import { chatApi } from "@/lib/api";
import { historialParaEnviar, type MensajeDonTino } from "@/lib/chat/conversacion";

/**
 * La conversación con Don Tino, una sola para toda la plataforma: la ven el
 * chat de Inicio y la burbuja de abajo a la derecha (25/11/2026). Vive
 * mientras la pestaña está abierta: navegar entre pantallas, o cerrar y abrir
 * la burbuja, no la borra.
 */
interface EstadoDonTino {
  mensajes: MensajeDonTino[];
  escribiendo: boolean;
  /** Si la burbuja está abierta. */
  abierta: boolean;
  /** El saludo del principio. Si la conversación ya arrancó, no la toca. */
  saludar: (texto: string) => void;
  enviar: (texto: string, error: string) => Promise<void>;
  setAbierta: (abierta: boolean) => void;
}

/** El saludo del principio, con el nombre si se sabe (el mismo que decía Inicio). */
export function saludoDeDonTino(t: TFunction, nombre: string): string {
  const saludo = nombre ? t("home.greeting", { name: nombre }) : t("home.greetingNoName");
  return `${saludo}! ${t("home.assistantWelcome")}`;
}

export const useDonTino = create<EstadoDonTino>((set, get) => ({
  mensajes: [],
  escribiendo: false,
  abierta: false,
  saludar: (texto) => set((s) => {
    if (s.mensajes.length > 1) return s;
    return { mensajes: [{ role: "bot", text: texto, ts: Date.now() }] };
  }),
  enviar: async (texto, error) => {
    const q = texto.trim();
    if (!q || get().escribiendo) return;
    const mensajes = [...get().mensajes, { role: "user" as const, text: q, ts: Date.now() }];
    set({ mensajes, escribiendo: true });
    try {
      const { data } = await chatApi.sendMessage(q, historialParaEnviar(mensajes));
      set((s) => ({ mensajes: [...s.mensajes, { role: "bot", text: data.reply, ts: Date.now(), usage: data.usage }] }));
    } catch {
      set((s) => ({ mensajes: [...s.mensajes, { role: "bot", text: error, ts: Date.now() }] }));
    } finally {
      set({ escribiendo: false });
    }
  },
  setAbierta: (abierta) => set({ abierta }),
}));

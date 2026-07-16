"use client";
import { useEffect } from "react";

/** Cierra un modal/overlay al presionar Escape — patrón mínimo de
 * accesibilidad de teclado que ningún modal de la app implementaba. */
export function useEscapeKey(onClose: () => void, enabled = true) {
  useEffect(() => {
    if (!enabled) return;
    function handler(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose, enabled]);
}

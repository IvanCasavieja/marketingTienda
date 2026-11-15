"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Toaster } from "sonner";

/**
 * Los avisos flotantes (sonner) con el tema de la plataforma.
 *
 * El tema no sale del sistema sino de la clase `dark` del <html>, que pone
 * ThemeProvider y cambia el botón del menú. Sonner por su cuenta seguía al
 * sistema, así que en modo oscuro elegido a mano los avisos salían blancos.
 *
 * En pantalla completa (el calendario la usa) el navegador muestra solo ese
 * elemento: los avisos se dibujan adentro de él, si no "No se pudo guardar"
 * o "Sin conexión" no se veían (pruebas del 15/11/2026).
 */
export default function ToasterConTema() {
  const [tema, setTema] = useState<"light" | "dark">("light");
  const [pantallaCompleta, setPantallaCompleta] = useState<Element | null>(null);

  useEffect(() => {
    const html = document.documentElement;
    const leer = () => setTema(html.classList.contains("dark") ? "dark" : "light");
    leer();
    const observador = new MutationObserver(leer);
    observador.observe(html, { attributes: true, attributeFilter: ["class"] });
    return () => observador.disconnect();
  }, []);

  useEffect(() => {
    const alCambiar = () => setPantallaCompleta(document.fullscreenElement);
    document.addEventListener("fullscreenchange", alCambiar);
    return () => document.removeEventListener("fullscreenchange", alCambiar);
  }, []);

  const avisos = <Toaster richColors position="top-right" theme={tema} />;
  return pantallaCompleta ? createPortal(avisos, pantallaCompleta) : avisos;
}

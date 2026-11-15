"use client";

import { useEffect, useState } from "react";
import { Toaster } from "sonner";

/**
 * Los avisos flotantes (sonner) con el tema de la plataforma.
 *
 * El tema no sale del sistema sino de la clase `dark` del <html>, que pone
 * ThemeProvider y cambia el botón del menú. Sonner por su cuenta seguía al
 * sistema, así que en modo oscuro elegido a mano los avisos salían blancos.
 */
export default function ToasterConTema() {
  const [tema, setTema] = useState<"light" | "dark">("light");

  useEffect(() => {
    const html = document.documentElement;
    const leer = () => setTema(html.classList.contains("dark") ? "dark" : "light");
    leer();
    const observador = new MutationObserver(leer);
    observador.observe(html, { attributes: true, attributeFilter: ["class"] });
    return () => observador.disconnect();
  }, []);

  return <Toaster richColors position="top-right" theme={tema} />;
}

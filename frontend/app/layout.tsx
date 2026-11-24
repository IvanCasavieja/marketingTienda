import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import I18nProvider from "@/components/I18nProvider";
import ThemeProvider from "@/components/ThemeProvider";
import ToasterConTema from "@/components/ToasterConTema";

const inter = Inter({ subsets: ["latin"] });

// El entorno de pruebas (docs/equipo-nocturno/README.md): la web que va contra el
// servidor de pruebas lleva NEXT_PUBLIC_ENTORNO=pruebas y se nota a simple
// vista, en la pestaña y con un cartel abajo, para no confundirla con la de
// verdad. En producción la variable no está y no cambia nada.
const ES_PRUEBAS = process.env.NEXT_PUBLIC_ENTORNO === "pruebas";

export const metadata: Metadata = {
  title: ES_PRUEBAS ? "Core Tienda · Pruebas" : "Core Tienda",
  description: "Marketing Intelligence Platform",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Sin maximumScale: en el teléfono se puede pellizcar para agrandar
  // (accesibilidad). Los campos del núcleo usan letra de 16px, así el
  // iPhone no agranda solo al tocarlos.
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" suppressHydrationWarning>
      <body className={inter.className}>
        <ThemeProvider>
          <I18nProvider>
            {children}
            <ToasterConTema />
            {/* En el teléfono, arriba de la barra de abajo (NavegacionInferior) para no taparla. */}
            {ES_PRUEBAS && (
              <div
                role="note"
                className="pointer-events-none fixed bottom-[calc(4rem+env(safe-area-inset-bottom))] left-1/2 z-[100] -translate-x-1/2 whitespace-nowrap rounded-full bg-amber-400 px-3 py-1 text-xs font-semibold text-black shadow-md md:bottom-[max(0.5rem,env(safe-area-inset-bottom))]"
              >
                Entorno de pruebas: no es la plataforma de verdad
              </div>
            )}
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

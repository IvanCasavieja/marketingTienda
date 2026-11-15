import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import I18nProvider from "@/components/I18nProvider";
import ThemeProvider from "@/components/ThemeProvider";
import ToasterConTema from "@/components/ToasterConTema";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Core Tienda",
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
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

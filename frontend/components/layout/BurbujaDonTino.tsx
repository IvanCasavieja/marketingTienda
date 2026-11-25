"use client";
import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { RobotMascot, RobotMini } from "@/components/RobotMascot";
import { ConversacionDonTino } from "@/components/chat/ConversacionDonTino";
import { saludoDeDonTino, useDonTino } from "@/store/donTino";
import { useCurrentUserStore } from "@/store/currentUser";
import { LUGAR_DE_DON_TINO } from "@/lib/chat/conversacion";

/**
 * Don Tino, siempre a mano: una burbuja abajo a la derecha en todas las
 * pantallas (25/11/2026, Ivan: "siempre tenemos que tener a Don Tino presente
 * en las pestañas como una burbuja abajo a la derecha"). Al tocarla se abre
 * el mismo chat de Inicio sin salir de la pantalla: en la notebook, una
 * ventana abajo a la derecha; en el teléfono, una hoja casi de pantalla
 * entera. Se cierra con la X o con Escape y el foco vuelve a la burbuja.
 *
 * Quién la ve y dónde: lib/chat/conversacion.ts (muestraBurbuja). Va por
 * debajo de las fichas y ventanas (z-35): una ficha abierta la tapa, nunca al
 * revés. En el teléfono queda arriba de la barra de abajo y del cartel del
 * entorno de pruebas (LUGAR_DE_DON_TINO).
 */
export default function BurbujaDonTino() {
  const { t } = useTranslation();
  const abierta = useDonTino((s) => s.abierta);
  const setAbierta = useDonTino((s) => s.setAbierta);
  const saludar = useDonTino((s) => s.saludar);
  const burbujaRef = useRef<HTMLButtonElement>(null);
  const campoRef = useRef<HTMLInputElement>(null);
  const yaAbrio = useRef(false);

  const nombre = useCurrentUserStore((s) => s.user?.full_name?.split(" ")[0] ?? "");
  useEffect(() => {
    saludar(saludoDeDonTino(t, nombre));
  }, [saludar, t, nombre]);

  // Al abrir, el foco al campo; al cerrar, de vuelta a la burbuja.
  useEffect(() => {
    if (abierta) {
      yaAbrio.current = true;
      campoRef.current?.focus();
    } else if (yaAbrio.current) {
      burbujaRef.current?.focus();
    }
  }, [abierta]);

  useEffect(() => {
    if (!abierta) return;
    const alTeclear = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAbierta(false);
    };
    window.addEventListener("keydown", alTeclear);
    return () => window.removeEventListener("keydown", alTeclear);
  }, [abierta, setAbierta]);

  return (
    <>
      {abierta && (
        <div
          role="dialog"
          aria-modal="false"
          aria-label={t("donTino.chat", "Chat con Don Tino")}
          className="fixed inset-x-0 bottom-0 top-[6vh] z-[35] flex flex-col overflow-hidden rounded-t-2xl border border-slate-200 bg-white pb-[env(safe-area-inset-bottom)] shadow-2xl animate-fade-in dark:border-slate-700 dark:bg-slate-900 md:inset-x-auto md:bottom-[6.25rem] md:right-5 md:top-auto md:h-[min(36rem,calc(100vh-9rem))] md:w-[24rem] md:rounded-2xl md:pb-0"
        >
          <div className="flex shrink-0 items-center gap-3 px-5 py-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-brand-500/10">
              <RobotMini />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">{t("home.assistantName")}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">{t("home.assistantSubtitle")}</p>
            </div>
            <button
              type="button"
              onClick={() => setAbierta(false)}
              aria-label={t("donTino.cerrar", "Cerrar el chat")}
              className="boton-icono"
            >
              <X size={18} />
            </button>
          </div>
          <ConversacionDonTino claseMensajes="min-h-0 flex-1" campoRef={campoRef} />
        </div>
      )}

      {/* En el teléfono, con el chat abierto la hoja ya ocupa la pantalla: la
          burbuja se esconde (se cierra con la X de arriba). */}
      <button
        ref={burbujaRef}
        type="button"
        onClick={() => setAbierta(!abierta)}
        aria-expanded={abierta}
        aria-label={abierta ? t("donTino.cerrar", "Cerrar el chat") : t("donTino.abrir", "Abrir el chat con Don Tino")}
        title={t("home.assistantName")}
        className={`fixed z-[35] h-14 w-14 items-center justify-center rounded-full border border-slate-200 bg-white shadow-lg transition hover:scale-105 active:scale-95 dark:border-slate-600 dark:bg-slate-800 ${LUGAR_DE_DON_TINO} ${abierta ? "hidden md:flex" : "flex"}`}
      >
        {abierta ? (
          <X size={18} className="text-slate-600 dark:text-slate-300" />
        ) : (
          <>
            <RobotMascot size={40} />
            <span className="absolute bottom-1 right-1 h-3 w-3 rounded-full border-2 border-white bg-emerald-500 dark:border-slate-800" aria-hidden />
          </>
        )}
      </button>
    </>
  );
}

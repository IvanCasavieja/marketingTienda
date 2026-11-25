"use client";
import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { RobotMascot, RobotMini } from "@/components/RobotMascot";
import { ConversacionDonTino } from "@/components/chat/ConversacionDonTino";
import { saludoDeDonTino, useDonTino } from "@/store/donTino";
import { useCurrentUser } from "@/hooks/useCurrentUser";

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
// El chat (mensajes, sugerencias y el campo) es ConversacionDonTino desde el
// 25/11/2026: es el mismo de la burbuja de abajo a la derecha, con la misma
// conversación (store/donTino). Acá en Inicio la burbuja no va.
export default function HomePage() {
  const { t } = useTranslation();
  const { user } = useCurrentUser();
  const [open, setOpen]     = useState(false);
  const saludar = useDonTino((s) => s.saludar);

  useEffect(() => {
    if (!user) return;
    saludar(saludoDeDonTino(t, user.full_name?.split(" ")[0] ?? ""));
  }, [user, t, saludar]);

  const firstName = user?.full_name?.split(" ")[0] ?? "";

  return (
    <div className="min-h-[calc(100vh-4rem)] flex flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-2xl space-y-8">

        {/* Mascot + greeting */}
        <div className="flex flex-col items-center text-center gap-4">
          <div className="relative">
            <RobotMascot />
            <span className="absolute -bottom-1 -right-1 w-5 h-5 bg-emerald-500 rounded-full border-2 border-white" />
          </div>

          <div>
            <p className="text-xs font-semibold text-brand-500 uppercase tracking-widest mb-1">
              {"Core Tienda"}
            </p>
            <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-100">
              {firstName ? t("home.greeting", { name: firstName }) : t("home.greetingNoName")} {t("home.waveEmoji")}
            </h1>
            <p className="text-slate-500 dark:text-slate-400 mt-1">{t("home.assistantReady")}</p>
          </div>
        </div>

        {/* Chat card */}
        <div className="card overflow-hidden shadow-card-hover">

          {/* Chat header */}
          <button
            onClick={() => setOpen((o) => !o)}
            className="w-full flex items-center gap-3 px-5 py-4 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
          >
            <div className="w-8 h-8 rounded-xl bg-brand-500/10 flex items-center justify-center shrink-0">
              <RobotMini />
            </div>
            <div className="flex-1 text-left">
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">{t("home.assistantName")}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">{t("home.assistantSubtitle")}</p>
            </div>
            <ChevronDown
              size={16}
              className={`text-slate-500 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
            />
          </button>

          {/* Messages, sugerencias y el campo: ConversacionDonTino */}
          {open && <ConversacionDonTino claseMensajes="max-h-[min(60vh,32rem)]" />}
        </div>

        {/* Quick note */}
        <p className="text-center text-xs text-slate-500 dark:text-slate-400">
          {t("home.comingSoon")}
        </p>
      </div>
    </div>
  );
}

// Robot mascot ("Don Tino") vive en components/RobotMascot.tsx — compartido
// con Ayuda y Login.

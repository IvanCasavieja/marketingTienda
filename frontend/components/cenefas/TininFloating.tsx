"use client";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { tininApi, type AiTaskUsage, type TininContexto } from "@/lib/api";
import { RobotMascot } from "@/components/RobotMascot";
import { X, Send } from "lucide-react";

// ── Tinín flotante — agente del área de Materiales. A diferencia de Doña
// Tina (precios), acá el modelo puede ejecutar una acción real (guardar una
// descripción en el catálogo compartido) vía tool-use — ver
// backend/app/services/cenefas/tinin_agent.py. No genera cenefas por chat:
// eso requiere un Excel real subido, así que solo guía y explica. ─────────

type Msg = { role: "bot" | "user"; text: string; usage?: AiTaskUsage };

interface TininFloatingProps {
  contexto?: TininContexto;
  /** Las filas de la grilla que se estan viendo, para que pueda mirarlas. */
  filas?: object[];
}

function TypingDots() {
  return (
    <div className="flex gap-1 items-center h-4 px-1">
      <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:0ms]" />
      <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:150ms]" />
      <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:300ms]" />
    </div>
  );
}

export default function TininFloating({ contexto, filas }: TininFloatingProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [mensaje, setMensaje] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [loading, setLoading] = useState(false);

  async function enviar() {
    const texto = mensaje.trim();
    if (!texto || loading) return;
    setMensaje("");
    const historial = messages.map((m) => ({
      role: (m.role === "bot" ? "assistant" : "user") as "user" | "assistant",
      content: m.text,
    }));
    setMessages((prev) => [...prev, { role: "user", text: texto }]);
    setLoading(true);
    try {
      const { data } = await tininApi.consultar(texto, historial, contexto, filas);
      setMessages((prev) => [...prev, { role: "bot", text: data.respuesta, usage: data.usage }]);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      const text = status === 503 ? t("tinin.notConfigured") : t("tinin.genericError");
      setMessages((prev) => [...prev, { role: "bot", text }]);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    enviar();
  }

  return (
    <div className="fixed bottom-5 right-5 z-[60] flex flex-col items-end gap-3">
      {open && (
        <div className="w-80 max-h-[70vh] flex flex-col bg-white dark:bg-slate-900 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-700 overflow-hidden animate-fade-in">
          {/* Header */}
          <div className="flex items-center gap-2.5 px-4 py-3 bg-brand-600 shrink-0">
            <div className="w-9 h-9 rounded-full bg-white flex items-center justify-center shrink-0 shadow-sm overflow-visible">
              <RobotMascot size={30} variant="tinin" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-white text-xs font-bold leading-none">{t("tinin.title")}</p>
              <p className="text-brand-100 text-[10px] mt-0.5">{t("tinin.subtitle")}</p>
            </div>
            <button onClick={() => setOpen(false)} className="text-white/70 hover:text-white shrink-0">
              <X size={15} />
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto px-3.5 py-3 space-y-2.5 bg-slate-50/50 dark:bg-slate-950/40">
            {messages.length === 0 && (
              <p className="text-xs text-slate-400 dark:text-slate-500 text-center py-4">
                {t("tinin.placeholderInicial")}
              </p>
            )}

            {messages.map((m, i) => (
              <div key={i} className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}>
                <div
                  className={`max-w-[85%] px-3 py-2 rounded-xl text-xs leading-relaxed whitespace-pre-wrap ${
                    m.role === "user"
                      ? "bg-brand-600 text-white rounded-br-sm"
                      : "bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800 text-slate-700 dark:text-slate-300 rounded-bl-sm shadow-sm"
                  }`}
                >
                  {m.text}
                </div>
                {m.usage && (
                  <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1 px-1">
                    {m.usage.total_tokens.toLocaleString()} tokens
                  </p>
                )}
              </div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-xl rounded-bl-sm shadow-sm">
                  <TypingDots />
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <form onSubmit={handleSubmit} className="flex gap-2 px-3.5 py-3 border-t border-slate-100 dark:border-slate-800">
            <input
              value={mensaje}
              onChange={(e) => setMensaje(e.target.value)}
              placeholder={t("tinin.inputPlaceholder")}
              disabled={loading}
              className="flex-1 text-xs bg-slate-100 dark:bg-slate-800 rounded-lg px-3 py-2 text-slate-800 dark:text-slate-200 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30 transition-all disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!mensaje.trim() || loading}
              className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center text-white disabled:opacity-40 hover:bg-brand-700 transition-colors shrink-0"
            >
              <Send size={13} />
            </button>
          </form>
        </div>
      )}

      {/* Burbuja colapsada */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-16 h-16 rounded-full bg-white dark:bg-slate-800 shadow-lg border border-slate-100 dark:border-slate-700 flex items-center justify-center transition-all hover:scale-105 active:scale-95 relative"
        title={t("tinin.title")}
      >
        {open ? (
          <X size={18} className="text-slate-500" />
        ) : (
          <>
            <RobotMascot size={44} variant="tinin" />
            <span className="absolute bottom-1 right-1 w-3 h-3 bg-emerald-500 rounded-full border-2 border-white dark:border-slate-800" />
          </>
        )}
      </button>
    </div>
  );
}

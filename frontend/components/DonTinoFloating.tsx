"use client";
import { useState } from "react";
import { preciosApi } from "@/lib/api";
import { RobotMini } from "@/components/RobotMascot";
import { MessageCircle, X, Send, BarChart3, Sparkles } from "lucide-react";

// ── Don Tino flotante — misma cara en todos lados, pero en "comparison" lo que
// contesta viene de Claude/ChatGPT por detrás (ver backend/app/services/don_tino_precios.py).
// El usuario nunca ve esos nombres, solo a Don Tino respondiendo. ─────────────

type Contexto = "precios" | "comparison" | "analytics";

type Msg = { role: "bot" | "user"; text: string };

interface ItemBasico {
  id: string;
  tienda: string;
  nombre: string;
}

interface ItemConPrecio {
  tienda: string;
  nombre: string;
  precio: number;
  moneda: string;
}

interface DonTinoFloatingProps {
  context: Contexto;
  // context="precios"
  hasResults?: boolean;
  onOpenChart?: () => void;
  // context="comparison"
  termino?: string;
  items?: ItemBasico[];
  chartItems?: ItemConPrecio[];
  ourPrice?: number | null;
  ourCurrency?: string | null;
  onApplySeleccion?: (ids: string[]) => void;
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

export default function DonTinoFloating({
  context, hasResults, onOpenChart,
  termino, items, chartItems, ourPrice, ourCurrency, onApplySeleccion,
}: DonTinoFloatingProps) {
  const [open, setOpen] = useState(false);
  const [instruccion, setInstruccion] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [loading, setLoading] = useState(false);

  async function limpiar() {
    const texto = instruccion.trim();
    if (!texto || !items || !termino) return;
    setInstruccion("");
    setMessages((prev) => [...prev, { role: "user", text: texto }]);
    setLoading(true);
    try {
      const { data } = await preciosApi.limpiarConIA(
        termino,
        items.map((it) => ({ tienda: it.tienda, nombre: it.nombre })),
        texto,
      );
      const idsAMantener = data.mantener
        .map((n) => items[n - 1]?.id)
        .filter((id): id is string => !!id);
      onApplySeleccion?.(idsAMantener);
      setMessages((prev) => [...prev, { role: "bot", text: data.comentario || "Listo, ya ajusté la selección." }]);
    } catch {
      setMessages((prev) => [...prev, { role: "bot", text: "No pude procesar el pedido — probá de nuevo." }]);
    } finally {
      setLoading(false);
    }
  }

  async function generarReporte() {
    if (!chartItems || chartItems.length === 0) {
      setMessages((prev) => [...prev, { role: "bot", text: "Tildá algún producto en la lista primero para poder armar el reporte." }]);
      return;
    }
    setMessages((prev) => [...prev, { role: "user", text: "Generar reporte" }]);
    setLoading(true);
    try {
      const { data } = await preciosApi.generarReporteIA(chartItems, ourPrice ?? null, ourCurrency ?? null);
      setMessages((prev) => [...prev, { role: "bot", text: data.reporte }]);
    } catch {
      setMessages((prev) => [...prev, { role: "bot", text: "No pude generar el reporte en este momento — probá de nuevo." }]);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    limpiar();
  }

  return (
    <div className="fixed bottom-5 right-5 z-[60] flex flex-col items-end gap-3">
      {open && (
        <div className="w-80 max-h-[70vh] flex flex-col bg-white dark:bg-slate-900 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-700 overflow-hidden animate-fade-in">
          {/* Header */}
          <div className="flex items-center gap-2.5 px-4 py-3 bg-brand-600 shrink-0">
            <div className="w-7 h-7 rounded-full bg-white/15 border border-white/20 flex items-center justify-center shrink-0">
              <RobotMini />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-white text-xs font-bold leading-none">Don Tino</p>
              <p className="text-brand-100 text-[10px] mt-0.5">
                {context === "comparison" ? "Analizando este gráfico" : "Tu asistente"}
              </p>
            </div>
            <button onClick={() => setOpen(false)} className="text-white/70 hover:text-white shrink-0">
              <X size={15} />
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto px-3.5 py-3 space-y-2.5 bg-slate-50/50 dark:bg-slate-950/40">
            {context === "analytics" && messages.length === 0 && (
              <p className="text-xs text-slate-400 dark:text-slate-500 text-center py-4">
                Preguntame lo que quieras sobre este análisis desde el chat de Home.
              </p>
            )}
            {context === "precios" && messages.length === 0 && (
              <p className="text-xs text-slate-400 dark:text-slate-500 text-center py-4">
                {hasResults
                  ? "Abrí el gráfico comparativo y te ayudo a limpiarlo o a armar un reporte."
                  : "Buscá algún producto primero para que te pueda ayudar."}
              </p>
            )}
            {context === "comparison" && messages.length === 0 && (
              <p className="text-xs text-slate-400 dark:text-slate-500 text-center py-4">
                Decime qué querés ver — ej. "quiero solo los celulares, no accesorios" — o pedime un reporte del gráfico.
              </p>
            )}

            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] px-3 py-2 rounded-xl text-xs leading-relaxed whitespace-pre-wrap ${
                    m.role === "user"
                      ? "bg-brand-600 text-white rounded-br-sm"
                      : "bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800 text-slate-700 dark:text-slate-300 rounded-bl-sm shadow-sm"
                  }`}
                >
                  {m.text}
                </div>
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

          {/* Footer / acciones */}
          {context === "precios" && hasResults && (
            <div className="px-3.5 py-3 border-t border-slate-100 dark:border-slate-800 shrink-0">
              <button
                onClick={onOpenChart}
                className="w-full flex items-center justify-center gap-1.5 py-2 rounded-xl bg-brand-600 text-white text-xs font-semibold hover:bg-brand-700 transition-colors"
              >
                <BarChart3 size={13} /> Abrir gráfico
              </button>
            </div>
          )}

          {context === "comparison" && (
            <div className="border-t border-slate-100 dark:border-slate-800 shrink-0">
              <div className="px-3.5 pt-2.5">
                <button
                  onClick={generarReporte}
                  disabled={loading}
                  className="w-full flex items-center justify-center gap-1.5 py-2 rounded-xl border border-brand-200 dark:border-brand-800 text-brand-600 dark:text-brand-400 text-xs font-semibold hover:bg-brand-50 dark:hover:bg-brand-950/30 transition-colors disabled:opacity-40"
                >
                  <Sparkles size={13} /> Generar reporte del gráfico
                </button>
              </div>
              <form onSubmit={handleSubmit} className="flex gap-2 px-3.5 py-3">
                <input
                  value={instruccion}
                  onChange={(e) => setInstruccion(e.target.value)}
                  placeholder="Ej: solo los celulares"
                  disabled={loading}
                  className="flex-1 text-xs bg-slate-100 dark:bg-slate-800 rounded-lg px-3 py-2 text-slate-800 dark:text-slate-200 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30 transition-all disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={!instruccion.trim() || loading}
                  className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center text-white disabled:opacity-40 hover:bg-brand-700 transition-colors shrink-0"
                >
                  <Send size={13} />
                </button>
              </form>
            </div>
          )}
        </div>
      )}

      {/* Burbuja colapsada */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-14 h-14 rounded-full bg-brand-600 hover:bg-brand-700 shadow-lg flex items-center justify-center transition-all hover:scale-105 active:scale-95"
        title="Don Tino"
      >
        {open ? <X size={18} className="text-white" /> : <MessageCircle size={20} className="text-white" />}
      </button>
    </div>
  );
}

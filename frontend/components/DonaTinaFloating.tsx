"use client";
import { useEffect, useState } from "react";
import { preciosApi, type AiTaskUsage } from "@/lib/api";
import { RobotMascot } from "@/components/RobotMascot";
import { X, Send, BarChart3, Sparkles } from "lucide-react";

// ── Doña Tina flotante — misma cara en todos lados, pero lo que contesta viene
// de Claude/ChatGPT por detrás (ver backend/app/services/dona_tina_precios.py).
// El usuario nunca ve esos nombres, solo a Doña Tina respondiendo. ─────────────

type Contexto = "precios" | "comparison" | "analytics";

type Msg = { role: "bot" | "user"; text: string; usage?: AiTaskUsage };

interface ItemConPrecio {
  id?: string; // solo presente cuando hay checklist para aplicar selección (comparison)
  tienda: string;
  nombre: string;
  precio: number;
  moneda: string;
}

interface DonaTinaFloatingProps {
  context: Contexto;
  termino?: string;
  items?: ItemConPrecio[];
  // context="comparison": los tildados actualmente, para el reporte + input de nuestro precio
  chartItems?: { tienda: string; nombre: string; precio: number; moneda: string }[];
  ourPrice?: number | null;
  ourCurrency?: string | null;
  onApplySeleccion?: (ids: string[]) => void;
  // context="precios": shortcut para abrir el gráfico
  onOpenChart?: () => void;
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

export default function DonaTinaFloating({
  context, termino, items, chartItems, ourPrice, ourCurrency, onApplySeleccion, onOpenChart,
}: DonaTinaFloatingProps) {
  const [open, setOpen] = useState(false);
  const [mensaje, setMensaje] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [loading, setLoading] = useState(false);

  const hayItems = !!items && items.length > 0;
  const reporteItems = context === "comparison" ? chartItems : items;
  const hayParaReporte = !!reporteItems && reporteItems.length > 0;

  // Tip proactivo: en /precios, apenas hay resultados y todavía no se habló
  // con Doña Tina, le avisamos que puede filtrar la lista por pedido — si no,
  // nadie se entera de que existe esta función salvo que la pruebe por las
  // suyas. Solo una vez (mientras no haya mensajes propios todavía).
  useEffect(() => {
    if (context === "precios" && hayItems && messages.length === 0) {
      setMessages([{
        role: "bot",
        text: '¡Hola! ¿Sabías que puedo filtrarte los productos que me pidas en esta sección? Por ejemplo: "dejame solo los Galaxy A16" o "sacá los que no sean Samsung".',
      }]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [context, hayItems]);

  async function enviar() {
    const texto = mensaje.trim();
    if (!texto || !items || !termino) return;
    setMensaje("");
    setMessages((prev) => [...prev, { role: "user", text: texto }]);
    setLoading(true);
    try {
      const { data } = await preciosApi.consultarIA(
        termino,
        items.map((it) => ({ tienda: it.tienda, nombre: it.nombre, precio: it.precio, moneda: it.moneda })),
        texto,
      );
      // data.mantener=[] (sin matches) NO debe vaciar la selección actual — un
      // array vacío es "truthy" en JS, así que sin este chequeo explícito de
      // longitud se aplicaría igual y borraría todo lo que el usuario ya tenía
      // tildado por una consulta que no encontró nada.
      if (data.tipo === "seleccion" && data.mantener && data.mantener.length > 0 && onApplySeleccion) {
        const idsAplicados = data.mantener.map((n) => items[n - 1]?.id).filter((id): id is string => !!id);
        onApplySeleccion(idsAplicados);
      }
      setMessages((prev) => [...prev, { role: "bot", text: data.respuesta, usage: data.usage }]);
    } catch {
      setMessages((prev) => [...prev, { role: "bot", text: "No pude procesar el pedido — probá de nuevo." }]);
    } finally {
      setLoading(false);
    }
  }

  async function generarReporte() {
    if (!reporteItems || reporteItems.length === 0) {
      setMessages((prev) => [...prev, {
        role: "bot",
        text: context === "comparison"
          ? "Tildá algún producto en la lista primero para poder armar el reporte."
          : "Buscá algo con resultados primero para que te pueda armar un reporte.",
      }]);
      return;
    }
    setMessages((prev) => [...prev, { role: "user", text: "Generar reporte" }]);
    setLoading(true);
    try {
      const { data } = await preciosApi.generarReporteIA(reporteItems, ourPrice ?? null, ourCurrency ?? null);
      setMessages((prev) => [...prev, { role: "bot", text: data.reporte, usage: data.usage }]);
    } catch {
      setMessages((prev) => [...prev, { role: "bot", text: "No pude generar el reporte en este momento — probá de nuevo." }]);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    enviar();
  }

  const placeholderInicial =
    context === "analytics"
      ? "Preguntame lo que quieras sobre este análisis desde el chat de Home."
      : hayItems
      ? 'Preguntame algo (ej. "¿cuál es el más barato?") o pedime que filtre la lista.'
      : "Buscá algún producto para que te pueda ayudar.";

  return (
    <div className="fixed bottom-5 right-5 z-[60] flex flex-col items-end gap-3">
      {open && (
        <div className="w-80 max-h-[70vh] flex flex-col bg-white dark:bg-slate-900 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-700 overflow-hidden animate-fade-in">
          {/* Header */}
          <div className="flex items-center gap-2.5 px-4 py-3 bg-brand-600 shrink-0">
            <div className="w-9 h-9 rounded-full bg-white flex items-center justify-center shrink-0 shadow-sm overflow-visible">
              <RobotMascot size={30} variant="tina" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-white text-xs font-bold leading-none">Doña Tina</p>
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
            {messages.length === 0 && (
              <p className="text-xs text-slate-400 dark:text-slate-500 text-center py-4">{placeholderInicial}</p>
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

          {/* Footer / acciones */}
          {context !== "analytics" && (
            <div className="border-t border-slate-100 dark:border-slate-800 shrink-0">
              <div className="px-3.5 pt-2.5 flex gap-2">
                <button
                  onClick={generarReporte}
                  disabled={loading || !hayParaReporte}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl border border-brand-200 dark:border-brand-800 text-brand-600 dark:text-brand-400 text-xs font-semibold hover:bg-brand-50 dark:hover:bg-brand-950/30 transition-colors disabled:opacity-40"
                >
                  <Sparkles size={13} /> Generar reporte
                </button>
                {context === "precios" && onOpenChart && (
                  <button
                    onClick={onOpenChart}
                    disabled={!hayItems}
                    className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 text-xs font-semibold hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors disabled:opacity-40"
                    title="Ver en gráfico"
                  >
                    <BarChart3 size={13} />
                  </button>
                )}
              </div>
              <form onSubmit={handleSubmit} className="flex gap-2 px-3.5 py-3">
                <input
                  value={mensaje}
                  onChange={(e) => setMensaje(e.target.value)}
                  placeholder={hayItems ? "Preguntame algo o pedime un filtro..." : "Buscá algo primero..."}
                  disabled={loading || !hayItems}
                  className="flex-1 text-xs bg-slate-100 dark:bg-slate-800 rounded-lg px-3 py-2 text-slate-800 dark:text-slate-200 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30 transition-all disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={!mensaje.trim() || loading || !hayItems}
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
        className="w-16 h-16 rounded-full bg-white dark:bg-slate-800 shadow-lg border border-slate-100 dark:border-slate-700 flex items-center justify-center transition-all hover:scale-105 active:scale-95 relative"
        title="Doña Tina"
      >
        {open ? (
          <X size={18} className="text-slate-500" />
        ) : (
          <>
            <RobotMascot size={44} variant="tina" />
            <span className="absolute bottom-1 right-1 w-3 h-3 bg-emerald-500 rounded-full border-2 border-white dark:border-slate-800" />
          </>
        )}
      </button>
    </div>
  );
}

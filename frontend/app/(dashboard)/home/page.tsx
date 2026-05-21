"use client";
import { useEffect, useRef, useState } from "react";
import { authApi } from "@/lib/api";
import type { CurrentUser } from "@/types";
import { Send, Sparkles, ChevronDown } from "lucide-react";

// ---------------------------------------------------------------------------
// Bot knowledge base — swap with real AI call later
// ---------------------------------------------------------------------------
type BotMessage = { role: "bot" | "user"; text: string; ts: Date };

const SUGGESTIONS = [
  "¿Cómo sincronizo Meta Ads?",
  "¿Cómo genero cenefas?",
  "¿Qué es el ROAS?",
  "¿Cómo invito a mi equipo?",
];

function getBotReply(input: string): string {
  const q = input.toLowerCase();

  if (q.includes("cenefas") || q.includes("pptx"))
    return "Para generar cenefas andá a **Herramientas → Cenefas** en el sidebar. Necesitás cargar el Excel de productos y la plantilla PPTX base. El sistema genera el archivo con 3 productos por slide automáticamente.";

  if (q.includes("meta") || q.includes("sincroniz") || q.includes("sync"))
    return "Para sincronizar Meta Ads primero agregá tu conexión en **Configuración → Conexiones** con tu Access Token. Después en la página de **Campañas** usá el botón "Meta Ads" arriba a la derecha para importar los datos.";

  if (q.includes("roas"))
    return "El **ROAS** (Return On Ad Spend) mide cuánto revenue generás por cada peso invertido. Un ROAS de 3x significa que por cada $1 invertido generás $3. En el Dashboard podés ver el ROAS global y por plataforma.";

  if (q.includes("equipo") || q.includes("invit") || q.includes("código"))
    return "En **Configuración → Conexiones** encontrás el botón "Copiar código de invitación". Compartí ese código con tu equipo — al registrarse o iniciar sesión pueden pegarlo para unirse automáticamente.";

  if (q.includes("dashboard") || q.includes("kpi"))
    return "El **Dashboard** muestra tus KPIs principales: inversión total, clicks, conversiones y ROAS global. Podés filtrar por 7D, 30D o 90D y comparar contra períodos anteriores. También detecta anomalías automáticamente.";

  if (q.includes("campaña") || q.includes("campaña"))
    return "En **Campañas** ves todas las métricas a nivel de campaña con filtros por plataforma, rango de fechas y búsqueda. Podés ordenar por inversión, ROAS, CTR y exportar a CSV.";

  if (q.includes("análisis") || q.includes("ia") || q.includes("inteligencia"))
    return "En **Análisis IA** podés pedirle a Claude que analice tus campañas y genere insights accionables. Seleccionás las plataformas y el tipo de análisis, y la IA cruza los datos y te da recomendaciones.";

  if (q.includes("conexion") || q.includes("token") || q.includes("api"))
    return "En **Configuración → Conexiones** podés agregar tus cuentas de Meta Ads, Google Ads, TikTok y DV360. Cada plataforma tiene una guía paso a paso para obtener el token de acceso.";

  if (q.includes("hola") || q.includes("buenas") || q.includes("hi"))
    return "¡Hola! Estoy aquí para ayudarte a sacarle el máximo provecho a la plataforma. Podés preguntarme sobre cualquier funcionalidad o cómo hacer algo específico.";

  return "Puedo ayudarte con **sincronización de plataformas**, **generación de cenefas**, **análisis IA**, **métricas y ROAS**, o **gestión del equipo**. ¿Sobre qué querés saber más?";
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function HomePage() {
  const [user, setUser]     = useState<CurrentUser | null>(null);
  const [messages, setMessages] = useState<BotMessage[]>([]);
  const [input, setInput]   = useState("");
  const [open, setOpen]     = useState(false);
  const [typing, setTyping] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    authApi.me().then(({ data }) => {
      setUser(data);
      const name = data.full_name?.split(" ")[0] ?? "";
      setMessages([{
        role: "bot",
        text: `¡Hola${name ? ", " + name : ""}! Soy tu asistente de MKTG Platform. Puedo guiarte en el uso de la plataforma, explicarte funcionalidades y ayudarte a sacarle el máximo provecho. ¿En qué te puedo ayudar hoy?`,
        ts: new Date(),
      }]);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, open]);

  async function send(text: string) {
    const q = text.trim();
    if (!q) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: q, ts: new Date() }]);
    setTyping(true);
    await new Promise((r) => setTimeout(r, 700 + Math.random() * 400));
    setTyping(false);
    setMessages((prev) => [...prev, { role: "bot", text: getBotReply(q), ts: new Date() }]);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    send(input);
  }

  const firstName = user?.full_name?.split(" ")[0] ?? "";

  return (
    <div className="min-h-[calc(100vh-4rem)] flex flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-2xl space-y-8">

        {/* Mascot + greeting */}
        <div className="flex flex-col items-center text-center gap-4">
          <div className="relative">
            <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shadow-lg shadow-brand-500/30">
              <Sparkles size={36} className="text-white" />
            </div>
            <span className="absolute -bottom-1 -right-1 w-5 h-5 bg-emerald-500 rounded-full border-2 border-white" />
          </div>

          <div>
            <p className="text-xs font-semibold text-brand-500 uppercase tracking-widest mb-1">
              {user?.team_name ?? "MKTG Platform"}
            </p>
            <h1 className="text-3xl font-bold text-slate-900">
              Hola{firstName ? `, ${firstName}` : ""} 👋
            </h1>
            <p className="text-slate-500 mt-1">Tu asistente de plataforma está listo</p>
          </div>
        </div>

        {/* Chat card */}
        <div className="card overflow-hidden shadow-card-hover">

          {/* Chat header */}
          <button
            onClick={() => setOpen((o) => !o)}
            className="w-full flex items-center gap-3 px-5 py-4 hover:bg-slate-50 transition-colors"
          >
            <div className="w-8 h-8 rounded-xl bg-brand-500/10 flex items-center justify-center shrink-0">
              <Sparkles size={16} className="text-brand-500" />
            </div>
            <div className="flex-1 text-left">
              <p className="text-sm font-semibold text-slate-800">Asistente MKTG</p>
              <p className="text-xs text-slate-400">Preguntame sobre la plataforma</p>
            </div>
            <ChevronDown
              size={16}
              className={`text-slate-400 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
            />
          </button>

          {/* Messages */}
          {open && (
            <>
              <div className="border-t border-slate-100 px-5 py-4 space-y-4 max-h-80 overflow-y-auto bg-slate-50/50">
                {messages.map((m, i) => (
                  <div key={i} className={`flex gap-3 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
                    {m.role === "bot" && (
                      <div className="w-7 h-7 rounded-xl bg-brand-500/10 flex items-center justify-center shrink-0 mt-0.5">
                        <Sparkles size={13} className="text-brand-500" />
                      </div>
                    )}
                    <div className={`max-w-[80%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
                      m.role === "user"
                        ? "bg-brand-600 text-white rounded-tr-sm"
                        : "bg-white border border-slate-100 text-slate-700 rounded-tl-sm shadow-sm"
                    }`}>
                      {m.text.split("**").map((part, j) =>
                        j % 2 === 1
                          ? <strong key={j} className={m.role === "user" ? "text-white" : "text-slate-900"}>{part}</strong>
                          : <span key={j}>{part}</span>
                      )}
                    </div>
                  </div>
                ))}
                {typing && (
                  <div className="flex gap-3">
                    <div className="w-7 h-7 rounded-xl bg-brand-500/10 flex items-center justify-center shrink-0">
                      <Sparkles size={13} className="text-brand-500" />
                    </div>
                    <div className="bg-white border border-slate-100 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm flex gap-1 items-center">
                      <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:0ms]" />
                      <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:150ms]" />
                      <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:300ms]" />
                    </div>
                  </div>
                )}
                <div ref={bottomRef} />
              </div>

              {/* Suggestions */}
              {messages.length <= 1 && (
                <div className="px-5 py-3 flex gap-2 flex-wrap border-t border-slate-100">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} onClick={() => send(s)}
                      className="text-xs px-3 py-1.5 rounded-full border border-slate-200 text-slate-600 hover:border-brand-400 hover:text-brand-600 hover:bg-brand-50 transition-all">
                      {s}
                    </button>
                  ))}
                </div>
              )}

              {/* Input */}
              <form onSubmit={handleSubmit} className="border-t border-slate-100 flex gap-3 px-4 py-3">
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Escribí tu pregunta..."
                  className="flex-1 text-sm bg-slate-100 rounded-xl px-4 py-2.5 text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:bg-white transition-all"
                />
                <button
                  type="submit"
                  disabled={!input.trim() || typing}
                  className="w-10 h-10 rounded-xl bg-brand-600 flex items-center justify-center text-white disabled:opacity-40 hover:bg-brand-700 transition-colors shrink-0"
                >
                  <Send size={15} />
                </button>
              </form>
            </>
          )}
        </div>

        {/* Quick note */}
        <p className="text-center text-xs text-slate-400">
          Pronto con IA real integrada · Por ahora respondo preguntas frecuentes sobre la plataforma
        </p>
      </div>
    </div>
  );
}

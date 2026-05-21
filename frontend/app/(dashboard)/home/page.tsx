"use client";
import { useEffect, useRef, useState } from "react";
import { authApi } from "@/lib/api";
import type { CurrentUser } from "@/types";
import { Send, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

// ---------------------------------------------------------------------------
// Bot knowledge base — swap with real AI call later
// ---------------------------------------------------------------------------
type BotMessage = { role: "bot" | "user"; text: string; ts: Date };

function getBotReply(input: string): string {
  const q = input.toLowerCase();

  if (q.includes("cenefa") || q.includes("banner") || q.includes("faixa") || q.includes("pptx"))
    return "Para generar cenefas andá a **Herramientas → Cenefas** en el sidebar. Necesitás cargar el Excel de productos y la plantilla PPTX base. El sistema genera el archivo con 3 productos por slide automáticamente.";

  if (q.includes("meta") || q.includes("sincroniz") || q.includes("sync"))
    return "Para sincronizar Meta Ads primero agregá tu conexión en **Configuración → Conexiones** con tu Access Token. Después en la página de **Campañas** usá el botón 'Meta Ads' arriba a la derecha para importar los datos.";

  if (q.includes("roas"))
    return "El **ROAS** (Return On Ad Spend) mide cuánto revenue generás por cada peso invertido. Un ROAS de 3x significa que por cada $1 invertido generás $3. En el Dashboard podés ver el ROAS global y por plataforma.";

  if (q.includes("equipo") || q.includes("team") || q.includes("invit") || q.includes("código") || q.includes("code"))
    return "En **Configuración → Conexiones** encontrás el botón 'Copiar código de invitación'. Compartí ese código con tu equipo — al registrarse o iniciar sesión pueden pegarlo para unirse automáticamente.";

  if (q.includes("dashboard") || q.includes("kpi"))
    return "El **Dashboard** muestra tus KPIs principales: inversión total, clicks, conversiones y ROAS global. Podés filtrar por 7D, 30D o 90D y comparar contra períodos anteriores. También detecta anomalías automáticamente.";

  if (q.includes("campaña") || q.includes("campaign"))
    return "En **Campañas** ves todas las métricas a nivel de campaña con filtros por plataforma, rango de fechas y búsqueda. Podés ordenar por inversión, ROAS, CTR y exportar a CSV.";

  if (q.includes("análisis") || q.includes("analysis") || q.includes("ia") || q.includes("ai") || q.includes("inteligencia"))
    return "En **Análisis IA** podés pedirle a Claude que analice tus campañas y genere insights accionables. Seleccionás las plataformas y el tipo de análisis, y la IA cruza los datos y te da recomendaciones.";

  if (q.includes("conexion") || q.includes("connection") || q.includes("token") || q.includes("api"))
    return "En **Configuración → Conexiones** podés agregar tus cuentas de Meta Ads, Google Ads, TikTok y DV360. Cada plataforma tiene una guía paso a paso para obtener el token de acceso.";

  if (q.includes("hola") || q.includes("hi") || q.includes("hello") || q.includes("buenas") || q.includes("olá"))
    return "¡Hola! Estoy aquí para ayudarte a sacarle el máximo provecho a la plataforma. Podés preguntarme sobre cualquier funcionalidad o cómo hacer algo específico.";

  return "Puedo ayudarte con **sincronización de plataformas**, **generación de cenefas**, **análisis IA**, **métricas y ROAS**, o **gestión del equipo**. ¿Sobre qué querés saber más?";
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function HomePage() {
  const { t } = useTranslation();
  const [user, setUser]     = useState<CurrentUser | null>(null);
  const [messages, setMessages] = useState<BotMessage[]>([]);
  const [input, setInput]   = useState("");
  const [open, setOpen]     = useState(false);
  const [typing, setTyping] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const SUGGESTIONS = [
    t("home.suggestions.s1"),
    t("home.suggestions.s2"),
    t("home.suggestions.s3"),
    t("home.suggestions.s4"),
  ];

  useEffect(() => {
    authApi.me().then(({ data }) => {
      setUser(data);
      const name = data.full_name?.split(" ")[0] ?? "";
      const greeting = name ? t("home.greeting", { name }) : t("home.greetingNoName");
      setMessages([{
        role: "bot",
        text: `${greeting}! ${t("home.assistantWelcome")}`,
        ts: new Date(),
      }]);
    }).catch(() => {});
  }, [t]);

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
            <RobotMascot />
            <span className="absolute -bottom-1 -right-1 w-5 h-5 bg-emerald-500 rounded-full border-2 border-white" />
          </div>

          <div>
            <p className="text-xs font-semibold text-brand-500 uppercase tracking-widest mb-1">
              {user?.team_name ?? "MKTG Platform"}
            </p>
            <h1 className="text-3xl font-bold text-slate-900">
              {firstName ? t("home.greeting", { name: firstName }) : t("home.greetingNoName")} {t("home.waveEmoji")}
            </h1>
            <p className="text-slate-500 mt-1">{t("home.assistantReady")}</p>
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
              <RobotMini />
            </div>
            <div className="flex-1 text-left">
              <p className="text-sm font-semibold text-slate-800">{t("home.assistantName")}</p>
              <p className="text-xs text-slate-400">{t("home.assistantSubtitle")}</p>
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
                        <RobotMini />
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
                      <RobotMini />
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
                  placeholder={t("home.inputPlaceholder")}
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
          {t("home.comingSoon")}
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Robot mascot SVGs
// ---------------------------------------------------------------------------

function RobotMascot() {
  return (
    <>
      <style>{`
        @keyframes robot-float {
          0%, 100% { transform: translateY(0px); }
          50%       { transform: translateY(-8px); }
        }
        @keyframes robot-shadow {
          0%, 100% { transform: scaleX(1);   opacity: 0.15; }
          50%       { transform: scaleX(0.7); opacity: 0.07; }
        }
        @keyframes robot-blink {
          0%, 88%, 100% { transform: scaleY(1); }
          92%           { transform: scaleY(0.08); }
        }
        @keyframes antenna-pulse {
          0%, 100% { opacity: 1;   r: 3; }
          50%       { opacity: 0.4; r: 4.5; }
        }
        @keyframes light-1 {
          0%,100% { opacity:1 } 20%,60% { opacity:0.2 }
        }
        @keyframes light-2 {
          0%,100% { opacity:0.2 } 40% { opacity:1 }
        }
        @keyframes light-3 {
          0%,100% { opacity:0.2 } 70% { opacity:1 }
        }
        @keyframes arm-wave {
          0%,100% { transform: rotate(0deg);   transform-origin: 20px 40px; }
          25%      { transform: rotate(-18deg); transform-origin: 20px 40px; }
          75%      { transform: rotate(10deg);  transform-origin: 20px 40px; }
        }
        .robot-body  { animation: robot-float  2.8s ease-in-out infinite; }
        .robot-shadow{ animation: robot-shadow 2.8s ease-in-out infinite; }
        .robot-eye-l { animation: robot-blink  3.5s ease-in-out infinite; transform-origin: 32px 24px; }
        .robot-eye-r { animation: robot-blink  3.5s ease-in-out infinite; transform-origin: 48px 24px; animation-delay: 0.05s; }
        .robot-ant   { animation: antenna-pulse 1.4s ease-in-out infinite; }
        .robot-l1    { animation: light-1 1.8s ease-in-out infinite; }
        .robot-l2    { animation: light-2 1.8s ease-in-out infinite; }
        .robot-l3    { animation: light-3 1.8s ease-in-out infinite; }
        .robot-arm-l { animation: arm-wave 2.8s ease-in-out infinite; }
      `}</style>

      <svg width="90" height="90" viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
      {/* Shadow under robot */}
      <ellipse className="robot-shadow" cx="40" cy="76" rx="22" ry="4" fill="#6366f1" />

      <g className="robot-body">
        {/* Body */}
        <rect x="22" y="38" width="36" height="26" rx="8" fill="#4f46e5" />
        {/* Belly panel */}
        <rect x="29" y="44" width="22" height="13" rx="4" fill="#4338ca" />
        {/* Belly lights */}
        <circle className="robot-l1" cx="34" cy="50" r="2.5" fill="#a5f3fc" />
        <circle className="robot-l2" cx="40" cy="50" r="2.5" fill="#6ee7b7" />
        <circle className="robot-l3" cx="46" cy="50" r="2.5" fill="#fca5a5" />
        {/* Left arm (waves) */}
        <g className="robot-arm-l">
          <rect x="10" y="40" width="10" height="18" rx="5" fill="#4f46e5" />
          <circle cx="15" cy="60" r="5" fill="#6366f1" />
        </g>
        {/* Right arm (static) */}
        <rect x="60" y="40" width="10" height="18" rx="5" fill="#4f46e5" />
        <circle cx="65" cy="60" r="5" fill="#6366f1" />
        {/* Neck */}
        <rect x="35" y="32" width="10" height="8" rx="3" fill="#6366f1" />
        {/* Head */}
        <rect x="18" y="10" width="44" height="30" rx="12" fill="#6366f1" />
        {/* Eye whites */}
        <rect x="26" y="19" width="12" height="10" rx="5" fill="white" />
        <rect x="42" y="19" width="12" height="10" rx="5" fill="white" />
        {/* Pupils */}
        <circle className="robot-eye-l" cx="32" cy="24" r="4" fill="#1e1b4b" />
        <circle className="robot-eye-r" cx="48" cy="24" r="4" fill="#1e1b4b" />
        {/* Eye shine */}
        <circle cx="33" cy="22" r="1.5" fill="white" />
        <circle cx="49" cy="22" r="1.5" fill="white" />
        {/* Smile */}
        <path d="M30 33 Q40 39 50 33" stroke="white" strokeWidth="2.5" strokeLinecap="round" fill="none" />
        {/* Antenna stem */}
        <line x1="40" y1="10" x2="40" y2="3" stroke="#818cf8" strokeWidth="2.5" strokeLinecap="round" />
        {/* Antenna ball */}
        <circle className="robot-ant" cx="40" cy="2" r="3" fill="#a5b4fc" />
      </g>
      </svg>
    </>
  );
}

function RobotMini() {
  return (
    <svg width="16" height="16" viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="18" y="10" width="44" height="30" rx="12" fill="#6366f1" />
      <rect x="26" y="19" width="12" height="10" rx="5" fill="white" />
      <rect x="42" y="19" width="12" height="10" rx="5" fill="white" />
      <circle cx="32" cy="24" r="4" fill="#1e1b4b" />
      <circle cx="48" cy="24" r="4" fill="#1e1b4b" />
      <path d="M30 33 Q40 39 50 33" stroke="white" strokeWidth="2.5" strokeLinecap="round" fill="none" />
      <line x1="40" y1="10" x2="40" y2="3" stroke="#818cf8" strokeWidth="2.5" strokeLinecap="round" />
      <circle cx="40" cy="2" r="3" fill="#a5b4fc" />
      <rect x="22" y="38" width="36" height="26" rx="8" fill="#4f46e5" />
    </svg>
  );
}

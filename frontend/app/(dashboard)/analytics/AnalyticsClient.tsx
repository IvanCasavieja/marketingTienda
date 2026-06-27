"use client";
import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { analyticsApi } from "@/lib/api";
import { Analysis, PLATFORM_LABELS } from "@/types";
import { format, subDays } from "date-fns";
import {
  Clock, ChevronRight, XCircle, MessageSquare,
  Send, StopCircle, Loader2, RotateCcw, Gavel, Globe, ChevronDown, ChevronUp,
} from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

const ALL_PLATFORMS = ["meta", "google_ads", "tiktok", "dv360"];

// Per-speaker design tokens
const S = {
  Claude: {
    avatar: "bg-orange-500",
    name: "text-orange-600",
    label: "Analista cuantitativo",
    border: "border-orange-100",
    dot: "bg-orange-500",
    side: "left" as const,
  },
  ChatGPT: {
    avatar: "bg-emerald-500",
    name: "text-emerald-600",
    label: "Estratega de crecimiento",
    border: "border-emerald-100",
    dot: "bg-emerald-500",
    side: "right" as const,
  },
  Llama: {
    avatar: "bg-purple-600",
    name: "text-purple-600",
    label: "Árbitro",
    border: "border-purple-200",
    dot: "bg-purple-500",
    side: "full" as const,
  },
} as const;

interface ChatMessage {
  id: string;
  speaker: "Claude" | "ChatGPT" | "Llama" | "user";
  content: string;
  role?: string;
  type: "greeting" | "debate" | "user" | "web_context";
}

interface TokenTotals {
  total: number;
  by_model: Record<string, number>;
}

function tryParseDebate(result: string): ChatMessage[] | null {
  try {
    const parsed = JSON.parse(result);
    if (parsed.debate && Array.isArray(parsed.debate)) {
      return parsed.debate.map((m: any, i: number) => ({
        id: `h-${i}`,
        speaker: m.speaker,
        content: m.content,
        role: m.role,
        type: m.speaker === "user" ? "user" : "debate",
      }));
    }
  } catch { /* not debate JSON */ }
  return null;
}

function Md({ text }: { text: string }) {
  return <div className="prose-analysis"><ReactMarkdown>{text}</ReactMarkdown></div>;
}

function TypingDots({ color }: { color: string }) {
  return (
    <div className="flex gap-1 items-center h-4">
      {[0, 120, 240].map((d) => (
        <span
          key={d}
          className={`w-1.5 h-1.5 rounded-full ${color} animate-bounce opacity-60`}
          style={{ animationDelay: `${d}ms` }}
        />
      ))}
    </div>
  );
}

const GREETINGS: ChatMessage[] = [
  { id: "g1", speaker: "Claude",  type: "greeting", role: "greeting", content: "Hola. Tengo cargados los datos de tus campañas para el período seleccionado. ¿Qué querés que analice o debata?" },
  { id: "g2", speaker: "ChatGPT", type: "greeting", role: "greeting", content: "Listo para empezar. Compartí tu pregunta y arrancamos." },
  { id: "g3", speaker: "Llama",   type: "greeting", role: "greeting", content: "Cuando quieras mi veredicto final, hacé click en el botón de abajo." },
];

// ── Message bubble components ─────────────────────────────────────────────────

function UserBubble({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[68%] bg-violet-600 text-white text-sm leading-relaxed px-4 py-3 rounded-2xl rounded-br-sm shadow-sm">
        {content}
      </div>
    </div>
  );
}

function LlamaBubble({ content, loading = false }: { content?: string; loading?: boolean }) {
  return (
    <div className="w-full rounded-2xl overflow-hidden border border-purple-200 dark:border-purple-800 shadow-md bg-white dark:bg-slate-900 animate-fade-in">
      <div className="flex items-center gap-2.5 px-4 py-3 bg-gradient-to-r from-purple-700 to-violet-600">
        <div className="w-7 h-7 rounded-full bg-white/15 border border-white/20 flex items-center justify-center">
          <Gavel size={13} className="text-white" />
        </div>
        <div>
          <p className="text-white text-xs font-bold leading-none">Llama</p>
          <p className="text-purple-200 text-[10px] mt-0.5">Árbitro · Veredicto</p>
        </div>
      </div>
      <div className="px-5 py-4 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
        {loading ? <TypingDots color="bg-purple-500" /> : content && <Md text={content} />}
      </div>
    </div>
  );
}

function LlamaGreetingBubble({ content }: { content: string }) {
  return (
    <div className="flex justify-center">
      <div className="flex items-center gap-2.5 bg-purple-50 border border-purple-100 rounded-2xl px-4 py-2.5 max-w-[75%]">
        <div className="w-6 h-6 rounded-full bg-purple-600 flex items-center justify-center shrink-0">
          <Gavel size={11} className="text-white" />
        </div>
        <p className="text-xs text-purple-700">{content}</p>
      </div>
    </div>
  );
}

function AiBubble({
  speaker, content, isGreeting = false, loading = false,
}: {
  speaker: "Claude" | "ChatGPT";
  content?: string;
  isGreeting?: boolean;
  loading?: boolean;
}) {
  const cfg = S[speaker];
  const isLeft = cfg.side === "left";

  return (
    <div className={`flex items-end gap-2.5 animate-fade-in ${isLeft ? "flex-row" : "flex-row-reverse"}`}>
      {/* Avatar */}
      <div className={`w-8 h-8 rounded-full ${cfg.avatar} flex items-center justify-center shrink-0 shadow-sm mb-0.5`}>
        <span className="text-white text-[11px] font-black">{speaker[0]}</span>
      </div>

      {/* Bubble */}
      <div className={`flex flex-col gap-1 max-w-[70%] ${isLeft ? "items-start" : "items-end"}`}>
        {!isGreeting && (
          <div className={`flex items-center gap-1.5 px-1 ${isLeft ? "" : "flex-row-reverse"}`}>
            <span className={`text-[11px] font-bold ${cfg.name}`}>{speaker}</span>
            <span className="text-[10px] text-slate-400">{cfg.label}</span>
          </div>
        )}
        <div
          className={`bg-white dark:bg-slate-900 border ${cfg.border} shadow-sm px-4 py-3 text-sm leading-relaxed text-slate-700 dark:text-slate-300
            ${isLeft ? "rounded-2xl rounded-bl-sm" : "rounded-2xl rounded-br-sm"}
            ${isGreeting ? "opacity-75" : ""}
          `}
        >
          {loading
            ? <TypingDots color={cfg.dot} />
            : content && <Md text={content} />
          }
        </div>
      </div>
    </div>
  );
}

function WebContextBubble({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="flex justify-center animate-fade-in">
      <div className="w-full max-w-[85%] rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/40 overflow-hidden">
        <button
          onClick={() => setExpanded((v) => !v)}
          className="w-full flex items-center gap-2.5 px-4 py-2.5 hover:bg-emerald-100/60 dark:hover:bg-emerald-900/30 transition-colors"
        >
          <Globe size={13} className="text-emerald-600 dark:text-emerald-400 shrink-0" />
          <span className="text-[11px] font-semibold text-emerald-700 dark:text-emerald-400 flex-1 text-left">
            ChatGPT buscó contexto del período
          </span>
          {expanded
            ? <ChevronUp size={13} className="text-emerald-500 shrink-0" />
            : <ChevronDown size={13} className="text-emerald-500 shrink-0" />
          }
        </button>
        {expanded && (
          <div className="px-4 pb-3 text-xs text-emerald-800 dark:text-emerald-300 leading-relaxed border-t border-emerald-200 dark:border-emerald-800 pt-2.5">
            <Md text={content} />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function AnalyticsPage() {
  const { t } = useTranslation();
  const [platforms, setPlatforms]           = useState<string[]>(ALL_PLATFORMS);
  const [dateFrom, setDateFrom]             = useState("");
  const [dateTo, setDateTo]                 = useState("");
  const [compareMode, setCompareMode]       = useState(false);
  const [dateFrom2, setDateFrom2]           = useState("");
  const [dateTo2, setDateTo2]               = useState("");
  const [chatMessages, setChatMessages]     = useState<ChatMessage[]>(GREETINGS);
  const [chatInput, setChatInput]           = useState("");
  const [tokenTotals, setTokenTotals]       = useState<TokenTotals>({ total: 0, by_model: {} });
  const [errorMsg, setErrorMsg]             = useState<string>("");
  const [loading, setLoading]               = useState(false);
  const [verdictLoading, setVerdictLoading] = useState(false);
  const [history, setHistory]               = useState<Analysis[]>([]);
  const [activeAnalysis, setActive]         = useState<number | null>(null);
  const [conversationId, setConversationId] = useState<number | null>(null);

  const abortRef        = useRef<AbortController | null>(null);
  const chatEndRef      = useRef<HTMLDivElement | null>(null);
  const currentSpeakers = useRef<Set<string>>(new Set());

  useEffect(() => {
    const to   = new Date();
    const from = subDays(to, 30);
    setDateFrom(format(from, "yyyy-MM-dd"));
    setDateTo(format(to, "yyyy-MM-dd"));
    // Default period 2 = previous 30 days
    setDateTo2(format(subDays(from, 1), "yyyy-MM-dd"));
    setDateFrom2(format(subDays(from, 30), "yyyy-MM-dd"));
    analyticsApi.getHistory().then(({ data }) => setHistory(data)).catch(() => {});
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages, loading, verdictLoading]);

  function accumulateTokens(event: { total: number; by_model: Record<string, number> }) {
    setTokenTotals((prev) => {
      const updated = { ...prev.by_model };
      for (const [model, count] of Object.entries(event.by_model)) {
        updated[model] = (updated[model] ?? 0) + (count as number);
      }
      return { total: prev.total + event.total, by_model: updated };
    });
  }

  function resetChat() {
    abortRef.current?.abort();
    setChatMessages(GREETINGS);
    setTokenTotals({ total: 0, by_model: {} });
    setErrorMsg("");
    setActive(null);
    setConversationId(null);
  }

  function stopCurrent() { abortRef.current?.abort(); }

  async function sendChatMessage() {
    const msg = chatInput.trim();
    if (!msg || loading || verdictLoading) return;
    setChatInput("");

    const userMsg: ChatMessage = { id: `u-${Date.now()}`, speaker: "user", type: "user", content: msg };
    setChatMessages((prev) => [...prev, userMsg]);

    const historyForApi = [...chatMessages, userMsg]
      .filter((m) => m.type !== "greeting" && m.type !== "web_context")
      .map((m) => ({ speaker: m.speaker, content: m.content, role: m.role, type: m.type }));

    await runTurn(historyForApi, msg);
  }

  async function runTurn(historyForApi: object[], userMessage: string) {
    setLoading(true);
    setErrorMsg("");
    currentSpeakers.current = new Set();
    abortRef.current = new AbortController();

    try {
      const response = await analyticsApi.streamDebateTurn(
        platforms, dateFrom, dateTo, historyForApi, userMessage,
        abortRef.current.signal,
        conversationId,
        compareMode ? dateFrom2 : undefined,
        compareMode ? dateTo2   : undefined,
      );
      if (!response.ok || !response.body) throw new Error(t("analytics.defaultError"));

      const reader  = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer    = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const event of events) {
          if (!event.startsWith("data: ")) continue;
          try {
            const parsed = JSON.parse(event.slice(6).trim());
            if (parsed.type === "web_context") {
              setChatMessages((prev) => [...prev, {
                id: `wc-${Date.now()}`,
                speaker: "ChatGPT",
                type: "web_context",
                content: parsed.content,
              }]);
            } else if (parsed.type === "message") {
              currentSpeakers.current.add(parsed.speaker);
              setChatMessages((prev) => [...prev, {
                id: `m-${Date.now()}-${parsed.speaker}`,
                speaker: parsed.speaker,
                type: "debate",
                role: parsed.role,
                content: parsed.content,
              }]);
            } else if (parsed.type === "tokens") {
              accumulateTokens(parsed);
            } else if (parsed.type === "session") {
              setConversationId(parsed.conversation_id);
              analyticsApi.getHistory().then(({ data }) => setHistory(data)).catch(() => {});
            } else if (parsed.type === "error") {
              setErrorMsg(parsed.detail ?? t("analytics.defaultError"));
              toast.error(t("analytics.errorToast"));
            }
          } catch { /* partial JSON */ }
        }
      }
    } catch (err: any) {
      if (err?.name !== "AbortError") {
        setErrorMsg(err?.message ?? t("analytics.defaultError"));
        toast.error(t("analytics.errorToast"));
      }
    } finally {
      setLoading(false);
    }
  }

  async function requestVerdict() {
    if (verdictLoading || loading) return;
    setVerdictLoading(true);
    setErrorMsg("");
    abortRef.current = new AbortController();

    const historyForApi = chatMessages
      .filter((m) => m.type !== "greeting")
      .map((m) => ({ speaker: m.speaker, content: m.content, role: m.role, type: m.type }));

    try {
      const response = await analyticsApi.streamDebateVerdict(
        platforms, dateFrom, dateTo, historyForApi,
        abortRef.current.signal,
        conversationId,
        compareMode ? dateFrom2 : undefined,
        compareMode ? dateTo2   : undefined,
      );
      if (!response.ok || !response.body) throw new Error(t("analytics.defaultError"));

      const reader  = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer    = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const event of events) {
          if (!event.startsWith("data: ")) continue;
          try {
            const parsed = JSON.parse(event.slice(6).trim());
            if (parsed.type === "message") {
              setChatMessages((prev) => [...prev, {
                id: `v-${Date.now()}`,
                speaker: "Llama",
                type: "debate",
                role: "synthesis",
                content: parsed.content,
              }]);
            } else if (parsed.type === "tokens") {
              accumulateTokens(parsed);
            } else if (parsed.type === "done") {
              setActive(parsed.id);
              toast.success(t("analytics.debate.successToast"));
              analyticsApi.getHistory().then(({ data }) => setHistory(data)).catch(() => {});
            } else if (parsed.type === "error") {
              setErrorMsg(parsed.detail ?? t("analytics.defaultError"));
              toast.error(t("analytics.errorToast"));
            }
          } catch { /* partial JSON */ }
        }
      }
    } catch (err: any) {
      if (err?.name !== "AbortError") {
        setErrorMsg(err?.message ?? t("analytics.defaultError"));
        toast.error(t("analytics.errorToast"));
      }
    } finally {
      setVerdictLoading(false);
    }
  }

  async function loadFromHistory(id: number) {
    setActive(id);
    try {
      const { data } = await analyticsApi.getAnalysis(id);
      const parsed = tryParseDebate(data.result);
      if (parsed) {
        setChatMessages(parsed);
        setTokenTotals({ total: 0, by_model: {} });
      }
    } catch { toast.error(t("analytics.loadError")); }
  }

  const hasDebateContent = chatMessages.some((m) => m.type === "debate");
  const llamaHasSpoken   = chatMessages.some((m) => m.speaker === "Llama" && m.type === "debate");
  const pendingSpeakers  = loading
    ? (["Claude", "ChatGPT"] as const).filter((s) => !currentSpeakers.current.has(s))
    : [];
  const debateHistory = history.filter((h) => h.analysis_type === "debate");

  return (
    <div className="animate-fade-in space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">La Triada</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">Claude · ChatGPT · Llama — debate con tus datos de campañas</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[280px_1fr] gap-5 items-start">
        {/* ── Left panel ── */}
        <div className="space-y-4">
          <div className="card p-5">
            <p className="section-title mb-3">{t("analytics.platformsLabel")}</p>
            <div className="space-y-2">
              {ALL_PLATFORMS.map((p) => (
                <label key={p} className="flex items-center gap-3 cursor-pointer group">
                  <div
                    className={`w-4 h-4 rounded border-2 flex items-center justify-center transition-all ${
                      platforms.includes(p) ? "bg-brand-600 border-brand-600" : "border-slate-300 group-hover:border-brand-400"
                    }`}
                    onClick={() => setPlatforms((prev) =>
                      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]
                    )}
                  >
                    {platforms.includes(p) && (
                      <svg viewBox="0 0 10 8" className="w-2.5 h-2.5" fill="none">
                        <path d="M1 4l2.5 2.5L9 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    )}
                  </div>
                  <span className="text-sm text-slate-700 dark:text-slate-300">{PLATFORM_LABELS[p]}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="card p-5 space-y-3">
            {/* Period 1 */}
            <div className="flex items-center justify-between">
              <p className="section-title">{compareMode ? "Período actual" : t("analytics.period")}</p>
              {compareMode && <span className="text-[10px] font-bold bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">P2</span>}
            </div>
            <div className="space-y-2">
              <div>
                <label className="text-xs text-slate-500 dark:text-slate-400 mb-1 block">{t("common.from")}</label>
                <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="input text-sm" />
              </div>
              <div>
                <label className="text-xs text-slate-500 dark:text-slate-400 mb-1 block">{t("common.to")}</label>
                <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="input text-sm" />
              </div>
            </div>

            {/* Compare toggle */}
            <button
              onClick={() => setCompareMode((v) => !v)}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg border text-xs font-semibold transition-all ${
                compareMode
                  ? "bg-blue-600 border-blue-600 text-white"
                  : "border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-blue-300 hover:text-blue-600"
              }`}
            >
              <span>Comparar períodos</span>
              <div className={`w-7 h-4 rounded-full transition-all relative ${compareMode ? "bg-white/30" : "bg-slate-200 dark:bg-slate-700"}`}>
                <div className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-all ${compareMode ? "left-3.5" : "left-0.5"}`} />
              </div>
            </button>

            {/* Period 2 (base) */}
            {compareMode && (
              <div className="pt-1 border-t border-slate-100 dark:border-slate-800 space-y-2">
                <div className="flex items-center gap-1.5">
                  <p className="text-xs font-semibold text-slate-600 dark:text-slate-400">Período base</p>
                  <span className="text-[10px] font-bold bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 px-2 py-0.5 rounded-full">P1</span>
                </div>
                <div>
                  <label className="text-xs text-slate-500 dark:text-slate-400 mb-1 block">{t("common.from")}</label>
                  <input type="date" value={dateFrom2} onChange={(e) => setDateFrom2(e.target.value)} className="input text-sm" />
                </div>
                <div>
                  <label className="text-xs text-slate-500 dark:text-slate-400 mb-1 block">{t("common.to")}</label>
                  <input type="date" value={dateTo2} onChange={(e) => setDateTo2(e.target.value)} className="input text-sm" />
                </div>
              </div>
            )}
          </div>

          <button
            onClick={resetChat}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
          >
            <RotateCcw size={14} />
            Nueva conversación
          </button>

          {debateHistory.length > 0 && (
            <div className="card overflow-hidden">
              <div className="px-5 py-3.5 border-b border-slate-50 dark:border-slate-800 flex items-center gap-2">
                <Clock size={14} className="text-slate-400" />
                <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">Debates anteriores</p>
              </div>
              <div className="divide-y divide-slate-50 dark:divide-slate-800">
                {debateHistory.slice(0, 8).map((h) => (
                  <button key={h.id} onClick={() => loadFromHistory(h.id)}
                    className={`w-full flex items-center gap-3 px-5 py-3 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors text-left ${activeAnalysis === h.id ? "bg-brand-50/50" : ""}`}>
                    <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 text-violet-600 bg-violet-50">
                      <MessageSquare size={13} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">La Triada</p>
                      <p className="text-[11px] text-slate-400">{format(new Date(h.created_at), "dd/MM HH:mm")}</p>
                    </div>
                    <ChevronRight size={14} className="text-slate-300 shrink-0" />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ── Chat ── */}
        <div className="space-y-3">
          {errorMsg && (
            <div className="flex items-start gap-3 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
              <XCircle size={16} className="text-red-500 shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-semibold text-red-700">{t("analytics.errorTitle")}</p>
                <p className="text-xs text-red-600 mt-0.5">{errorMsg}</p>
              </div>
              <button onClick={() => setErrorMsg("")} className="text-red-400 hover:text-red-600"><XCircle size={14} /></button>
            </div>
          )}

          <div
            className="flex flex-col rounded-2xl overflow-hidden border border-slate-200/80 shadow-xl"
            style={{ height: "calc(100vh - 175px)", minHeight: "640px" }}
          >
            {/* ── Header ── */}
            <div className="shrink-0 bg-slate-900 px-5 py-3.5 flex items-center gap-4">
              {/* Speaker pills */}
              <div className="flex items-center gap-1.5">
                {[
                  { bg: "bg-orange-500", name: "Claude" },
                  { bg: "bg-emerald-400", name: "ChatGPT" },
                  { bg: "bg-purple-500", name: "Llama" },
                ].map((a) => (
                  <div key={a.name} className={`flex items-center gap-1.5 ${a.bg} bg-opacity-20 border border-white/10 rounded-full pl-1.5 pr-2.5 py-1`}>
                    <div className={`w-4 h-4 rounded-full ${a.bg} flex items-center justify-center`}>
                      <span className="text-white text-[8px] font-black">{a.name[0]}</span>
                    </div>
                    <span className="text-white text-[11px] font-semibold">{a.name}</span>
                  </div>
                ))}
              </div>
              <div className="flex-1" />
              {(loading || verdictLoading) && (
                <button
                  onClick={stopCurrent}
                  className="flex items-center gap-1.5 text-[11px] font-semibold text-red-400 hover:text-red-300 transition-colors"
                >
                  <StopCircle size={13} />
                  Detener
                </button>
              )}
            </div>

            {/* ── Debate labels ── */}
            <div className="shrink-0 grid grid-cols-2 border-b border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900">
              <div className="flex items-center gap-2 px-4 py-2 border-r border-slate-100 dark:border-slate-800">
                <div className="w-2 h-2 rounded-full bg-orange-400" />
                <span className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">Claude</span>
              </div>
              <div className="flex items-center justify-end gap-2 px-4 py-2">
                <span className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">ChatGPT</span>
                <div className="w-2 h-2 rounded-full bg-emerald-400" />
              </div>
            </div>

            {/* ── Messages ── */}
            <div className="flex-1 overflow-y-auto px-5 py-5 space-y-4 bg-slate-50/60 dark:bg-slate-900/50">
              {chatMessages.map((msg) => {
                if (msg.type === "web_context") {
                  return <WebContextBubble key={msg.id} content={msg.content} />;
                }
                if (msg.speaker === "user") {
                  return <UserBubble key={msg.id} content={msg.content} />;
                }
                if (msg.speaker === "Llama") {
                  return msg.type === "greeting"
                    ? <LlamaGreetingBubble key={msg.id} content={msg.content} />
                    : <LlamaBubble key={msg.id} content={msg.content} />;
                }
                return (
                  <AiBubble
                    key={msg.id}
                    speaker={msg.speaker}
                    content={msg.content}
                    isGreeting={msg.type === "greeting"}
                  />
                );
              })}

              {/* Typing indicators */}
              {pendingSpeakers.map((speaker) => (
                <AiBubble key={`t-${speaker}`} speaker={speaker} loading />
              ))}
              {verdictLoading && <LlamaBubble loading />}

              <div ref={chatEndRef} />
            </div>

            {/* ── Token strip ── */}
            {tokenTotals.total > 0 && (
              <div className="shrink-0 px-5 py-2 bg-white dark:bg-slate-900 border-t border-slate-100 dark:border-slate-800 flex items-center gap-2.5 flex-wrap">
                <span className="text-[10px] font-medium text-slate-400 uppercase tracking-wide">Tokens</span>
                <span className="text-[11px] font-bold text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded-full">
                  {tokenTotals.total.toLocaleString()}
                </span>
                {Object.entries(tokenTotals.by_model).map(([model, count]) => {
                  const colors: Record<string, string> = {
                    Claude:  "bg-orange-100 text-orange-700",
                    ChatGPT: "bg-emerald-100 text-emerald-700",
                    Llama:   "bg-purple-100 text-purple-700",
                  };
                  return (
                    <span key={model} className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${colors[model] ?? "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400"}`}>
                      {model} {(count as number).toLocaleString()}
                    </span>
                  );
                })}
              </div>
            )}

            {/* ── Llama verdict button ── */}
            {hasDebateContent && !loading && !verdictLoading && !llamaHasSpoken && (
              <div className="shrink-0 px-5 py-3 bg-white dark:bg-slate-900 border-t border-slate-100 dark:border-slate-800">
                <button
                  onClick={requestVerdict}
                  className="w-full flex items-center justify-center gap-2.5 py-3 rounded-xl bg-gradient-to-r from-purple-700 to-violet-600 hover:from-purple-800 hover:to-violet-700 text-white text-sm font-bold transition-all shadow-sm shadow-purple-300/40"
                >
                  <Gavel size={15} />
                  Pedir veredicto a Llama
                </button>
              </div>
            )}

            {/* ── Input ── */}
            <div className="shrink-0 px-5 py-3.5 bg-white dark:bg-slate-900 border-t border-slate-100 dark:border-slate-800">
              <div className="flex gap-2.5">
                <input
                  type="text"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChatMessage(); }
                  }}
                  disabled={loading || verdictLoading}
                  placeholder={
                    loading ? "Claude y ChatGPT están pensando..." :
                    verdictLoading ? "Llama está elaborando el veredicto..." :
                    "Preguntá algo o seguí el debate..."
                  }
                  className="flex-1 px-4 py-2.5 text-sm bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-violet-400/60 focus:border-violet-400 focus:bg-white dark:focus:bg-slate-900 disabled:text-slate-400 dark:placeholder:text-slate-500 disabled:placeholder:text-slate-300 transition-all"
                />
                <button
                  onClick={sendChatMessage}
                  disabled={!chatInput.trim() || loading || verdictLoading}
                  className="w-10 h-10 rounded-xl bg-violet-600 text-white flex items-center justify-center hover:bg-violet-700 active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed transition-all shrink-0 shadow-sm"
                >
                  {loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={15} />}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

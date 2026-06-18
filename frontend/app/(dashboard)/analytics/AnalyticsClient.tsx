"use client";
import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { analyticsApi } from "@/lib/api";
import { Analysis, PLATFORM_LABELS } from "@/types";
import { format, subDays } from "date-fns";
import {
  Brain, Loader2, Sparkles, Clock, ChevronRight,
  BarChart3, AlertTriangle, TrendingUp, Globe, XCircle,
  MessageSquare, Send, StopCircle,
} from "lucide-react";
import { toast } from "sonner";
import { SkeletonText } from "@/components/ui/SkeletonCard";
import { useTranslation } from "react-i18next";

const ALL_PLATFORMS = ["meta", "google_ads", "tiktok", "dv360"];

const SPEAKER_STYLES: Record<string, { bg: string; text: string; border: string; dot: string }> = {
  Claude:  { bg: "bg-orange-50",  text: "text-orange-700",  border: "border-orange-200",  dot: "bg-orange-500"  },
  ChatGPT: { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-200", dot: "bg-emerald-500" },
  Llama:   { bg: "bg-purple-50",  text: "text-purple-700",  border: "border-purple-200",  dot: "bg-purple-500"  },
};

interface ChatMessage {
  id: string;
  speaker: "Claude" | "ChatGPT" | "Llama" | "user";
  content: string;
  role?: string;
  type: "greeting" | "debate" | "user";
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

function MarkdownOutput({ text }: { text: string }) {
  return (
    <div className="prose-analysis">
      <ReactMarkdown>{text}</ReactMarkdown>
    </div>
  );
}

const GREETINGS: ChatMessage[] = [
  { id: "g1", speaker: "Claude",  type: "greeting", role: "greeting", content: "Hola. Tengo cargados los datos de tus campañas para el período seleccionado. ¿Qué querés que analice o debata?" },
  { id: "g2", speaker: "ChatGPT", type: "greeting", role: "greeting", content: "Listo para empezar. Compartí tu pregunta y arrancamos." },
  { id: "g3", speaker: "Llama",   type: "greeting", role: "greeting", content: "Cuando quieras mi veredicto, hacé click en el botón. ¿De qué empezamos?" },
];

export default function AnalyticsPage() {
  const { t } = useTranslation();
  const [platforms, setPlatforms]         = useState<string[]>(ALL_PLATFORMS);
  const [analysisType, setType]           = useState("full_report");
  const [dateFrom, setDateFrom]           = useState("");
  const [dateTo, setDateTo]               = useState("");
  const [result, setResult]               = useState<string>("");
  const [chatMode, setChatMode]           = useState(false);
  const [chatMessages, setChatMessages]   = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput]         = useState("");
  const [tokenTotals, setTokenTotals]     = useState<TokenTotals>({ total: 0, by_model: {} });
  const [errorMsg, setErrorMsg]           = useState<string>("");
  const [loading, setLoading]             = useState(false);
  const [verdictLoading, setVerdictLoading] = useState(false);
  const [reportResult, setReportResult]   = useState<string>("");
  const [reportLoading, setReportLoading] = useState(false);
  const [history, setHistory]             = useState<Analysis[]>([]);
  const [activeAnalysis, setActive]       = useState<number | null>(null);

  const abortRef         = useRef<AbortController | null>(null);
  const chatEndRef       = useRef<HTMLDivElement | null>(null);
  const currentSpeakers  = useRef<Set<string>>(new Set());

  const ANALYSIS_TYPES = [
    { value: "full_report",       label: t("analytics.types.full_report_label"),       desc: t("analytics.types.full_report_desc"),       icon: BarChart3,     color: "text-brand-600 bg-brand-50"     },
    { value: "anomaly_detection", label: t("analytics.types.anomaly_detection_label"), desc: t("analytics.types.anomaly_detection_desc"), icon: AlertTriangle, color: "text-amber-600 bg-amber-50"     },
    { value: "optimization",      label: t("analytics.types.optimization_label"),      desc: t("analytics.types.optimization_desc"),      icon: TrendingUp,    color: "text-emerald-600 bg-emerald-50" },
    { value: "cross_platform",    label: t("analytics.types.cross_platform_label"),    desc: t("analytics.types.cross_platform_desc"),    icon: Globe,         color: "text-purple-600 bg-purple-50"   },
    { value: "debate",            label: t("analytics.types.debate_label"),            desc: t("analytics.types.debate_desc"),            icon: MessageSquare, color: "text-violet-600 bg-violet-50"   },
  ];

  useEffect(() => {
    setDateFrom(format(subDays(new Date(), 30), "yyyy-MM-dd"));
    setDateTo(format(new Date(), "yyyy-MM-dd"));
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

  async function runAnalysis() {
    if (!platforms.length) return toast.error(t("analytics.selectPlatform"));
    if (analysisType === "debate") {
      setChatMode(true);
      setChatMessages(GREETINGS);
      setTokenTotals({ total: 0, by_model: {} });
      setResult("");
      setReportResult("");
      setErrorMsg("");
      setActive(null);
      return;
    }
    setChatMode(false);
    await executeAnalysis();
  }

  function stopCurrent() {
    abortRef.current?.abort();
  }

  async function sendChatMessage() {
    const msg = chatInput.trim();
    if (!msg || loading || verdictLoading) return;
    setChatInput("");

    const userMsg: ChatMessage = { id: `u-${Date.now()}`, speaker: "user", type: "user", content: msg };
    setChatMessages((prev) => [...prev, userMsg]);

    const historyForApi = [...chatMessages, userMsg]
      .filter((m) => m.type !== "greeting")
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
        platforms, dateFrom, dateTo, historyForApi, userMessage, abortRef.current.signal,
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
              currentSpeakers.current.add(parsed.speaker);
              setChatMessages((prev) => [...prev, {
                id:      `m-${Date.now()}-${parsed.speaker}`,
                speaker: parsed.speaker,
                type:    "debate",
                role:    parsed.role,
                content: parsed.content,
              }]);
            } else if (parsed.type === "tokens") {
              accumulateTokens(parsed);
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
        platforms, dateFrom, dateTo, historyForApi, abortRef.current.signal,
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
                id:      `v-${Date.now()}`,
                speaker: "Llama",
                type:    "debate",
                role:    "synthesis",
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

  async function executeAnalysis() {
    setLoading(true);
    setResult("");
    setErrorMsg("");
    setReportResult("");
    setActive(null);

    try {
      const response = await analyticsApi.streamAnalyze(platforms, dateFrom, dateTo, analysisType);
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
          const raw = event.slice(6).trim();
          try {
            const parsed = JSON.parse(raw);
            if (parsed.error) { setErrorMsg(parsed.error); toast.error(t("analytics.errorToast")); return; }
            if (parsed.text)  { setResult((prev) => prev + parsed.text); }
            if (parsed.done && parsed.id) {
              setActive(parsed.id);
              toast.success(t("analytics.successToast"));
              analyticsApi.getHistory().then(({ data }) => setHistory(data)).catch(() => {});
            }
          } catch { /* partial JSON */ }
        }
      }
    } catch (err: any) {
      setErrorMsg(err?.message ?? t("analytics.defaultError"));
      toast.error(t("analytics.errorToast"));
    } finally {
      setLoading(false);
    }
  }

  async function generateReport() {
    setReportLoading(true);
    setReportResult("");
    setErrorMsg("");

    try {
      const response = await analyticsApi.streamAnalyze(platforms, dateFrom, dateTo, "full_report");
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
          const raw = event.slice(6).trim();
          try {
            const parsed = JSON.parse(raw);
            if (parsed.error) { setErrorMsg(parsed.error); toast.error(t("analytics.errorToast")); return; }
            if (parsed.text)  { setReportResult((prev) => prev + parsed.text); }
            if (parsed.done && parsed.id) {
              toast.success(t("analytics.successToast"));
              analyticsApi.getHistory().then(({ data }) => setHistory(data)).catch(() => {});
            }
          } catch { /* partial JSON */ }
        }
      }
    } catch (err: any) {
      setErrorMsg(err?.message ?? t("analytics.defaultError"));
      toast.error(t("analytics.errorToast"));
    } finally {
      setReportLoading(false);
    }
  }

  async function loadFromHistory(id: number) {
    setActive(id);
    setChatMessages([]);
    setResult("");
    setReportResult("");
    setTokenTotals({ total: 0, by_model: {} });
    try {
      const { data } = await analyticsApi.getAnalysis(id);
      const parsed = tryParseDebate(data.result);
      if (parsed) {
        setChatMode(true);
        setType("debate");
        setChatMessages(parsed);
      } else {
        setChatMode(false);
        setResult(data.result);
      }
    } catch { toast.error(t("analytics.loadError")); }
  }

  const selectedType     = ANALYSIS_TYPES.find((tp) => tp.value === analysisType);
  const hasTextContent   = result.length > 0;
  const hasReportContent = reportResult.length > 0;
  const hasDebateContent = chatMessages.some((m) => m.type === "debate");
  const llamaHasSpoken   = chatMessages.some((m) => m.speaker === "Llama" && m.type === "debate");
  const pendingSpeakers  = loading
    ? ["Claude", "ChatGPT"].filter((s) => !currentSpeakers.current.has(s))
    : [];

  return (
    <div className="animate-fade-in space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{t("analytics.title")}</h1>
        <p className="text-sm text-slate-500 mt-0.5">{t("analytics.subtitle")}</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[340px_1fr] gap-5 items-start">
        {/* ── Config panel ── */}
        <div className="space-y-4">
          <div className="card p-5">
            <p className="section-title mb-3">{t("analytics.analysisType")}</p>
            <div className="space-y-2">
              {ANALYSIS_TYPES.map(({ value, label, desc, icon: Icon, color }) => (
                <button key={value} onClick={() => setType(value)}
                  className={`w-full flex items-center gap-3 p-3 rounded-xl border-2 text-left transition-all duration-150 ${
                    analysisType === value ? "border-brand-500 bg-brand-50/50" : "border-transparent bg-slate-50 hover:bg-slate-100"
                  }`}>
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${color}`}>
                    <Icon size={15} />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-slate-800">{label}</p>
                    <p className="text-xs text-slate-500">{desc}</p>
                  </div>
                  {value === "debate" && (
                    <span className="ml-auto shrink-0 text-[10px] font-bold uppercase tracking-wide bg-violet-100 text-violet-600 px-1.5 py-0.5 rounded-full">NEW</span>
                  )}
                </button>
              ))}
            </div>
          </div>

          <div className="card p-5">
            <p className="section-title mb-3">{t("analytics.platformsLabel")}</p>
            <div className="space-y-2">
              {ALL_PLATFORMS.map((p) => (
                <label key={p} className="flex items-center gap-3 cursor-pointer group">
                  <div className={`w-4 h-4 rounded border-2 flex items-center justify-center transition-all ${platforms.includes(p) ? "bg-brand-600 border-brand-600" : "border-slate-300 group-hover:border-brand-400"}`}
                    onClick={() => setPlatforms((prev) => prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p])}>
                    {platforms.includes(p) && <svg viewBox="0 0 10 8" className="w-2.5 h-2.5" fill="none"><path d="M1 4l2.5 2.5L9 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                  </div>
                  <span className="text-sm text-slate-700">{PLATFORM_LABELS[p]}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="card p-5">
            <p className="section-title mb-3">{t("analytics.period")}</p>
            <div className="space-y-2.5">
              <div>
                <label className="text-xs text-slate-500 mb-1 block">{t("common.from")}</label>
                <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="input text-sm" />
              </div>
              <div>
                <label className="text-xs text-slate-500 mb-1 block">{t("common.to")}</label>
                <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="input text-sm" />
              </div>
            </div>
          </div>

          <button onClick={runAnalysis} disabled={loading || !platforms.length}
            className={`btn-primary w-full py-3 ${analysisType === "debate" ? "bg-violet-600 hover:bg-violet-700 focus:ring-violet-500" : ""}`}>
            <Sparkles size={16} />
            {analysisType === "debate" ? "Abrir La Triada" : t("analytics.runAnalysis")}
          </button>

          {analysisType === "debate" && (
            <p className="text-xs text-slate-400 text-center -mt-1">
              Claude y ChatGPT debaten · Llama opina cuando vos lo pedís
            </p>
          )}
        </div>

        {/* ── Result panel ── */}
        <div className="space-y-4">
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

          {/* ── Chat (La Triada) ── */}
          {chatMode ? (
            <div className="card flex flex-col" style={{ height: "calc(100vh - 200px)", minHeight: "640px" }}>

              {/* Header */}
              <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-slate-100 shrink-0">
                <div className="flex -space-x-1.5">
                  {[{ dot: "bg-orange-500", l: "C" }, { dot: "bg-emerald-500", l: "G" }, { dot: "bg-purple-500", l: "L" }].map((a) => (
                    <div key={a.l} className={`w-6 h-6 rounded-full ${a.dot} border-2 border-white flex items-center justify-center`}>
                      <span className="text-white text-[9px] font-bold">{a.l}</span>
                    </div>
                  ))}
                </div>
                <div className="flex-1">
                  <p className="text-sm font-bold text-slate-800">La Triada</p>
                  <p className="text-[10px] text-slate-400">Claude · ChatGPT · Llama</p>
                </div>

                {(loading || verdictLoading) && (
                  <button onClick={stopCurrent} className="flex items-center gap-1.5 text-xs text-red-500 hover:text-red-700 font-medium ml-2 shrink-0">
                    <StopCircle size={14} /> Detener
                  </button>
                )}
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {chatMessages.map((msg) => {
                  if (msg.speaker === "user") {
                    return (
                      <div key={msg.id} className="flex justify-end">
                        <div className="bg-violet-600 text-white rounded-2xl rounded-br-sm px-4 py-2.5 text-sm max-w-[80%] leading-relaxed">
                          {msg.content}
                        </div>
                      </div>
                    );
                  }
                  const style = SPEAKER_STYLES[msg.speaker] ?? SPEAKER_STYLES.Claude;
                  const roleLabels: Record<string, string> = { debate: "debate", synthesis: "veredicto", greeting: "" };
                  const roleLabel = msg.role && msg.type === "debate" ? (roleLabels[msg.role] ?? msg.role) : "";
                  return (
                    <div key={msg.id} className={`rounded-xl border p-3.5 ${style.bg} ${style.border} animate-fade-in`}>
                      <div className="flex items-center gap-2 mb-2">
                        <div className={`w-5 h-5 rounded-full ${style.dot} flex items-center justify-center shrink-0`}>
                          <span className="text-white text-[9px] font-bold">{msg.speaker[0]}</span>
                        </div>
                        <span className={`text-xs font-bold ${style.text}`}>{msg.speaker}</span>
                        {roleLabel && (
                          <>
                            <span className="text-[10px] text-slate-300">·</span>
                            <span className="text-[10px] text-slate-400">{roleLabel}</span>
                          </>
                        )}
                      </div>
                      <div className={`text-sm leading-relaxed ${style.text.replace("700", "800")}`}>
                        <MarkdownOutput text={msg.content} />
                      </div>
                    </div>
                  );
                })}

                {/* Thinking placeholders */}
                {pendingSpeakers.map((speaker) => {
                  const style = SPEAKER_STYLES[speaker];
                  return (
                    <div key={`t-${speaker}`} className={`rounded-xl border p-3.5 ${style.bg} ${style.border} animate-pulse`}>
                      <div className="flex items-center gap-2 mb-2">
                        <div className={`w-5 h-5 rounded-full ${style.dot} flex items-center justify-center shrink-0`}>
                          <span className="text-white text-[9px] font-bold">{speaker[0]}</span>
                        </div>
                        <span className={`text-xs font-bold ${style.text}`}>{speaker}</span>
                        <span className="text-[10px] text-slate-400">· analizando...</span>
                        <div className="flex gap-1 ml-1">
                          {[0, 150, 300].map((d) => (
                            <div key={d} className={`w-1 h-1 rounded-full ${style.dot} animate-bounce`} style={{ animationDelay: `${d}ms` }} />
                          ))}
                        </div>
                      </div>
                      <SkeletonText lines={3} />
                    </div>
                  );
                })}

                {/* Llama thinking */}
                {verdictLoading && (
                  <div className={`rounded-xl border p-3.5 ${SPEAKER_STYLES.Llama.bg} ${SPEAKER_STYLES.Llama.border} animate-pulse`}>
                    <div className="flex items-center gap-2 mb-2">
                      <div className={`w-5 h-5 rounded-full ${SPEAKER_STYLES.Llama.dot} flex items-center justify-center shrink-0`}>
                        <span className="text-white text-[9px] font-bold">L</span>
                      </div>
                      <span className={`text-xs font-bold ${SPEAKER_STYLES.Llama.text}`}>Llama</span>
                      <span className="text-[10px] text-slate-400">· elaborando veredicto...</span>
                      <div className="flex gap-1 ml-1">
                        {[0, 150, 300].map((d) => (
                          <div key={d} className={`w-1 h-1 rounded-full ${SPEAKER_STYLES.Llama.dot} animate-bounce`} style={{ animationDelay: `${d}ms` }} />
                        ))}
                      </div>
                    </div>
                    <SkeletonText lines={4} />
                  </div>
                )}

                <div ref={chatEndRef} />
              </div>

              {/* Token usage strip — shown after first completed turn */}
              {tokenTotals.total > 0 && (
                <div className="px-4 py-2.5 border-t border-slate-100 bg-slate-50/60 shrink-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs text-slate-500">Tokens consumidos:</span>
                    <span className="text-xs font-bold text-slate-700 bg-white border border-slate-200 px-2.5 py-0.5 rounded-full">
                      {tokenTotals.total.toLocaleString()} total
                    </span>
                    {Object.entries(tokenTotals.by_model).map(([model, count]) => {
                      const s: Record<string, string> = {
                        Claude:  "bg-orange-50 text-orange-700 border-orange-200",
                        ChatGPT: "bg-emerald-50 text-emerald-700 border-emerald-200",
                        Llama:   "bg-purple-50 text-purple-700 border-purple-200",
                      };
                      return (
                        <span key={model} className={`text-xs font-semibold px-2.5 py-0.5 rounded-full border ${s[model] ?? "bg-slate-100 text-slate-600 border-slate-200"}`}>
                          {model}: {(count as number).toLocaleString()}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Llama verdict button — only when there are AI messages and Llama hasn't spoken */}
              {hasDebateContent && !loading && !verdictLoading && !llamaHasSpoken && (
                <div className="px-4 py-2.5 border-t border-slate-50 shrink-0">
                  <button
                    onClick={requestVerdict}
                    className="w-full flex items-center justify-center gap-2 py-2 rounded-xl border border-purple-200 text-purple-600 text-xs font-semibold hover:bg-purple-50 transition-colors"
                  >
                    <div className="w-4 h-4 rounded-full bg-purple-500 flex items-center justify-center">
                      <span className="text-white text-[8px] font-bold">L</span>
                    </div>
                    Pedir veredicto a Llama
                  </button>
                </div>
              )}

              {/* Post-verdict: generate full report */}
              {llamaHasSpoken && !loading && !verdictLoading && !hasReportContent && !reportLoading && (
                <div className="px-4 py-2.5 border-t border-slate-50 shrink-0">
                  <button
                    onClick={generateReport}
                    className="w-full flex items-center justify-center gap-2 py-2 rounded-xl border border-slate-200 text-slate-600 text-xs font-semibold hover:bg-slate-50 transition-colors"
                  >
                    <BarChart3 size={13} />
                    Generar informe completo
                  </button>
                </div>
              )}

              {/* Input */}
              <div className="px-4 py-3 border-t border-slate-100 shrink-0">
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChatMessage(); } }}
                    disabled={loading || verdictLoading}
                    placeholder={loading ? "Claude y ChatGPT están pensando..." : verdictLoading ? "Llama está elaborando el veredicto..." : "Escribí tu pregunta o seguí el debate..."}
                    className="flex-1 px-4 py-2.5 text-sm border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-violet-400 disabled:bg-slate-50 disabled:text-slate-400 disabled:placeholder:text-slate-300"
                  />
                  <button
                    onClick={sendChatMessage}
                    disabled={!chatInput.trim() || loading || verdictLoading}
                    className="w-10 h-10 rounded-xl bg-violet-600 text-white flex items-center justify-center hover:bg-violet-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
                  >
                    {loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={15} />}
                  </button>
                </div>
              </div>
            </div>
          ) : hasTextContent ? (
            <div className="card p-6">
              <div className="flex items-center gap-2 mb-5 pb-4 border-b border-slate-50">
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${selectedType?.color ?? "bg-slate-100 text-slate-500"}`}>
                  {selectedType && <selectedType.icon size={16} />}
                </div>
                <div>
                  <p className="font-semibold text-slate-800 text-sm">{selectedType?.label}</p>
                  <p className="text-xs text-slate-400">{t("analytics.generatedBy", { date: format(new Date(), "dd/MM/yyyy HH:mm") })}</p>
                </div>
              </div>
              <MarkdownOutput text={result} />
            </div>
          ) : loading ? (
            <div className="card p-6 min-h-[400px]">
              <div className="space-y-6">
                <div className="flex items-center gap-2 text-brand-600">
                  <Brain size={20} className="animate-pulse-slow" />
                  <span className="text-sm font-semibold">{t("analytics.analyzing")}</span>
                </div>
                {[5, 4, 6, 3, 5].map((lines, i) => (
                  <div key={i}>
                    <div className="skeleton h-3 w-32 rounded mb-3" />
                    <SkeletonText lines={lines} />
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="card p-6 min-h-[400px] flex flex-col items-center justify-center text-center">
              <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
                <Brain size={28} className="text-slate-300" />
              </div>
              <p className="text-sm font-medium text-slate-500">{t("analytics.emptyTitle")}</p>
              <p className="text-xs text-slate-400 mt-1">{t("analytics.emptySub")}</p>
            </div>
          )}

          {reportLoading && (
            <div className="card p-6">
              <div className="flex items-center gap-2 text-brand-600 mb-6">
                <Brain size={20} className="animate-pulse-slow" />
                <span className="text-sm font-semibold">{t("analytics.analyzing")}</span>
              </div>
              {[5, 4, 6, 3, 5].map((lines, i) => (
                <div key={i} className="mb-5">
                  <div className="skeleton h-3 w-32 rounded mb-3" />
                  <SkeletonText lines={lines} />
                </div>
              ))}
            </div>
          )}

          {hasReportContent && (
            <div className="card p-6">
              <div className="flex items-center gap-2 mb-5 pb-4 border-b border-slate-50">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center text-brand-600 bg-brand-50">
                  <BarChart3 size={16} />
                </div>
                <div>
                  <p className="font-semibold text-slate-800 text-sm">{t("analytics.types.full_report_label")}</p>
                  <p className="text-xs text-slate-400">{t("analytics.generatedBy", { date: format(new Date(), "dd/MM/yyyy HH:mm") })}</p>
                </div>
              </div>
              <MarkdownOutput text={reportResult} />
            </div>
          )}

          {history.length > 0 && (
            <div className="card overflow-hidden">
              <div className="px-5 py-3.5 border-b border-slate-50 flex items-center gap-2">
                <Clock size={14} className="text-slate-400" />
                <p className="text-sm font-semibold text-slate-700">{t("analytics.recentAnalyses")}</p>
              </div>
              <div className="divide-y divide-slate-50">
                {history.slice(0, 6).map((h) => {
                  const tp = ANALYSIS_TYPES.find((x) => x.value === h.analysis_type);
                  return (
                    <button key={h.id} onClick={() => loadFromHistory(h.id)}
                      className={`w-full flex items-center gap-3 px-5 py-3 hover:bg-slate-50 transition-colors text-left ${activeAnalysis === h.id ? "bg-brand-50/50" : ""}`}>
                      {tp && (
                        <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${tp.color}`}>
                          <tp.icon size={13} />
                        </div>
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-semibold text-slate-700">{tp?.label ?? h.analysis_type}</p>
                        <p className="text-[11px] text-slate-400">{format(new Date(h.created_at), "dd/MM HH:mm")}</p>
                      </div>
                      <ChevronRight size={14} className="text-slate-300 shrink-0" />
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

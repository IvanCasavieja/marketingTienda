"use client";
import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { analyticsApi } from "@/lib/api";
import { Analysis, PLATFORM_LABELS } from "@/types";
import { format, subDays } from "date-fns";
import {
  Brain, Loader2, Sparkles, Clock, ChevronRight,
  BarChart3, AlertTriangle, TrendingUp, Globe, XCircle, MessageSquare,
} from "lucide-react";
import { toast } from "sonner";
import { SkeletonText } from "@/components/ui/SkeletonCard";
import { useTranslation } from "react-i18next";

const ALL_PLATFORMS = ["meta", "google_ads", "tiktok", "dv360"];

const SPEAKER_STYLES: Record<string, { bg: string; text: string; border: string; dot: string; ring: string }> = {
  Claude:  { bg: "bg-orange-50",  text: "text-orange-700",  border: "border-orange-200",  dot: "bg-orange-500",  ring: "ring-orange-300"  },
  ChatGPT: { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-200", dot: "bg-emerald-500", ring: "ring-emerald-300" },
  Llama:   { bg: "bg-purple-50",  text: "text-purple-700",  border: "border-purple-200",  dot: "bg-purple-500",  ring: "ring-purple-300"  },
};

interface DebateMessage {
  speaker: string;
  round: number;
  role: string;
  content: string;
}

interface DebateTokens {
  total: number;
  by_model: Record<string, number>;
}

function tryParseDebate(result: string): DebateMessage[] | null {
  try {
    const parsed = JSON.parse(result);
    if (parsed.debate && Array.isArray(parsed.debate)) return parsed.debate;
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

function ThinkingCard({ speaker }: { speaker: string }) {
  const style = SPEAKER_STYLES[speaker] ?? SPEAKER_STYLES.Claude;
  return (
    <div className={`rounded-xl border p-4 ${style.bg} ${style.border} animate-pulse`}>
      <div className="flex items-center gap-2 mb-3">
        <div className={`w-6 h-6 rounded-full ${style.dot} ring-2 ${style.ring} ring-offset-1 flex items-center justify-center shrink-0`}>
          <span className="text-white text-[10px] font-bold">{speaker[0]}</span>
        </div>
        <span className={`text-sm font-bold ${style.text}`}>{speaker}</span>
        <span className="text-xs text-slate-400">· pensando...</span>
        <div className="flex gap-1 ml-1">
          {[0, 150, 300].map((d) => (
            <div key={d} className={`w-1.5 h-1.5 rounded-full ${style.dot} animate-bounce`} style={{ animationDelay: `${d}ms` }} />
          ))}
        </div>
      </div>
      <SkeletonText lines={3} />
    </div>
  );
}

function DebateOutput({
  messages,
  loading,
  activeRound,
}: {
  messages: DebateMessage[];
  loading: boolean;
  activeRound: number | null;
}) {
  const { t } = useTranslation();

  const ROUND_TITLES: Record<number, string> = {
    1: t("analytics.debate.round1Title"),
    2: t("analytics.debate.round2Title"),
    3: t("analytics.debate.round3Title"),
  };
  const ROLE_LABELS: Record<string, string> = {
    analysis:  t("analytics.debate.roleAnalysis"),
    rebuttal:  t("analytics.debate.roleRebuttal"),
    synthesis: t("analytics.debate.roleSynthesis"),
  };

  const ROUND_SPEAKERS: Record<number, string[]> = {
    1: ["Claude", "ChatGPT"],
    2: ["Claude", "ChatGPT"],
    3: ["Llama"],
  };

  const rounds = [1, 2, 3];
  const answered = new Set(messages.map((m) => `${m.round}:${m.speaker}`));

  return (
    <div className="space-y-8">
      {rounds.map((round) => {
        const roundMessages = messages.filter((m) => m.round === round);
        const isCurrentRound = loading && activeRound === round;
        const pendingSpeakers = isCurrentRound
          ? (ROUND_SPEAKERS[round] ?? []).filter((s) => !answered.has(`${round}:${s}`))
          : [];

        if (!roundMessages.length && !isCurrentRound) return null;

        return (
          <div key={round}>
            <div className="flex items-center gap-3 mb-4">
              <div className="h-px flex-1 bg-slate-100" />
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider px-2 flex items-center gap-1.5">
                {ROUND_TITLES[round]}
                {isCurrentRound && <Loader2 size={10} className="animate-spin text-violet-400" />}
              </span>
              <div className="h-px flex-1 bg-slate-100" />
            </div>

            <div className="space-y-4">
              {roundMessages.map((msg, idx) => {
                const style = SPEAKER_STYLES[msg.speaker] ?? SPEAKER_STYLES.Claude;
                return (
                  <div key={idx} className={`rounded-xl border p-4 ${style.bg} ${style.border} animate-fade-in`}>
                    <div className="flex items-center gap-2 mb-3">
                      <div className={`w-6 h-6 rounded-full ${style.dot} flex items-center justify-center shrink-0`}>
                        <span className="text-white text-[10px] font-bold">{msg.speaker[0]}</span>
                      </div>
                      <span className={`text-sm font-bold ${style.text}`}>{msg.speaker}</span>
                      <span className="text-xs text-slate-400">·</span>
                      <span className="text-xs text-slate-400">{ROLE_LABELS[msg.role] ?? msg.role}</span>
                    </div>
                    <div className={`text-sm leading-relaxed ${style.text.replace("700", "800")}`}>
                      <MarkdownOutput text={msg.content} />
                    </div>
                  </div>
                );
              })}

              {pendingSpeakers.map((speaker) => (
                <ThinkingCard key={speaker} speaker={speaker} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function AnalyticsPage() {
  const { t } = useTranslation();
  const [platforms, setPlatforms]             = useState<string[]>(ALL_PLATFORMS);
  const [analysisType, setType]               = useState("full_report");
  const [dateFrom, setDateFrom]               = useState("");
  const [dateTo, setDateTo]                   = useState("");
  const [result, setResult]                   = useState<string>("");
  const [debateMessages, setDebateMessages]   = useState<DebateMessage[]>([]);
  const [debateTokens, setDebateTokens]       = useState<DebateTokens | null>(null);
  const [activeRound, setActiveRound]         = useState<number | null>(null);
  const [errorMsg, setErrorMsg]               = useState<string>("");
  const [loading, setLoading]                 = useState(false);
  const [reportResult, setReportResult]       = useState<string>("");
  const [reportLoading, setReportLoading]     = useState(false);
  const [history, setHistory]                 = useState<Analysis[]>([]);
  const [activeAnalysis, setActive]           = useState<number | null>(null);
  const [showDebateModal, setShowDebateModal] = useState(false);
  const [debatePrompt, setDebatePrompt]       = useState("");

  const ANALYSIS_TYPES = [
    {
      value: "full_report",
      label: t("analytics.types.full_report_label"),
      desc:  t("analytics.types.full_report_desc"),
      icon: BarChart3,
      color: "text-brand-600 bg-brand-50",
    },
    {
      value: "anomaly_detection",
      label: t("analytics.types.anomaly_detection_label"),
      desc:  t("analytics.types.anomaly_detection_desc"),
      icon: AlertTriangle,
      color: "text-amber-600 bg-amber-50",
    },
    {
      value: "optimization",
      label: t("analytics.types.optimization_label"),
      desc:  t("analytics.types.optimization_desc"),
      icon: TrendingUp,
      color: "text-emerald-600 bg-emerald-50",
    },
    {
      value: "cross_platform",
      label: t("analytics.types.cross_platform_label"),
      desc:  t("analytics.types.cross_platform_desc"),
      icon: Globe,
      color: "text-purple-600 bg-purple-50",
    },
    {
      value: "debate",
      label: t("analytics.types.debate_label"),
      desc:  t("analytics.types.debate_desc"),
      icon: MessageSquare,
      color: "text-violet-600 bg-violet-50",
    },
  ];

  useEffect(() => {
    setDateFrom(format(subDays(new Date(), 30), "yyyy-MM-dd"));
    setDateTo(format(new Date(), "yyyy-MM-dd"));
    analyticsApi.getHistory().then(({ data }) => setHistory(data)).catch(() => {});
  }, []);

  async function runAnalysis() {
    if (!platforms.length) return toast.error(t("analytics.selectPlatform"));
    if (analysisType === "debate") {
      setDebatePrompt("");
      setShowDebateModal(true);
      return;
    }
    await executeAnalysis();
  }

  async function startDebate(prompt: string) {
    setShowDebateModal(false);
    setLoading(true);
    setResult("");
    setDebateMessages([]);
    setDebateTokens(null);
    setActiveRound(null);
    setErrorMsg("");
    setReportResult("");
    setActive(null);

    try {
      const response = await analyticsApi.streamDebate(platforms, dateFrom, dateTo, prompt);
      if (!response.ok || !response.body) throw new Error(t("analytics.defaultError"));

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

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
            if (parsed.type === "round_start") {
              setActiveRound(parsed.round);
            } else if (parsed.type === "message") {
              setDebateMessages((prev) => [...prev, {
                speaker: parsed.speaker,
                round:   parsed.round,
                role:    parsed.role,
                content: parsed.content,
              }]);
            } else if (parsed.type === "tokens") {
              setDebateTokens({ total: parsed.total, by_model: parsed.by_model });
            } else if (parsed.type === "done") {
              setActive(parsed.id);
              setActiveRound(null);
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
      setErrorMsg(err?.message ?? t("analytics.defaultError"));
      toast.error(t("analytics.errorToast"));
    } finally {
      setLoading(false);
      setActiveRound(null);
    }
  }

  async function executeAnalysis() {
    setLoading(true);
    setResult("");
    setDebateMessages([]);
    setDebateTokens(null);
    setActiveRound(null);
    setErrorMsg("");
    setReportResult("");
    setActive(null);

    try {
      const response = await analyticsApi.streamAnalyze(platforms, dateFrom, dateTo, analysisType);
      if (!response.ok || !response.body) throw new Error(t("analytics.defaultError"));

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

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
            if (parsed.text)  { setResult(prev => prev + parsed.text); }
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

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

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
            if (parsed.text)  { setReportResult(prev => prev + parsed.text); }
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
    setDebateMessages([]);
    setDebateTokens(null);
    setResult("");
    setReportResult("");
    try {
      const { data } = await analyticsApi.getAnalysis(id);
      const parsed = tryParseDebate(data.result);
      if (parsed) {
        setDebateMessages(parsed);
        setType("debate");
      } else {
        setResult(data.result);
      }
    } catch { toast.error(t("analytics.loadError")); }
  }

  const selectedType = ANALYSIS_TYPES.find((tp) => tp.value === analysisType);
  const isDebate = analysisType === "debate" || debateMessages.length > 0;
  const hasDebateContent = debateMessages.length > 0;
  const hasTextContent = result.length > 0;
  const hasReportContent = reportResult.length > 0;

  return (
    <>
    {/* ── Debate prompt modal ── */}
    {showDebateModal && (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setShowDebateModal(false)} />
        <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6 animate-fade-in">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-xl bg-violet-100 flex items-center justify-center shrink-0">
              <MessageSquare size={18} className="text-violet-600" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">¿Qué querés analizar?</h2>
              <p className="text-xs text-slate-500">Escribí una pregunta o dejalo vacío para un análisis libre</p>
            </div>
          </div>

          <textarea
            autoFocus
            value={debatePrompt}
            onChange={(e) => setDebatePrompt(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) startDebate(debatePrompt); }}
            placeholder="Ej: ¿Cuál plataforma tiene mejor ROAS y cómo podemos escalarla?"
            className="w-full h-28 px-4 py-3 text-sm border border-slate-200 rounded-xl resize-none focus:outline-none focus:ring-2 focus:ring-violet-400 placeholder:text-slate-300"
          />
          <p className="text-[11px] text-slate-400 mt-1.5 mb-4">
            Claude y ChatGPT debaten con posiciones opuestas · Llama da un veredicto final
          </p>

          <div className="flex gap-2">
            <button
              onClick={() => setShowDebateModal(false)}
              className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 text-sm text-slate-600 hover:bg-slate-50 transition-colors"
            >
              Cancelar
            </button>
            <button
              onClick={() => startDebate("")}
              className="px-4 py-2.5 rounded-xl border border-violet-200 text-sm text-violet-600 hover:bg-violet-50 transition-colors"
            >
              Debate libre
            </button>
            <button
              onClick={() => startDebate(debatePrompt)}
              className="flex-1 px-4 py-2.5 rounded-xl bg-violet-600 text-white text-sm font-semibold hover:bg-violet-700 transition-colors"
            >
              Iniciar debate
            </button>
          </div>
        </div>
      </div>
    )}

    <div className="animate-fade-in space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{t("analytics.title")}</h1>
        <p className="text-sm text-slate-500 mt-0.5">{t("analytics.subtitle")}</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[340px_1fr] gap-5">
        {/* ── Config panel ── */}
        <div className="space-y-4">
          <div className="card p-5">
            <p className="section-title mb-3">{t("analytics.analysisType")}</p>
            <div className="space-y-2">
              {ANALYSIS_TYPES.map(({ value, label, desc, icon: Icon, color }) => (
                <button key={value} onClick={() => setType(value)}
                  className={`w-full flex items-center gap-3 p-3 rounded-xl border-2 text-left transition-all duration-150 ${
                    analysisType === value
                      ? "border-brand-500 bg-brand-50/50"
                      : "border-transparent bg-slate-50 hover:bg-slate-100"
                  }`}>
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${color}`}>
                    <Icon size={15} />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-slate-800">{label}</p>
                    <p className="text-xs text-slate-500">{desc}</p>
                  </div>
                  {value === "debate" && (
                    <span className="ml-auto shrink-0 text-[10px] font-bold uppercase tracking-wide bg-violet-100 text-violet-600 px-1.5 py-0.5 rounded-full">
                      NEW
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Platforms */}
          <div className="card p-5">
            <p className="section-title mb-3">{t("analytics.platformsLabel")}</p>
            <div className="space-y-2">
              {ALL_PLATFORMS.map((p) => (
                <label key={p} className="flex items-center gap-3 cursor-pointer group">
                  <div className={`w-4 h-4 rounded border-2 flex items-center justify-center transition-all ${
                    platforms.includes(p) ? "bg-brand-600 border-brand-600" : "border-slate-300 group-hover:border-brand-400"
                  }`}
                    onClick={() => setPlatforms((prev) => prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p])}>
                    {platforms.includes(p) && <svg viewBox="0 0 10 8" className="w-2.5 h-2.5" fill="none"><path d="M1 4l2.5 2.5L9 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                  </div>
                  <span className="text-sm text-slate-700">{PLATFORM_LABELS[p]}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Date range */}
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
            {loading
              ? <><Loader2 size={16} className="animate-spin" /> {isDebate ? t("analytics.debate.analyzing") : t("analytics.analyzing")}</>
              : <><Sparkles size={16} /> {t("analytics.runAnalysis")}</>}
          </button>

          {analysisType === "debate" && !loading && (
            <p className="text-xs text-slate-400 text-center -mt-1">
              {t("analytics.debate.disclaimer")}
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
              <button onClick={() => setErrorMsg("")} className="text-red-400 hover:text-red-600">
                <XCircle size={14} />
              </button>
            </div>
          )}

          {/* Main result card */}
          <div className="card p-6 min-h-[400px]">
            {(isDebate && (hasDebateContent || loading)) ? (
              <>
                <div className="flex items-center gap-2 mb-5 pb-4 border-b border-slate-50">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center text-violet-600 bg-violet-50">
                    <MessageSquare size={16} />
                  </div>
                  <div className="flex-1">
                    <p className="font-semibold text-slate-800 text-sm">{t("analytics.types.debate_label")}</p>
                    <p className="text-xs text-slate-400">{t("analytics.debate.generatedBy")}</p>
                  </div>
                  {loading && (
                    <div className="flex items-center gap-1.5 text-xs text-violet-500 font-medium">
                      <Loader2 size={12} className="animate-spin" />
                      {t("analytics.debate.analyzing")}
                    </div>
                  )}
                  {hasDebateContent && !loading && (
                    <div className="flex gap-1">
                      {["C", "G", "L"].map((initial, i) => (
                        <div key={i} className={`w-6 h-6 rounded-full flex items-center justify-center text-white text-[10px] font-bold ${["bg-orange-500", "bg-emerald-500", "bg-purple-500"][i]}`}>
                          {initial}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <DebateOutput messages={debateMessages} loading={loading} activeRound={activeRound} />

                {/* Token consumption badge */}
                {hasDebateContent && !loading && debateTokens && (
                  <div className="flex items-center gap-2 pt-5 mt-5 border-t border-slate-50 flex-wrap">
                    <span className="text-xs font-semibold text-slate-400">Tokens consumidos:</span>
                    <span className="text-xs font-bold text-slate-600 bg-slate-100 px-2.5 py-1 rounded-full">
                      {debateTokens.total.toLocaleString()} total
                    </span>
                    {Object.entries(debateTokens.by_model).map(([model, tokens]) => {
                      const colorMap: Record<string, string> = {
                        Claude: "bg-orange-100 text-orange-700",
                        ChatGPT: "bg-emerald-100 text-emerald-700",
                        Llama: "bg-purple-100 text-purple-700",
                      };
                      return (
                        <span key={model} className={`text-xs px-2.5 py-1 rounded-full font-medium ${colorMap[model] ?? "bg-slate-100 text-slate-600"}`}>
                          {model}: {(tokens as number).toLocaleString()}
                        </span>
                      );
                    })}
                  </div>
                )}
              </>
            ) : hasTextContent ? (
              <>
                <div className="flex items-center gap-2 mb-5 pb-4 border-b border-slate-50">
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${selectedType?.color ?? "bg-slate-100 text-slate-500"}`}>
                    {selectedType && <selectedType.icon size={16} />}
                  </div>
                  <div>
                    <p className="font-semibold text-slate-800 text-sm">{selectedType?.label}</p>
                    <p className="text-xs text-slate-400">
                      {t("analytics.generatedBy", { date: format(new Date(), "dd/MM/yyyy HH:mm") })}
                    </p>
                  </div>
                </div>
                <MarkdownOutput text={result} />
              </>
            ) : loading && !isDebate ? (
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
            ) : (
              <div className="flex flex-col items-center justify-center h-64 text-center">
                <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
                  <Brain size={28} className="text-slate-300" />
                </div>
                <p className="text-sm font-medium text-slate-500">{t("analytics.emptyTitle")}</p>
                <p className="text-xs text-slate-400 mt-1">{t("analytics.emptySub")}</p>
              </div>
            )}
          </div>

          {/* Post-debate: generate full report prompt */}
          {hasDebateContent && !loading && !hasReportContent && !reportLoading && (
            <div className="card p-4 border border-dashed border-violet-200 bg-violet-50/20">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-violet-100 flex items-center justify-center shrink-0">
                  <BarChart3 size={16} className="text-violet-600" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-semibold text-slate-800">¿Querés un informe visual completo?</p>
                  <p className="text-xs text-slate-500">Claude genera un reporte ejecutivo detallado con todos los datos del período</p>
                </div>
                <button
                  onClick={generateReport}
                  className="px-4 py-2 rounded-xl bg-violet-600 text-white text-sm font-semibold hover:bg-violet-700 transition-colors flex items-center gap-1.5 shrink-0"
                >
                  <Sparkles size={14} />
                  Generar informe
                </button>
              </div>
            </div>
          )}

          {/* Report loading skeleton */}
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

          {/* Report output — shown below debate */}
          {hasReportContent && (
            <div className="card p-6">
              <div className="flex items-center gap-2 mb-5 pb-4 border-b border-slate-50">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center text-brand-600 bg-brand-50">
                  <BarChart3 size={16} />
                </div>
                <div>
                  <p className="font-semibold text-slate-800 text-sm">{t("analytics.types.full_report_label")}</p>
                  <p className="text-xs text-slate-400">
                    {t("analytics.generatedBy", { date: format(new Date(), "dd/MM/yyyy HH:mm") })}
                  </p>
                </div>
              </div>
              <MarkdownOutput text={reportResult} />
            </div>
          )}

          {/* History */}
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
    </>
  );
}

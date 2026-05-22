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

const SPEAKER_STYLES: Record<string, { bg: string; text: string; border: string; dot: string }> = {
  Claude:  { bg: "bg-orange-50",  text: "text-orange-700",  border: "border-orange-200",  dot: "bg-orange-500"  },
  ChatGPT: { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-200", dot: "bg-emerald-500" },
  Llama:   { bg: "bg-purple-50",  text: "text-purple-700",  border: "border-purple-200",  dot: "bg-purple-500"  },
};

interface DebateMessage {
  speaker: string;
  round: number;
  role: string;
  content: string;
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

function DebateOutput({ messages }: { messages: DebateMessage[] }) {
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

  const rounds = [1, 2, 3];

  return (
    <div className="space-y-8">
      {rounds.map((round) => {
        const roundMessages = messages.filter((m) => m.round === round);
        if (!roundMessages.length) return null;
        return (
          <div key={round}>
            <div className="flex items-center gap-3 mb-4">
              <div className="h-px flex-1 bg-slate-100" />
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider px-2">
                {ROUND_TITLES[round]}
              </span>
              <div className="h-px flex-1 bg-slate-100" />
            </div>
            <div className="space-y-4">
              {roundMessages.map((msg, idx) => {
                const style = SPEAKER_STYLES[msg.speaker] ?? SPEAKER_STYLES.Claude;
                return (
                  <div key={idx} className={`rounded-xl border p-4 ${style.bg} ${style.border}`}>
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
            </div>
          </div>
        );
      })}
    </div>
  );
}

function DebateLoadingSkeleton() {
  const { t } = useTranslation();
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-violet-600">
        <MessageSquare size={20} className="animate-pulse-slow" />
        <span className="text-sm font-semibold">{t("analytics.debate.analyzing")}</span>
      </div>
      <div className="space-y-2 text-xs text-slate-400">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-orange-400 animate-bounce" style={{ animationDelay: "0ms" }} />
          <span>Claude — {t("analytics.debate.modelStatus")}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-bounce" style={{ animationDelay: "150ms" }} />
          <span>ChatGPT — {t("analytics.debate.modelStatus")}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-bounce" style={{ animationDelay: "300ms" }} />
          <span>Llama — {t("analytics.debate.modelStatus")}</span>
        </div>
      </div>
      <div className="space-y-3">
        {[
          "bg-orange-50 border-orange-100",
          "bg-emerald-50 border-emerald-100",
          "bg-purple-50 border-purple-100",
        ].map((cls, i) => (
          <div key={i} className={`rounded-xl border p-4 ${cls}`}>
            <div className="flex items-center gap-2 mb-3">
              <div className="skeleton w-6 h-6 rounded-full" />
              <div className="skeleton h-3 w-16 rounded" />
            </div>
            <SkeletonText lines={3} />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AnalyticsPage() {
  const { t } = useTranslation();
  const [platforms, setPlatforms]     = useState<string[]>(ALL_PLATFORMS);
  const [analysisType, setType]       = useState("full_report");
  const [dateFrom, setDateFrom]       = useState(format(subDays(new Date(), 30), "yyyy-MM-dd"));
  const [dateTo, setDateTo]           = useState(format(new Date(), "yyyy-MM-dd"));
  const [result, setResult]           = useState<string>("");
  const [errorMsg, setErrorMsg]       = useState<string>("");
  const [loading, setLoading]         = useState(false);
  const [history, setHistory]         = useState<Analysis[]>([]);
  const [activeAnalysis, setActive]   = useState<number | null>(null);

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
    analyticsApi.getHistory().then(({ data }) => setHistory(data)).catch(() => {});
  }, []);

  async function runAnalysis() {
    if (!platforms.length) return toast.error(t("analytics.selectPlatform"));
    setLoading(true);
    setResult("");
    setErrorMsg("");
    setActive(null);

    if (analysisType === "debate") {
      // Debate uses multiple models concurrently — can't stream, use regular endpoint
      try {
        const { data } = await analyticsApi.analyze(platforms, dateFrom, dateTo, analysisType);
        setResult(data.result);
        setActive(data.id);
        toast.success(t("analytics.debate.successToast"));
        analyticsApi.getHistory().then(({ data }) => setHistory(data)).catch(() => {});
      } catch (err: any) {
        const detail = err?.response?.data?.detail ?? t("analytics.defaultError");
        setErrorMsg(detail);
        toast.error(t("analytics.errorToast"));
      } finally {
        setLoading(false);
      }
      return;
    }

    // All other types: SSE streaming
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
          } catch { /* partial JSON, skip */ }
        }
      }
    } catch (err: any) {
      setErrorMsg(err?.message ?? t("analytics.defaultError"));
      toast.error(t("analytics.errorToast"));
    } finally {
      setLoading(false);
    }
  }

  async function loadFromHistory(id: number) {
    setActive(id);
    try {
      const { data } = await analyticsApi.getAnalysis(id);
      setResult(data.result);
    } catch { toast.error(t("analytics.loadError")); }
  }

  const selectedType = ANALYSIS_TYPES.find((tp) => tp.value === analysisType);
  const debateMessages = result ? tryParseDebate(result) : null;
  const isDebate = analysisType === "debate" || debateMessages !== null;

  return (
    <div className="animate-fade-in space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{t("analytics.title")}</h1>
        <p className="text-sm text-slate-500 mt-0.5">{t("analytics.subtitle")}</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[340px_1fr] gap-5">
        {/* ── Config panel ── */}
        <div className="space-y-4">
          {/* Analysis type */}
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
          {/* Error */}
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

          <div className="card p-6 min-h-[400px]">
            {loading ? (
              isDebate
                ? <DebateLoadingSkeleton />
                : (
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
                )
            ) : result ? (
              <>
                <div className="flex items-center gap-2 mb-5 pb-4 border-b border-slate-50">
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${selectedType?.color ?? "bg-slate-100 text-slate-500"}`}>
                    {selectedType && <selectedType.icon size={16} />}
                  </div>
                  <div>
                    <p className="font-semibold text-slate-800 text-sm">{selectedType?.label}</p>
                    <p className="text-xs text-slate-400">
                      {debateMessages
                        ? t("analytics.debate.generatedBy")
                        : t("analytics.generatedBy", { date: format(new Date(), "dd/MM/yyyy HH:mm") })}
                    </p>
                  </div>
                  {debateMessages && (
                    <div className="ml-auto flex gap-1">
                      {["C", "G", "L"].map((initial, i) => (
                        <div key={i} className={`w-6 h-6 rounded-full flex items-center justify-center text-white text-[10px] font-bold ${["bg-orange-500", "bg-emerald-500", "bg-purple-500"][i]}`}>
                          {initial}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                {debateMessages
                  ? <DebateOutput messages={debateMessages} />
                  : <MarkdownOutput text={result} />}
              </>
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
  );
}

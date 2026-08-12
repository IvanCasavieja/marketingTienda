"use client";
import { useEffect, useRef, useState } from "react";
import { chatApi, type AiTaskUsage } from "@/lib/api";
import { Send, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { RobotMascot, RobotMini } from "@/components/RobotMascot";
import { useCurrentUser } from "@/hooks/useCurrentUser";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type BotMessage = { role: "bot" | "user"; text: string; ts: Date; usage?: AiTaskUsage };

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function HomePage() {
  const { t } = useTranslation();
  const { user } = useCurrentUser();
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
    if (!user) return;
    const name = user.full_name?.split(" ")[0] ?? "";
    const greeting = name ? t("home.greeting", { name }) : t("home.greetingNoName");
    setMessages([{
      role: "bot",
      text: `${greeting}! ${t("home.assistantWelcome")}`,
      ts: new Date(),
    }]);
  }, [user, t]);

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, open]);

  async function send(text: string) {
    const q = text.trim();
    if (!q) return;
    setInput("");
    setMessages((prev) => {
      const next = [...prev, { role: "user" as const, text: q, ts: new Date() }];
      _sendToApi(q, next);
      return next;
    });
  }

  async function _sendToApi(q: string, currentMessages: BotMessage[]) {
    setTyping(true);
    try {
      const history = currentMessages
        .filter((m) => m.role !== "bot" || m !== currentMessages[0])
        .slice(-11, -1)
        .map((m) => ({ role: m.role === "bot" ? "assistant" : "user", content: m.text }));
      const { data } = await chatApi.sendMessage(q, history);
      setMessages((prev) => [...prev, { role: "bot", text: data.reply, ts: new Date(), usage: data.usage }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "bot", text: "Lo siento, hubo un error al contactar el asistente. Intentá de nuevo.", ts: new Date() },
      ]);
    } finally {
      setTyping(false);
    }
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
              {"MKTG Platform"}
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
              <p className="text-xs text-slate-400 dark:text-slate-500">{t("home.assistantSubtitle")}</p>
            </div>
            <ChevronDown
              size={16}
              className={`text-slate-400 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
            />
          </button>

          {/* Messages */}
          {open && (
            <>
              <div className="border-t border-slate-100 dark:border-slate-800 px-5 py-4 space-y-4 max-h-80 overflow-y-auto bg-slate-50/50 dark:bg-slate-900/50">
                {messages.map((m, i) => (
                  <div key={i} className={`flex gap-3 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
                    {m.role === "bot" && (
                      <div className="w-7 h-7 rounded-xl bg-brand-500/10 flex items-center justify-center shrink-0 mt-0.5">
                        <RobotMini />
                      </div>
                    )}
                    <div className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}>
                      <div className={`max-w-[80%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
                        m.role === "user"
                          ? "bg-brand-600 text-white rounded-tr-sm"
                          : "bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800 text-slate-700 dark:text-slate-300 rounded-tl-sm shadow-sm"
                      }`}>
                        {m.text.split("**").map((part, j) =>
                          j % 2 === 1
                            ? <strong key={j} className={m.role === "user" ? "text-white" : "text-slate-900"}>{part}</strong>
                            : <span key={j}>{part}</span>
                        )}
                      </div>
                      {m.usage && (
                        <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1 px-1">
                          {m.usage.total_tokens.toLocaleString()} tokens
                        </p>
                      )}
                    </div>
                  </div>
                ))}
                {typing && (
                  <div className="flex gap-3">
                    <div className="w-7 h-7 rounded-xl bg-brand-500/10 flex items-center justify-center shrink-0">
                      <RobotMini />
                    </div>
                    <div className="bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm flex gap-1 items-center">
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
                <div className="px-5 py-3 flex gap-2 flex-wrap border-t border-slate-100 dark:border-slate-800">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} onClick={() => send(s)}
                      className="text-xs px-3 py-1.5 rounded-full border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-brand-400 hover:text-brand-600 hover:bg-brand-50 transition-all">
                      {s}
                    </button>
                  ))}
                </div>
              )}

              {/* Input */}
              <form onSubmit={handleSubmit} className="border-t border-slate-100 dark:border-slate-800 flex gap-3 px-4 py-3">
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={t("home.inputPlaceholder")}
                  className="flex-1 text-sm bg-slate-100 dark:bg-slate-800 rounded-xl px-4 py-2.5 text-slate-800 dark:text-slate-200 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:bg-white dark:focus:bg-slate-900 transition-all"
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
        <p className="text-center text-xs text-slate-400 dark:text-slate-500">
          {t("home.comingSoon")}
        </p>
      </div>
    </div>
  );
}

// Robot mascot ("Don Tino") vive en components/RobotMascot.tsx — compartido
// con Ayuda y Login.

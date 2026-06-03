"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import { toast } from "sonner";
import { Eye, EyeOff, Loader2, BarChart3, TrendingUp, Brain, Zap, X } from "lucide-react";
import { useTranslation } from "react-i18next";

export default function LoginPage() {
  const router = useRouter();
  const { t } = useTranslation();
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [showJoinStep, setShowJoinStep] = useState(false);
  const [showPwd, setShowPwd]   = useState(false);
  const [loading, setLoading]   = useState(false);

  const features = [
    { icon: BarChart3,  label: t("login.features.realtime"), desc: t("login.features.realtimeDesc") },
    { icon: Brain,      label: t("login.features.ai"),       desc: t("login.features.aiDesc") },
    { icon: TrendingUp, label: t("login.features.roas"),     desc: t("login.features.roasDesc") },
    { icon: Zap,        label: t("login.features.alerts"),   desc: t("login.features.alertsDesc") },
  ];

  async function handleLogin(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    // Read directly from DOM to handle browser autofill (autofill doesn't fire onChange)
    const form = e.currentTarget;
    const emailVal    = (form.elements.namedItem("email")    as HTMLInputElement).value;
    const passwordVal = (form.elements.namedItem("password") as HTMLInputElement).value;
    setLoading(true);
    try {
      await authApi.login(emailVal, passwordVal, "");
      const { data: me } = await authApi.me();
      if (!me.team_group_id) {
        setShowJoinStep(true);
        return;
      }
      router.push("/dashboard");
    } catch {
      toast.error(t("login.wrongCredentials"));
    } finally {
      setLoading(false);
    }
  }

  async function handleJoinTeam(e: React.FormEvent) {
    e.preventDefault();
    if (!joinCode.trim()) return;

    setLoading(true);
    try {
      await authApi.joinTeam(joinCode.trim());
      toast.success(t("login.joinTeamSuccess"));
      router.push("/dashboard");
    } catch {
      toast.error(t("login.invalidCode"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex">
      {/* ── Left panel ─────────────────────────────── */}
      <div className="hidden lg:flex lg:w-[55%] bg-navy-900 flex-col justify-between p-12 relative overflow-hidden">
        {/* Background glow */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute -top-40 -left-40 w-[500px] h-[500px] rounded-full bg-brand-600/20 blur-3xl" />
          <div className="absolute bottom-0 right-0 w-[400px] h-[400px] rounded-full bg-brand-800/20 blur-3xl" />
        </div>

        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-14">
            <div className="w-9 h-9 rounded-xl bg-brand-500 flex items-center justify-center">
              <BarChart3 size={18} className="text-white" />
            </div>
            <span className="text-white font-bold text-lg tracking-tight">MKTG Platform</span>
          </div>

          <h1 className="text-4xl font-bold text-white leading-tight mb-4">
            {t("login.tagline")}
          </h1>
          <p className="text-slate-400 text-base leading-relaxed max-w-sm">
            {t("login.taglineSub")}
          </p>
        </div>

        <div className="relative z-10 grid grid-cols-2 gap-4">
          {features.map(({ icon: Icon, label, desc }) => (
            <div key={label} className="bg-white/5 backdrop-blur rounded-2xl p-4 border border-white/10">
              <div className="w-8 h-8 rounded-lg bg-brand-500/20 flex items-center justify-center mb-3">
                <Icon size={16} className="text-brand-400" />
              </div>
              <p className="text-white text-sm font-semibold mb-0.5">{label}</p>
              <p className="text-slate-500 text-xs leading-snug">{desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* ── Right panel ────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center p-8 bg-slate-50">
        <div className="w-full max-w-sm animate-fade-in">
          {/* Mobile logo */}
          <div className="flex items-center gap-2.5 mb-8 lg:hidden">
            <div className="w-8 h-8 rounded-xl bg-brand-500 flex items-center justify-center">
              <BarChart3 size={16} className="text-white" />
            </div>
            <span className="font-bold text-slate-800">MKTG Platform</span>
          </div>

          <h2 className="text-2xl font-bold text-slate-900 mb-1">{t("login.welcome")}</h2>
          <p className="text-slate-500 text-sm mb-8">{t("login.subtitle")}</p>

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                {t("login.email")}
              </label>
              <input
                type="email"
                name="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input"
                placeholder="tu@empresa.com"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                {t("login.password")}
              </label>
              <div className="relative">
                <input
                  type={showPwd ? "text" : "password"}
                  name="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="input pr-10"
                  placeholder="••••••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPwd(!showPwd)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                >
                  {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button type="submit" disabled={loading} className="btn-primary w-full mt-2">
              {loading
                ? <><Loader2 size={16} className="animate-spin" /> {t("login.signingIn")}</>
                : t("login.signIn")}
            </button>
          </form>

          <p className="text-center text-xs text-slate-400 mt-8">
            Marketing Intelligence Platform · {new Date().getFullYear()}
          </p>
        </div>
      </div>

      {showJoinStep && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4">
          <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl relative">
            <button
              type="button"
              onClick={() => setShowJoinStep(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 transition-colors"
            >
              <X size={18} />
            </button>
            <h3 className="text-lg font-bold text-slate-900 mb-1">{t("login.joinTeamTitle")}</h3>
            <p className="text-sm text-slate-500 mb-5">{t("login.joinTeamSub")}</p>
            <form onSubmit={handleJoinTeam} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">
                  {t("login.joinTeamCode")}
                </label>
                <input
                  type="text"
                  required
                  autoFocus
                  value={joinCode}
                  onChange={(e) => setJoinCode(e.target.value)}
                  className="input"
                  placeholder={t("login.joinTeamPaste")}
                />
              </div>
              <button type="submit" disabled={loading} className="btn-primary w-full">
                {loading
                  ? <><Loader2 size={16} className="animate-spin" /> {t("login.joinTeamValidating")}</>
                  : t("login.joinTeamBtn")}
              </button>
              <button
                type="button"
                onClick={() => router.push("/home")}
                className="w-full text-sm text-slate-500 hover:text-slate-700"
              >
                {t("login.continueWithoutTeam")}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

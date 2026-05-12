"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import { toast } from "sonner";
import { Eye, EyeOff, Loader2, BarChart3, TrendingUp, Brain, Zap } from "lucide-react";

const features = [
  { icon: BarChart3, label: "Datos en tiempo real", desc: "Meta, Google, TikTok y DV360 unificados" },
  { icon: Brain,     label: "Análisis con IA",      desc: "Claude genera insights accionables" },
  { icon: TrendingUp,label: "ROAS cross-platform",  desc: "Compará el rendimiento entre canales" },
  { icon: Zap,       label: "Alertas inteligentes", desc: "Detectá anomalías automáticamente" },
];

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd]   = useState(false);
  const [loading, setLoading]   = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await authApi.login(email, password);
      localStorage.setItem("access_token",  data.access_token);
      localStorage.setItem("refresh_token", data.refresh_token);
      router.push("/dashboard");
    } catch {
      toast.error("Email o contraseña incorrectos");
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
            Toda tu inversión<br />en un solo lugar.
          </h1>
          <p className="text-slate-400 text-base leading-relaxed max-w-sm">
            Conectá Meta, Google Ads, TikTok y DV360. Analizá con IA. Tomá mejores decisiones.
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

          <h2 className="text-2xl font-bold text-slate-900 mb-1">Bienvenido</h2>
          <p className="text-slate-500 text-sm mb-8">Ingresá con tu cuenta de trabajo</p>

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                Email
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input"
                placeholder="tu@empresa.com"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                Contraseña
              </label>
              <div className="relative">
                <input
                  type={showPwd ? "text" : "password"}
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
                ? <><Loader2 size={16} className="animate-spin" /> Ingresando...</>
                : "Ingresar"}
            </button>
          </form>

          <p className="text-center text-xs text-slate-400 mt-8">
            Marketing Intelligence Platform · {new Date().getFullYear()}
          </p>
        </div>
      </div>
    </div>
  );
}

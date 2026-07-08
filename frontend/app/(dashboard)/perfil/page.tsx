"use client";
import { useEffect, useState } from "react";
import { authApi } from "@/lib/api";
import type { CurrentUser } from "@/types";
import { Eye, EyeOff, Loader2, KeyRound, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

const ROLE_COLORS: Record<string, string> = {
  Superadmin: "bg-rose-100 text-rose-700",
  Admin:      "bg-brand-100 text-brand-700",
  Usuario:    "bg-amber-100 text-amber-700",
  Viewer:     "bg-slate-100 text-slate-500",
};

export default function PerfilPage() {
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  const [currentPwd, setCurrentPwd] = useState("");
  const [newPwd,     setNewPwd]     = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew,     setShowNew]     = useState(false);
  const [saving,      setSaving]      = useState(false);

  useEffect(() => {
    authApi.me()
      .then(({ data }) => setMe(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    if (newPwd !== confirmPwd) {
      toast.error("Las contraseñas nuevas no coinciden");
      return;
    }
    setSaving(true);
    try {
      await authApi.changePassword(currentPwd, newPwd);
      toast.success("Contraseña actualizada correctamente");
      setCurrentPwd(""); setNewPwd(""); setConfirmPwd("");
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Error al cambiar la contraseña");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={22} className="animate-spin text-slate-400" />
      </div>
    );
  }

  const initial = me?.full_name?.charAt(0).toUpperCase() ?? "?";

  return (
    <div className="max-w-lg mx-auto space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Mi perfil</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">Tu cuenta y tu contraseña</p>
      </div>

      {/* Info de la cuenta */}
      <div className="card p-5 flex items-center gap-4">
        <div className="w-14 h-14 rounded-full bg-brand-100 text-brand-600 flex items-center justify-center text-xl font-bold shrink-0">
          {initial}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-base font-semibold text-slate-800 dark:text-slate-200 truncate">{me?.full_name}</p>
            {me?.is_superuser ? (
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-100 text-rose-700">SUPER ADMIN</span>
            ) : me?.role_name ? (
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${ROLE_COLORS[me.role_name] ?? "bg-violet-100 text-violet-700"}`}>
                {me.role_name.toUpperCase()}
              </span>
            ) : null}
          </div>
          <p className="text-sm text-slate-400 dark:text-slate-500 truncate">{me?.email}</p>
        </div>
        <ShieldCheck size={18} className="text-slate-300 dark:text-slate-600 shrink-0" />
      </div>

      {/* Cambiar contraseña */}
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-4">
          <KeyRound size={15} className="text-brand-500" />
          <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">Cambiar contraseña</p>
        </div>
        <form onSubmit={handleChangePassword} className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Contraseña actual</label>
            <div className="relative">
              <input
                type={showCurrent ? "text" : "password"}
                required
                autoComplete="current-password"
                value={currentPwd}
                onChange={(e) => setCurrentPwd(e.target.value)}
                className="input text-sm w-full pr-10"
              />
              <button type="button" onClick={() => setShowCurrent((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                {showCurrent ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Contraseña nueva</label>
            <div className="relative">
              <input
                type={showNew ? "text" : "password"}
                required
                autoComplete="new-password"
                value={newPwd}
                onChange={(e) => setNewPwd(e.target.value)}
                placeholder="Mín. 12 caracteres, mayúscula, número y símbolo"
                className="input text-sm w-full pr-10"
              />
              <button type="button" onClick={() => setShowNew((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                {showNew ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Confirmar contraseña nueva</label>
            <input
              type={showNew ? "text" : "password"}
              required
              autoComplete="new-password"
              value={confirmPwd}
              onChange={(e) => setConfirmPwd(e.target.value)}
              className="input text-sm w-full"
            />
          </div>

          <button type="submit" disabled={saving} className="btn-primary w-full mt-2">
            {saving ? <><Loader2 size={15} className="animate-spin" /> Guardando…</> : "Actualizar contraseña"}
          </button>
        </form>
      </div>
    </div>
  );
}

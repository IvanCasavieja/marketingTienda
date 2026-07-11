"use client";
import { useEffect, useState } from "react";
import { authApi } from "@/lib/api";
import type { CurrentUser } from "@/types";
import { Loader2, KeyRound, ShieldCheck } from "lucide-react";
import ChangePasswordForm from "@/components/ChangePasswordForm";

const ROLE_COLORS: Record<string, string> = {
  Superadmin: "bg-rose-100 text-rose-700",
  Admin:      "bg-brand-100 text-brand-700",
  Usuario:    "bg-amber-100 text-amber-700",
  Viewer:     "bg-slate-100 text-slate-500",
};

export default function PerfilPage() {
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    authApi.me()
      .then(({ data }) => setMe(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

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
        <ChangePasswordForm />
      </div>
    </div>
  );
}

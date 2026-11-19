"use client";
import { useState } from "react";
import { toast } from "sonner";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { Loader2, KeyRound, Mail, ShieldCheck } from "lucide-react";
import ChangePasswordForm from "@/components/ChangePasswordForm";
import { authApi } from "@/lib/api";

const ROLE_COLORS: Record<string, string> = {
  Superadmin: "bg-rose-100 text-rose-700",
  Admin:      "bg-brand-100 text-brand-700",
  Usuario:    "bg-amber-100 text-amber-700",
  Viewer:     "bg-slate-100 text-slate-500",
};

export default function PerfilPage() {
  const { user: me, loading } = useCurrentUser();

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
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">Tu cuenta, tus avisos y tu contraseña</p>
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

      {/* Los avisos por mail (18/11/2026): prendidos por defecto, se apagan acá. */}
      <AvisosPorMail prendidos={me?.avisos_por_mail !== false} email={me?.email ?? ""} />

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

/** "Recibir los avisos por mail": lo que llega a la campanita llega también
 *  al mail de la cuenta (Ivan, 18/11/2026), menos lo del tablero, que queda
 *  solo en la campanita (19/11/2026: tope de 3.000 mails por mes). */
function AvisosPorMail({ prendidos, email }: { prendidos: boolean; email: string }) {
  const { refetch } = useCurrentUser();
  const [valor, setValor] = useState<boolean | null>(null);
  const [guardando, setGuardando] = useState(false);
  const actual = valor ?? prendidos;

  async function cambiar() {
    const nuevo = !actual;
    setValor(nuevo);
    setGuardando(true);
    try {
      await authApi.preferencias({ avisosPorMail: nuevo });
      toast.success(nuevo ? "Listo: los avisos te van a llegar también por mail." : "Listo: los avisos quedan solo en la campanita.");
      await refetch?.();
    } catch {
      setValor(!nuevo);
      toast.error("No se pudo guardar. Probá de nuevo en un momento.");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="card p-5">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-brand-500/15 dark:text-brand-300">
          <Mail size={17} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">Recibir los avisos por mail</p>
          <p className="mt-0.5 text-[13px] leading-snug text-slate-500 dark:text-slate-400">
            Lo que llega a la campanita te llega también a <span className="font-medium text-slate-700 dark:text-slate-300">{email}</span>, al momento. Lo del tablero (entregas, cambios, aprobaciones y comentarios) queda solo en la campanita.
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={actual}
          aria-label="Recibir los avisos por mail"
          onClick={cambiar}
          disabled={guardando}
          className={`relative mt-1 inline-flex h-7 w-12 shrink-0 items-center rounded-full transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 disabled:opacity-60 ${actual ? "bg-brand-600" : "bg-slate-300 dark:bg-slate-600"}`}
        >
          <span className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform duration-200 ${actual ? "translate-x-6" : "translate-x-1"}`} />
        </button>
      </div>
    </div>
  );
}

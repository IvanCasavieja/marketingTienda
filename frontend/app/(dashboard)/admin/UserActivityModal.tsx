"use client";
import { useEffect, useState } from "react";
import { X, LogIn, FileSpreadsheet, DollarSign, CalendarClock } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { adminApi, type UserStats } from "@/lib/api";
import { useEscapeKey } from "@/hooks/useEscapeKey";
import { SkeletonCard } from "@/components/ui/SkeletonCard";
import AuditLogTab from "./AuditLogTab";
import AiUsageTab from "./AiUsageTab";

// Junta, para un solo usuario, lo que ya muestran por separado AuditLogTab
// (historial completo, ya filtrable por userId) y AiUsageTab (costo/uso de
// IA, idem) detrás de un header de stats compactas propio de esta vista —
// reusa esos dos componentes tal cual en vez de duplicar sus tablas/gráficos.

interface UserActivityModalProps {
  user: { id: number; full_name: string; email: string };
  onClose: () => void;
}

function fUsd(n: number): string {
  if (n === 0) return "$0.00";
  if (n < 0.01) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(2)}`;
}

export default function UserActivityModal({ user, onClose }: UserActivityModalProps) {
  const { t, i18n } = useTranslation();
  useEscapeKey(onClose);

  const [stats, setStats] = useState<UserStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    adminApi.userStats(user.id)
      .then(({ data }) => setStats(data))
      .catch(() => toast.error(t("admin.userActivity.loadError")))
      .finally(() => setLoading(false));
  }, [user.id]); // eslint-disable-line react-hooks/exhaustive-deps

  function fmtDate(iso: string | null): string {
    if (!iso) return "—";
    return new Date(iso).toLocaleString(i18n.language, {
      day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="user-activity-title"
        className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-slate-800 shrink-0">
          <div className="min-w-0">
            <p id="user-activity-title" className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">
              {t("admin.userActivity.title", { name: user.full_name })}
            </p>
            <p className="text-xs text-slate-400 dark:text-slate-500 truncate">{user.email}</p>
          </div>
          <button onClick={onClose} aria-label={t("common.close")} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 shrink-0">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {loading ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[1, 2, 3, 4].map((i) => <SkeletonCard key={i} className="h-20" />)}
            </div>
          ) : stats && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="card p-3.5">
                <LogIn size={14} className="text-brand-500 mb-1.5" />
                <p className="text-lg font-bold text-slate-900 dark:text-slate-100">{stats.login_count}</p>
                <p className="text-[11px] text-slate-500 mt-0.5">{t("admin.userActivity.logins")}</p>
              </div>
              <div className="card p-3.5">
                <CalendarClock size={14} className="text-brand-500 mb-1.5" />
                <p className="text-xs font-semibold text-slate-900 dark:text-slate-100">{fmtDate(stats.last_login_at)}</p>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  {t("admin.userActivity.lastLogin")}{stats.last_login_ip ? ` · ${stats.last_login_ip}` : ""}
                </p>
              </div>
              <div className="card p-3.5">
                <FileSpreadsheet size={14} className="text-brand-500 mb-1.5" />
                <p className="text-lg font-bold text-slate-900 dark:text-slate-100">{stats.cenefas_generated_count}</p>
                <p className="text-[11px] text-slate-500 mt-0.5">{t("admin.userActivity.cenefasGenerated")}</p>
              </div>
              <div className="card p-3.5">
                <DollarSign size={14} className="text-brand-500 mb-1.5" />
                <p className="text-lg font-bold text-slate-900 dark:text-slate-100">{fUsd(stats.ai_cost_last_30d_usd)}</p>
                <p className="text-[11px] text-slate-500 mt-0.5">{t("admin.userActivity.aiCost30d")}</p>
              </div>
            </div>
          )}

          <AiUsageTab userId={user.id} />
          <AuditLogTab userId={user.id} />
        </div>
      </div>
    </div>
  );
}

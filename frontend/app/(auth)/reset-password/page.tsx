"use client";
import { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { authApi } from "@/lib/api";
import { toast } from "sonner";
import { BarChart3, Loader2, Eye, EyeOff, CheckCircle2 } from "lucide-react";
import { useTranslation } from "react-i18next";

function ResetForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { t } = useTranslation();
  const token = params.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm]   = useState("");
  const [showPwd, setShowPwd]   = useState(false);
  const [loading, setLoading]   = useState(false);
  const [done, setDone]         = useState(false);
  const [error, setError]       = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setError(t("resetPassword.mismatch"));
      return;
    }
    setError("");
    setLoading(true);
    try {
      await authApi.resetPassword(token, password);
      setDone(true);
      setTimeout(() => router.push("/login"), 3000);
    } catch (err: any) {
      const detail = err?.response?.data?.detail ?? t("resetPassword.errorToast");
      setError(detail);
      toast.error(detail);
    } finally {
      setLoading(false);
    }
  }

  if (!token) {
    return (
      <div className="text-center space-y-3">
        <p className="text-sm text-red-500">{t("resetPassword.invalidLink")}</p>
        <Link href="/forgot-password" className="text-sm text-brand-600 hover:text-brand-700 font-medium">
          {t("forgotPassword.send")}
        </Link>
      </div>
    );
  }

  if (done) {
    return (
      <div className="text-center">
        <div className="w-14 h-14 rounded-2xl bg-emerald-50 flex items-center justify-center mx-auto mb-5">
          <CheckCircle2 size={28} className="text-emerald-500" />
        </div>
        <h2 className="text-xl font-bold text-slate-900 mb-2">{t("resetPassword.successTitle")}</h2>
        <p className="text-sm text-slate-500 leading-relaxed">{t("resetPassword.successSub")}</p>
      </div>
    );
  }

  return (
    <>
      <h2 className="text-2xl font-bold text-slate-900 mb-1">{t("resetPassword.title")}</h2>
      <p className="text-slate-500 text-sm mb-8">{t("resetPassword.subtitle")}</p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">
            {t("resetPassword.newPassword")}
          </label>
          <div className="relative">
            <input
              type={showPwd ? "text" : "password"}
              required
              autoFocus
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
          <p className="text-xs text-slate-400 mt-1.5">{t("resetPassword.hint")}</p>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">
            {t("resetPassword.confirmPassword")}
          </label>
          <input
            type={showPwd ? "text" : "password"}
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="input"
            placeholder="••••••••••••"
          />
        </div>

        {error && <p className="text-xs text-red-500">{error}</p>}

        <button type="submit" disabled={loading} className="btn-primary w-full mt-2">
          {loading
            ? <><Loader2 size={16} className="animate-spin" /> {t("resetPassword.saving")}</>
            : t("resetPassword.save")}
        </button>
      </form>
    </>
  );
}

export default function ResetPasswordPage() {
  const { t } = useTranslation();
  return (
    <div className="min-h-screen flex items-center justify-center p-8 bg-slate-50">
      <div className="w-full max-w-sm animate-fade-in">
        <div className="flex items-center gap-2.5 mb-8">
          <div className="w-8 h-8 rounded-xl bg-brand-500 flex items-center justify-center">
            <BarChart3 size={16} className="text-white" />
          </div>
          <span className="font-bold text-slate-800">MKTG Platform</span>
        </div>
        <Suspense fallback={<p className="text-sm text-slate-400">{t("common.loading")}</p>}>
          <ResetForm />
        </Suspense>
      </div>
    </div>
  );
}

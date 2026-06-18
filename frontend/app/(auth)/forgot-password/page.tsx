"use client";
import { useState } from "react";
import Link from "next/link";
import { authApi } from "@/lib/api";
import { toast } from "sonner";
import { BarChart3, Loader2, Mail, ArrowLeft, CheckCircle2 } from "lucide-react";
import { useTranslation } from "react-i18next";

export default function ForgotPasswordPage() {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      await authApi.forgotPassword(email);
      setSent(true);
    } catch {
      toast.error(t("forgotPassword.errorToast"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-8 bg-slate-50">
      <div className="w-full max-w-sm animate-fade-in">
        <div className="flex items-center gap-2.5 mb-8">
          <div className="w-8 h-8 rounded-xl bg-brand-500 flex items-center justify-center">
            <BarChart3 size={16} className="text-white" />
          </div>
          <span className="font-bold text-slate-800">MKTG Platform</span>
        </div>

        {sent ? (
          <div className="text-center">
            <div className="w-14 h-14 rounded-2xl bg-emerald-50 flex items-center justify-center mx-auto mb-5">
              <CheckCircle2 size={28} className="text-emerald-500" />
            </div>
            <h2 className="text-xl font-bold text-slate-900 mb-2">{t("forgotPassword.sentTitle")}</h2>
            <p className="text-sm text-slate-500 leading-relaxed mb-6">{t("forgotPassword.sentSub")}</p>
            <Link
              href="/login"
              className="text-sm text-brand-600 hover:text-brand-700 font-medium inline-flex items-center gap-1"
            >
              <ArrowLeft size={14} /> {t("forgotPassword.backToLogin")}
            </Link>
          </div>
        ) : (
          <>
            <h2 className="text-2xl font-bold text-slate-900 mb-1">{t("forgotPassword.title")}</h2>
            <p className="text-slate-500 text-sm mb-8">{t("forgotPassword.subtitle")}</p>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">
                  {t("login.email")}
                </label>
                <div className="relative">
                  <Mail size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                  <input
                    type="email"
                    required
                    autoFocus
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="input pl-9"
                    placeholder="tu@empresa.com"
                  />
                </div>
              </div>

              <button type="submit" disabled={loading} className="btn-primary w-full mt-2">
                {loading
                  ? <><Loader2 size={16} className="animate-spin" /> {t("forgotPassword.sending")}</>
                  : t("forgotPassword.send")}
              </button>
            </form>

            <div className="text-center mt-6">
              <Link
                href="/login"
                className="text-sm text-slate-500 hover:text-slate-700 inline-flex items-center gap-1 transition-colors"
              >
                <ArrowLeft size={14} /> {t("forgotPassword.backToLogin")}
              </Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

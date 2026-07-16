"use client";
import { useState } from "react";
import { authApi } from "@/lib/api";
import { extractErrorDetail } from "@/lib/errors";
import { Eye, EyeOff, Loader2, KeyRound } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

export default function ChangePasswordForm({ onSuccess }: { onSuccess?: () => void }) {
  const { t } = useTranslation();
  const [currentPwd, setCurrentPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (newPwd !== confirmPwd) {
      toast.error(t("changePassword.mismatch"));
      return;
    }
    setSaving(true);
    try {
      await authApi.changePassword(currentPwd, newPwd);
      toast.success(t("changePassword.successToast"));
      setCurrentPwd("");
      setNewPwd("");
      setConfirmPwd("");
      onSuccess?.();
    } catch (err) {
      toast.error(extractErrorDetail(err, t("changePassword.errorToast")));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div>
        <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">{t("changePassword.currentPassword")}</label>
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
        <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">{t("changePassword.newPassword")}</label>
        <div className="relative">
          <input
            type={showNew ? "text" : "password"}
            required
            autoComplete="new-password"
            value={newPwd}
            onChange={(e) => setNewPwd(e.target.value)}
            placeholder={t("changePassword.hint")}
            className="input text-sm w-full pr-10"
          />
          <button type="button" onClick={() => setShowNew((v) => !v)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
            {showNew ? <EyeOff size={15} /> : <Eye size={15} />}
          </button>
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">{t("changePassword.confirmPassword")}</label>
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
        {saving ? <><Loader2 size={15} className="animate-spin" /> {t("changePassword.saving")}</> : (
          <><KeyRound size={15} /> {t("changePassword.submit")}</>
        )}
      </button>
    </form>
  );
}

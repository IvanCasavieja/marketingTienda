"use client";
import { useState } from "react";
import { authApi } from "@/lib/api";
import { Eye, EyeOff, Loader2, KeyRound } from "lucide-react";
import { toast } from "sonner";

export default function ChangePasswordForm({ onSuccess }: { onSuccess?: () => void }) {
  const [currentPwd, setCurrentPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (newPwd !== confirmPwd) {
      toast.error("Las contraseñas nuevas no coinciden");
      return;
    }
    setSaving(true);
    try {
      await authApi.changePassword(currentPwd, newPwd);
      toast.success("Contraseña actualizada correctamente");
      setCurrentPwd("");
      setNewPwd("");
      setConfirmPwd("");
      onSuccess?.();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Error al cambiar la contraseña");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
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
        {saving ? <><Loader2 size={15} className="animate-spin" /> Guardando…</> : (
          <><KeyRound size={15} /> Actualizar contraseña</>
        )}
      </button>
    </form>
  );
}

"use client";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Receipt, Upload } from "lucide-react";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { hasPermission } from "@/lib/permissions";
import FacturacionDashboard from "@/components/facturacion/FacturacionDashboard";
import FacturaUploadModal from "@/components/facturacion/FacturaUploadModal";
import DogTiFloating from "@/components/facturacion/DogTiFloating";

export default function FacturacionPage() {
  const { t } = useTranslation();
  const { user } = useCurrentUser();
  const [showUpload, setShowUpload] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);

  return (
    <div className="animate-fade-in w-full space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-4">
          <div className="w-11 h-11 rounded-2xl bg-amber-500/10 flex items-center justify-center shrink-0">
            <Receipt size={22} className="text-amber-500" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">{t("facturacion.title")}</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{t("facturacion.subtitle")}</p>
          </div>
        </div>
        {hasPermission(user, "facturacion.upload") && (
          <button onClick={() => setShowUpload(true)} className="btn-primary flex items-center gap-2 text-sm">
            <Upload size={15} /> {t("facturacion.uploadButton")}
          </button>
        )}
      </div>

      <FacturacionDashboard refreshToken={refreshToken} />

      {showUpload && (
        <FacturaUploadModal
          onClose={() => setShowUpload(false)}
          onConfirmed={() => setRefreshToken((v) => v + 1)}
        />
      )}

      {hasPermission(user, "ai.dogti") && <DogTiFloating contexto="dashboard" />}
    </div>
  );
}

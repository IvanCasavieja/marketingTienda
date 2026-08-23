"use client";
import { useState, ChangeEvent, FormEvent } from "react";
import { FileSpreadsheet, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { convertidorApi, type ConvertidorRow, type MaPair } from "@/lib/api";
import { FileDropField } from "@/components/cenefas/fields";
import ConvertidorGrid from "./ConvertidorGrid";

export default function ConvertidorPanel() {
  const { t } = useTranslation();
  const [excel, setExcel] = useState<File | null>(null);
  const [rows, setRows] = useState<ConvertidorRow[] | null>(null);
  const [maPairs, setMaPairs] = useState<MaPair[]>([]);
  const [loading, setLoading] = useState(false);

  function reset() {
    setRows(null);
    setMaPairs([]);
    setExcel(null);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!excel) return;
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append("excel", excel);
      const { data } = await convertidorApi.preview(fd);
      setRows(data.rows);
      setMaPairs(data.ma_pairs);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("convertidor.unknownError"));
    } finally {
      setLoading(false);
    }
  }

  if (rows) {
    return (
      <ConvertidorGrid
        rows={rows}
        setRows={setRows}
        maPairs={maPairs}
        onReset={reset}
      />
    );
  }

  return (
    <div className="card p-6 space-y-4 max-w-xl mx-auto">
      <p className="text-sm text-slate-500 dark:text-slate-400">{t("convertidor.intro")}</p>
      <form onSubmit={handleSubmit} className="space-y-4">
        <FileDropField
          label={t("convertidor.excelLabel")}
          hint=".xlsx / .csv"
          accept=".xlsx,.xlsm,.csv"
          file={excel}
          onChange={(e: ChangeEvent<HTMLInputElement>) => e.target.files?.[0] && setExcel(e.target.files[0])}
          icon={FileSpreadsheet}
          accentColor="brand"
          chooseLabel={t("cenefas.chooseFile")}
          readyLabel={t("cenefas.ready")}
          searchLabel={t("cenefas.search")}
        />
        <button
          type="submit"
          disabled={!excel || loading}
          className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50"
        >
          {loading ? <Loader2 size={16} className="animate-spin" /> : <FileSpreadsheet size={16} />}
          {loading ? t("convertidor.processing") : t("convertidor.process")}
        </button>
      </form>
    </div>
  );
}

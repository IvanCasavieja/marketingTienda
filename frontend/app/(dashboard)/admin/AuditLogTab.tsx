"use client";
import { useEffect, useState } from "react";
import { Loader2, History } from "lucide-react";
import { toast } from "sonner";
import { adminApi, type AuditLogEntry } from "@/lib/api";

const PAGE_SIZE = 50;

function formatDetails(details: Record<string, unknown> | null): string {
  if (!details || Object.keys(details).length === 0) return "—";
  return Object.entries(details)
    .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") || "—" : v ?? "—"}`)
    .join(" · ");
}

export default function AuditLogTab() {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);

  useEffect(() => { load(0, true); }, []);

  async function load(offset: number, replace: boolean) {
    replace ? setLoading(true) : setLoadingMore(true);
    try {
      const { data } = await adminApi.auditLog(PAGE_SIZE, offset);
      setEntries((prev) => replace ? data : [...prev, ...data]);
      setHasMore(data.length === PAGE_SIZE);
    } catch {
      toast.error("No se pudo cargar el historial de auditoría.");
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }

  return (
    <div className="card overflow-hidden">
      <div className="px-4 sm:px-6 py-4 border-b border-slate-50 dark:border-slate-800 flex items-center gap-2">
        <History size={15} className="text-slate-400" />
        <p className="section-title">Auditoría</p>
        <span className="text-xs text-slate-400 dark:text-slate-500 ml-auto">{entries.length} registro{entries.length === 1 ? "" : "s"}</span>
      </div>

      {loading ? (
        <div className="flex items-center justify-center p-10"><Loader2 size={20} className="animate-spin text-slate-400" /></div>
      ) : entries.length === 0 ? (
        <p className="text-sm text-slate-400 px-6 py-10 text-center">Sin actividad registrada todavía.</p>
      ) : (
        <>
          <div className="overflow-x-auto overflow-y-auto max-h-[calc(100svh-26rem)]">
            <table className="w-full min-w-[720px]">
              <thead className="sticky top-0 z-10">
                <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-950">
                  <th className="table-th">Fecha</th>
                  <th className="table-th">Usuario</th>
                  <th className="table-th">Acción</th>
                  <th className="table-th">Recurso</th>
                  <th className="table-th">Detalle</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id} className="table-tr">
                    <td className="table-td text-slate-400 text-xs whitespace-nowrap">
                      {e.created_at ? new Date(e.created_at).toLocaleString("es-UY", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"}
                    </td>
                    <td className="table-td text-xs">{e.user_email ?? "—"}</td>
                    <td className="table-td text-xs font-mono">{e.action}</td>
                    <td className="table-td text-xs text-slate-500 dark:text-slate-400">
                      {e.resource ? `${e.resource}${e.resource_id ? ` #${e.resource_id}` : ""}` : "—"}
                    </td>
                    <td className="table-td text-xs text-slate-500 dark:text-slate-400 max-w-[320px] truncate" title={formatDetails(e.details)}>
                      {formatDetails(e.details)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {hasMore && (
            <div className="px-4 py-3 border-t border-slate-50 dark:border-slate-800 flex justify-center">
              <button onClick={() => load(entries.length, false)} disabled={loadingMore}
                className="btn-secondary text-xs py-2 px-4 flex items-center gap-2">
                {loadingMore && <Loader2 size={12} className="animate-spin" />}
                Cargar más
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

"use client";
import { useEffect, useState } from "react";
import { watchlistApi, type WatchlistConItems } from "@/lib/api";
import { fMoneyByCurrency } from "@/lib/format";
import { CadenaBadge } from "@/components/precios/cadenaConfig";
import { Loader2, Star, Trash2, ExternalLink, ClipboardList } from "lucide-react";
import { toast } from "sonner";

function formatFecha(iso: string | null): string {
  if (!iso) return "todavía sin chequear";
  const d = new Date(iso);
  return d.toLocaleDateString("es-UY", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export default function ListasMonitoreoPage() {
  const [listas, setListas] = useState<WatchlistConItems[] | null>(null);
  const [borrando, setBorrando] = useState<number | null>(null);

  useEffect(() => {
    cargar();
  }, []);

  async function cargar() {
    try {
      const { data } = await watchlistApi.listar();
      setListas(data);
    } catch {
      toast.error("No se pudieron cargar las listas de monitoreo");
      setListas([]);
    }
  }

  async function eliminarLista(id: number) {
    setBorrando(id);
    try {
      await watchlistApi.eliminar(id);
      setListas((prev) => prev?.filter((l) => l.id !== id) ?? null);
      toast.success("Lista eliminada");
    } catch {
      toast.error("No se pudo eliminar la lista");
    } finally {
      setBorrando(null);
    }
  }

  async function eliminarItem(watchlistId: number, itemId: number) {
    try {
      await watchlistApi.eliminarItem(itemId);
      setListas((prev) =>
        prev?.map((l) =>
          l.id === watchlistId ? { ...l, items: l.items.filter((it) => it.id !== itemId) } : l
        ) ?? null
      );
    } catch {
      toast.error("No se pudo sacar el producto de la lista");
    }
  }

  if (listas === null) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={22} className="animate-spin text-slate-400" />
      </div>
    );
  }

  const hayListas = listas.length > 0;

  return (
    <div className="max-w-3xl mx-auto space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Listas de monitoreo</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
          Productos que seguís de la competencia — se chequean solos todos los días y te avisamos si cambia el precio.
        </p>
      </div>

      {!hayListas && (
        <div className="card p-10 flex flex-col items-center text-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-brand-600/10 flex items-center justify-center">
            <Star size={22} className="text-brand-600" />
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400 max-w-sm">
            Todavía no seguís ningún producto. Andá a{" "}
            <a href="/precios" className="text-brand-600 hover:underline">Buscar precios</a>, abrí el
            gráfico comparativo y tocá la estrellita en cualquier producto para empezar a seguirlo.
          </p>
        </div>
      )}

      {listas.map((lista) => (
        <div key={lista.id} className="card overflow-hidden">
          <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-slate-100 dark:border-slate-800">
            <ClipboardList size={15} className="text-brand-500 shrink-0" />
            <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 flex-1 truncate">{lista.nombre}</p>
            <span className="text-xs text-slate-400 shrink-0">{lista.items.length} producto(s)</span>
            <button
              onClick={() => eliminarLista(lista.id)}
              disabled={borrando === lista.id}
              className="text-slate-300 hover:text-red-500 dark:text-slate-600 dark:hover:text-red-400 transition-colors shrink-0 disabled:opacity-40"
              title="Eliminar lista"
            >
              <Trash2 size={14} />
            </button>
          </div>

          {lista.items.length === 0 ? (
            <p className="text-xs text-slate-400 text-center py-6">Esta lista todavía no tiene productos.</p>
          ) : (
            <div className="divide-y divide-slate-50 dark:divide-slate-800">
              {lista.items.map((item) => (
                <div key={item.id} className="flex items-center gap-3 px-5 py-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{item.nombre}</p>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <CadenaBadge tienda={item.tienda} />
                      {item.sucursal_nombre && (
                        <span className="text-[11px] text-slate-500 dark:text-slate-400">{item.sucursal_nombre}</span>
                      )}
                      <span className="text-[11px] text-slate-400">
                        Último chequeo: {formatFecha(item.ultimo_chequeo)}
                      </span>
                    </div>
                  </div>
                  <span className="text-sm font-bold text-slate-900 dark:text-slate-100 shrink-0">
                    {fMoneyByCurrency(item.precio_actual, item.moneda)}
                  </span>
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-slate-400 hover:text-brand-600 dark:hover:text-brand-400 transition-colors shrink-0"
                    title="Ver en la tienda"
                  >
                    <ExternalLink size={14} />
                  </a>
                  <button
                    onClick={() => eliminarItem(lista.id, item.id)}
                    className="text-slate-300 hover:text-red-500 dark:text-slate-600 dark:hover:text-red-400 transition-colors shrink-0"
                    title="Dejar de seguir"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

"use client";
import { useCallback, useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { preciosApi, type CompararGrupo, type CompararTiendaItem } from "@/lib/api";
import { fMoneyExact } from "@/lib/format";
import { Search, ExternalLink, ArrowRight, Scale } from "lucide-react";
import { toast } from "sonner";
import Link from "next/link";

const TIENDA_COLORS: Record<string, string> = {
  "Disco":           "bg-blue-50 text-blue-700 border-blue-100",
  "Devoto":          "bg-green-50 text-green-700 border-green-100",
  "Géant":           "bg-purple-50 text-purple-700 border-purple-100",
  "Ta-Ta":           "bg-red-50 text-red-700 border-red-100",
  "Farmashop":       "bg-orange-50 text-orange-700 border-orange-100",
  "Tienda Inglesa":  "bg-teal-50 text-teal-700 border-teal-100",
};

function TiendaCard({ item, minPrecio }: { item: CompararTiendaItem; minPrecio: number }) {
  const cls = TIENDA_COLORS[item.tienda] ?? "bg-slate-50 text-slate-600 border-slate-100";
  const isCheapest = item.precio !== null && item.precio === minPrecio;
  const hasDesc = item.precio_lista !== null && item.precio_lista > (item.precio ?? 0);
  const pct = hasDesc ? Math.round((1 - (item.precio ?? 0) / item.precio_lista!) * 100) : 0;

  return (
    <div className={`rounded-xl border p-3 flex flex-col gap-1 ${cls} ${isCheapest ? "ring-2 ring-emerald-400" : ""}`}>
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-bold uppercase tracking-wide">{item.tienda}</span>
        {isCheapest && (
          <span className="text-[10px] font-bold bg-emerald-500 text-white px-1.5 py-0.5 rounded-full">
            + barato
          </span>
        )}
      </div>
      <div className="flex items-center gap-1.5 mt-0.5">
        {hasDesc && (
          <span className="text-[10px] font-bold bg-red-100 text-red-600 px-1 py-0.5 rounded">
            -{pct}%
          </span>
        )}
        <span className="text-base font-bold">
          {item.precio !== null ? fMoneyExact(item.precio) : "—"}
        </span>
      </div>
      {hasDesc && (
        <span className="text-[11px] text-current/60 line-through">
          {fMoneyExact(item.precio_lista!)}
        </span>
      )}
      <a
        href={item.url}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-1 flex items-center gap-1 text-[11px] opacity-60 hover:opacity-100 transition-opacity"
      >
        Ver <ExternalLink size={10} />
      </a>
    </div>
  );
}

function GrupoRow({ grupo }: { grupo: CompararGrupo }) {
  const precios = grupo.tiendas.map((t) => t.precio).filter((p): p is number => p !== null);
  const minPrecio = precios.length ? Math.min(...precios) : 0;
  const maxPrecio = precios.length ? Math.max(...precios) : 0;
  const ahorro = minPrecio > 0 && maxPrecio > minPrecio
    ? Math.round((1 - minPrecio / maxPrecio) * 100)
    : 0;

  return (
    <div className="card p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-200 leading-tight">
            {grupo.nombre_ref ?? "—"}
          </p>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
            Barcode: {grupo.barcode} · {grupo.n_tiendas} tiendas
          </p>
        </div>
        {ahorro > 0 && (
          <div className="shrink-0 text-right">
            <span className="text-xs text-slate-500 dark:text-slate-400">diferencia</span>
            <p className="text-sm font-bold text-emerald-600">-{ahorro}%</p>
          </div>
        )}
      </div>

      <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${grupo.tiendas.length}, 1fr)` }}>
        {grupo.tiendas.map((t) => (
          <TiendaCard key={t.tienda} item={t} minPrecio={minPrecio} />
        ))}
      </div>
    </div>
  );
}

function CompararContent() {
  const searchParams = useSearchParams();
  const barcodeParam = searchParams.get("barcode");

  const [q,        setQ]        = useState(barcodeParam ?? "");
  const [grupos,   setGrupos]   = useState<CompararGrupo[]>([]);
  const [loading,  setLoading]  = useState(false);
  const [searched, setSearched] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const search = useCallback(async (query: string) => {
    if (!query.trim()) {
      setGrupos([]);
      setSearched(false);
      return;
    }
    setLoading(true);
    setSearched(true);
    try {
      const params = barcodeParam && query === barcodeParam
        ? { barcode: query, limit: 50 }
        : { q: query, limit: 50 };
      const { data } = await preciosApi.comparar(params);
      setGrupos(data.grupos);
    } catch {
      toast.error("Error al buscar");
    } finally {
      setLoading(false);
    }
  }, [barcodeParam]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const delay = barcodeParam ? 0 : 500;
    debounceRef.current = setTimeout(() => search(q), delay);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [q, search, barcodeParam]);

  return (
    <div className="p-6 lg:p-8 max-w-5xl mx-auto space-y-5">

      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="section-title flex items-center gap-2">
            <Scale size={17} className="text-brand-600" />
            Comparar precios entre tiendas
          </h1>
          <p className="section-sub mt-0.5">
            Busca un producto para ver su precio en cada supermercado
          </p>
        </div>
        <Link href="/precios" className="btn-secondary text-xs px-3 py-1.5 shrink-0">
          <ArrowRight size={13} className="rotate-180" />
          Catálogo
        </Link>
      </div>

      <div className="card p-4">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar producto para comparar (ej: leche, jabón, yerba…)"
            className="input pl-8 text-sm"
            autoFocus
          />
        </div>
      </div>

      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card p-4 h-32 animate-pulse bg-slate-50" />
          ))}
        </div>
      )}

      {!loading && searched && grupos.length === 0 && (
        <div className="card p-12 text-center">
          <p className="text-slate-400 dark:text-slate-500 text-sm">
            Sin productos que aparezcan en más de una tienda para esa búsqueda.
          </p>
          <p className="text-slate-300 dark:text-slate-600 text-xs mt-1">
            La comparación requiere barcode coincidente entre tiendas.
          </p>
        </div>
      )}

      {!loading && grupos.length > 0 && (
        <>
          <p className="text-xs text-slate-400 dark:text-slate-500">{grupos.length} productos comparables encontrados</p>
          <div className="space-y-3">
            {grupos.map((g) => <GrupoRow key={g.barcode} grupo={g} />)}
          </div>
        </>
      )}
    </div>
  );
}

export default function CompararPage() {
  return (
    <Suspense fallback={<div className="p-8 text-slate-400 text-sm">Cargando…</div>}>
      <CompararContent />
    </Suspense>
  );
}

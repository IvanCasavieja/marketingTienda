"use client";
import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import { watchlistApi, type WatchlistConItems } from "@/lib/api";

interface ProductoParaMatch {
  tienda: string;
  sku: string | null;
  nombre: string;
}

interface WatchlistsContextValue {
  listas: WatchlistConItems[];
  loading: boolean;
  refrescar: () => Promise<void>;
  listasConProducto: (producto: ProductoParaMatch) => Set<number>;
}

const WatchlistsContext = createContext<WatchlistsContextValue | null>(null);

// Mismo criterio que watchlist_service.py del lado del backend: match por sku
// si el producto lo tiene, si no por nombre exacto (case-insensitive) — DIMM
// y Stienda son las únicas cadenas sin sku.
function coincide(item: { tienda: string; sku: string | null; nombre: string }, producto: ProductoParaMatch): boolean {
  if (item.tienda !== producto.tienda) return false;
  if (producto.sku) return item.sku === producto.sku;
  return item.nombre.trim().toLowerCase() === producto.nombre.trim().toLowerCase();
}

// Se carga una sola vez por página (no una vez por fila) y se comparte entre
// todos los <SeguirButton> montados — así la estrellita refleja de entrada
// qué está guardado de verdad (persistido por usuario), no solo lo que se
// tocó en esta sesión.
export function WatchlistsProvider({ children }: { children: ReactNode }) {
  const [listas, setListas] = useState<WatchlistConItems[]>([]);
  const [loading, setLoading] = useState(true);

  const refrescar = useCallback(async () => {
    try {
      const { data } = await watchlistApi.listar();
      setListas(data);
    } catch {
      // silencioso — el feature de seguir queda inerte pero no rompe la página
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refrescar();
  }, [refrescar]);

  function listasConProducto(producto: ProductoParaMatch): Set<number> {
    const ids = new Set<number>();
    for (const l of listas) {
      if (l.items.some((it) => coincide(it, producto))) ids.add(l.id);
    }
    return ids;
  }

  return (
    <WatchlistsContext.Provider value={{ listas, loading, refrescar, listasConProducto }}>
      {children}
    </WatchlistsContext.Provider>
  );
}

export function useWatchlists(): WatchlistsContextValue {
  const ctx = useContext(WatchlistsContext);
  if (!ctx) throw new Error("useWatchlists debe usarse dentro de <WatchlistsProvider>");
  return ctx;
}

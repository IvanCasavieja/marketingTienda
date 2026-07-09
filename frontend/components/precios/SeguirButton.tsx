"use client";
import { useState } from "react";
import { watchlistApi } from "@/lib/api";
import { useWatchlists } from "@/components/precios/WatchlistsContext";
import { Star, Plus, Check } from "lucide-react";
import { toast } from "sonner";

interface ProductoParaSeguir {
  tienda: string;
  sku: string | null;
  nombre: string;
  termino_busqueda: string;
  url: string;
  precio: number;
  moneda: string;
  // Ta-Ta/ElDorado/GDU tienen precio distinto por sucursal — sin esto el
  // monitoreo diario no sabe cuál de las ~15-17 sucursales seguir.
  sucursal_id?: string | null;
  sucursal_nombre?: string | null;
}

export default function SeguirButton({ producto }: { producto: ProductoParaSeguir }) {
  const { listas, refrescar, listasConProducto } = useWatchlists();
  const [open, setOpen] = useState(false);
  const [nuevoNombre, setNuevoNombre] = useState("");
  const [creandoNueva, setCreandoNueva] = useState(false);
  const [agregandoA, setAgregandoA] = useState<number | null>(null);

  // Se recalcula en cada render a partir del estado compartido (WatchlistsContext)
  // — refleja lo que de verdad está guardado para este usuario, no una bandera
  // local que solo recuerda lo que se tocó en esta sesión.
  const idsConProducto = listasConProducto(producto);
  const yaGuardado = idsConProducto.size > 0;

  async function agregarA(watchlistId: number) {
    if (idsConProducto.has(watchlistId)) {
      toast.info("Ya está en esta lista");
      return;
    }
    setAgregandoA(watchlistId);
    try {
      await watchlistApi.agregarItem(watchlistId, {
        tienda: producto.tienda, sku: producto.sku, nombre: producto.nombre,
        termino_busqueda: producto.termino_busqueda, url: producto.url,
        precio: producto.precio, moneda: producto.moneda,
        sucursal_id: producto.sucursal_id, sucursal_nombre: producto.sucursal_nombre,
      });
      await refrescar();
      toast.success("Agregado a la lista de monitoreo");
    } catch {
      toast.error("No se pudo agregar el producto");
    } finally {
      setAgregandoA(null);
    }
  }

  async function crearYAgregar() {
    const nombre = nuevoNombre.trim();
    if (!nombre) return;
    setCreandoNueva(true);
    try {
      const { data: nueva } = await watchlistApi.crear(nombre);
      await watchlistApi.agregarItem(nueva.id, {
        tienda: producto.tienda, sku: producto.sku, nombre: producto.nombre,
        termino_busqueda: producto.termino_busqueda, url: producto.url,
        precio: producto.precio, moneda: producto.moneda,
        sucursal_id: producto.sucursal_id, sucursal_nombre: producto.sucursal_nombre,
      });
      await refrescar();
      setNuevoNombre("");
      setOpen(false);
      toast.success("Lista creada y producto agregado");
    } catch {
      toast.error("No se pudo crear la lista");
    } finally {
      setCreandoNueva(false);
    }
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className={`transition-colors shrink-0 ${
          yaGuardado ? "text-amber-500" : "text-slate-300 hover:text-amber-500 dark:text-slate-600 dark:hover:text-amber-400"
        }`}
        title={yaGuardado ? "Ya seguís este producto — tocá para agregarlo a otra lista" : "Seguir este producto"}
      >
        <Star size={14} fill={yaGuardado ? "currentColor" : "none"} />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 z-50 w-56 bg-white dark:bg-slate-900 rounded-xl shadow-lg border border-slate-200 dark:border-slate-700 p-2.5 text-left">
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide px-1 mb-1.5">Agregar a lista</p>
          {producto.sucursal_nombre && (
            <p className="text-[11px] text-slate-500 dark:text-slate-400 px-1 mb-1.5 leading-snug">
              Vas a seguir el precio de <span className="font-medium text-slate-700 dark:text-slate-300">{producto.sucursal_nombre}</span> — no el de otras sucursales.
            </p>
          )}
          <div className="space-y-0.5 max-h-40 overflow-y-auto mb-2">
            {listas.length === 0 && (
              <p className="text-xs text-slate-400 px-1 py-1">No tenés listas todavía.</p>
            )}
            {listas.map((l) => {
              const yaEnEsta = idsConProducto.has(l.id);
              return (
                <button
                  key={l.id}
                  onClick={() => agregarA(l.id)}
                  disabled={yaEnEsta || agregandoA === l.id}
                  className={`w-full flex items-center justify-between gap-2 text-left text-xs px-2 py-1.5 rounded-lg truncate transition-colors ${
                    yaEnEsta
                      ? "text-emerald-600 dark:text-emerald-400 cursor-default"
                      : "hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300"
                  }`}
                >
                  <span className="truncate">{l.nombre}</span>
                  {yaEnEsta && <Check size={12} className="shrink-0" />}
                </button>
              );
            })}
          </div>
          <div className="flex gap-1.5 border-t border-slate-100 dark:border-slate-800 pt-2">
            <input
              value={nuevoNombre}
              onChange={(e) => setNuevoNombre(e.target.value)}
              placeholder="Nueva lista..."
              className="flex-1 text-xs bg-slate-100 dark:bg-slate-800 rounded-lg px-2 py-1.5 text-slate-800 dark:text-slate-200 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
            />
            <button
              onClick={crearYAgregar}
              disabled={!nuevoNombre.trim() || creandoNueva}
              className="w-7 h-7 rounded-lg bg-brand-600 text-white flex items-center justify-center disabled:opacity-40 hover:bg-brand-700 transition-colors shrink-0"
            >
              <Plus size={13} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

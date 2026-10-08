"use client";
import { useState } from "react";
import { ArrowDown, ArrowUp, Plus, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { redexpresApi } from "@/lib/api";
import { CAMPOS_FIJOS, COLORES_GRUPO, type Estructura } from "@/lib/redexpres/estructura";

const NOMBRE_MES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

function mover<T>(lista: T[], i: number, d: -1 | 1): T[] {
  const j = i + d;
  if (j < 0 || j >= lista.length) return lista;
  const copia = [...lista];
  [copia[i], copia[j]] = [copia[j], copia[i]];
  return copia;
}

/**
 * Editor de la planilla del mes (Ivan, 08/10/2026): quien gestiona Redexpres
 * agrega, renombra, mueve o saca grupos y columnas y cambia los topes, para
 * dejar lista la planilla que completan las sucursales. Sacar una columna NO
 * borra lo que ya se cargó en ella: solo deja de mostrarse.
 */
export default function EditorPlanilla({
  year, month, inicial, onGuardado, onCerrar,
}: {
  year: number;
  month: number;
  inicial: Estructura;
  onGuardado: () => void;
  onCerrar: () => void;
}) {
  const [est, setEst] = useState<Estructura>(() => JSON.parse(JSON.stringify(inicial)));
  const [guardando, setGuardando] = useState(false);

  const setGrupo = (gi: number, parche: object) =>
    setEst((e) => ({ grupos: e.grupos.map((g, i) => (i === gi ? { ...g, ...parche } : g)) }));
  const setCol = (gi: number, ci: number, parche: object) =>
    setEst((e) => ({ grupos: e.grupos.map((g, i) => (i !== gi ? g : { ...g, cols: g.cols.map((c, j) => (j === ci ? { ...c, ...parche } : c)) })) }));

  async function guardar() {
    setGuardando(true);
    try {
      await redexpresApi.putEstructura(year, month, est);
      toast.success("Planilla guardada");
      onGuardado();
      onCerrar();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "No se pudo guardar la planilla");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onCerrar}>
      <div
        role="dialog" aria-modal="true"
        className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-slate-800">
          <div>
            <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
              Editar planilla de {NOMBRE_MES[month]} {year}
            </p>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Los cambios valen solo para este mes. Un mes nuevo arranca igual al anterior. Sacar una columna no borra lo que ya cargaron las sucursales.
            </p>
          </div>
          <button onClick={onCerrar} aria-label="Cerrar" className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"><X size={18} /></button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {est.grupos.map((g, gi) => (
            <div key={gi} className="card p-3 space-y-2">
              <div className="flex items-center gap-2 flex-wrap">
                <input
                  value={g.label} onChange={(e) => setGrupo(gi, { label: e.target.value })}
                  placeholder="Nombre del grupo" className="input text-sm font-semibold w-56"
                />
                <select value={g.color} onChange={(e) => setGrupo(gi, { color: e.target.value })} className="input text-xs w-28">
                  {Object.keys(COLORES_GRUPO).map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
                <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded-lg ${COLORES_GRUPO[g.color] ?? COLORES_GRUPO.slate}`}>{g.label || "…"}</span>
                <div className="ml-auto flex items-center gap-1">
                  <button title="Subir grupo" onClick={() => setEst((e) => ({ grupos: mover(e.grupos, gi, -1) }))} className="btn-secondary p-1.5"><ArrowUp size={13} /></button>
                  <button title="Bajar grupo" onClick={() => setEst((e) => ({ grupos: mover(e.grupos, gi, 1) }))} className="btn-secondary p-1.5"><ArrowDown size={13} /></button>
                  <button
                    title="Sacar grupo"
                    onClick={() => { if (confirm(`¿Sacar el grupo «${g.label}» con sus ${g.cols.length} columnas de este mes? Lo ya cargado no se borra.`)) setEst((e) => ({ grupos: e.grupos.filter((_, i) => i !== gi) })); }}
                    className="btn-secondary p-1.5 text-red-500"
                  ><Trash2 size={13} /></button>
                </div>
              </div>

              {g.cols.map((c, ci) => (
                <div key={ci} className="flex items-center gap-2 flex-wrap pl-3">
                  <input value={c.label} onChange={(e) => setCol(gi, ci, { label: e.target.value })} placeholder="Nombre de la columna" className="input text-sm w-64" />
                  {c.texto ? (
                    <span className="text-[11px] text-slate-400 w-28">Texto libre</span>
                  ) : (
                    <label className="flex items-center gap-1 text-[11px] text-slate-500">
                      Tope
                      <input
                        type="number" min={0} value={c.max ?? ""} placeholder="sin tope"
                        onChange={(e) => setCol(gi, ci, { max: e.target.value === "" ? undefined : Number(e.target.value) })}
                        className="input text-sm w-24"
                      />
                    </label>
                  )}
                  {!CAMPOS_FIJOS.has(c.key) && (
                    <label className="flex items-center gap-1 text-[11px] text-slate-500">
                      <input type="checkbox" checked={!!c.texto} onChange={(e) => setCol(gi, ci, { texto: e.target.checked || undefined, max: undefined })} />
                      Es texto
                    </label>
                  )}
                  <div className="ml-auto flex items-center gap-1">
                    <button title="Subir" onClick={() => setGrupo(gi, { cols: mover(g.cols, ci, -1) })} className="btn-secondary p-1.5"><ArrowUp size={12} /></button>
                    <button title="Bajar" onClick={() => setGrupo(gi, { cols: mover(g.cols, ci, 1) })} className="btn-secondary p-1.5"><ArrowDown size={12} /></button>
                    <button title="Sacar columna" onClick={() => setGrupo(gi, { cols: g.cols.filter((_, j) => j !== ci) })} className="btn-secondary p-1.5 text-red-500"><Trash2 size={12} /></button>
                  </div>
                </div>
              ))}

              <button
                onClick={() => setGrupo(gi, { cols: [...g.cols, { key: "", label: "", max: 100 }] })}
                className="text-xs text-brand-600 dark:text-brand-400 flex items-center gap-1 pl-3"
              ><Plus size={12} /> Agregar columna</button>
            </div>
          ))}

          <button
            onClick={() => setEst((e) => ({ grupos: [...e.grupos, { id: "", label: "", color: "slate", cols: [] }] }))}
            className="btn-secondary text-xs flex items-center gap-1.5"
          ><Plus size={13} /> Agregar grupo</button>
        </div>

        <div className="flex justify-end gap-2 px-5 py-3 border-t border-slate-100 dark:border-slate-800">
          <button onClick={onCerrar} className="btn-secondary text-xs">Cancelar</button>
          <button onClick={guardar} disabled={guardando} className="btn-primary text-xs disabled:opacity-50">
            {guardando ? "Guardando…" : "Guardar planilla"}
          </button>
        </div>
      </div>
    </div>
  );
}

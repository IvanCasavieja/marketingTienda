'use client'

import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Check, Plus, X } from 'lucide-react'
import { camposVisibles, linkValido, type TipoDeTarea } from '@/lib/calendario/tipos-de-tarea'
import { useDialogo } from './useDialogo'

/**
 * Lo que se tilda de un tipo de pedido (Banners: Header, Slider…; el CTA; los
 * bloques del mailing), en «Nueva tarea». Antes estaba en «Pedir una pieza»,
 * que desde el 24/11/2026 es la misma «Nueva tarea» (una tarea = un pedido).
 *
 * El catálogo (los tipos, las opciones y sus medidas) lo manda el servidor:
 * se edita en un solo lugar (backend/app/services/tipos_de_tarea.py).
 */

/**
 * Las opciones de un tipo de pieza en un modal en el centro de la pantalla.
 *
 * Ivan (17/11/2026): "si aprieto banners que se abra un modal en el centro
 * que me dé todas las opciones de banners a marcar, y así con todo". Va con
 * portal al <body> (o al calendario en pantalla completa, donde el navegador
 * muestra solo ese elemento): adentro de la ficha, que se anima con
 * transform, un `fixed` quedaba atado a la ficha y no a la pantalla.
 */
export function ModalDeOpciones({ tipo, opciones, detalles, onAlternar, onAgregarOtra, onDetalle, onCerrar }: {
  tipo: TipoDeTarea
  opciones: string[]
  detalles: Record<string, string>
  onAlternar: (opcion: string) => void
  onAgregarOtra: (texto: string) => void
  onDetalle: (clave: string, valor: string) => void
  onCerrar: () => void
}) {
  const cajaRef = useRef<HTMLDivElement>(null)
  const [otra, setOtra] = useState('')
  useDialogo(true, cajaRef)

  // Escape cierra el modal y nada más: va en la captura y corta ahí, así la
  // ficha y el pedido de abajo se quedan abiertos (como en DialogoPlantillas).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.stopPropagation()
      e.preventDefault()
      onCerrar()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [onCerrar])

  function agregar() {
    onAgregarOtra(otra)
    setOtra('')
  }

  const extras = opciones.filter(o => !tipo.opciones.some(x => x.nombre === o))
  const destino = typeof document === 'undefined' ? null : (document.fullscreenElement ?? document.body)
  if (!destino) return null

  return createPortal(
    // z-[70]: por encima de la ficha (z-50) y de las plantillas (z-[60]).
    <div className="fixed inset-0 z-[70] flex items-end justify-center sm:items-center sm:p-4">
      <div className="velo animate-fade-in" onClick={onCerrar} aria-hidden />
      <div
        ref={cajaRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="opciones-del-tipo"
        tabIndex={-1}
        className="relative flex max-h-[92dvh] w-full max-w-2xl animate-sheet-up flex-col overflow-hidden rounded-t-3xl bg-white shadow-panel outline-none dark:bg-slate-900 dark:ring-1 dark:ring-slate-800 sm:animate-scale-in sm:rounded-2xl"
      >
        <div className="flex items-start gap-3 border-b border-slate-200 px-5 py-4 dark:border-slate-800">
          <div className="min-w-0 flex-1">
            <h2 id="opciones-del-tipo" className="text-lg font-bold text-slate-900 dark:text-slate-100">{tipo.nombre}</h2>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              {tipo.opciones.length > 0 ? 'Tildá todo lo que hace falta.' : 'Completá lo que haga falta.'}
            </p>
            {tipo.bajada && <p className="mt-1.5 rounded-lg bg-amber-50 px-2.5 py-1.5 text-xs text-amber-900 dark:bg-amber-500/10 dark:text-amber-100">{tipo.bajada}</p>}
          </div>
          <button type="button" onClick={onCerrar} aria-label="Cerrar" className="-mr-1.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto overscroll-contain px-5 py-4">
          {(tipo.opciones.length > 0 || extras.length > 0) && (
            <ul className="grid gap-1.5 sm:grid-cols-2">
              {tipo.opciones.map(o => {
                const si = opciones.includes(o.nombre)
                return (
                  <li key={o.nombre}>
                    <label className={`flex min-h-[48px] cursor-pointer items-start gap-2.5 rounded-xl border px-3 py-2.5 transition ${
                      si ? 'border-brand-400 bg-brand-50 dark:border-brand-500/50 dark:bg-brand-500/10' : 'border-slate-300 hover:border-slate-400 dark:border-slate-700'
                    }`}>
                      {/* El tilde real es invisible: con el teclado, el foco se
                          pinta en la casilla dibujada. */}
                      <input type="checkbox" checked={si} onChange={() => onAlternar(o.nombre)} className="peer sr-only" />
                      <span aria-hidden className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border-2 peer-focus-visible:ring-2 peer-focus-visible:ring-brand-500 peer-focus-visible:ring-offset-2 dark:peer-focus-visible:ring-offset-slate-900 ${
                        si ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-500 dark:border-slate-500'
                      }`}>{si && <Check className="h-3.5 w-3.5" strokeWidth={3} />}</span>
                      <span className="min-w-0">
                        <span className="block text-sm font-semibold text-slate-900 dark:text-slate-100">{o.nombre}</span>
                        {o.medida && <span className="block text-xs text-slate-600 dark:text-slate-400">{o.medida}</span>}
                      </span>
                    </label>
                  </li>
                )
              })}
              {extras.map(o => (
                <li key={o}>
                  <span className="flex min-h-[48px] items-center gap-2 rounded-xl border border-brand-400 bg-brand-50 px-3 text-sm font-semibold text-slate-900 dark:border-brand-500/50 dark:bg-brand-500/10 dark:text-slate-100">
                    <span className="min-w-0 flex-1 truncate">{o}</span>
                    <button type="button" onClick={() => onAlternar(o)} aria-label={`Sacar ${o}`} className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-slate-500 hover:bg-white dark:text-slate-400 dark:hover:bg-slate-800">
                      <X className="h-4 w-4" />
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}

          {tipo.otras && (
            <div className="flex gap-2">
              <input value={otra} onChange={e => setOtra(e.target.value)} maxLength={80}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); agregar() } }}
                placeholder="Otra (escribila)" aria-label={`Otra opción de ${tipo.nombre}`} className="campo flex-1" />
              <button type="button" onClick={agregar} disabled={!otra.trim()}
                className="flex min-h-[44px] items-center gap-1 rounded-xl border border-slate-300 bg-white px-3 text-sm font-semibold text-slate-700 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200 sm:min-h-[40px]">
                <Plus className="h-4 w-4" /> Agregar
              </button>
            </div>
          )}

          {camposVisibles(tipo, opciones).map(c => (
            <label key={c.clave} className="block">
              <span className="etiqueta-campo">{c.nombre} (opcional)</span>
              {c.opciones ? (
                <select value={detalles[c.clave] ?? ''} onChange={e => onDetalle(c.clave, e.target.value)} className="campo">
                  <option value="">—</option>
                  {c.opciones.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              ) : c.tipo === 'texto' ? (
                <input value={detalles[c.clave] ?? ''} maxLength={c.largo ?? 300}
                  onChange={e => onDetalle(c.clave, e.target.value)} className="campo" />
              ) : c.tipo === 'link' ? (
                <>
                  <input type="url" inputMode="url" value={detalles[c.clave] ?? ''} maxLength={1000} placeholder="https://"
                    onChange={e => onDetalle(c.clave, e.target.value)} className="campo" />
                  {detalles[c.clave]?.trim() && !linkValido(detalles[c.clave]) && (
                    <span className="mt-1 block text-xs text-amber-700 dark:text-amber-300">Tiene que empezar con https://</span>
                  )}
                </>
              ) : c.tipo === 'fechaHora' ? (
                <input type="datetime-local" min="2000-01-01T00:00" max="2100-12-31T23:59" value={detalles[c.clave] ?? ''}
                  onChange={e => onDetalle(c.clave, e.target.value)} className="campo !w-auto" />
              ) : (
                <input type="number" inputMode="numeric" min={c.minimo} max={c.maximo} value={detalles[c.clave] ?? ''}
                  onChange={e => onDetalle(c.clave, e.target.value)} className="campo !w-32" />
              )}
            </label>
          ))}
        </div>

        <div className="flex items-center gap-3 border-t border-slate-200 px-5 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] dark:border-slate-800">
          <p className="mr-auto text-sm text-slate-600 dark:text-slate-400">
            {tipo.opciones.length === 0 && !tipo.otras
              ? 'Todo es opcional'
              : opciones.length === 0 ? 'Nada elegido todavía' : opciones.length === 1 ? '1 elegida' : `${opciones.length} elegidas`}
          </p>
          <button
            type="button"
            onClick={onCerrar}
            className="min-h-[44px] rounded-xl bg-brand-600 px-5 text-sm font-bold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.98]"
          >
            Listo
          </button>
        </div>
      </div>
    </div>,
    destino,
  )
}

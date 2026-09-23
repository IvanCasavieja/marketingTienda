'use client'

import { useEffect, useState } from 'react'
import { AlertTriangle, ChevronLeft, ChevronRight, LayoutPanelTop, Lock, Settings2, X } from 'lucide-react'
import { textoSobre } from '@/lib/calendario/colores'
import { diaDeHoy, nombreMes } from '@/lib/calendario/fechas'
import { headerEnFecha, ocupacionHeader, useCalendario } from '@/lib/calendario/store'
import { usePermisosCalendario } from '@/lib/calendario/permisos'
import { REGLAS_HEADER } from '@/lib/calendario/tipos'

const TONO_ESTADO = {
  ok: 'bg-emerald-100 dark:bg-emerald-900/50 text-emerald-800 dark:text-emerald-200',
  tolerable: 'bg-amber-200 dark:bg-amber-800/70 text-amber-900 dark:text-amber-100',
  excedido: 'bg-rose-500 text-white',
} as const

/**
 * Los headers activos en UNA fecha, en una lista para abajo.
 *
 * Antes esto era una rejilla de 10 posiciones por 31 días: para saber qué se
 * está viendo hoy en la home había que buscar una columna entre treinta. La
 * pregunta real es "¿qué hay puesto tal día?", así que el panel arranca por la
 * fecha y muestra las diez posiciones una abajo de la otra.
 */
export function PanelHeaders({ abierto, onCerrar }: { abierto: boolean; onCerrar: () => void }) {
  const mes = useCalendario(s => s.meses[s.mesActivo])
  const abrirEditor = useCalendario(s => s.abrirEditor)
  const abrirAccion = useCalendario(s => s.abrirAccion)
  const moverPosicionesRM = useCalendario(s => s.moverPosicionesRM)
  const { editable, moverRM: puedeMover } = usePermisosCalendario()

  const [dia, setDia] = useState(() => diaDeHoy(mes.clave) ?? 1)
  const [ajustandoRM, setAjustandoRM] = useState(false)

  // Al cambiar de mes, la fecha elegida puede no existir (un 31 en un mes de 30)
  useEffect(() => {
    setDia(d => Math.min(Math.max(d, 1), mes.dias))
  }, [mes.clave, mes.dias])

  useEffect(() => {
    if (!abierto) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onCerrar() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [abierto, onCerrar])

  const posiciones = headerEnFecha(mes, dia)
  const ocupadas = posiciones.filter(p => p.barra).length
  const estado = ocupadas > REGLAS_HEADER.tolerable ? 'excedido'
    : ocupadas > REGLAS_HEADER.ideal ? 'tolerable' : 'ok'
  const ocupacion = ocupacionHeader(mes)
  const noEntran = mes.sinLugar.filter(s => s.desde <= dia && dia <= s.hasta)

  function irAAccion(accionId: string) {
    for (const banda of mes.comercial) {
      for (let i = 0; i < banda.filas.length; i++) {
        if (banda.filas[i].some(b => b.id === accionId)) {
          abrirAccion({ bandaId: banda.id, filaIdx: i, barraId: accionId })
          onCerrar()
          return
        }
      }
    }
  }

  function cambiarPosicionRM(indice: number, valor: number) {
    const siguiente = [...mes.posicionesRM]
    const yaEstaEn = siguiente.indexOf(valor)
    if (yaEstaEn !== -1) siguiente[yaEstaEn] = siguiente[indice]  // intercambio, nunca duplica
    siguiente[indice] = valor
    moverPosicionesRM(siguiente)
  }

  return (
    <>
      <div
        onClick={onCerrar}
        className={`fixed inset-0 z-40 bg-slate-900/30 transition-opacity duration-300 ${
          abierto ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
      />
      <aside
        className={`fixed right-0 top-0 z-50 flex h-full w-full max-w-[520px] flex-col bg-white dark:bg-slate-900 shadow-2xl transition-transform duration-300 ease-out ${
          abierto ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <header className="shrink-0 border-b border-slate-200 dark:border-slate-700 bg-slate-900 px-5 py-4 text-white">
          <div className="flex items-start gap-3">
            <LayoutPanelTop className="mt-0.5 h-5 w-5 shrink-0" />
            <div className="min-w-0 flex-1">
              <h2 className="text-base font-semibold leading-tight">Headers activos por fecha</h2>
              <p className="text-xs text-slate-300">Las {REGLAS_HEADER.tope} posiciones de la home, tal como quedan ese día.</p>
            </div>
            <button onClick={onCerrar} aria-label="Cerrar" className="shrink-0 rounded-md p-1 transition hover:bg-white/10">
              <X className="h-4 w-4" />
            </button>
          </div>
        </header>

        {/* Selector de fecha */}
        <div className="shrink-0 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/40 px-5 py-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setDia(d => Math.max(1, d - 1))}
              disabled={dia <= 1}
              aria-label="Día anterior"
              className="rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-1.5 text-slate-500 dark:text-slate-400 transition hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-30"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <select
              value={dia}
              onChange={e => setDia(Number(e.target.value))}
              aria-label="Día"
              className="flex-1 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm font-semibold text-slate-900 dark:text-slate-100 outline-none"
            >
              {Array.from({ length: mes.dias }, (_, i) => i + 1).map(d => (
                <option key={d} value={d}>
                  {d} de {nombreMes(mes.clave)} · {ocupacion[d - 1]?.cantidad ?? 0} en el header
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => setDia(d => Math.min(mes.dias, d + 1))}
              disabled={dia >= mes.dias}
              aria-label="Día siguiente"
              className="rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-1.5 text-slate-500 dark:text-slate-400 transition hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-30"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-2.5 flex items-center gap-2">
            <span className={`rounded-md px-2 py-1 text-[11px] font-bold ${TONO_ESTADO[estado]}`}>
              {ocupadas} de {REGLAS_HEADER.tope} ocupadas
            </span>
            <span className="text-[11px] text-slate-500 dark:text-slate-400">
              ideal {REGLAS_HEADER.ideal} · tolerable {REGLAS_HEADER.tolerable}
            </span>
            {puedeMover && (
              <button
                type="button"
                onClick={() => setAjustandoRM(v => !v)}
                className="ml-auto flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] font-medium text-slate-500 dark:text-slate-400 transition hover:bg-slate-200 dark:hover:bg-slate-700"
              >
                <Settings2 className="h-3 w-3" /> posiciones de RM
              </button>
            )}
            {!puedeMover && (
              <span className="ml-auto flex items-center gap-1 text-[11px] text-slate-400 dark:text-slate-500">
                <Lock className="h-3 w-3" /> RM en {mes.posicionesRM.join(', ')}
              </span>
            )}
          </div>

          {ajustandoRM && puedeMover && (
            <div className="mt-2.5 flex flex-wrap items-center gap-2 rounded-lg bg-violet-50 dark:bg-violet-950/40 p-2.5">
              <span className="text-[11px] font-medium text-violet-900 dark:text-violet-200">Retail Media ocupa:</span>
              {mes.posicionesRM.map((pos, i) => (
                <select
                  key={i}
                  value={pos}
                  onChange={e => cambiarPosicionRM(i, Number(e.target.value))}
                  className="rounded-md border border-violet-300 dark:border-violet-700 bg-white dark:bg-slate-900 px-2 py-1 text-xs font-semibold text-violet-900 dark:text-violet-200"
                >
                  {Array.from({ length: REGLAS_HEADER.tope }, (_, n) => n + 1).map(n => (
                    <option key={n} value={n}>Posición {n}</option>
                  ))}
                </select>
              ))}
              <span className="w-full text-[10px] text-violet-700 dark:text-violet-300">
                Al cambiarlas le llega el aviso a quien lleva Retail Media.
              </span>
            </div>
          )}
        </div>

        {/* La lista, para abajo */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {noEntran.length > 0 && (
            <div className="mb-4 rounded-lg border border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/30 px-3 py-2.5">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-rose-800 dark:text-rose-200">
                <AlertTriangle className="h-3.5 w-3.5" />
                {noEntran.length === 1 ? 'Una acción pide header este día y no entra' : `${noEntran.length} acciones piden header este día y no entran`}
              </p>
              <ul className="mt-1 space-y-0.5">
                {noEntran.map(s => (
                  <li key={s.accionId} className="text-[11px] text-rose-700 dark:text-rose-300">
                    <button onClick={() => irAAccion(s.accionId)} className="font-medium underline underline-offset-2">
                      {s.nombre}
                    </button>
                    {' · del '}{s.desde} al {s.hasta}
                  </li>
                ))}
              </ul>
              <p className="mt-1 text-[10px] text-rose-600 dark:text-rose-400">
                El sistema avisa, no decide: qué se baja se resuelve por venta.
              </p>
            </div>
          )}

          <ul className="space-y-1.5">
            {posiciones.map(pos => {
              const b = pos.barra
              const derivada = b?.origen?.tipo === 'retail' || b?.origen?.tipo === 'accion'
              return (
                <li
                  key={pos.numero}
                  className={`flex items-stretch gap-3 rounded-lg border px-3 py-2.5 ${
                    pos.esRM
                      ? 'border-violet-200 dark:border-violet-900 bg-violet-50/60 dark:bg-violet-950/20'
                      : 'border-slate-200 dark:border-slate-700'
                  }`}
                >
                  <div className="flex w-10 shrink-0 flex-col items-center justify-center">
                    <span className="text-lg font-bold leading-none text-slate-800 dark:text-slate-200">{pos.numero}</span>
                    <span className={`mt-0.5 text-[8px] font-semibold uppercase leading-none ${
                      pos.esRM ? 'text-violet-500 dark:text-violet-400' : 'text-slate-400 dark:text-slate-500'
                    }`}>
                      {pos.esRM ? 'RM' : 'Mkt'}
                    </span>
                  </div>

                  {b ? (
                    <button
                      type="button"
                      onClick={() => {
                        if (b.origen?.tipo === 'accion') return irAAccion(b.origen.accionId)
                        if (b.origen?.tipo === 'retail') return
                        abrirEditor({ seccion: 'header', bandaId: mes.header[pos.numero - 1].id, filaIdx: 0, barra: b })
                        onCerrar()
                      }}
                      className="min-w-0 flex-1 text-left"
                    >
                      <span
                        className={`inline-block max-w-full truncate rounded px-2 py-1 text-xs font-semibold ${
                          derivada ? 'border-l-[3px] border-l-slate-900/40' : ''
                        }`}
                        style={{ backgroundColor: b.color ?? '#e2e8f0', color: textoSobre(b.color) }}
                      >
                        {b.nombre}
                      </span>
                      <span className="mt-1 block text-[11px] text-slate-500 dark:text-slate-400">
                        del {b.desde} al {b.hasta}
                        {b.origen?.tipo === 'accion' && ' · viene de su acción'}
                        {b.origen?.tipo === 'retail' && ' · viene de Retail Media'}
                        {(!b.origen || b.origen.tipo === 'manual') && ' · cargado a mano'}
                      </span>
                    </button>
                  ) : editable && !pos.esRM ? (
                    <button
                      type="button"
                      onClick={() => {
                        abrirEditor({ seccion: 'header', bandaId: mes.header[pos.numero - 1].id, filaIdx: 0, barra: null, diaInicial: dia })
                        onCerrar()
                      }}
                      className="flex flex-1 items-center rounded-md border border-dashed border-slate-300 dark:border-slate-600 px-2 py-1.5 text-left text-xs text-slate-400 dark:text-slate-500 transition hover:border-emerald-400 hover:text-emerald-600"
                    >
                      Libre — poner algo este día
                    </button>
                  ) : (
                    <span className="flex flex-1 items-center text-xs text-slate-400 dark:text-slate-500">Libre</span>
                  )}
                </li>
              )
            })}
          </ul>

          <p className="mt-4 rounded-lg bg-slate-50 dark:bg-slate-800/40 px-3 py-2.5 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
            Lo que dice <strong>viene de su acción</strong> o <strong>de Retail Media</strong> no se
            edita acá: tocalo y te lleva a donde sí. Las posiciones de Retail Media tampoco se
            cargan a mano, bajan solas de su calendario.
          </p>
        </div>
      </aside>
    </>
  )
}

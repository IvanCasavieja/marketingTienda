'use client'

import { useEffect, useState } from 'react'
import { AlertTriangle, Check, LayoutPanelTop, Pencil, Plus, X } from 'lucide-react'
import { textoSobre } from '@/lib/calendario/colores'
import { nombreMes } from '@/lib/calendario/fechas'
import { useCalendario } from '@/lib/calendario/store'
import { usePermisosCalendario } from '@/lib/calendario/permisos'
import {
  CATALOGO_PIEZAS, ETIQUETA_ESTADO, esPiezaDeEnvio, esPiezaHeader,
  type AreaPieza, type Barra, type EstadoPieza, type Pieza,
} from '@/lib/calendario/tipos'

const ESTADOS: EstadoPieza[] = ['pendiente', 'en-proceso', 'aprobado', 'publicado']

const TONO_ESTADO: Record<EstadoPieza, string> = {
  pendiente: 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400',
  'en-proceso': 'bg-amber-100 text-amber-800',
  aprobado: 'bg-sky-100 dark:bg-sky-900/40 text-sky-800',
  publicado: 'bg-emerald-100 dark:bg-emerald-900/50 text-emerald-800 dark:text-emerald-200',
}

export function PanelAccion() {
  const abierta = useCalendario(s => s.abierta)
  const mes = useCalendario(s => s.meses[s.mesActivo])
  const cerrar = useCalendario(s => s.cerrarAccion)
  const abrirEditor = useCalendario(s => s.abrirEditor)
  const agregarPieza = useCalendario(s => s.agregarPieza)
  const quitarPieza = useCalendario(s => s.quitarPieza)
  const actualizarPieza = useCalendario(s => s.actualizarPieza)

  const accionViva = useCalendario(s => s.accionAbierta())

  // Se guarda la última acción para que el panel tenga qué pintar mientras sale
  const [ultima, setUltima] = useState<{ accion: Barra; tipo: string } | null>(null)
  useEffect(() => {
    if (!abierta || !accionViva) return
    const banda = mes.comercial.find(b => b.id === abierta.bandaId)
    setUltima({ accion: accionViva, tipo: banda?.nombre ?? '' })
  }, [abierta, accionViva, mes.comercial])

  useEffect(() => {
    if (!abierta) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') cerrar() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [abierta, cerrar])

  const visible = Boolean(abierta && accionViva)
  const datos = visible ? { accion: accionViva!, tipo: ultima?.tipo ?? '' } : ultima
  const { editable } = usePermisosCalendario()

  const piezas = datos?.accion.piezas ?? []
  const publicadas = piezas.filter(p => p.estado === 'publicado').length

  // ¿En qué posición del header quedó esta acción? ¿O no entró?
  const posicionHeader = datos
    ? mes.header.findIndex(pos =>
        pos.filas[0].some(b => b.origen?.tipo === 'accion' && b.origen.accionId === datos.accion.id))
    : -1
  const noEntro = datos ? mes.sinLugar.find(s => s.accionId === datos.accion.id) : undefined

  return (
    <>
      <div
        onClick={cerrar}
        className={`fixed inset-0 z-40 bg-slate-900/30 transition-opacity duration-300 ${
          visible ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
      />
      <aside
        className={`fixed right-0 top-0 z-50 flex h-full w-full max-w-[560px] flex-col bg-white dark:bg-slate-900 shadow-2xl transition-transform duration-300 ease-out ${
          visible ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {datos && (
          <>
            <header
              className="shrink-0 px-5 py-4"
              style={{ backgroundColor: datos.accion.color ?? '#e2e8f0', color: textoSobre(datos.accion.color) }}
            >
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] font-medium uppercase tracking-wide opacity-70">{datos.tipo}</p>
                  <h2 className="mt-0.5 text-lg font-semibold leading-tight">{datos.accion.nombre}</h2>
                  <p className="mt-1 text-xs opacity-80">
                    {datos.accion.desde} al {datos.accion.hasta} de {nombreMes(mes.clave)}
                    {' · '}{datos.accion.hasta - datos.accion.desde + 1} días
                  </p>
                </div>
                <button
                  onClick={cerrar}
                  className="rounded-lg p-1.5 transition hover:bg-black/10"
                  aria-label="Cerrar"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              {editable && abierta && (
                <button
                  onClick={() => abrirEditor({
                    seccion: 'comercial',
                    bandaId: abierta.bandaId,
                    filaIdx: abierta.filaIdx,
                    barra: datos.accion,
                  })}
                  className="mt-3 flex items-center gap-1.5 rounded-lg bg-white/80 px-2.5 py-1.5 text-[11px] font-semibold text-slate-800 dark:text-slate-200 transition hover:bg-white"
                >
                  <Pencil className="h-3 w-3" /> Editar nombre, fechas y color
                </button>
              )}
            </header>

            <div className="flex shrink-0 items-center gap-3 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/40 px-5 py-2.5 text-xs">
              <span className="font-medium text-slate-700 dark:text-slate-300">
                {piezas.length === 0
                  ? 'Todavía no tiene piezas cargadas'
                  : `${publicadas} de ${piezas.length} piezas publicadas`}
              </span>
              {piezas.length > 0 && (
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                  <div
                    className="h-full rounded-full bg-emerald-500 transition-all"
                    style={{ width: `${(publicadas / piezas.length) * 100}%` }}
                  />
                </div>
              )}
            </div>

            {/* Estado del header: la pieza que toca el calendario de abajo */}
            {piezas.some(esPiezaHeader) && (
              <div className={`shrink-0 border-b px-5 py-2.5 text-xs ${
                noEntro
                  ? 'border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/30 text-rose-800 dark:text-rose-200'
                  : 'border-violet-200 dark:border-violet-900 bg-violet-50 dark:bg-violet-950/40 text-violet-900 dark:text-violet-200'
              }`}>
                {noEntro ? (
                  <p className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    <span>
                      Pide header pero <strong>no entró</strong>: el header ya está completo
                      {noEntro.diasLlenos.length > 0 && ` los días ${noEntro.diasLlenos.join(', ')}`}.
                      Hay que bajar algo, y eso lo decidís vos.
                    </span>
                  </p>
                ) : (
                  <p className="flex items-center gap-2">
                    <LayoutPanelTop className="h-3.5 w-3.5 shrink-0" />
                    <span>Ocupa la <strong>posición {posicionHeader + 1}</strong> del header de la home.</span>
                  </p>
                )}
              </div>
            )}

            <div className="flex-1 overflow-y-auto px-5 py-4">
              <div className="space-y-5">
                {CATALOGO_PIEZAS.map(area => (
                  <BloqueArea
                    key={area.area}
                    area={area.area}
                    titulo={area.titulo}
                    formatos={area.formatos}
                    piezas={piezas.filter(p => p.area === area.area)}
                    editable={editable}
                    dias={mes.dias}
                    inicioAccion={datos.accion.desde}
                    onAgregar={formato => agregarPieza(area.area, formato)}
                    onQuitar={quitarPieza}
                    onEstado={(id, estado) => actualizarPieza(id, { estado })}
                    onEnvio={(id, cambios) => actualizarPieza(id, cambios)}
                  />
                ))}
              </div>

              <p className="mt-6 rounded-lg bg-slate-50 dark:bg-slate-800/40 px-3 py-2.5 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
                Agregar <strong>Web · Home → Header</strong> baja la acción sola al calendario de
                headers, igual que hace Retail Media con sus tres posiciones. Las subtareas por
                pieza (arte desktop, arte mobile, aprobación comercial) vienen después.
              </p>
            </div>
          </>
        )}
      </aside>
    </>
  )
}

// ---------------------------------------------------------------------------

function BloqueArea({
  area, titulo, formatos, piezas, editable, dias, inicioAccion,
  onAgregar, onQuitar, onEstado, onEnvio,
}: {
  area: AreaPieza
  titulo: string
  formatos: string[]
  piezas: Pieza[]
  editable: boolean
  /** Días que tiene el mes: acota el selector de fecha de envío. */
  dias: number
  /** Día en que arranca la acción: es lo que usa un envío sin fecha propia. */
  inicioAccion: number
  onAgregar: (formato: string) => void
  onQuitar: (id: string) => void
  onEstado: (id: string, estado: EstadoPieza) => void
  onEnvio: (id: string, cambios: Partial<Pieza>) => void
}) {
  const [agregando, setAgregando] = useState(false)
  const disponibles = formatos.filter(f => !piezas.some(p => p.formato === f))

  return (
    <section>
      <div className="mb-2 flex items-center gap-2">
        <h3 className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">{titulo}</h3>
        <span className="text-[10px] text-slate-400 dark:text-slate-500">{piezas.length || '—'}</span>
        <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
        {editable && disponibles.length > 0 && (
          <button
            onClick={() => setAgregando(v => !v)}
            className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium text-slate-500 dark:text-slate-400 transition hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100"
          >
            <Plus className="h-3 w-3" /> agregar
          </button>
        )}
      </div>

      {agregando && (
        <div className="mb-2 flex flex-wrap gap-1.5 rounded-lg bg-slate-50 dark:bg-slate-800/40 p-2">
          {disponibles.map(f => (
            <button
              key={f}
              onClick={() => { onAgregar(f); setAgregando(false) }}
              className={`rounded-md border px-2 py-1 text-[11px] font-medium transition ${
                area === 'web-home' && f === 'Header'
                  ? 'border-violet-300 dark:border-violet-700 bg-violet-50 dark:bg-violet-950/40 text-violet-800 dark:text-violet-200 hover:bg-violet-100 dark:hover:bg-violet-900/40'
                  : 'border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
              }`}
            >
              {f}
              {area === 'web-home' && f === 'Header' && ' ↓ header'}
            </button>
          ))}
        </div>
      )}

      {piezas.length === 0 ? (
        <p className="text-xs text-slate-400 dark:text-slate-500">Sin piezas en esta área.</p>
      ) : (
        <ul className="space-y-1">
          {piezas.map(p => (
            <li key={p.id} className="rounded-lg border border-slate-200 dark:border-slate-700 px-2.5 py-1.5">
            <div className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-xs font-medium text-slate-800 dark:text-slate-200">
                {p.formato}
                {esPiezaHeader(p) && (
                  <span className="ml-1.5 rounded bg-violet-100 dark:bg-violet-900/50 px-1 py-0.5 text-[9px] font-semibold uppercase text-violet-700 dark:text-violet-300">
                    header
                  </span>
                )}
              </span>
              {p.estado === 'publicado' && (
                <Check className="h-3.5 w-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
              )}
              <select
                value={p.estado}
                disabled={!editable}
                onChange={e => onEstado(p.id, e.target.value as EstadoPieza)}
                className={`appearance-none rounded-md border-0 px-1.5 py-0.5 text-[10px] font-semibold outline-none ${TONO_ESTADO[p.estado]} disabled:opacity-60`}
              >
                {ESTADOS.map(e => (
                  <option key={e} value={e}>{ETIQUETA_ESTADO[e]}</option>
                ))}
              </select>
              {editable && (
                <button
                  onClick={() => onQuitar(p.id)}
                  className="shrink-0 rounded p-0.5 text-slate-300 dark:text-slate-600 transition hover:bg-rose-50 dark:hover:bg-rose-950/40 hover:text-rose-500"
                  aria-label={`Quitar ${p.formato}`}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            {/* Los envíos salen un día y a una hora: eso es lo que arma el
                cronograma. Sin fecha propia caen el día que arranca la acción. */}
            {esPiezaDeEnvio(p) && (
              <div className="mt-1.5 flex flex-wrap items-center gap-2 border-t border-slate-100 dark:border-slate-800 pt-1.5">
                <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">Sale</span>
                <select
                  value={p.desde ?? ''}
                  disabled={!editable}
                  aria-label={`Día de envío de ${p.formato}`}
                  onChange={e => onEnvio(p.id, {
                    desde: e.target.value === '' ? undefined : Number(e.target.value),
                    hasta: e.target.value === '' ? undefined : Number(e.target.value),
                  })}
                  className="rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 px-1.5 py-0.5 text-[11px] font-medium text-slate-700 dark:text-slate-300 disabled:opacity-60"
                >
                  <option value="">el día {inicioAccion} (con la acción)</option>
                  {Array.from({ length: dias }, (_, i) => i + 1).map(d => (
                    <option key={d} value={d}>día {d}</option>
                  ))}
                </select>
                <input
                  type="time"
                  value={p.hora ?? ''}
                  disabled={!editable}
                  aria-label={`Hora de envío de ${p.formato}`}
                  onChange={e => onEnvio(p.id, { hora: e.target.value || undefined })}
                  className="rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 px-1.5 py-0.5 text-[11px] font-medium text-slate-700 dark:text-slate-300 disabled:opacity-60"
                />
                {p.desde == null && (
                  <span className="text-[10px] text-amber-600 dark:text-amber-400">sin fecha propia</span>
                )}
              </div>
            )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

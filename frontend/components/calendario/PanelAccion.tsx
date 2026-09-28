'use client'

import { useEffect, useState } from 'react'
import { AlertTriangle, Bell, Check, LayoutPanelTop, Pencil, Plus, X } from 'lucide-react'
import { textoSobre } from '@/lib/calendario/colores'
import { diasEntre, fechaCorta, hoyIso, rangoLargo, sumarDias } from '@/lib/calendario/fechas'
import { useCalendario, useHeaderDerivado } from '@/lib/calendario/store'
import { usePermisosCalendario } from '@/lib/calendario/permisos'
import {
  ANTICIPACIONES_DE_AVISO, CATALOGO_PIEZAS, ETIQUETA_ESTADO, esPiezaDeEnvio, esPiezaHeader, tituloDeCanal,
  type AreaPieza, type Aviso, type BarraGuardada, type EstadoPieza, type Persona, type Pieza,
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
  const cerrar = useCalendario(s => s.cerrarAccion)
  const abrirEditor = useCalendario(s => s.abrirEditor)
  const agregarPieza = useCalendario(s => s.agregarPieza)
  const quitarPieza = useCalendario(s => s.quitarPieza)
  const actualizarPieza = useCalendario(s => s.actualizarPieza)
  const personas = useCalendario(s => s.personas)
  const header = useHeaderDerivado()

  const accionViva = useCalendario(s => s.accionAbierta())

  // Se guarda la última acción para que el panel tenga qué pintar mientras sale
  const [ultima, setUltima] = useState<BarraGuardada | null>(null)
  useEffect(() => {
    if (accionViva) setUltima(accionViva)
  }, [accionViva])

  useEffect(() => {
    if (!abierta) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') cerrar() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [abierta, cerrar])

  const visible = Boolean(abierta && accionViva)
  const accion = visible ? accionViva : ultima
  const { editable, user } = usePermisosCalendario()

  const piezas = accion?.piezas ?? []
  const publicadas = piezas.filter(p => p.estado === 'publicado').length

  // ¿En qué posición del header quedó esta acción? ¿O no entró? Se mira el
  // header de todas las fechas, no el del mes: la acción puede cruzar de mes.
  const tramo = accion
    ? header.tramos.find(t => t.origen.tipo === 'accion' && t.origen.accionId === accion.id)
    : undefined
  const noEntro = accion ? header.sinLugar.find(s => s.accionId === accion.id) : undefined

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
        {accion && accion.seccion === 'envio' && (
          <FichaEnvio
            envio={accion}
            editable={editable}
            personas={personas}
            usuarioId={user?.id ?? null}
            onCerrar={cerrar}
          />
        )}
        {accion && accion.seccion !== 'envio' && (
          <>
            <header
              className="shrink-0 px-5 py-4"
              style={{ backgroundColor: accion.color ?? '#e2e8f0', color: textoSobre(accion.color) }}
            >
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] font-medium uppercase tracking-wide opacity-70">{accion.banda}</p>
                  <h2 className="mt-0.5 text-lg font-semibold leading-tight">{accion.nombre}</h2>
                  <p className="mt-1 text-xs opacity-80">
                    {rangoLargo(accion.desde, accion.hasta).replace(/^./, c => c.toUpperCase())}
                    {' · '}{diasEntre(accion.desde, accion.hasta) + 1} días
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

              {editable && (
                <button
                  onClick={() => abrirEditor({
                    seccion: 'comercial',
                    banda: accion.banda,
                    carril: accion.carril,
                    barra: accion,
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
                      {noEntro.diasLlenos.length > 0 && ` los días ${noEntro.diasLlenos.map(fechaCorta).join(', ')}`}.
                      Hay que bajar algo, y eso lo decidís vos.
                    </span>
                  </p>
                ) : tramo ? (
                  <p className="flex items-center gap-2">
                    <LayoutPanelTop className="h-3.5 w-3.5 shrink-0" />
                    <span>Ocupa la <strong>posición {tramo.posicion}</strong> del header de la home.</span>
                  </p>
                ) : null}
              </div>
            )}

            <div className="flex-1 overflow-y-auto px-5 py-4">
              <BloqueAvisos
                accion={accion}
                editable={editable}
                personas={personas}
                usuarioId={user?.id ?? null}
              />

              <div className="mt-6 space-y-5">
                {CATALOGO_PIEZAS.map(area => (
                  <BloqueArea
                    key={area.area}
                    area={area.area}
                    titulo={area.titulo}
                    formatos={area.formatos}
                    piezas={piezas.filter(p => p.area === area.area)}
                    editable={editable}
                    inicioAccion={accion.desde}
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
// La ficha de un envío suelto
// ---------------------------------------------------------------------------

/**
 * Un mailing, un WhatsApp o una push sin una acción detrás. Su ficha es más
 * corta que la de una acción: qué es, cuándo sale, en qué estado está y sus
 * avisos. No tiene áreas ni piezas: el envío ES la pieza.
 */
function FichaEnvio({
  envio, editable, personas, usuarioId, onCerrar,
}: {
  envio: BarraGuardada
  editable: boolean
  personas: Persona[]
  usuarioId: number | null
  onCerrar: () => void
}) {
  const abrirEditor = useCalendario(s => s.abrirEditor)
  const cambiarEstado = useCalendario(s => s.cambiarEstadoEnvio)
  const estado: EstadoPieza = envio.estado ?? 'pendiente'
  const canal = tituloDeCanal(envio.banda)

  return (
    <>
      <header
        className="shrink-0 px-5 py-4"
        style={{ backgroundColor: envio.color ?? '#e2e8f0', color: textoSobre(envio.color) }}
      >
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-medium uppercase tracking-wide opacity-70">
              {canal} · envío suelto
            </p>
            <h2 className="mt-0.5 text-lg font-semibold leading-tight">{envio.nombre}</h2>
            <p className="mt-1 text-xs opacity-80">
              {envio.formato ? `${envio.formato} · ` : ''}
              Sale {rangoLargo(envio.desde, envio.desde)}{envio.hora ? ` a las ${envio.hora}` : ', sin hora todavía'}
            </p>
          </div>
          <button onClick={onCerrar} className="rounded-lg p-1.5 transition hover:bg-black/10" aria-label="Cerrar">
            <X className="h-4 w-4" />
          </button>
        </div>

        {editable && (
          <button
            onClick={() => abrirEditor({ seccion: 'envio', banda: envio.banda, carril: 0, barra: envio })}
            className="mt-3 flex items-center gap-1.5 rounded-lg bg-white/80 px-2.5 py-1.5 text-[11px] font-semibold text-slate-800 dark:text-slate-200 transition hover:bg-white"
          >
            <Pencil className="h-3 w-3" /> Editar nombre, fecha, hora y color
          </button>
        )}
      </header>

      <div className="flex shrink-0 items-center gap-3 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/40 px-5 py-2.5 text-xs">
        <span className="font-medium text-slate-700 dark:text-slate-300">Estado</span>
        <select
          value={estado}
          disabled={!editable}
          aria-label="Estado del envío"
          onChange={e => cambiarEstado(envio.id, e.target.value as EstadoPieza)}
          className={`appearance-none rounded-md border-0 px-1.5 py-0.5 text-[10px] font-semibold outline-none ${TONO_ESTADO[estado]} disabled:opacity-60`}
        >
          {ESTADOS.map(e => <option key={e} value={e}>{ETIQUETA_ESTADO[e]}</option>)}
        </select>
        {estado === 'publicado' && <Check className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />}
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4">
        <BloqueAvisos accion={envio} editable={editable} personas={personas} usuarioId={usuarioId} />
        <p className="mt-6 rounded-lg bg-slate-50 dark:bg-slate-800/40 px-3 py-2.5 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
          Es un envío que no sale de ninguna acción. Los que sí son parte de una acción se cargan en
          la ficha de esa acción, en Email, WhatsApp o Push, y aparecen solos en el cronograma.
        </p>
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// Avisos
// ---------------------------------------------------------------------------

/**
 * Los avisos de la acción. No hay ninguno por defecto (pedido de Ivan,
 * 28/09/2026): los configura a mano quien carga la acción, eligiendo cuántos
 * días antes y a quién, para que cuando llegue uno sea porque vale la pena.
 */
function BloqueAvisos({
  accion, editable, personas, usuarioId,
}: {
  accion: BarraGuardada
  editable: boolean
  personas: Persona[]
  usuarioId: number | null
}) {
  const agregarAviso = useCalendario(s => s.agregarAviso)
  const quitarAviso = useCalendario(s => s.quitarAviso)
  const avisos = accion.avisos ?? []
  const hoy = hoyIso()
  const yaArranco = hoy > accion.desde
  // Una acción "arranca"; un envío suelto "sale".
  const esEnvio = accion.seccion === 'envio'

  const [dias, setDias] = useState<number>(10)
  const [elegidos, setElegidos] = useState<number[]>([])

  // Al abrir otra acción, arranca elegido quien la está mirando.
  useEffect(() => {
    setElegidos(usuarioId != null && personas.some(p => p.id === usuarioId) ? [usuarioId] : [])
  }, [accion.id, usuarioId, personas])

  const nombreDe = (id: number) => personas.find(p => p.id === id)?.nombre ?? 'alguien que ya no ve el calendario'

  function estadoDe(a: Aviso): string {
    if (yaArranco) return esEnvio ? 'el envío ya salió' : 'la acción ya arrancó'
    const fecha = sumarDias(accion.desde, -a.diasAntes)
    return hoy >= fecha ? 'ya salió' : `sale el ${fechaCorta(fecha)}`
  }

  function alternar(id: number) {
    setElegidos(v => (v.includes(id) ? v.filter(x => x !== id) : [...v, id]))
  }

  return (
    <section className="rounded-lg border border-slate-200 dark:border-slate-700 p-3">
      <div className="mb-1 flex items-center gap-2">
        <Bell className="h-3.5 w-3.5 text-slate-500 dark:text-slate-400" />
        <h3 className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">Avisos</h3>
        <span className="text-[10px] text-slate-400 dark:text-slate-500">{avisos.length || '—'}</span>
      </div>
      <p className="mb-2 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
        Solo salen los avisos que se configuran acá. Le llegan a la campanita de cada persona elegida,
        los días antes de que {esEnvio ? 'salga el envío' : 'arranque la acción'} que se elijan.
      </p>

      {avisos.length === 0 ? (
        <p className="text-xs text-slate-400 dark:text-slate-500">
          {esEnvio ? 'Este envío no tiene avisos.' : 'Esta acción no tiene avisos.'}
        </p>
      ) : (
        <ul className="space-y-1">
          {avisos.map(a => (
            <li key={a.id} className="flex items-start gap-2 rounded-lg border border-slate-200 dark:border-slate-700 px-2.5 py-1.5">
              <div className="min-w-0 flex-1 text-xs">
                <span className="font-semibold text-slate-800 dark:text-slate-200">{a.diasAntes} días antes</span>
                <span className="text-slate-500 dark:text-slate-400"> · {estadoDe(a)}</span>
                <span className="block truncate text-[11px] text-slate-500 dark:text-slate-400">
                  A {a.destinatarios.map(nombreDe).join(', ')}
                </span>
              </div>
              {editable && (
                <button
                  onClick={() => quitarAviso(a.id)}
                  className="shrink-0 rounded p-0.5 text-slate-300 dark:text-slate-600 transition hover:bg-rose-50 dark:hover:bg-rose-950/40 hover:text-rose-500"
                  aria-label={`Quitar el aviso de ${a.diasAntes} días antes`}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {editable && !yaArranco && (
        <div className="mt-3 space-y-2 rounded-lg bg-slate-50 dark:bg-slate-800/40 p-2.5">
          <label className="flex items-center gap-2 text-xs text-slate-700 dark:text-slate-300">
            Avisar
            <select
              value={dias}
              onChange={e => setDias(Number(e.target.value))}
              className="rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 px-1.5 py-0.5 text-xs font-semibold"
            >
              {ANTICIPACIONES_DE_AVISO.map(n => <option key={n} value={n}>{n} días antes</option>)}
            </select>
            <span className="text-[11px] text-slate-500 dark:text-slate-400">
              ({hoy >= sumarDias(accion.desde, -dias) ? 'sale ahora' : `el ${fechaCorta(sumarDias(accion.desde, -dias))}`})
            </span>
          </label>

          <div>
            <p className="mb-1 text-[11px] font-medium text-slate-600 dark:text-slate-400">A quién</p>
            {personas.length === 0 ? (
              <p className="text-[11px] text-slate-400 dark:text-slate-500">Cargando las personas…</p>
            ) : (
              <div className="max-h-36 space-y-0.5 overflow-y-auto">
                {personas.map(p => (
                  <label key={p.id} className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-xs text-slate-700 hover:bg-white dark:text-slate-300 dark:hover:bg-slate-900">
                    <input type="checkbox" checked={elegidos.includes(p.id)} onChange={() => alternar(p.id)} />
                    {p.nombre}{p.id === usuarioId ? ' (vos)' : ''}
                  </label>
                ))}
              </div>
            )}
          </div>

          <button
            type="button"
            disabled={elegidos.length === 0}
            onClick={() => agregarAviso(dias, elegidos)}
            className="flex items-center gap-1 rounded-md bg-slate-900 px-2.5 py-1 text-[11px] font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white"
          >
            <Plus className="h-3 w-3" /> Agregar aviso
          </button>
        </div>
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------

function BloqueArea({
  area, titulo, formatos, piezas, editable, inicioAccion,
  onAgregar, onQuitar, onEstado, onEnvio,
}: {
  area: AreaPieza
  titulo: string
  formatos: string[]
  piezas: Pieza[]
  editable: boolean
  /** Fecha en que arranca la acción: es lo que usa un envío sin fecha propia. */
  inicioAccion: string
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
                cronograma. Sin fecha propia caen el día que arranca la acción.
                La fecha puede ser de otro mes que el del arranque. */}
            {esPiezaDeEnvio(p) && (
              <div className="mt-1.5 flex flex-wrap items-center gap-2 border-t border-slate-100 dark:border-slate-800 pt-1.5">
                <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">Sale</span>
                <input
                  type="date"
                  value={p.desde ?? ''}
                  disabled={!editable}
                  aria-label={`Día de envío de ${p.formato}`}
                  onChange={e => onEnvio(p.id, e.target.value
                    ? { desde: e.target.value, hasta: e.target.value }
                    : { desde: undefined, hasta: undefined })}
                  className="rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 px-1.5 py-0.5 text-[11px] font-medium text-slate-700 dark:text-slate-300 disabled:opacity-60"
                />
                <input
                  type="time"
                  value={p.hora ?? ''}
                  disabled={!editable}
                  aria-label={`Hora de envío de ${p.formato}`}
                  onChange={e => onEnvio(p.id, { hora: e.target.value || undefined })}
                  className="rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 px-1.5 py-0.5 text-[11px] font-medium text-slate-700 dark:text-slate-300 disabled:opacity-60"
                />
                {p.desde == null ? (
                  <span className="text-[10px] text-amber-600 dark:text-amber-400">
                    sin fecha propia: sale el {fechaCorta(inicioAccion)}, con la acción
                  </span>
                ) : editable ? (
                  <button
                    type="button"
                    onClick={() => onEnvio(p.id, { desde: undefined, hasta: undefined })}
                    className="text-[10px] text-slate-500 underline underline-offset-2 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
                  >
                    que salga con la acción
                  </button>
                ) : null}
              </div>
            )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

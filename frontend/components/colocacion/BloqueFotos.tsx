'use client'

import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import {
  AlertTriangle, Camera, CheckCircle2, ChevronDown, Clock, MessageSquareText, RefreshCw, Search, Send, Trash2,
} from 'lucide-react'
import {
  colocacionApi, type LocalColocacion, type PedidoColocacion, type TableroColocacion,
} from '@/lib/api'
import { extractErrorDetail } from '@/lib/errors'
import { fechaCorta, rangoLargo } from '@/lib/calendario/fechas'
import { useCalendario } from '@/lib/calendario/store'
import type { BarraGuardada } from '@/lib/calendario/tipos'
import {
  ETIQUETA_PROMO, ORDEN_FILTROS, PUNTO, TONO, cuandoVence, type EstadoVisibleColocacion,
} from '@/lib/colocacion/estados'
import { FotoProtegida } from './FotoProtegida'
import { VisorFoto } from './VisorFoto'

/**
 * La pestaña "Fotos" de la ficha de una acción: pedirle a los locales una
 * foto de cómo quedó la cartelería y, después, el tablero para revisarlas.
 *
 * Es de promo: la ve quien edita el calendario (lo mismo que exige el
 * servidor). Los datos no vienen con el calendario sino aparte, cuando se
 * abre la pestaña, y se ponen al día solos cada 30 segundos mientras está
 * abierta: las fotos van llegando de a una.
 */
export function BloqueFotos({ accion }: { accion: BarraGuardada }) {
  const [tablero, setTablero] = useState<TableroColocacion | null>(null)
  const [fallo, setFallo] = useState<string | null>(null)
  const [vuelta, setVuelta] = useState(0)
  // Lo cargado es de ESTA acción: al pasar a otra no se muestra lo de la anterior.
  const datos = tablero?.accion.id === accion.id ? tablero : null

  useEffect(() => {
    let vivo = true
    const traer = () => colocacionApi.tablero(accion.id)
      .then(({ data }) => { if (vivo) { setTablero(data); setFallo(null) } })
      .catch(() => { if (vivo) setFallo(accion.id) })
    void traer()
    const cada = window.setInterval(() => {
      if (document.visibilityState === 'visible') void traer()
    }, 30_000)
    return () => { vivo = false; window.clearInterval(cada) }
  }, [accion.id, vuelta])

  /** Lo que cambió en el servidor y se ve en el calendario (cuántos locales, hasta cuándo). */
  function alCambiarElPedido(pedido: PedidoColocacion | null) {
    setTablero(t => (t ? { ...t, pedido } : t))
    void useCalendario.getState().sincronizar()
  }

  if (fallo === accion.id && !datos) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-slate-300 px-4 py-8 text-center dark:border-slate-700">
        <AlertTriangle className="h-6 w-6 text-amber-500" />
        <p className="text-sm text-slate-600 dark:text-slate-300">No se pudieron traer las fotos de esta acción.</p>
        <button type="button" onClick={() => setVuelta(v => v + 1)} className="btn-secondary">
          <RefreshCw className="h-4 w-4" /> Probar de nuevo
        </button>
      </div>
    )
  }
  if (!datos) {
    return (
      <div className="space-y-3" aria-label="Cargando las fotos…">
        <div className="skeleton h-24 rounded-2xl" />
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map(i => <div key={i} className="skeleton aspect-[4/5] rounded-xl" />)}
        </div>
      </div>
    )
  }
  if (!datos.pedido) {
    return <FormularioPedido tablero={datos} onPedido={alCambiarElPedido} />
  }
  return (
    <Tablero
      tablero={datos}
      pedido={datos.pedido}
      onPedido={alCambiarElPedido}
      onLocal={local => {
        // Se ve enseguida; el resumen (el porcentaje) lo vuelve a contar el servidor.
        setTablero(t => (t?.pedido ? {
          ...t, pedido: { ...t.pedido, locales: t.pedido.locales.map(l => (l.id === local.id ? local : l)) },
        } : t))
        setVuelta(v => v + 1)
      }}
    />
  )
}

// ---------------------------------------------------------------------------
// Elegir locales (al pedir y al editar)
// ---------------------------------------------------------------------------

function ElegirLocales({
  disponibles, elegidos, onCambio, conFotos,
}: {
  disponibles: string[]
  elegidos: Set<string>
  onCambio: (s: Set<string>) => void
  /** Los que ya mandaron algo: sacarlos borra sus fotos. */
  conFotos?: Set<string>
}) {
  const [busca, setBusca] = useState('')
  const filtro = busca.trim().toLocaleLowerCase('es')
  const lista = filtro ? disponibles.filter(n => n.toLocaleLowerCase('es').includes(filtro)) : disponibles
  const todos = disponibles.length > 0 && disponibles.every(n => elegidos.has(n))

  function alternar(n: string) {
    const s = new Set(elegidos)
    if (s.has(n)) s.delete(n)
    else s.add(n)
    onCambio(s)
  }

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="etiqueta-campo !mb-0">A qué locales</span>
        <span className="text-xs tabular-nums text-slate-500 dark:text-slate-400">{elegidos.size} de {disponibles.length}</span>
        <button
          type="button"
          onClick={() => onCambio(todos ? new Set() : new Set(disponibles))}
          className="ml-auto rounded-lg px-2 py-1 text-xs font-semibold text-brand-600 transition hover:bg-brand-50 dark:text-brand-300 dark:hover:bg-brand-500/10"
        >
          {todos ? 'Ninguno' : 'Todos'}
        </button>
      </div>
      {disponibles.length > 8 && (
        <label className="relative mb-2 block">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
          <input
            value={busca}
            onChange={e => setBusca(e.target.value)}
            placeholder="Buscar un local"
            aria-label="Buscar un local"
            className="campo !pl-9"
          />
        </label>
      )}
      <div className="max-h-56 overflow-y-auto overscroll-contain rounded-xl border border-slate-200 bg-white p-1 dark:border-slate-700 dark:bg-slate-900">
        {lista.length === 0 && <p className="px-3 py-2.5 text-sm text-slate-500 dark:text-slate-400">Ningún local se llama así.</p>}
        {lista.map(n => {
          const marcado = elegidos.has(n)
          return (
            <label
              key={n}
              className={`flex min-h-[40px] cursor-pointer items-center gap-2.5 rounded-lg px-2.5 text-sm transition ${
                marcado ? 'bg-brand-50 text-brand-900 dark:bg-brand-500/10 dark:text-brand-100' : 'text-slate-700 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800'
              }`}
            >
              <input type="checkbox" checked={marcado} onChange={() => alternar(n)} className="h-4 w-4 rounded border-slate-300 accent-brand-600" />
              <span className="min-w-0 flex-1 truncate">{n}</span>
              {conFotos?.has(n) && <span className="shrink-0 text-[11px] text-slate-500 dark:text-slate-400">ya mandó</span>}
            </label>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pedir la foto
// ---------------------------------------------------------------------------

function FormularioPedido({ tablero, onPedido }: { tablero: TableroColocacion; onPedido: (p: PedidoColocacion) => void }) {
  const [elegidos, setElegidos] = useState<Set<string>>(() => new Set(tablero.disponibles))
  const [limite, setLimite] = useState(tablero.limitePorDefecto)
  const [indicacion, setIndicacion] = useState('')
  const [enviando, setEnviando] = useState(false)

  if (tablero.disponibles.length === 0) {
    return (
      <div className="flex items-start gap-3 rounded-2xl border border-dashed border-slate-300 px-4 py-4 text-sm text-slate-600 dark:border-slate-700 dark:text-slate-300">
        <Camera className="mt-0.5 h-5 w-5 shrink-0 text-slate-400" />
        <p>Todavía no hay locales con usuario en este mundo: cuando los den de alta, desde acá se les va a poder pedir la foto.</p>
      </div>
    )
  }

  const valido = elegidos.size > 0 && limite >= tablero.hoy
  const todos = elegidos.size === tablero.disponibles.length

  async function pedir() {
    if (!valido) return
    setEnviando(true)
    try {
      const { data } = await colocacionApi.pedir(tablero.accion.id, {
        // Todos = que el servidor tome los que haya en ese momento.
        locales: todos ? null : [...elegidos],
        limite,
        indicacion: indicacion.trim() || null,
      })
      toast.success(`Listo: se le pidió la foto a ${data.pedido.locales.length} ${data.pedido.locales.length === 1 ? 'local' : 'locales'}. Les llegó el aviso.`)
      onPedido(data.pedido)
    } catch (e) {
      toast.error(extractErrorDetail(e, 'No se pudo pedir la foto. Probá de nuevo.'))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex items-start gap-3 rounded-2xl bg-brand-50 px-4 py-3.5 dark:bg-brand-500/10">
        <Camera className="mt-0.5 h-5 w-5 shrink-0 text-brand-600 dark:text-brand-300" />
        <div className="text-sm text-slate-700 dark:text-slate-200">
          <p className="font-bold text-slate-900 dark:text-white">Pedir foto de colocación a los locales</p>
          <p className="mt-0.5 leading-relaxed">
            Cada local recibe un aviso, saca la foto con el teléfono y la sube. Acá ves quién la mandó y la
            aprobás o la devolvés.
          </p>
        </div>
      </div>

      <ElegirLocales disponibles={tablero.disponibles} elegidos={elegidos} onCambio={setElegidos} />

      <label className="block">
        <span className="etiqueta-campo">Fecha límite</span>
        <input
          type="date"
          value={limite}
          min={tablero.hoy}
          max="2100-12-31"
          onChange={e => setLimite(e.target.value)}
          className="campo"
        />
        <span className="mt-1 block text-xs text-slate-500 dark:text-slate-400">
          {limite === tablero.limitePorDefecto ? 'El día siguiente al inicio de la acción. ' : ''}
          Pasada esta fecha, el local que no mandó la foto figura como atrasado.
        </span>
      </label>

      <label className="block">
        <span className="etiqueta-campo">Qué fotografiar <span className="font-normal text-slate-500">(opcional)</span></span>
        <textarea
          value={indicacion}
          onChange={e => setIndicacion(e.target.value)}
          maxLength={1000}
          rows={2}
          placeholder="Ej: cenefas en cabecera 3 y 4"
          className="campo !h-auto py-2.5"
        />
      </label>

      <button
        type="button"
        disabled={!valido || enviando}
        onClick={pedir}
        className="flex min-h-[48px] w-full items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 text-sm font-bold text-white shadow-sm shadow-brand-600/25 transition hover:bg-brand-700 active:scale-[.98] disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:shadow-none dark:disabled:bg-slate-700 dark:disabled:text-slate-400"
      >
        <Send className="h-4 w-4" />
        {enviando ? 'Pidiendo…' : `Pedir foto a ${elegidos.size} ${elegidos.size === 1 ? 'local' : 'locales'}`}
      </button>
    </section>
  )
}

// ---------------------------------------------------------------------------
// El tablero
// ---------------------------------------------------------------------------

/** La primera foto que no se devolvió (o la primera, si todas): la que va en la grilla. */
function portada(l: LocalColocacion) {
  return l.fotos.find(f => !f.devuelta) ?? l.fotos[0]
}

function Tablero({
  tablero, pedido, onPedido, onLocal,
}: {
  tablero: TableroColocacion
  pedido: PedidoColocacion
  onPedido: (p: PedidoColocacion | null) => void
  onLocal: (l: LocalColocacion) => void
}) {
  const [filtro, setFiltro] = useState<EstadoVisibleColocacion | 'todos'>('todos')
  const [abierto, setAbierto] = useState<number | null>(null)
  const [editando, setEditando] = useState(false)
  const r = pedido.resumen
  const vence = cuandoVence(pedido.limite, tablero.hoy)
  const lista = filtro === 'todos' ? pedido.locales : pedido.locales.filter(l => l.visible === filtro)
  const conFoto = pedido.locales.filter(l => l.fotos.length > 0)
  const primeraPorRevisar = pedido.locales.find(l => l.visible === 'enviada')
  const cuenta: Record<EstadoVisibleColocacion, number> = {
    enviada: r.enviadas, atrasada: r.atrasadas, pendiente: r.pendientes, devuelta: r.devueltas, aprobada: r.aprobadas,
  }

  return (
    <section className="space-y-4">
      {/* El cumplimiento: cuántos tienen la foto aprobada */}
      <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
        <div className="flex items-end gap-3">
          <p className="text-4xl font-bold tabular-nums leading-none text-slate-900 dark:text-white">{r.porcentaje}%</p>
          <p className="pb-0.5 text-sm text-slate-600 dark:text-slate-300">
            de cumplimiento · <strong className="text-slate-900 dark:text-white">{r.aprobadas} de {r.total}</strong> aprobadas
          </p>
        </div>
        <div className="mt-3 flex h-2.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800" aria-hidden>
          {(['aprobada', 'enviada', 'devuelta', 'atrasada'] as const).map(e => (
            <div key={e} className={`h-full ${PUNTO[e]} transition-[width] duration-500`} style={{ width: `${r.total ? (cuenta[e] / r.total) * 100 : 0}%` }} />
          ))}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm">
          <span className={`flex items-center gap-1.5 ${vence.vencida ? 'font-semibold text-rose-700 dark:text-rose-300' : vence.urgente ? 'font-semibold text-amber-700 dark:text-amber-300' : 'text-slate-600 dark:text-slate-300'}`}>
            <Clock className="h-4 w-4" /> Fecha límite: {vence.texto}
          </span>
          {pedido.creadoPor && <span className="text-xs text-slate-500 dark:text-slate-400">Lo pidió {pedido.creadoPor}</span>}
        </div>
        {pedido.indicacion && (
          <p className="mt-2 flex items-start gap-2 rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-700 dark:bg-slate-800/60 dark:text-slate-200">
            <MessageSquareText className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" /> {pedido.indicacion}
          </p>
        )}
        {primeraPorRevisar && (
          <button
            type="button"
            onClick={() => setAbierto(primeraPorRevisar.id)}
            className="mt-3 flex min-h-[44px] w-full items-center justify-center gap-2 rounded-xl bg-sky-600 px-4 text-sm font-bold text-white shadow-sm transition hover:bg-sky-700 active:scale-[.98]"
          >
            <CheckCircle2 className="h-4 w-4" /> Revisar {r.enviadas === 1 ? 'la foto que llegó' : `las ${r.enviadas} fotos por revisar`}
          </button>
        )}
      </div>

      {/* Filtros: primero lo que hay que hacer */}
      <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1" role="group" aria-label="Filtrar locales">
        <BotonFiltro activo={filtro === 'todos'} onClick={() => setFiltro('todos')} texto="Todos" n={r.total} />
        {ORDEN_FILTROS.filter(e => cuenta[e] > 0).map(e => (
          <BotonFiltro key={e} activo={filtro === e} onClick={() => setFiltro(e)} texto={ETIQUETA_PROMO[e]} n={cuenta[e]} punto={PUNTO[e]} />
        ))}
      </div>

      {/* La grilla de locales */}
      <ul className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
        {lista.map(l => {
          const foto = portada(l)
          return (
            <li key={l.id}>
              <button
                type="button"
                onClick={() => (l.fotos.length > 0 ? setAbierto(l.id) : undefined)}
                disabled={l.fotos.length === 0}
                aria-label={`${l.local}: ${ETIQUETA_PROMO[l.visible]}${l.fotos.length ? ', ver la foto' : ', sin foto todavía'}`}
                className="group flex w-full flex-col overflow-hidden rounded-xl border border-slate-200 bg-white text-left transition enabled:hover:border-brand-300 enabled:hover:shadow-card-hover enabled:active:scale-[.98] disabled:cursor-default dark:border-slate-700 dark:bg-slate-900 dark:enabled:hover:border-brand-500/50"
              >
                <div className="relative aspect-[4/3] w-full">
                  {foto ? (
                    <FotoProtegida id={foto.id} tamano="mini" alt={`Foto de ${l.local}`} className="h-full w-full" />
                  ) : (
                    <div className={`flex h-full w-full flex-col items-center justify-center gap-1 ${l.visible === 'atrasada' ? 'bg-rose-50 text-rose-400 dark:bg-rose-500/10 dark:text-rose-300' : 'bg-slate-50 text-slate-300 dark:bg-slate-800/60 dark:text-slate-600'}`}>
                      <Camera className="h-7 w-7" aria-hidden />
                      <span className="text-[11px] font-medium">Sin foto</span>
                    </div>
                  )}
                  {l.fotos.length > 1 && (
                    <span className="absolute right-1.5 top-1.5 rounded-full bg-black/60 px-1.5 py-0.5 text-[11px] font-semibold text-white">
                      {l.fotos.length} fotos
                    </span>
                  )}
                </div>
                <div className="flex flex-1 flex-col gap-1.5 p-2.5">
                  <p className="line-clamp-2 text-[13px] font-semibold leading-snug text-slate-800 dark:text-slate-100">{l.local}</p>
                  <div className="mt-auto flex flex-wrap items-center gap-1">
                    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${TONO[l.visible]}`}>
                      <span className={`h-1.5 w-1.5 rounded-full ${PUNTO[l.visible]}`} aria-hidden />
                      {ETIQUETA_PROMO[l.visible]}
                    </span>
                    {l.tarde && <span className="text-[11px] font-medium text-rose-600 dark:text-rose-300">tarde</span>}
                  </div>
                </div>
              </button>
            </li>
          )
        })}
      </ul>

      <EditarPedido
        abierto={editando}
        onAbrir={setEditando}
        tablero={tablero}
        pedido={pedido}
        onPedido={onPedido}
      />

      {abierto !== null && (
        <VisorFoto
          locales={conFoto}
          inicial={abierto}
          onCerrar={() => setAbierto(null)}
          onActualizado={onLocal}
        />
      )}
    </section>
  )
}

function BotonFiltro({ activo, onClick, texto, n, punto }: { activo: boolean; onClick: () => void; texto: string; n: number; punto?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={activo}
      className={`flex min-h-[36px] shrink-0 items-center gap-1.5 rounded-full border px-3 text-[13px] font-semibold transition active:scale-95 ${
        activo
          ? 'border-brand-600 bg-brand-600 text-white dark:border-brand-500 dark:bg-brand-500'
          : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200'
      }`}
    >
      {punto && <span className={`h-2 w-2 rounded-full ${punto}`} aria-hidden />}
      {texto}
      <span className={`tabular-nums ${activo ? 'text-white/80' : 'text-slate-500 dark:text-slate-400'}`}>{n}</span>
    </button>
  )
}

// ---------------------------------------------------------------------------
// Cambiar el pedido: fecha, indicación, sumar o sacar locales, cancelar
// ---------------------------------------------------------------------------

function EditarPedido({
  abierto, onAbrir, tablero, pedido, onPedido,
}: {
  abierto: boolean
  onAbrir: (v: boolean) => void
  tablero: TableroColocacion
  pedido: PedidoColocacion
  onPedido: (p: PedidoColocacion | null) => void
}) {
  const actuales = useMemo(() => new Set(pedido.locales.map(l => l.local)), [pedido.locales])
  const conFotos = useMemo(
    () => new Set(pedido.locales.filter(l => l.fotos.length > 0 || l.estado !== 'pendiente').map(l => l.local)),
    [pedido.locales],
  )
  // Los que se pueden elegir: los que tienen usuario y los que ya estaban (aunque hoy no lo tengan).
  const disponibles = useMemo(
    () => [...new Set([...tablero.disponibles, ...actuales])].sort((a, b) => a.localeCompare(b, 'es')),
    [tablero.disponibles, actuales],
  )
  const [elegidos, setElegidos] = useState<Set<string>>(actuales)
  const [limite, setLimite] = useState(pedido.limite)
  const [indicacion, setIndicacion] = useState(pedido.indicacion ?? '')
  const [guardando, setGuardando] = useState(false)
  const [confirmar, setConfirmar] = useState<'sacar' | 'cancelar' | null>(null)

  function abrir() {
    // Arranca con lo que está guardado ahora.
    setElegidos(new Set(actuales))
    setLimite(pedido.limite)
    setIndicacion(pedido.indicacion ?? '')
    setConfirmar(null)
    onAbrir(!abierto)
  }

  const sacados = [...actuales].filter(n => !elegidos.has(n))
  const sacadosConFotos = sacados.filter(n => conFotos.has(n))
  const sumados = [...elegidos].filter(n => !actuales.has(n))
  const cambioLocales = sacados.length > 0 || sumados.length > 0
  const cambioLimite = limite !== pedido.limite
  const cambioIndicacion = indicacion.trim() !== (pedido.indicacion ?? '')
  const hayCambios = cambioLocales || cambioLimite || cambioIndicacion
  const valido = elegidos.size > 0 && (!cambioLimite || limite >= tablero.hoy)

  async function guardar(confirmado = false) {
    if (!valido || !hayCambios) return
    if (sacadosConFotos.length > 0 && !confirmado) { setConfirmar('sacar'); return }
    setGuardando(true)
    try {
      const { data } = await colocacionApi.cambiarPedido(pedido.id, {
        ...(cambioLocales ? { locales: [...elegidos] } : {}),
        ...(cambioLimite ? { limite } : {}),
        ...(cambioIndicacion ? { indicacion: indicacion.trim() || null } : {}),
      })
      const partes = [
        sumados.length ? `se sumaron ${sumados.length} (les llegó el aviso)` : '',
        sacados.length ? `se sacaron ${sacados.length}` : '',
      ].filter(Boolean)
      toast.success(partes.length ? `Pedido actualizado: ${partes.join(' y ')}.` : 'Pedido actualizado.')
      onPedido(data.pedido)
      onAbrir(false)
      setConfirmar(null)
    } catch (e) {
      toast.error(extractErrorDetail(e, 'No se pudo guardar el cambio. Probá de nuevo.'))
    } finally {
      setGuardando(false)
    }
  }

  async function cancelar() {
    setGuardando(true)
    try {
      await colocacionApi.cancelarPedido(pedido.id)
      toast.success('Se canceló el pedido de fotos.')
      onPedido(null)
    } catch (e) {
      toast.error(extractErrorDetail(e, 'No se pudo cancelar. Probá de nuevo.'))
    } finally {
      setGuardando(false)
    }
  }

  return (
    <div className="rounded-2xl border border-slate-200 dark:border-slate-700">
      <button
        type="button"
        onClick={abrir}
        aria-expanded={abierto}
        className="flex min-h-[48px] w-full items-center gap-2 px-4 text-left text-sm font-semibold text-slate-700 transition hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800/50"
      >
        <span className="flex-1">Cambiar el pedido: fecha, indicación o locales</span>
        <ChevronDown className={`h-4 w-4 transition-transform ${abierto ? 'rotate-180' : ''}`} />
      </button>
      {abierto && (
        <div className="animate-fade-in space-y-4 border-t border-slate-200 px-4 py-4 dark:border-slate-700">
          <ElegirLocales disponibles={disponibles} elegidos={elegidos} onCambio={setElegidos} conFotos={conFotos} />
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="etiqueta-campo">Fecha límite</span>
              <input type="date" value={limite} min={tablero.hoy} max="2100-12-31" onChange={e => setLimite(e.target.value)} className="campo" />
            </label>
            <label className="block">
              <span className="etiqueta-campo">Qué fotografiar</span>
              <input value={indicacion} onChange={e => setIndicacion(e.target.value)} maxLength={1000} placeholder="Ej: cenefas en cabecera 3 y 4" className="campo" />
            </label>
          </div>

          {confirmar === 'sacar' ? (
            <div role="alertdialog" aria-labelledby="confirmar-sacar" className="space-y-3 rounded-xl border border-rose-200 bg-rose-50 p-3.5 dark:border-rose-500/30 dark:bg-rose-500/10">
              <p id="confirmar-sacar" className="text-sm text-rose-900 dark:text-rose-100">
                {sacadosConFotos.length === 1
                  ? <><strong>{sacadosConFotos[0]}</strong> ya mandó foto: si lo sacás, se borra. </>
                  : <><strong>{sacadosConFotos.length} locales</strong> que sacás ya mandaron foto: se borran. </>}
                No se puede deshacer.
              </p>
              <div className="flex justify-end gap-2">
                <button type="button" autoFocus onClick={() => setConfirmar(null)} className="min-h-[44px] rounded-xl px-4 text-sm font-semibold text-slate-700 hover:bg-white/70 dark:text-slate-200 dark:hover:bg-slate-800">
                  No, dejarlos
                </button>
                <button type="button" disabled={guardando} onClick={() => guardar(true)} className="min-h-[44px] rounded-xl bg-rose-600 px-4 text-sm font-semibold text-white hover:bg-rose-700">
                  Sí, sacarlos
                </button>
              </div>
            </div>
          ) : confirmar === 'cancelar' ? (
            <div role="alertdialog" aria-labelledby="confirmar-cancelar" className="space-y-3 rounded-xl border border-rose-200 bg-rose-50 p-3.5 dark:border-rose-500/30 dark:bg-rose-500/10">
              <p id="confirmar-cancelar" className="text-sm text-rose-900 dark:text-rose-100">
                ¿Cancelar el pedido? Se borran el estado de los {pedido.locales.length} locales
                {conFotos.size > 0 ? ` y las fotos que ya mandaron ${conFotos.size}` : ''}. No se puede deshacer.
              </p>
              <div className="flex justify-end gap-2">
                <button type="button" autoFocus onClick={() => setConfirmar(null)} className="min-h-[44px] rounded-xl px-4 text-sm font-semibold text-slate-700 hover:bg-white/70 dark:text-slate-200 dark:hover:bg-slate-800">
                  No, dejarlo
                </button>
                <button type="button" disabled={guardando} onClick={cancelar} className="flex min-h-[44px] items-center gap-1.5 rounded-xl bg-rose-600 px-4 text-sm font-semibold text-white hover:bg-rose-700">
                  <Trash2 className="h-4 w-4" /> Sí, cancelar
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => setConfirmar('cancelar')}
                className="flex min-h-[44px] items-center gap-1.5 rounded-xl px-3 text-sm font-semibold text-rose-600 transition hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-500/10"
              >
                <Trash2 className="h-4 w-4" /> Cancelar el pedido
              </button>
              <button
                type="button"
                disabled={!valido || !hayCambios || guardando}
                onClick={() => guardar()}
                className="min-h-[44px] rounded-xl bg-brand-600 px-5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.98] disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 dark:disabled:bg-slate-700 dark:disabled:text-slate-400"
              >
                {guardando ? 'Guardando…' : 'Guardar cambios'}
              </button>
            </div>
          )}
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Pedido el {pedido.createdAt ? fechaCorta(pedido.createdAt.slice(0, 10)) : '—'} para la acción que va {rangoLargo(tablero.accion.desde, tablero.accion.hasta)}.
          </p>
        </div>
      )}
    </div>
  )
}

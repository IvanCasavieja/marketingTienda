'use client'

/**
 * Mi agenda: el calendario de Outlook o Google de cada persona, en una fila
 * arriba del calendario. Pedido de Ivan (17/11/2026): "que la gente pueda
 * importar su propio calendario a la aplicación y que se vaya actualizando
 * con los eventos que vayan agregando". Solo la ve su dueño.
 *
 * Es al revés de lo que había antes (un link para llevar las acciones de
 * Tienda a Outlook), que se sacó: "no me gusta que las acciones del
 * calendario de Tienda puedan estar en un calendario cualquiera".
 *
 * Se conecta una vez, pegando el link del calendario. El servidor lo relee
 * cada 15 minutos cuando alguien mira (ver backend/app/api/routes/mi_agenda.py);
 * acá se vuelve a preguntar cada 15 minutos y al volver a la pestaña.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, CalendarDays, ChevronLeft, ChevronRight, Link2, Loader2, MapPin, RefreshCw, Settings2, Unplug, X,
} from 'lucide-react'
import { toast } from 'sonner'
import { calendarioApi } from '@/lib/api'
import { extractErrorDetail } from '@/lib/errors'
import { diaDeHoy, fechaLarga, isoDe } from '@/lib/calendario/fechas'
import { useCalendario, useMesActivo } from '@/lib/calendario/store'
import {
  ANCHO_PARA_EL_NOMBRE, barrasDeAgenda, cuandoSeLeyo, eventosPorDia, horarioDe, pareceLinkDeCalendario, tituloDelDia,
  type EventoAgenda, type MiAgenda as Agenda,
} from '@/lib/calendario/mi-agenda'
import { CabeceraDias, EtiquetaBanda, FilaRejilla, Renglones, useAnchoTotal } from './Rejilla'
import { MarcoScroll } from './MarcoScroll'
import { Seccion } from './Seccion'
import { useDialogo } from './useDialogo'

const PREGUNTAR_CADA = 15 * 60_000
/** Al volver a la pestaña, si pasó al menos esto desde la última vez. */
const AL_VOLVER = 5 * 60_000

/** undefined: todavía no se sabe; null: no corresponde (sin acceso o sin servidor). */
function useMiAgenda() {
  const [agenda, setAgenda] = useState<Agenda | null | undefined>(undefined)
  const ultima = useRef(0)

  const traer = useCallback(async () => {
    ultima.current = Date.now()
    try {
      const { data } = await calendarioApi.miAgenda()
      setAgenda(data)
    } catch {
      // Sin conexión un rato: queda lo que había. Si nunca se pudo, no se muestra.
      setAgenda(a => (a === undefined ? null : a))
    }
  }, [])

  useEffect(() => {
    traer()
    const cada = setInterval(() => { if (document.visibilityState === 'visible') traer() }, PREGUNTAR_CADA)
    const alVolver = () => {
      if (document.visibilityState === 'visible' && Date.now() - ultima.current > AL_VOLVER) traer()
    }
    document.addEventListener('visibilitychange', alVolver)
    window.addEventListener('focus', alVolver)
    return () => {
      clearInterval(cada)
      document.removeEventListener('visibilitychange', alVolver)
      window.removeEventListener('focus', alVolver)
    }
  }, [traer])

  return { agenda, setAgenda }
}

export function MiAgenda() {
  const { agenda, setAgenda } = useMiAgenda()
  const [ajustes, setAjustes] = useState(false)
  if (!agenda) return null
  return (
    <>
      {agenda.conectada
        ? <FilaAgenda agenda={agenda} setAgenda={setAgenda} onAjustes={() => setAjustes(true)} />
        : <TiraConectar onConectar={() => setAjustes(true)} />}
      {ajustes && (
        <DialogoConectar
          agenda={agenda}
          onListo={a => { setAgenda(a); setAjustes(false) }}
          onCerrar={() => setAjustes(false)}
        />
      )}
    </>
  )
}

/** Sin calendario conectado: una sola línea con el botón, no una rejilla vacía. */
function TiraConectar({ onConectar }: { onConectar: () => void }) {
  return (
    <section
      aria-label="Mi agenda"
      className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-2xl border border-dashed border-slate-300 bg-white px-4 py-2.5 dark:border-slate-700 dark:bg-slate-900 sm:px-5"
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 ring-1 ring-inset ring-indigo-100 dark:bg-indigo-500/15 dark:text-indigo-300 dark:ring-indigo-500/20">
        <CalendarDays className="h-4 w-4" />
      </span>
      <p className="min-w-0 flex-1 basis-60 text-[13px] leading-snug text-slate-600 dark:text-slate-300">
        <b className="font-bold text-slate-900 dark:text-slate-100">Mi agenda.</b>{' '}
        Traé tus reuniones de Outlook o Google y miralas acá, al lado de las acciones. Solo las ves vos.
      </p>
      <button
        type="button"
        onClick={onConectar}
        className="flex h-9 shrink-0 items-center gap-1.5 rounded-xl bg-brand-600 px-3.5 text-xs font-semibold text-white shadow-sm transition hover:bg-brand-700 active:scale-95"
      >
        <Link2 className="h-3.5 w-3.5" />
        Conectar mi calendario
      </button>
    </section>
  )
}

function FilaAgenda({
  agenda, setAgenda, onAjustes,
}: { agenda: Agenda; setAgenda: (a: Agenda) => void; onAjustes: () => void }) {
  const mes = useMesActivo()
  const ancho = useAnchoTotal(mes.dias)
  const hoy = diaDeHoy(mes.clave)
  const [dia, setDia] = useState<number | null>(null)
  const [actualizando, setActualizando] = useState(false)

  const porDia = useMemo(() => eventosPorDia(agenda.eventos, mes.clave, mes.dias), [agenda.eventos, mes.clave, mes.dias])
  const angosta = useCalendario(s => s.zoom) < ANCHO_PARA_EL_NOMBRE
  const barras = useMemo(() => barrasDeAgenda(porDia, mes.clave, angosta), [porDia, mes.clave, angosta])
  // Uno de varios días cuenta una vez.
  const total = useMemo(() => {
    const unicos = new Set<string>()
    porDia.forEach(lista => lista.forEach(e => unicos.add(`${e.uid}|${e.inicio}`)))
    return unicos.size
  }, [porDia])

  async function actualizar() {
    setActualizando(true)
    try {
      const { data } = await calendarioApi.actualizarAgenda()
      setAgenda(data)
      if (data.error) toast.error(data.error)
      else toast.success('Listo: tu agenda está al día.')
    } catch (e) {
      toast.error(extractErrorDetail(e, 'No se pudo actualizar. Probá de nuevo en un momento.'))
    } finally {
      setActualizando(false)
    }
  }

  const leida = cuandoSeLeyo(agenda.leidaEl)
  return (
    <>
    <Seccion
      icono={<CalendarDays className="h-4 w-4" />}
      titulo="Mi agenda"
      bajada="Tu calendario de Outlook o Google. Solo lo ves vos; se actualiza solo cada 15 minutos."
      contador={total === 0 ? 'sin eventos este mes' : total === 1 ? '1 evento' : `${total} eventos`}
      acciones={
        <div className="flex items-center gap-1.5">
          {leida && (
            <span className="hidden text-[11px] text-slate-500 dark:text-slate-400 md:inline">Actualizada {leida}</span>
          )}
          <button
            type="button"
            onClick={actualizar}
            disabled={actualizando}
            title="Traer ya lo último de tu calendario"
            className="flex h-8 items-center gap-1.5 rounded-xl border border-slate-300 px-2.5 text-xs font-semibold text-slate-600 transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700 active:scale-95 disabled:opacity-60 dark:border-slate-700 dark:text-slate-300 dark:hover:border-brand-500/40 dark:hover:bg-brand-500/10 dark:hover:text-brand-200"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${actualizando ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">Actualizar</span>
          </button>
          <button type="button" onClick={onAjustes} title="Cambiar el link o desconectar" aria-label="Ajustes de mi agenda" className="boton-icono">
            <Settings2 className="h-4 w-4" />
          </button>
        </div>
      }
    >
      {agenda.error && (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          <span className="font-semibold">No se pudo leer tu calendario:</span>
          <span>{agenda.error}</span>
          <span className="text-amber-800 dark:text-amber-300">Se ven los eventos de la última vez.</span>
          <button type="button" onClick={onAjustes} className="font-semibold underline underline-offset-2">Revisar el link</button>
        </div>
      )}
      <MarcoScroll ancho={ancho}>
        <CabeceraDias mes={mes} hoy={hoy} titulo="Mi agenda" />
        <div className="flex">
          <EtiquetaBanda
            clave="agenda:mia"
            extra={
              <span className="text-[10px] font-semibold uppercase leading-none tracking-wide text-slate-500 dark:text-slate-400">
                solo la ves vos
              </span>
            }
          >
            <span className="flex items-center gap-1.5"><CalendarDays className="h-3.5 w-3.5" /> Mis eventos</span>
          </EtiquetaBanda>
          <Renglones clave="agenda:mia">
            <FilaRejilla
              mes={mes}
              fila={barras}
              hoy={hoy}
              // Se tocan para ver el día; no se crea nada (no hay onDiaVacio).
              editable
              tituloDe={b => tituloDelDia(porDia.get(b.desde) ?? [])}
              onBarra={b => setDia(b.desde)}
            />
          </Renglones>
        </div>
      </MarcoScroll>
    </Seccion>
    {/* Afuera de la sección: el cuadro va encima de todo, no recortado por ella. */}
    {dia != null && porDia.has(dia) && (
        <DialogoDia
          clave={mes.clave}
          dia={dia}
          dias={[...porDia.keys()].sort((a, b) => a - b)}
          eventos={porDia.get(dia)!}
          onDia={setDia}
          onCerrar={() => setDia(null)}
        />
      )}
    </>
  )
}

/** "Miércoles 18 de noviembre" */
function nombreDelDia(iso: string): string {
  const semana = new Date(`${iso}T12:00:00Z`).toLocaleDateString('es-UY', { weekday: 'long', timeZone: 'UTC' })
  return `${semana.charAt(0).toUpperCase()}${semana.slice(1)} ${fechaLarga(iso, iso)}`
}

/** Lo que hay un día: se abre tocando su barra. */
function DialogoDia({
  clave, dia, dias, eventos, onDia, onCerrar,
}: {
  clave: string; dia: number; dias: number[]; eventos: EventoAgenda[]; onDia: (d: number) => void; onCerrar: () => void
}) {
  const caja = useRef<HTMLDivElement>(null)
  useDialogo(true, caja)
  const i = dias.indexOf(dia)
  const anterior = i > 0 ? dias[i - 1] : null
  const siguiente = i >= 0 && i < dias.length - 1 ? dias[i + 1] : null
  return (
    <Marco caja={caja} titulo="agenda-dia-titulo" onCerrar={onCerrar}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-indigo-600 dark:text-indigo-300">Mi agenda</p>
          <h2 id="agenda-dia-titulo" className="text-lg font-bold leading-tight text-slate-900 dark:text-slate-100">
            {nombreDelDia(isoDe(clave, dia))}
          </h2>
        </div>
        <button type="button" onClick={() => anterior != null && onDia(anterior)} disabled={anterior == null} className="boton-icono disabled:opacity-30" aria-label="Día anterior con eventos">
          <ChevronLeft className="h-5 w-5" />
        </button>
        <button type="button" onClick={() => siguiente != null && onDia(siguiente)} disabled={siguiente == null} className="boton-icono disabled:opacity-30" aria-label="Día siguiente con eventos">
          <ChevronRight className="h-5 w-5" />
        </button>
        <button type="button" onClick={onCerrar} className="boton-icono -mr-1" aria-label="Cerrar">
          <X className="h-5 w-5" />
        </button>
      </div>
      <ul className="mt-4 divide-y divide-slate-200 dark:divide-slate-800">
        {eventos.map(e => (
          <li key={`${e.uid}|${e.inicio}`} className="flex gap-3 py-2.5">
            <span className="w-24 shrink-0 pt-0.5 text-xs font-semibold tabular-nums text-slate-500 dark:text-slate-400">{horarioDe(e)}</span>
            <div className="min-w-0 flex-1">
              <p className="break-words text-sm font-semibold text-slate-900 dark:text-slate-100">{e.titulo}</p>
              {e.lugar && (
                <p className="mt-0.5 flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                  <MapPin className="h-3 w-3 shrink-0" /> <span className="truncate">{e.lugar}</span>
                </p>
              )}
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
        Viene de tu calendario: para cambiar algo, hacelo en Outlook o Google. Solo lo ves vos.
      </p>
    </Marco>
  )
}

/** El cuadro centrado (abajo, en el teléfono), como los demás del calendario. */
function Marco({
  caja, titulo, onCerrar, children,
}: { caja: React.RefObject<HTMLDivElement>; titulo: string; onCerrar: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center sm:items-center sm:p-4" onKeyDown={e => { if (e.key === 'Escape') onCerrar() }}>
      <div className="velo animate-fade-in" onClick={onCerrar} aria-hidden />
      <div
        ref={caja}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titulo}
        tabIndex={-1}
        className="relative flex max-h-[92dvh] w-full max-w-lg animate-sheet-up flex-col overflow-y-auto rounded-t-3xl bg-white p-5 shadow-panel outline-none dark:bg-slate-900 dark:ring-1 dark:ring-slate-800 sm:animate-scale-in sm:rounded-2xl sm:p-6"
      >
        {children}
      </div>
    </div>
  )
}

const PASOS = {
  outlook: [
    <>Abrí Outlook en la web (<b>outlook.office.com</b>) y andá a <b>Configuración</b> (el engranaje) → <b>Calendario</b> → <b>Calendarios compartidos</b>.</>,
    <>En <b>Publicar un calendario</b>, elegí tu calendario y <b>Puede ver todos los detalles</b>. Tocá <b>Publicar</b>.</>,
    <>Copiá el link <b>ICS</b> y pegalo acá abajo.</>,
  ],
  google: [
    <>Abrí <b>Google Calendar</b> en la compu y andá a <b>Configuración</b> (el engranaje).</>,
    <>A la izquierda, en <b>Configuración de mis calendarios</b>, elegí tu calendario.</>,
    <>En <b>Integrar el calendario</b>, copiá la <b>Dirección secreta en formato iCal</b> y pegala acá abajo.</>,
  ],
}

/** Conectar el calendario, o cambiar el link o desconectarlo si ya está. */
function DialogoConectar({
  agenda, onListo, onCerrar,
}: { agenda: Agenda; onListo: (a: Agenda) => void; onCerrar: () => void }) {
  const caja = useRef<HTMLDivElement>(null)
  const campo = useRef<HTMLInputElement>(null)
  useDialogo(true, caja, campo)
  const [donde, setDonde] = useState<keyof typeof PASOS>('outlook')
  const [url, setUrl] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmarSacar, setConfirmarSacar] = useState(false)

  async function conectar(e: React.FormEvent) {
    e.preventDefault()
    if (!pareceLinkDeCalendario(url)) {
      setError('Pegá el link entero: empieza con https:// (o webcal://).')
      return
    }
    setEnviando(true)
    setError(null)
    try {
      const { data } = await calendarioApi.conectarAgenda(url.trim())
      const n = data.eventos.length
      toast.success(n === 0 ? 'Listo: tu calendario quedó conectado (todavía sin eventos).' : `Listo: se trajeron ${n === 1 ? '1 evento' : `${n} eventos`} de tu calendario.`)
      onListo(data)
    } catch (err) {
      const tardo = (err as { code?: string })?.code === 'ECONNABORTED'
      setError(tardo
        ? 'Tu calendario tardó demasiado en contestar. Probá de nuevo en un momento.'
        : extractErrorDetail(err, 'No se pudo conectar. Revisá el link y probá de nuevo.'))
    } finally {
      setEnviando(false)
    }
  }

  async function desconectar() {
    try {
      const { data } = await calendarioApi.desconectarAgenda()
      toast.success('Listo: tu calendario ya no está conectado.')
      onListo(data)
    } catch (err) {
      toast.error(extractErrorDetail(err, 'No se pudo desconectar. Probá de nuevo en un momento.'))
    }
  }

  return (
    <Marco caja={caja} titulo="agenda-conectar-titulo" onCerrar={onCerrar}>
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-300">
          <CalendarDays className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 id="agenda-conectar-titulo" className="text-lg font-bold leading-tight text-slate-900 dark:text-slate-100">
            {agenda.conectada ? 'Mi agenda' : 'Conectar mi calendario'}
          </h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
            Tus reuniones, en una fila arriba del calendario. Solo las ves vos y se actualizan solas.
          </p>
        </div>
        <button type="button" onClick={onCerrar} className="boton-icono -mr-1 -mt-1" aria-label="Cerrar">
          <X className="h-5 w-5" />
        </button>
      </div>

      {agenda.conectada && (
        <div className="mt-4 rounded-xl bg-emerald-50 p-3 text-sm text-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200">
          <p className="font-semibold">Tu calendario está conectado.</p>
          {agenda.leidaEl && <p className="text-xs">Se leyó por última vez {cuandoSeLeyo(agenda.leidaEl)}.</p>}
          <div className="mt-2">
            {confirmarSacar ? (
              <span className="flex flex-wrap items-center gap-2 text-xs">
                <span className="font-semibold">¿Desconectarlo? Se borran los eventos de acá (en tu calendario no se toca nada).</span>
                <button type="button" onClick={desconectar} className="rounded-lg bg-red-600 px-2.5 py-1 font-semibold text-white hover:bg-red-700">Sí, desconectar</button>
                <button type="button" onClick={() => setConfirmarSacar(false)} className="rounded-lg px-2.5 py-1 font-semibold hover:bg-emerald-100 dark:hover:bg-emerald-900/40">No</button>
              </span>
            ) : (
              <button type="button" onClick={() => setConfirmarSacar(true)} className="flex items-center gap-1.5 text-xs font-semibold hover:underline">
                <Unplug className="h-3.5 w-3.5" /> Desconectar
              </button>
            )}
          </div>
        </div>
      )}

      <div className="mt-4">
        <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">
          {agenda.conectada ? 'Para cambiar el link, copiá el nuevo:' : '¿De dónde es tu calendario?'}
        </p>
        <div role="tablist" aria-label="De dónde es tu calendario" className="mt-2 inline-flex rounded-xl bg-slate-100 p-1 dark:bg-slate-800">
          {(['outlook', 'google'] as const).map(d => (
            <button
              key={d}
              type="button"
              role="tab"
              aria-selected={donde === d}
              onClick={() => setDonde(d)}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${donde === d
                ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white'
                : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'}`}
            >
              {d === 'outlook' ? 'Outlook' : 'Google'}
            </button>
          ))}
        </div>
        <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-sm text-slate-700 marker:font-semibold marker:text-slate-400 dark:text-slate-300">
          {PASOS[donde].map((paso, i) => <li key={i}>{paso}</li>)}
        </ol>
        {donde === 'outlook' && (
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
            Si no te aparece «Publicar un calendario», tu cuenta no lo tiene habilitado: pedíselo a sistemas.
          </p>
        )}
      </div>

      <form onSubmit={conectar} className="mt-4">
        <label htmlFor="agenda-link" className="text-xs font-semibold text-slate-600 dark:text-slate-400">El link de tu calendario</label>
        <div className="mt-1 flex gap-2">
          <input
            id="agenda-link"
            ref={campo}
            value={url}
            onChange={e => { setUrl(e.target.value); setError(null) }}
            placeholder={donde === 'outlook' ? 'https://outlook.office365.com/owa/calendar/…/calendar.ics' : 'https://calendar.google.com/calendar/ical/…/basic.ics'}
            inputMode="url"
            autoComplete="off"
            spellCheck={false}
            aria-invalid={!!error}
            aria-describedby={error ? 'agenda-error' : undefined}
            className="min-w-0 flex-1 rounded-xl border border-slate-300 bg-white px-3 py-2 font-mono text-xs text-slate-800 placeholder:text-slate-400 focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          />
          <button
            type="submit"
            disabled={enviando || !url.trim()}
            className="flex shrink-0 items-center gap-1.5 rounded-xl bg-brand-600 px-3.5 text-sm font-semibold text-white transition hover:bg-brand-700 active:scale-95 disabled:opacity-50"
          >
            {enviando && <Loader2 className="h-4 w-4 animate-spin" />}
            {enviando ? 'Leyendo…' : 'Conectar'}
          </button>
        </div>
        {error && <p id="agenda-error" role="alert" className="mt-2 text-xs font-semibold text-red-600 dark:text-red-400">{error}</p>}
      </form>

      <p className="mt-4 rounded-xl bg-slate-50 p-3 text-xs text-slate-600 dark:bg-slate-800/60 dark:text-slate-400">
        El link se guarda cifrado y no se le muestra a nadie. Es solo de ida: tus reuniones entran a Core Tienda, pero las acciones de Tienda no salen a tu calendario.
      </p>
    </Marco>
  )
}

'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { Download, File as IconoArchivo, FileArchive, FileImage, FileSpreadsheet, FileText, Loader2, Paperclip, Trash2, X } from 'lucide-react'
import { toast } from 'sonner'
import { adjuntosApi } from '@/lib/api'
import {
  ACEPTA_ADJUNTOS, EVENTO_ADJUNTOS, MAX_ADJUNTOS, MAX_BYTES_ADJUNTO, claseDeArchivo, sumarArchivos,
  type Adjunto, type ClaseDeArchivo,
} from '@/lib/calendario/adjuntos'
import { pesoLegible } from '@/lib/calendario/zip'

/**
 * Los archivos del pedido de una tarea (24/11/2026). Ivan: "en el brief de
 * las tareas deberíamos poder adjuntar archivos, como el Excel por ejemplo".
 *
 * - `ElegirAdjuntos`: en «Nueva tarea», antes de crearla. Se suben solos
 *   después del alta (ver `adjuntar` en el store); si se pidieron varias
 *   cosas juntas, a cada tarea.
 * - `ListaDeAdjuntos`: en la tarjeta («Lo que se pidió») y en la ficha de la
 *   acción, con su ícono, nombre, peso y «Bajar»; quien puede, adjunta más o
 *   saca alguno.
 * - `AdjuntosDeLaTarea`: la lista en la ficha de la acción, que los pide al
 *   abrir la tarea.
 */

const ICONO: Record<ClaseDeArchivo, { Icono: typeof FileText; tono: string }> = {
  excel: { Icono: FileSpreadsheet, tono: 'text-emerald-700 dark:text-emerald-300' },
  csv: { Icono: FileSpreadsheet, tono: 'text-emerald-700 dark:text-emerald-300' },
  pdf: { Icono: FileText, tono: 'text-rose-700 dark:text-rose-300' },
  word: { Icono: FileText, tono: 'text-brand-700 dark:text-brand-200' },
  imagen: { Icono: FileImage, tono: 'text-amber-700 dark:text-amber-300' },
  zip: { Icono: FileArchive, tono: 'text-slate-700 dark:text-slate-200' },
  otro: { Icono: IconoArchivo, tono: 'text-slate-700 dark:text-slate-200' },
}

function IconoDe({ nombre }: { nombre: string }) {
  const { Icono, tono } = ICONO[claseDeArchivo(nombre)]
  return <Icono className={`h-5 w-5 shrink-0 ${tono}`} aria-hidden />
}

const AYUDA = `Excel, CSV, PDF, Word, imágenes o ZIP · hasta ${pesoLegible(MAX_BYTES_ADJUNTO)} cada uno, ${MAX_ADJUNTOS} por tarea`

const BOTON_ADJUNTAR = 'flex min-h-[44px] items-center gap-2 rounded-xl border border-dashed border-slate-400 px-3 text-sm font-semibold text-slate-700 transition hover:border-brand-500 hover:bg-brand-50 hover:text-brand-800 active:scale-[.98] disabled:opacity-60 dark:border-slate-600 dark:text-slate-200 dark:hover:border-brand-400 dark:hover:bg-brand-500/10 dark:hover:text-brand-100 sm:min-h-[40px]'

function detalleDeError(e: unknown): string | null {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === 'string' ? d : null
}

/** El selector escondido y su botón: elegir uno o varios archivos. */
function BotonAdjuntar({ onElegidos, cargando = false, etiqueta = 'Adjuntar archivo' }: {
  onElegidos: (archivos: File[]) => void
  cargando?: boolean
  etiqueta?: string
}) {
  const ref = useRef<HTMLInputElement>(null)
  return (
    <>
      <input
        ref={ref}
        type="file"
        multiple
        accept={ACEPTA_ADJUNTOS}
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        onChange={e => {
          const elegidos = Array.from(e.target.files ?? [])
          // Vaciarlo: si se elige el mismo archivo otra vez, igual avisa.
          e.target.value = ''
          if (elegidos.length > 0) onElegidos(elegidos)
        }}
      />
      <button type="button" onClick={() => ref.current?.click()} disabled={cargando} className={BOTON_ADJUNTAR} title={AYUDA}>
        {cargando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
        {cargando ? 'Subiendo…' : etiqueta}
      </button>
    </>
  )
}

/** Los archivos elegidos al crear la tarea, antes de que exista. */
export function ElegirAdjuntos({ valor, onCambiar, ayuda }: {
  valor: File[]
  onCambiar: (archivos: File[]) => void
  /** Una línea más debajo (a quién le llegan). */
  ayuda?: string
}) {
  const [avisos, setAvisos] = useState<string[]>([])
  function sumar(nuevos: File[]) {
    const r = sumarArchivos(valor, nuevos)
    onCambiar(r.lista)
    setAvisos(r.avisos)
  }
  return (
    <div className="min-w-0">
      <p className="etiqueta-campo">Archivos (opcional)</p>
      {valor.length > 0 && (
        <ul className="mb-2 space-y-1.5" aria-label="Archivos para adjuntar">
          {valor.map(a => (
            <li key={`${a.name}-${a.size}`} className="flex min-h-[44px] items-center gap-2.5 rounded-xl border border-slate-300 bg-white px-3 py-1.5 dark:border-slate-700 dark:bg-slate-900">
              <IconoDe nombre={a.name} />
              <span className="min-w-0 flex-1 text-sm">
                <span className="block truncate font-semibold text-slate-900 dark:text-slate-100" title={a.name}>{a.name}</span>
                <span className="text-xs text-slate-600 dark:text-slate-400">{pesoLegible(a.size)}</span>
              </span>
              <button
                type="button"
                onClick={() => { onCambiar(valor.filter(x => x !== a)); setAvisos([]) }}
                aria-label={`Sacar ${a.name}`}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-slate-600 transition hover:bg-slate-100 hover:text-rose-700 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-rose-300"
              >
                <X className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {valor.length < MAX_ADJUNTOS && <BotonAdjuntar onElegidos={sumar} etiqueta={valor.length > 0 ? 'Adjuntar otro' : 'Adjuntar archivo'} />}
      <p className="mt-1.5 text-xs text-slate-600 dark:text-slate-400">{AYUDA}{ayuda ? `. ${ayuda}` : ''}</p>
      {avisos.map(a => (
        <p key={a} role="alert" className="mt-1.5 rounded-lg bg-amber-50 px-2.5 py-1.5 text-xs font-medium text-amber-900 ring-1 ring-amber-300 dark:bg-amber-500/10 dark:text-amber-100 dark:ring-amber-500/40">
          {a}
        </p>
      ))}
    </div>
  )
}

/**
 * Los archivos del pedido, para bajar (y, quien puede, adjuntar más o sacar
 * alguno). `desde`: la tarea de la que son.
 */
export function ListaDeAdjuntos({ desde, adjuntos, puedeAdjuntar, onCambio, conAyuda = true }: {
  desde: string
  adjuntos: Adjunto[]
  puedeAdjuntar: boolean
  /** Después de adjuntar o sacar: la lista nueva, si vino. */
  onCambio: (lista?: Adjunto[]) => void
  /** Qué se puede adjuntar, debajo del botón mientras no hay ninguno. En
   *  la ficha de la acción no: se repetiría en cada tarea abierta. */
  conAyuda?: boolean
}) {
  const [bajando, setBajando] = useState<string | null>(null)
  const [subiendo, setSubiendo] = useState(false)
  const [sacando, setSacando] = useState<string | null>(null)
  const [confirmando, setConfirmando] = useState<string | null>(null)
  const [avisos, setAvisos] = useState<string[]>([])
  const propios = adjuntos.length

  async function bajar(a: Adjunto) {
    if (bajando) return
    setBajando(a.id)
    try {
      const { data } = await adjuntosApi.bajar(a.id)
      const url = URL.createObjectURL(data)
      const enlace = document.createElement('a')
      enlace.href = url
      enlace.download = a.nombre
      document.body.appendChild(enlace)
      enlace.click()
      enlace.remove()
      // Que el navegador alcance a empezar la descarga antes de soltarlo.
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch {
      toast.error(`No se pudo bajar «${a.nombre}». Probá de nuevo.`)
    } finally {
      setBajando(null)
    }
  }

  async function subir(elegidos: File[]) {
    const r = sumarArchivos([], elegidos, propios)
    setAvisos(r.avisos)
    if (r.lista.length === 0) return
    setSubiendo(true)
    try {
      const { data } = await adjuntosApi.subir(desde, r.lista)
      toast.success(r.lista.length === 1 ? 'Se adjuntó el archivo al pedido.' : `Se adjuntaron ${r.lista.length} archivos al pedido.`)
      onCambio(data.adjuntos)
    } catch (e) {
      setAvisos([detalleDeError(e) ?? 'No se pudo adjuntar. Probá de nuevo.'])
    } finally {
      setSubiendo(false)
    }
  }

  async function sacar(a: Adjunto) {
    setSacando(a.id)
    try {
      await adjuntosApi.sacar(a.id)
      toast.success(`Se sacó «${a.nombre}» del pedido.`)
      onCambio(adjuntos.filter(x => x.id !== a.id))
    } catch (e) {
      toast.error(detalleDeError(e) ?? 'No se pudo sacar. Probá de nuevo.')
      onCambio()
    } finally {
      setSacando(null)
      setConfirmando(null)
    }
  }

  if (adjuntos.length === 0 && !puedeAdjuntar) return null
  return (
    <div className="space-y-2">
      {adjuntos.length > 0 && (
        <ul className="space-y-1.5" aria-label="Archivos del pedido">
          {adjuntos.map(a => (
            <li key={a.id} className="flex min-h-[48px] items-center gap-2.5 rounded-xl border border-slate-300 bg-white px-3 py-1.5 dark:border-slate-700 dark:bg-slate-900">
              <IconoDe nombre={a.nombre} />
              <span className="min-w-0 flex-1 text-sm">
                <span className="block truncate font-semibold text-slate-900 dark:text-slate-100" title={a.nombre}>{a.nombre}</span>
                <span className="block truncate text-xs text-slate-600 dark:text-slate-400">{pesoLegible(a.tamano)}</span>
              </span>
              <button
                type="button"
                onClick={() => void bajar(a)}
                disabled={bajando !== null}
                className="flex min-h-[44px] shrink-0 items-center gap-1.5 rounded-lg px-2.5 text-sm font-bold text-brand-700 transition hover:bg-brand-50 disabled:opacity-60 dark:text-brand-200 dark:hover:bg-brand-500/10 sm:min-h-[36px]"
                aria-label={`Bajar ${a.nombre}`}
                title={`Bajar ${a.nombre}`}
              >
                {bajando === a.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                <span>Bajar</span>
              </button>
              {a.puedoSacar && (confirmando === a.id ? (
                <button
                  type="button"
                  autoFocus
                  onClick={() => void sacar(a)}
                  onBlur={() => { if (sacando !== a.id) setConfirmando(null) }}
                  disabled={sacando === a.id}
                  className="min-h-[44px] shrink-0 animate-scale-in rounded-lg bg-rose-600 px-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-rose-700 disabled:opacity-70 sm:min-h-[36px]"
                >
                  {sacando === a.id ? 'Sacando…' : 'Sí, sacar'}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => setConfirmando(a.id)}
                  aria-label={`Sacar ${a.nombre} del pedido`}
                  title="Sacar del pedido"
                  className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-slate-600 transition hover:bg-rose-50 hover:text-rose-700 dark:text-slate-300 dark:hover:bg-rose-500/10 dark:hover:text-rose-300 sm:h-9 sm:w-9"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              ))}
            </li>
          ))}
        </ul>
      )}
      {puedeAdjuntar && propios < MAX_ADJUNTOS && (
        <div>
          <BotonAdjuntar onElegidos={files => void subir(files)} cargando={subiendo} />
          {adjuntos.length === 0 && conAyuda && <p className="mt-1.5 text-xs text-slate-600 dark:text-slate-400">{AYUDA}</p>}
        </div>
      )}
      {avisos.map(a => (
        <p key={a} role="alert" className="rounded-lg bg-amber-50 px-2.5 py-1.5 text-xs font-medium text-amber-900 ring-1 ring-amber-300 dark:bg-amber-500/10 dark:text-amber-100 dark:ring-amber-500/40">
          {a}
        </p>
      ))}
    </div>
  )
}

/**
 * En la ficha de la acción, adentro de una tarea abierta: sus archivos. Los
 * pide al abrirse, y de nuevo cuando terminan de subir los que se eligieron
 * al crearla.
 */
export function AdjuntosDeLaTarea({ tareaId }: { tareaId: string }) {
  const [datos, setDatos] = useState<{ adjuntos: Adjunto[]; puedoAdjuntar: boolean } | null>(null)

  const traer = useCallback(() => {
    let vivo = true
    adjuntosApi.listar(tareaId)
      .then(({ data }) => { if (vivo) setDatos(data) })
      // Recién creada, el alta todavía puede estar en camino: cuando suban
      // sus archivos, llega el aviso y se vuelve a pedir.
      .catch(() => { /* sin la lista no se muestra nada */ })
    return () => { vivo = false }
  }, [tareaId])

  useEffect(() => {
    const soltar = traer()
    const alCambiar = (e: Event) => { if ((e as CustomEvent<string>).detail === tareaId) traer() }
    window.addEventListener(EVENTO_ADJUNTOS, alCambiar)
    return () => { soltar(); window.removeEventListener(EVENTO_ADJUNTOS, alCambiar) }
  }, [tareaId, traer])

  if (!datos || (datos.adjuntos.length === 0 && !datos.puedoAdjuntar)) return null
  return (
    <div className="mt-2.5">
      {datos.adjuntos.length > 0 && (
        <p className="mb-1.5 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-600 dark:text-slate-400">
          <Paperclip className="h-3.5 w-3.5" aria-hidden /> Archivos del pedido
        </p>
      )}
      <ListaDeAdjuntos
        desde={tareaId}
        adjuntos={datos.adjuntos}
        puedeAdjuntar={datos.puedoAdjuntar}
        onCambio={lista => (lista ? setDatos(d => (d ? { ...d, adjuntos: lista } : d)) : traer())}
        conAyuda={false}
      />
    </div>
  )
}

'use client'

import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { toast } from 'sonner'
import { Check, ChevronLeft, ChevronRight, Clock, CornerUpLeft, X } from 'lucide-react'
import { colocacionApi, type LocalColocacion } from '@/lib/api'
import { extractErrorDetail } from '@/lib/errors'
import { ETIQUETA_PROMO, TONO } from '@/lib/colocacion/estados'
import { useDialogo } from '@/components/calendario/useDialogo'
import { FotoProtegida } from './FotoProtegida'

/** "15/11 a las 18:42", en la hora de quien mira. */
function cuando(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const dd = String(d.getDate()).padStart(2, '0')
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  return `${dd}/${mm} a las ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/**
 * La foto grande de un local, para aprobarla o devolverla con un comentario.
 *
 * Revisar 60 fotos una por una abriendo y cerrando es mucho tocar: después
 * de aprobar o devolver pasa sola a la próxima que esté por revisar, y con
 * las flechas se recorren los locales que mandaron foto.
 *
 * Se dibuja en el <body> (un portal) y no adentro de la ficha: la ficha se
 * mueve con un transform, y un "fixed" adentro de algo con transform queda
 * atrapado en su caja. En la notebook la foto se veía del ancho de la ficha.
 */
export function VisorFoto({
  locales, inicial, onCerrar, onActualizado,
}: {
  /** Los locales que tienen alguna foto, en el orden del tablero. */
  locales: LocalColocacion[]
  inicial: number
  onCerrar: () => void
  onActualizado: (local: LocalColocacion) => void
}) {
  const [actualId, setActualId] = useState(inicial)
  const [fotoIdx, setFotoIdx] = useState(0)
  const [devolviendo, setDevolviendo] = useState(false)
  const [comentario, setComentario] = useState('')
  const [guardando, setGuardando] = useState(false)
  const caja = useRef<HTMLDivElement>(null)
  const cerrarRef = useRef<HTMLButtonElement>(null)
  useDialogo(true, caja, cerrarRef)

  const idx = Math.max(0, locales.findIndex(l => l.id === actualId))
  const local = locales[idx] as LocalColocacion | undefined
  const fotos = local?.fotos ?? []
  const foto = fotos[Math.min(fotoIdx, Math.max(0, fotos.length - 1))]

  function ir(id: number) {
    setActualId(id)
    setFotoIdx(0)
    setDevolviendo(false)
    setComentario('')
  }

  function mover(paso: number) {
    if (locales.length < 2) return
    ir(locales[(idx + paso + locales.length) % locales.length].id)
  }

  /** Después de revisar uno, el próximo por revisar (dando la vuelta). */
  function siguientePorRevisar(revisado: LocalColocacion) {
    const lista = locales.map(l => (l.id === revisado.id ? revisado : l))
    const desde = lista.findIndex(l => l.id === revisado.id)
    for (let i = 1; i <= lista.length; i++) {
      const otro = lista[(desde + i) % lista.length]
      if (otro.visible === 'enviada') { ir(otro.id); return }
    }
    toast.success('No queda ninguna foto por revisar.')
    onCerrar()
  }

  // Escape cierra el visor y nada más (la ficha de abajo se queda); las
  // flechas pasan de local, salvo que se esté escribiendo el comentario.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const escribiendo = (e.target as HTMLElement | null)?.tagName === 'TEXTAREA'
      if (e.key === 'Escape') {
        e.stopPropagation()
        if (devolviendo) setDevolviendo(false)
        else onCerrar()
      } else if (!escribiendo && e.key === 'ArrowRight') mover(1)
      else if (!escribiendo && e.key === 'ArrowLeft') mover(-1)
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  })

  if (!local) return null

  async function aprobar() {
    if (!local) return
    setGuardando(true)
    try {
      const { data } = await colocacionApi.aprobar(local.id)
      onActualizado(data)
      toast.success(`Aprobada: ${data.local}`)
      siguientePorRevisar(data)
    } catch (e) {
      toast.error(extractErrorDetail(e, 'No se pudo aprobar. Probá de nuevo.'))
    } finally {
      setGuardando(false)
    }
  }

  async function devolver() {
    if (!local || comentario.trim().length < 3) return
    setGuardando(true)
    try {
      const { data } = await colocacionApi.devolver(local.id, comentario.trim())
      onActualizado(data)
      toast.success(`Devuelta a ${data.local}: le llegó el aviso con tu comentario.`)
      siguientePorRevisar(data)
    } catch (e) {
      toast.error(extractErrorDetail(e, 'No se pudo devolver. Probá de nuevo.'))
    } finally {
      setGuardando(false)
    }
  }

  const yaAprobada = local.estado === 'aprobada'
  const puedeDevolver = local.estado === 'enviada' || local.estado === 'aprobada'

  return createPortal(
    <div className="fixed inset-0 z-[70] flex items-stretch justify-center sm:items-center sm:p-4">
      <div className="absolute inset-0 animate-fade-in bg-slate-950/90" onClick={onCerrar} aria-hidden />
      <div
        ref={caja}
        role="dialog"
        aria-modal="true"
        aria-labelledby="visor-titulo"
        className="relative flex w-full max-w-4xl animate-scale-in flex-col overflow-hidden bg-slate-950 text-white sm:max-h-[94dvh] sm:rounded-2xl sm:ring-1 sm:ring-white/10"
      >
        <header className="flex shrink-0 items-center gap-2 px-3 py-2.5 sm:px-4">
          <div className="min-w-0 flex-1">
            <p id="visor-titulo" className="truncate text-base font-bold">{local.local}</p>
            <p className="flex flex-wrap items-center gap-x-2 text-xs text-slate-300">
              <span className={`rounded-full px-2 py-0.5 font-semibold ${TONO[local.visible]}`}>{ETIQUETA_PROMO[local.visible]}</span>
              {local.enviadaAt && <span>Enviada el {cuando(local.enviadaAt)}</span>}
              {local.tarde && <span className="font-semibold text-rose-300">· después de la fecha límite</span>}
              {locales.length > 1 && <span className="tabular-nums">· {idx + 1} de {locales.length}</span>}
            </p>
          </div>
          <button
            ref={cerrarRef}
            type="button"
            onClick={onCerrar}
            aria-label="Cerrar la foto"
            title="Cerrar (Esc)"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-slate-300 transition hover:bg-white/10 hover:text-white active:scale-95"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="relative min-h-0 flex-1 bg-black">
          {foto ? (
            <FotoProtegida
              key={foto.id}
              id={foto.id}
              tamano="grande"
              alt={`Foto de colocación de ${local.local}`}
              ajuste="contain"
              className="h-[52dvh] w-full !bg-black sm:h-[60dvh]"
            />
          ) : (
            <p className="flex h-[40dvh] items-center justify-center text-sm text-slate-500">Este local todavía no mandó foto.</p>
          )}
          {foto?.devuelta && (
            <span className="absolute left-3 top-3 rounded-full bg-amber-400 px-2.5 py-1 text-xs font-bold text-amber-950">
              Devuelta
            </span>
          )}
          {locales.length > 1 && (
            <>
              <button
                type="button"
                onClick={() => mover(-1)}
                aria-label="Local anterior"
                className="absolute left-2 top-1/2 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full bg-black/50 text-white transition hover:bg-black/70 active:scale-95"
              >
                <ChevronLeft className="h-6 w-6" />
              </button>
              <button
                type="button"
                onClick={() => mover(1)}
                aria-label="Local siguiente"
                className="absolute right-2 top-1/2 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full bg-black/50 text-white transition hover:bg-black/70 active:scale-95"
              >
                <ChevronRight className="h-6 w-6" />
              </button>
            </>
          )}
        </div>

        <div className="shrink-0 space-y-3 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 sm:px-4">
          {fotos.length > 1 && (
            <div className="flex gap-2" role="group" aria-label="Fotos de este local">
              {fotos.map((f, i) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setFotoIdx(i)}
                  aria-label={`Foto ${i + 1} de ${fotos.length}`}
                  aria-pressed={i === fotoIdx}
                  className={`h-14 w-16 overflow-hidden rounded-lg ring-2 transition ${i === fotoIdx ? 'ring-white' : 'ring-transparent opacity-70 hover:opacity-100'}`}
                >
                  <FotoProtegida id={f.id} tamano="mini" alt="" className="h-full w-full" />
                </button>
              ))}
            </div>
          )}

          {local.comentario && (
            <p className="rounded-xl bg-white/5 px-3 py-2 text-sm text-slate-200">
              <span className="font-semibold text-amber-300">{local.estado === 'devuelta' ? 'Se devolvió' : 'La habían devuelto'}:</span>{' '}
              «{local.comentario}»{local.revisadoPor ? ` — ${local.revisadoPor}` : ''}
            </p>
          )}

          {devolviendo ? (
            <div className="space-y-2">
              <label className="block text-sm font-semibold" htmlFor="comentario-devolucion">
                ¿Qué hay que arreglar? Le llega al local tal cual.
              </label>
              <textarea
                id="comentario-devolucion"
                autoFocus
                value={comentario}
                onChange={e => setComentario(e.target.value)}
                maxLength={1000}
                rows={2}
                placeholder="Ej: no se ve la cabecera 4, sacala de más lejos"
                className="w-full rounded-xl border border-white/15 bg-white/10 px-3 py-2 text-base text-white placeholder:text-slate-400 focus:border-amber-300 focus:outline-none focus:ring-2 focus:ring-amber-300/30"
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setDevolviendo(false)}
                  className="min-h-[44px] flex-1 rounded-xl px-4 text-sm font-semibold text-slate-200 transition hover:bg-white/10 sm:flex-none"
                >
                  Cancelar
                </button>
                <button
                  type="button"
                  disabled={guardando || comentario.trim().length < 3}
                  onClick={devolver}
                  className="flex min-h-[44px] flex-1 items-center justify-center gap-1.5 rounded-xl bg-amber-400 px-4 text-sm font-bold text-amber-950 transition hover:bg-amber-300 active:scale-[.98] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <CornerUpLeft className="h-4 w-4" /> Devolver al local
                </button>
              </div>
            </div>
          ) : (
            <div className="flex gap-2">
              <button
                type="button"
                disabled={guardando || !puedeDevolver}
                onClick={() => setDevolviendo(true)}
                className="flex min-h-[48px] flex-1 items-center justify-center gap-1.5 rounded-xl bg-white/10 px-4 text-sm font-bold text-white transition hover:bg-white/15 active:scale-[.98] disabled:cursor-not-allowed disabled:opacity-40"
              >
                <CornerUpLeft className="h-4 w-4" /> Devolver
              </button>
              <button
                type="button"
                disabled={guardando || yaAprobada || fotos.length === 0}
                onClick={aprobar}
                className="flex min-h-[48px] flex-1 items-center justify-center gap-1.5 rounded-xl bg-emerald-500 px-4 text-sm font-bold text-white shadow-sm transition hover:bg-emerald-400 active:scale-[.98] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {yaAprobada ? <><Check className="h-4 w-4" /> Aprobada</> : guardando ? <><Clock className="h-4 w-4 animate-spin" /> Guardando…</> : <><Check className="h-4 w-4" /> Aprobar</>}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body,
  )
}

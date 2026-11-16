'use client'

import { useState } from 'react'
import { ChevronDown, Loader2, MapPin, RotateCcw, Sparkles, Stamp, X } from 'lucide-react'
import {
  TIPO_OBSERVACION, ordenarObservaciones, tieneLugar, tituloRevisionIA, type ObservacionIA, type RevisionIA,
} from '@/lib/calendario/revision-ia'

/**
 * Lo que encontró la IA en la pieza, arriba de la imagen del Revisor.
 *
 * Es una ayuda para quien aprueba, no una decisión, y se dice así: la IA se
 * puede equivocar, decide la persona, y a la agencia no le llega nada de esta
 * lista (solo las marcas que la persona haga). Por eso cada observación tiene
 * dos salidas y ninguna es automática: "Hacer marca" (pasa a ser una marca
 * normal, del aprobador, que puede corregir antes de mandar) o "Descartar".
 *
 * Tocar una observación muestra en la imagen dónde la vio la IA (un pin
 * violeta con chispas, que no es una marca).
 *
 * Mientras la IA mira la pieza se avisa en una línea; si falló o no se
 * revisó, no se muestra nada: la revisión sigue como siempre.
 */
export function PanelRevisionIA({
  revision, imagenes, elegida, convertidas, deshabilitado, onElegir, onConvertir, onDeshacer, onDescartar,
}: {
  revision: RevisionIA | null
  imagenes: { id: string; orden: number }[]
  elegida: string | null
  /** id de observación -> número de la marca que se hizo con ella en esta revisión (sin mandar todavía). */
  convertidas: Record<string, number>
  deshabilitado: boolean
  onElegir: (o: ObservacionIA) => void
  onConvertir: (o: ObservacionIA) => void
  onDeshacer: (o: ObservacionIA) => void
  onDescartar: (o: ObservacionIA, descartada: boolean) => Promise<void>
}) {
  const [abierta, setAbierta] = useState(true)
  const [ocupada, setOcupada] = useState<string | null>(null)

  if (!revision || revision.estado === 'nada') return null

  if (revision.estado === 'pendiente') {
    return (
      <p role="status" className="flex items-center gap-2 rounded-xl border border-violet-200 bg-violet-50/70 px-3 py-2 text-sm text-violet-900 dark:border-violet-500/30 dark:bg-violet-500/10 dark:text-violet-100">
        <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden />
        La IA está mirando la pieza (ortografía, mundo, legales, precio, QR)…
      </p>
    )
  }

  const obs = revision.observaciones
  const ordenadas = ordenarObservaciones(obs)
  const numeroDeImagen = (id: string | null) => {
    const i = imagenes.findIndex(im => im.id === id)
    return i === -1 ? null : i + 1
  }

  async function descartar(o: ObservacionIA, descartada: boolean) {
    setOcupada(o.id)
    try { await onDescartar(o, descartada) } finally { setOcupada(null) }
  }

  return (
    <section
      aria-labelledby="revision-ia-titulo"
      className="rounded-2xl border border-violet-200 bg-violet-50/70 p-3 dark:border-violet-500/30 dark:bg-violet-500/10"
    >
      <div className="flex items-start gap-2.5">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-violet-600 text-white" aria-hidden>
          <Sparkles className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <h4 id="revision-ia-titulo" className="text-sm font-bold leading-snug text-violet-950 dark:text-violet-50">
            {tituloRevisionIA(obs)}
          </h4>
          <p className="mt-0.5 text-xs leading-snug text-violet-900/80 dark:text-violet-200/80">
            {obs.length === 0
              ? 'Miró ortografía, mundo, legales, precio y QR. Es una ayuda: igual mirala vos.'
              : 'Es una ayuda y se puede equivocar: decidís vos. La agencia no ve esta lista, solo las marcas que hagas.'}
          </p>
        </div>
        {obs.length > 0 && (
          <button
            type="button"
            onClick={() => setAbierta(v => !v)}
            aria-expanded={abierta}
            aria-controls="revision-ia-lista"
            className="-mr-1 -mt-1 flex min-h-[36px] shrink-0 items-center gap-1 rounded-lg px-2 text-xs font-semibold text-violet-800 transition hover:bg-violet-100 dark:text-violet-200 dark:hover:bg-violet-500/20"
          >
            {abierta ? 'Ocultar' : 'Ver'}
            <ChevronDown className={`h-4 w-4 transition-transform ${abierta ? 'rotate-180' : ''}`} aria-hidden />
          </button>
        )}
      </div>

      {abierta && obs.length > 0 && (
        <ul id="revision-ia-lista" className="mt-2.5 space-y-1.5">
          {ordenadas.map(o => {
            const esElegida = elegida === o.id
            const local = convertidas[o.id]
            const conLugar = tieneLugar(o, imagenes)
            const nImagen = imagenes.length > 1 ? numeroDeImagen(o.imagenId) : null
            const cerrada = o.estado !== 'nueva' || local != null
            return (
              <li
                key={o.id}
                className={`rounded-xl border bg-white p-2.5 transition dark:bg-slate-900 ${
                  esElegida ? 'border-violet-400 ring-2 ring-violet-200 dark:border-violet-400/70 dark:ring-violet-500/30' : 'border-violet-100 dark:border-slate-700'
                } ${o.estado === 'descartada' ? 'opacity-60' : ''}`}
              >
                <button
                  type="button"
                  onClick={() => onElegir(o)}
                  aria-pressed={esElegida}
                  className="block w-full text-left"
                >
                  {/* La gravedad va adentro del renglón: en la columna angosta
                      (el teléfono, o al lado de la imagen en la notebook) el
                      texto sigue abajo y no queda una columna vacía. */}
                  <span className={`text-sm leading-snug text-slate-800 dark:text-slate-200 ${o.estado === 'descartada' ? 'line-through decoration-slate-400' : ''}`}>
                    <span className={`mr-1.5 inline-block rounded-full px-1.5 py-px align-[1px] text-[11px] font-bold no-underline ${
                      o.gravedad === 'importante'
                        ? 'bg-rose-100 text-rose-800 dark:bg-rose-500/20 dark:text-rose-200'
                        : 'bg-amber-100 text-amber-900 dark:bg-amber-500/20 dark:text-amber-100'
                    }`}>
                      {o.gravedad === 'importante' ? 'Importante' : 'A revisar'}
                    </span>
                    <span className="font-semibold">{TIPO_OBSERVACION[o.tipo] ?? 'Otro'}</span>
                    {' · '}{o.texto}
                  </span>
                  {/* Dónde está, mientras sigue abierta (resuelta, ya no hace falta). */}
                  {!cerrada && (
                    <span className="mt-1 flex items-center gap-1 text-xs font-medium text-violet-700 dark:text-violet-300">
                      {conLugar ? (
                        <><MapPin className="h-3.5 w-3.5" aria-hidden /> {esElegida ? 'Marcado en la imagen' : 'Tocá para ver dónde'}{nImagen ? ` (imagen ${nImagen})` : ''}</>
                      ) : 'Sin un lugar exacto en la imagen'}
                    </span>
                  )}
                </button>

                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {!cerrada && (
                    <>
                      <button
                        type="button"
                        onClick={() => onConvertir(o)}
                        disabled={deshabilitado}
                        className="flex min-h-[36px] items-center gap-1.5 rounded-lg bg-violet-600 px-3 text-xs font-bold text-white shadow-sm transition hover:bg-violet-700 active:scale-[.98] disabled:opacity-50"
                      >
                        <Stamp className="h-3.5 w-3.5" aria-hidden /> Hacer marca
                      </button>
                      <button
                        type="button"
                        onClick={() => void descartar(o, true)}
                        disabled={deshabilitado || ocupada === o.id}
                        className="flex min-h-[36px] items-center gap-1.5 rounded-lg px-3 text-xs font-semibold text-slate-600 transition hover:bg-slate-100 disabled:opacity-50 dark:text-slate-300 dark:hover:bg-slate-800"
                      >
                        {ocupada === o.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <X className="h-3.5 w-3.5" aria-hidden />} Descartar
                      </button>
                    </>
                  )}
                  {local != null && (
                    <p className="flex flex-wrap items-center gap-x-2 text-xs font-semibold text-brand-700 dark:text-brand-200">
                      Es tu marca {local}: se manda con tu decisión.
                      <button type="button" onClick={() => onDeshacer(o)} disabled={deshabilitado}
                        className="min-h-[32px] rounded-lg px-1.5 font-semibold text-slate-600 underline underline-offset-2 hover:text-slate-900 dark:text-slate-300">
                        Deshacer
                      </button>
                    </p>
                  )}
                  {o.estado === 'marca' && (
                    <p className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                      Ya es la marca {o.numero}{o.porNombre ? ` (la hizo ${o.porNombre})` : ''}.
                    </p>
                  )}
                  {o.estado === 'descartada' && (
                    <p className="flex flex-wrap items-center gap-x-2 text-xs text-slate-600 dark:text-slate-400">
                      Descartada{o.porNombre ? ` por ${o.porNombre}` : ''}.
                      <button type="button" onClick={() => void descartar(o, false)} disabled={deshabilitado || ocupada === o.id}
                        className="flex min-h-[32px] items-center gap-1 rounded-lg px-1.5 font-semibold text-slate-700 underline underline-offset-2 hover:text-slate-900 dark:text-slate-300">
                        <RotateCcw className="h-3 w-3" aria-hidden /> Traerla de vuelta
                      </button>
                    </p>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

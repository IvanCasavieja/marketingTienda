'use client'

import { useState } from 'react'
import { AlertTriangle, FileArchive, Link2, Loader2, MapPin, MessageSquarePlus, RotateCcw, Sparkles, Stamp, X } from 'lucide-react'
import {
  TIPO_OBSERVACION, archivoDe, ordenarObservaciones, textoRevisados, tieneLugar, tituloRevisionIA,
  type ObservacionIA, type RevisionIA,
} from '@/lib/calendario/revision-ia'

/**
 * Lo que encontró la IA en la pieza, en el Revisor.
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
 * No aparece sola (Ivan, 19/11/2026: "quizás está demasiado inteligencia
 * artificial y puede llegar a provocar confusión"): el Revisor la muestra
 * recién cuando se toca "Ver lo que encontró la IA", y acá hay una X para
 * cerrarla. Cuándo se calcula no cambió: la hace el servidor al entregar.
 *
 * Desde el 19/11/2026 la IA mira también lo que vino en un ZIP o detrás del
 * link: esas observaciones dicen de qué archivo son (no se ven acá, no se
 * guardan), y abajo va qué más miró y qué no pudo abrir (un link de Smash,
 * un ZIP roto), para que quien aprueba sepa qué le falta mirar a él. En una
 * ronda que vino solo con el link no hay imagen donde marcar: "Hacer marca"
 * pasa a ser "Pasar al comentario".
 */
export function PanelRevisionIA({
  revision, imagenes, elegida, convertidas, pasadas, deshabilitado, onElegir, onConvertir, onDeshacer, onDescartar, onCerrar,
}: {
  revision: RevisionIA | null
  imagenes: { id: string; orden: number }[]
  elegida: string | null
  /** id de observación -> número de la marca que se hizo con ella en esta revisión (sin mandar todavía). */
  convertidas: Record<string, number>
  /** Las que se pasaron al comentario (ronda sin imágenes). */
  pasadas: string[]
  deshabilitado: boolean
  onElegir: (o: ObservacionIA) => void
  onConvertir: (o: ObservacionIA) => void
  onDeshacer: (o: ObservacionIA) => void
  onDescartar: (o: ObservacionIA, descartada: boolean) => Promise<void>
  onCerrar: () => void
}) {
  const [ocupada, setOcupada] = useState<string | null>(null)

  if (!revision || revision.estado === 'nada') return null

  if (revision.estado === 'pendiente') {
    return (
      <p id="revision-ia" role="status" className="flex items-center gap-2 rounded-xl border border-slate-300 px-3 py-2 text-sm text-slate-700 dark:border-slate-700 dark:text-slate-300">
        <Loader2 className="h-4 w-4 shrink-0 animate-spin text-violet-600 dark:text-violet-300" aria-hidden />
        La IA está mirando la pieza (ortografía, mundo, legales, precio, QR)…
      </p>
    )
  }

  const obs = revision.observaciones
  const ordenadas = ordenarObservaciones(obs)
  const revisados = revision.revisados ?? []
  const noSePudo = revision.noSePudoAbrir ?? []
  const ignorados = revision.ignorados ?? []
  // Sin imágenes subidas y sin poder abrir el link: no miró nada. Que no
  // diga "no encontró nada", que suena a que estaba todo bien.
  const nadaMirado = imagenes.length === 0 && revisados.length === 0
  const sinImagenes = imagenes.length === 0
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
      id="revision-ia"
      aria-labelledby="revision-ia-titulo"
      className="rounded-2xl border border-slate-300 p-3 dark:border-slate-700"
    >
      <div className="flex items-start gap-2.5">
        <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-violet-600 dark:text-violet-300" aria-hidden />
        <div className="min-w-0 flex-1">
          <h4 id="revision-ia-titulo" className="text-sm font-bold leading-snug text-slate-900 dark:text-slate-100">
            {nadaMirado && obs.length === 0 ? 'La IA no pudo mirar la pieza' : tituloRevisionIA(obs)}
          </h4>
          <p className="mt-0.5 text-xs leading-snug text-slate-500 dark:text-slate-400">
            {nadaMirado && obs.length === 0
              ? 'No pudo abrir lo que entregó la agencia (abajo, el porqué): revisala vos en el link.'
              : obs.length === 0
                ? 'Miró ortografía, mundo, legales, precio y QR. Es una ayuda: igual mirala vos.'
                : 'Es una ayuda y se puede equivocar: decidís vos. La agencia no ve esta lista, solo lo que pases a tus marcas o al comentario.'}
          </p>
        </div>
        <button
          type="button"
          onClick={onCerrar}
          aria-label="Cerrar lo que encontró la IA"
          title="Cerrar"
          className="-mr-2 -mt-2 flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100 sm:-mr-1.5 sm:-mt-1.5 sm:h-9 sm:w-9"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {obs.length > 0 && (
        <ul id="revision-ia-lista" className="mt-2.5 space-y-1.5">
          {ordenadas.map(o => {
            const esElegida = elegida === o.id
            const local = convertidas[o.id]
            const conLugar = tieneLugar(o, imagenes)
            const nImagen = imagenes.length > 1 ? numeroDeImagen(o.imagenId) : null
            const pasada = pasadas.includes(o.id)
            const cerrada = o.estado !== 'nueva' || local != null || pasada
            // De un archivo del ZIP o del link (no se ve acá): se dice cuál.
            const archivo = archivoDe(o)
            return (
              <li
                key={o.id}
                className={`rounded-xl border p-2.5 transition ${
                  esElegida ? 'border-violet-400 ring-2 ring-violet-200 dark:border-violet-400/70 dark:ring-violet-500/30' : 'border-slate-200 dark:border-slate-700'
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
                        ? 'bg-violet-100 text-violet-900 dark:bg-violet-500/20 dark:text-violet-100'
                        : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
                    }`}>
                      {o.gravedad === 'importante' ? 'Importante' : 'A revisar'}
                    </span>
                    <span className="font-semibold">{TIPO_OBSERVACION[o.tipo] ?? 'Otro'}</span>
                    {' · '}{o.texto}
                  </span>
                  {/* De qué archivo es (siempre: es lo que hay que ir a mirar), o
                      dónde está en la imagen mientras sigue abierta. */}
                  {archivo ? (
                    <span className="mt-1 flex items-start gap-1 text-xs font-medium text-slate-700 dark:text-slate-300">
                      {o.origen === 'link'
                        ? <Link2 className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
                        : <FileArchive className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />}
                      <span className="min-w-0 break-words">En {archivo} ({o.origen === 'link' ? 'del link' : 'del ZIP'})</span>
                    </span>
                  ) : !cerrada && (
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
                        {sinImagenes
                          ? <><MessageSquarePlus className="h-3.5 w-3.5" aria-hidden /> Pasar al comentario</>
                          : <><Stamp className="h-3.5 w-3.5" aria-hidden /> Hacer marca</>}
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
                  {pasada && (
                    <p className="text-xs font-semibold text-brand-700 dark:text-brand-200">
                      Está en tu comentario: se manda con tu decisión.
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

      {/* Lo del ZIP y el link: qué más miró, qué no pudo abrir y qué no mira. */}
      {(revisados.length > 0 || noSePudo.length > 0 || ignorados.length > 0) && (
        <div className="mt-3 space-y-1.5 border-t border-slate-300 pt-2.5 text-xs leading-snug dark:border-slate-700">
          {revisados.length > 0 && (
            <p className="text-slate-600 dark:text-slate-400">
              <span className="font-semibold text-slate-800 dark:text-slate-200">También miró </span>
              {textoRevisados(revisados)}.
            </p>
          )}
          {noSePudo.length > 0 && (
            <ul className="space-y-1">
              {noSePudo.map((m, i) => (
                <li key={i} className="flex gap-1.5 text-amber-900 dark:text-amber-200">
                  <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
                  <span className="min-w-0 break-words">{m}</span>
                </li>
              ))}
            </ul>
          )}
          {ignorados.length > 0 && (
            <p className="break-words text-slate-500 dark:text-slate-400">
              No mira lo que no es imagen ni PDF: {ignorados.slice(0, 4).map(n => `«${n}»`).join(', ')}
              {ignorados.length > 4 ? ` y ${ignorados.length - 4} más` : ''}.
            </p>
          )}
        </div>
      )}
    </section>
  )
}

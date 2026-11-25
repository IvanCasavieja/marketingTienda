'use client'

import { useState } from 'react'
import { AlertTriangle, FileArchive, Link2, Loader2, MapPin, MessageSquarePlus, RotateCcw, Sparkles, Stamp, X } from 'lucide-react'
import {
  TIPO_OBSERVACION, agruparIguales, archivoDe, cambiosPorMarca, ordenarObservaciones, puntosParaMostrar, textoDeImagenes,
  textoRevisados, tieneLugar, tituloRevisionIA, type ObservacionIA, type RevisionIA,
} from '@/lib/calendario/revision-ia'

/**
 * Lo que encontró la IA en la pieza, en el Revisor.
 *
 * Es una ayuda para quien aprueba, no una decisión, y se dice así: la IA se
 * puede equivocar y decide la persona. Por eso cada observación tiene dos
 * salidas y ninguna es automática: "Hacer marca" (pasa a ser una marca
 * normal, del aprobador, que puede corregir antes de mandar) o "Descartar".
 * La agencia vio lo mismo antes de mandar (su control previo, 24/11/2026);
 * esta lista, con lo que se descartó o se hizo marca, es del equipo.
 *
 * Tocar una observación muestra en la imagen dónde la vio la IA (un pin rojo
 * con chispas, que no es una marca).
 *
 * Se ve abierta, sin tocar nada, en el costado junto con lo que falta y lo
 * que se pidió (24/11/2026, Ivan: "siempre se debe abrir por defecto lo que
 * la IA detecta, no esperar que yo presione arriba"). Del 19/11/2026 hasta
 * ese día había que tocar "Ver lo que encontró la IA" (Ivan: "quizás está
 * demasiado inteligencia artificial"). El borde lo pone el Revisor, que la
 * junta con lo demás. Lo que está mal va en rojo y lo dudoso en ámbar (Ivan:
 * "que sea azul da impresión de estar bien"); antes era violeta.
 *
 * Desde el 19/11/2026 la IA mira también lo que vino en un ZIP o detrás del
 * link: esas observaciones dicen de qué archivo son (no se ven acá, no se
 * guardan), y abajo va qué más miró y qué no pudo abrir (un link vencido o
 * con contraseña, un ZIP roto), para que quien aprueba sepa qué le falta
 * mirar a él. Los links de WeTransfer y de Smash los baja sin cuenta, como
 * sus páginas (backend/app/services/materiales.py). En una ronda que vino
 * solo con el link no hay imagen donde marcar: "Hacer marca" pasa a ser
 * "Pasar al comentario".
 */
export function PanelRevisionIA({
  revision, imagenes, elegida, convertidas, pasadas, deshabilitado, onElegir, onConvertir, onDeshacer, onDescartar,
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
}) {
  const [ocupada, setOcupada] = useState<string | null>(null)

  if (!revision || revision.estado === 'nada') return null

  if (revision.estado === 'pendiente') {
    return (
      <p id="revision-ia" role="status" className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
        <Loader2 className="h-4 w-4 shrink-0 animate-spin text-rose-600 dark:text-rose-300" aria-hidden />
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
  // Si al lado de las marcas de la ronda anterior dice «IA: falta», sin
  // observaciones el título dice «nada nuevo», no «nada» (19/11/2026). Lo
  // mismo con lo que se pidió sin marcas, que se ve en su caja (21/11/2026).
  const conCambiosPedidos = cambiosPorMarca(revision).size > 0 || puntosParaMostrar(revision) != null
  const sinImagenes = imagenes.length === 0
  // Algo para mirar todavía abierto: el título va en rojo.
  const hayAbiertas = obs.some(o => o.estado === 'nueva')
  const numeroDeImagen = (id: string | null) => {
    const i = imagenes.findIndex(im => im.id === id)
    return i === -1 ? null : i + 1
  }

  async function descartar(o: ObservacionIA, descartada: boolean) {
    setOcupada(o.id)
    try { await onDescartar(o, descartada) } finally { setOcupada(null) }
  }

  // Las que dicen lo mismo en varias imágenes van juntas mientras siguen
  // abiertas (25/11/2026: "¿se repiten?"). Marcarlas pone una marca en cada
  // imagen; descartarlas, las descarta todas.
  const abierta = (o: ObservacionIA) =>
    o.estado === 'nueva' && convertidas[o.id] == null && !pasadas.includes(o.id) && !archivoDe(o)
  const grupos = agruparIguales(ordenadas, abierta)

  return (
    <section id="revision-ia" aria-labelledby="revision-ia-titulo">
      <div className="flex items-start gap-2">
        {hayAbiertas
          ? <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600 dark:text-rose-400" aria-hidden />
          : <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-slate-500 dark:text-slate-400" aria-hidden />}
        <div className="min-w-0 flex-1">
          <h4 id="revision-ia-titulo" className={`text-sm font-bold leading-snug ${hayAbiertas ? 'text-rose-800 dark:text-rose-200' : 'text-slate-900 dark:text-slate-100'}`}>
            {nadaMirado && obs.length === 0 ? 'La IA no pudo mirar la pieza' : tituloRevisionIA(obs, conCambiosPedidos)}
          </h4>
          <p className="mt-0.5 text-xs leading-snug text-slate-600 dark:text-slate-400">
            {nadaMirado && obs.length === 0
              ? 'No pudo abrir lo que entregó la agencia (abajo, el porqué): revisala vos en el link.'
              : obs.length === 0
                ? 'Miró ortografía, mundo, legales, precio y QR. Es una ayuda: igual mirala vos.'
                : 'Es una ayuda y se puede equivocar: decidís vos. A la agencia le llega lo que pases a tus marcas o al comentario.'}
          </p>
        </div>
      </div>

      {obs.length > 0 && (
        <ul id="revision-ia-lista" className="mt-2.5 space-y-1.5">
          {grupos.map(g => {
            if (g.length > 1) {
              const o = g[0]
              const ids = g.map(x => x.id)
              const algunaElegida = g.some(x => x.id === elegida)
              const ocupado = ocupada != null && ids.includes(ocupada)
              const numeros = g.map(x => numeroDeImagen(x.imagenId)).filter((n): n is number => n != null)
              return (
                <li
                  key={ids.join('+')}
                  className={`rounded-xl border p-2.5 transition ${
                    o.gravedad === 'importante'
                      ? 'border-rose-300 bg-rose-50 dark:border-rose-500/40 dark:bg-rose-500/10'
                      : 'border-amber-300 bg-amber-50 dark:border-amber-500/40 dark:bg-amber-500/10'
                  } ${algunaElegida ? 'ring-2 ring-rose-400 dark:ring-rose-400/70' : ''}`}
                >
                  <p className="text-sm leading-snug text-slate-900 dark:text-slate-100">
                    <span className={`mr-1.5 inline-block rounded-full px-1.5 py-px align-[1px] text-[11px] font-bold ${
                      o.gravedad === 'importante'
                        ? 'bg-rose-600 text-white'
                        : 'bg-amber-200 text-amber-950 dark:bg-amber-400/25 dark:text-amber-100'
                    }`}>
                      {o.gravedad === 'importante' ? 'Importante' : 'A revisar'}
                    </span>
                    <span className="font-semibold">{TIPO_OBSERVACION[o.tipo] ?? 'Otro'}</span>
                    {' · '}{o.texto}
                  </p>
                  <p className="mt-1 flex flex-wrap items-center gap-x-1 text-xs font-semibold text-rose-800 dark:text-rose-200">
                    <MapPin className="h-3.5 w-3.5" aria-hidden />
                    {numeros.length > 0 ? `Está en ${textoDeImagenes(numeros)}. Ver dónde:` : `Está en ${g.length} lugares. Ver dónde:`}
                    {g.map((x, i) => (
                      <button
                        key={x.id}
                        type="button"
                        onClick={() => onElegir(x)}
                        aria-pressed={elegida === x.id}
                        className={`min-h-[32px] rounded-md px-1.5 underline underline-offset-2 hover:bg-white/70 dark:hover:bg-slate-800 ${elegida === x.id ? 'bg-white/80 dark:bg-slate-800' : ''}`}
                      >
                        {numeroDeImagen(x.imagenId) != null ? `imagen ${numeroDeImagen(x.imagenId)}` : `lugar ${i + 1}`}
                      </button>
                    ))}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => g.forEach(x => onConvertir(x))}
                      disabled={deshabilitado}
                      className="flex min-h-[36px] items-center gap-1.5 rounded-lg bg-rose-700 px-3 text-xs font-bold text-white shadow-sm transition hover:bg-rose-800 active:scale-[.98] disabled:opacity-50"
                    >
                      {sinImagenes
                        ? <><MessageSquarePlus className="h-3.5 w-3.5" aria-hidden /> Pasar al comentario</>
                        : <><Stamp className="h-3.5 w-3.5" aria-hidden /> Hacer una marca en cada una</>}
                    </button>
                    <button
                      type="button"
                      onClick={() => void (async () => { for (const x of g) await descartar(x, true) })()}
                      disabled={deshabilitado || ocupado}
                      className="flex min-h-[36px] items-center gap-1.5 rounded-lg px-3 text-xs font-semibold text-slate-700 transition hover:bg-white/70 disabled:opacity-50 dark:text-slate-300 dark:hover:bg-slate-800"
                    >
                      {ocupado ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <X className="h-3.5 w-3.5" aria-hidden />} Descartar
                    </button>
                  </div>
                </li>
              )
            }
            const o = g[0]
            const esElegida = elegida === o.id
            const local = convertidas[o.id]
            const conLugar = tieneLugar(o, imagenes)
            const nImagen = imagenes.length > 1 ? numeroDeImagen(o.imagenId) : null
            const pasada = pasadas.includes(o.id)
            const cerrada = o.estado !== 'nueva' || local != null || pasada
            // De un archivo del ZIP o del link (no se ve acá): se dice cuál.
            const archivo = archivoDe(o)
            // Rojo lo importante, ámbar lo dudoso; lo que ya se resolvió, neutro.
            const tono = cerrada
              ? 'border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-900'
              : o.gravedad === 'importante'
                ? 'border-rose-300 bg-rose-50 dark:border-rose-500/40 dark:bg-rose-500/10'
                : 'border-amber-300 bg-amber-50 dark:border-amber-500/40 dark:bg-amber-500/10'
            return (
              <li
                key={o.id}
                className={`rounded-xl border p-2.5 transition ${tono} ${
                  esElegida ? 'ring-2 ring-rose-400 dark:ring-rose-400/70' : ''
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
                  <span className={`text-sm leading-snug text-slate-900 dark:text-slate-100 ${o.estado === 'descartada' ? 'line-through decoration-slate-400' : ''}`}>
                    <span className={`mr-1.5 inline-block rounded-full px-1.5 py-px align-[1px] text-[11px] font-bold no-underline ${
                      o.gravedad === 'importante'
                        ? 'bg-rose-600 text-white'
                        : 'bg-amber-200 text-amber-950 dark:bg-amber-400/25 dark:text-amber-100'
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
                    <span className="mt-1 flex items-center gap-1 text-xs font-semibold text-rose-800 dark:text-rose-200">
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
                        className="flex min-h-[36px] items-center gap-1.5 rounded-lg bg-rose-700 px-3 text-xs font-bold text-white shadow-sm transition hover:bg-rose-800 active:scale-[.98] disabled:opacity-50"
                      >
                        {sinImagenes
                          ? <><MessageSquarePlus className="h-3.5 w-3.5" aria-hidden /> Pasar al comentario</>
                          : <><Stamp className="h-3.5 w-3.5" aria-hidden /> Hacer marca</>}
                      </button>
                      <button
                        type="button"
                        onClick={() => void descartar(o, true)}
                        disabled={deshabilitado || ocupada === o.id}
                        className="flex min-h-[36px] items-center gap-1.5 rounded-lg px-3 text-xs font-semibold text-slate-700 transition hover:bg-white/70 disabled:opacity-50 dark:text-slate-300 dark:hover:bg-slate-800"
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

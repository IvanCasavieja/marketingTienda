'use client'

import { useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, CheckCircle2, HelpCircle, Keyboard, Loader2, Mic, RotateCcw, Sparkles, Square,
} from 'lucide-react'
import {
  iaApi, MAX_TEXTO_BRIEF, type BriefOrdenado, type CampoBrief, type TipoPiezaBrief as TipoPieza,
} from '@/lib/api'
import { extractErrorDetail } from '@/lib/errors'
import { useDictado } from './useDictado'

/**
 * Dictar un pedido para la agencia y que la IA lo ordene.
 *
 * Pedido (15/11/2026): desde el celular, la persona aprieta el micrófono, dice
 * "necesito cenefas para el Ciberlunes, 2x1 en vinos, del 28 al 30, 40
 * locales..." y la IA lo ordena en los campos de ese tipo de pieza y le avisa
 * qué falta ("Falta la vigencia", "Faltan las medidas").
 *
 * Es un componente suelto para enchufar en cualquier formulario de pedido:
 * muestra el micrófono, el texto (que se ve en vivo mientras se dicta y se
 * puede corregir a mano), el resultado ordenado, editable, y lo que falta. El
 * resultado sale por `onListo`; qué hacer con él lo decide el formulario (en
 * las tareas del calendario, va a la descripción).
 *
 * Sin dictado en el navegador (Firefox, por ejemplo) se escribe el pedido y
 * es el mismo camino: la IA ordena texto, no audio.
 */

export const TIPOS_DE_PIEZA: { tipo: TipoPieza; nombre: string }[] = [
  { tipo: 'cenefa', nombre: 'Cenefa' },
  { tipo: 'mailing', nombre: 'Mailing' },
  { tipo: 'banner_web', nombre: 'Banner web' },
  { tipo: 'redes', nombre: 'Redes' },
  { tipo: 'otro', nombre: 'Otro' },
]

/** Lo que entrega el componente: lo ordenado (con lo que la persona corrigió). */
export type BriefListo = Omit<BriefOrdenado, 'usage'> & {
  /** Lo que se dictó o escribió, tal cual. */
  textoOriginal: string
  /** El pedido en texto, listo para pegar en una descripción. */
  comoTexto: string
}

/** Los campos que se escriben en más de un renglón. */
const LARGOS = new Set(['copy', 'texto', 'legales'])

function vacio(v: string | null | undefined): boolean {
  return !v || !v.trim()
}

/** Lo que falta, recalculado con lo que hay ahora (se completa a mano). */
export function faltantes(campos: CampoBrief[]): string[] {
  return campos.filter(c => vacio(c.valor)).map(c => c.falta)
}

/** El pedido en texto plano, para una descripción o un mail. */
export function briefComoTexto(b: Pick<BriefOrdenado, 'tipoNombre' | 'resumen' | 'campos' | 'notas' | 'dudas'>): string {
  // El título ya suele decir el tipo ("Cenefas Ciberlunes"): va aparte, con raya.
  const renglones = [`Pedido de ${b.tipoNombre.toLowerCase()} — ${b.resumen}`]
  for (const c of b.campos) renglones.push(`- ${c.etiqueta}: ${vacio(c.valor) ? '(falta)' : c.valor!.trim()}`)
  if (!vacio(b.notas)) renglones.push(`Notas: ${b.notas!.trim()}`)
  if (b.dudas.length) renglones.push(`Para confirmar: ${b.dudas.join(' ')}`)
  return renglones.join('\n')
}

export function DictarBrief({
  tipoInicial = 'cenefa',
  tipos,
  textoInicial = '',
  etiquetaUsar = 'Usar este pedido',
  onListo,
  onCancelar,
}: {
  tipoInicial?: TipoPieza
  /** Qué tipos se ofrecen. Con uno solo, no se muestra para elegir. Por defecto, todos. */
  tipos?: TipoPieza[]
  textoInicial?: string
  /** El botón que entrega el resultado, ej. "Usar en la tarea". */
  etiquetaUsar?: string
  onListo: (brief: BriefListo) => void
  onCancelar?: () => void
}) {
  const ofrecidos = TIPOS_DE_PIEZA.filter(t => !tipos || tipos.includes(t.tipo))
  const [tipo, setTipo] = useState<TipoPieza>(tipoInicial)
  const [texto, setTexto] = useState(textoInicial)
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [resultado, setResultado] = useState<BriefOrdenado | null>(null)
  const resultadoRef = useRef<HTMLDivElement>(null)

  const dictado = useDictado(tramo => {
    if (!tramo) return
    setTexto(t => {
      const junto = t.trim() ? `${t.trimEnd()} ${tramo}` : tramo
      return junto.slice(0, MAX_TEXTO_BRIEF)
    })
  })

  const falta = useMemo(() => (resultado ? faltantes(resultado.campos) : []), [resultado])
  const nombreTipo = TIPOS_DE_PIEZA.find(t => t.tipo === (resultado?.tipo ?? tipo))?.nombre ?? 'pieza'
  const sePuedeOrdenar = texto.trim().length >= 3 && !cargando && !dictado.escuchando

  async function ordenar() {
    if (!sePuedeOrdenar) return
    setCargando(true)
    setError(null)
    try {
      const { data } = await iaApi.ordenarBrief(texto.trim(), tipo)
      setResultado(data)
      // En el teléfono el resultado queda abajo del texto: se lo lleva a la vista.
      requestAnimationFrame(() => resultadoRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
    } catch (err) {
      setError(extractErrorDetail(err, 'No se pudo ordenar el pedido. Probá de nuevo en un ratito.'))
    } finally {
      setCargando(false)
    }
  }

  function cambiarCampo(clave: string, valor: string) {
    setResultado(r => r && { ...r, campos: r.campos.map(c => (c.clave === clave ? { ...c, valor } : c)) })
  }

  function usar() {
    if (!resultado) return
    const campos = resultado.campos.map(c => ({ ...c, valor: vacio(c.valor) ? null : c.valor!.trim() }))
    const limpio = {
      tipo: resultado.tipo,
      tipoNombre: resultado.tipoNombre,
      resumen: resultado.resumen.trim() || resultado.tipoNombre,
      campos,
      falta: faltantes(campos),
      dudas: resultado.dudas,
      notas: vacio(resultado.notas) ? null : resultado.notas!.trim(),
    }
    onListo({ ...limpio, textoOriginal: texto.trim(), comoTexto: briefComoTexto(limpio) })
  }

  return (
    <div
      className="space-y-4 rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900 sm:p-4"
      // Va adentro de formularios (el de una tarea nueva): un Enter en un campo
      // de acá no tiene que mandar el formulario de afuera a medio completar.
      onKeyDown={e => { if (e.key === 'Enter' && (e.target as HTMLElement).tagName === 'INPUT') e.preventDefault() }}
    >
      {ofrecidos.length > 1 && (
        <div>
          <span className="etiqueta-campo">Qué hay que pedir</span>
          <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1" role="radiogroup" aria-label="Tipo de pieza">
            {ofrecidos.map(t => (
              <button
                key={t.tipo}
                type="button"
                role="radio"
                aria-checked={tipo === t.tipo}
                onClick={() => setTipo(t.tipo)}
                className={`h-10 shrink-0 rounded-full px-4 text-sm font-semibold transition active:scale-95 sm:h-9 ${
                  tipo === t.tipo
                    ? 'bg-brand-600 text-white shadow-sm'
                    : 'bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700'
                }`}
              >
                {t.nombre}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* El micrófono, o el aviso de que acá se escribe */}
      {dictado.disponible === false ? (
        <p className="flex items-start gap-2.5 rounded-xl bg-slate-50 px-3.5 py-3 text-sm text-slate-600 dark:bg-slate-800/60 dark:text-slate-300">
          <Keyboard className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" aria-hidden />
          <span>Tu navegador no permite dictar. Escribí el pedido acá abajo y la IA lo ordena igual.</span>
        </p>
      ) : (
        <div className="flex items-center gap-3.5">
          <button
            type="button"
            onClick={dictado.escuchando ? dictado.parar : dictado.empezar}
            disabled={dictado.disponible === null || cargando}
            aria-pressed={dictado.escuchando}
            aria-label={dictado.escuchando ? 'Parar el dictado' : 'Empezar a dictar'}
            className={`relative flex h-14 w-14 shrink-0 items-center justify-center rounded-full text-white shadow-md transition active:scale-95 disabled:opacity-50 ${
              dictado.escuchando ? 'bg-rose-600 hover:bg-rose-700' : 'bg-brand-600 hover:bg-brand-700'
            }`}
          >
            {dictado.escuchando && <span className="absolute inset-0 animate-ping rounded-full bg-rose-500/40" aria-hidden />}
            {dictado.escuchando ? <Square className="relative h-5 w-5 fill-current" /> : <Mic className="relative h-6 w-6" />}
          </button>
          {/* Lo que va entendiendo se ve acá, al lado del micrófono: en el
              teléfono es lo que queda a la vista mientras se habla. Lo que ya
              dio por definitivo va sumándose al texto de abajo. */}
          <div className="min-w-0 text-sm" aria-live="polite">
            <p className="font-semibold text-slate-900 dark:text-slate-100">
              {dictado.escuchando ? 'Escuchando… tocá para terminar' : 'Tocá el micrófono y contá el pedido'}
            </p>
            {dictado.escuchando && dictado.provisorio ? (
              <p className="break-words italic text-slate-700 dark:text-slate-300">“{dictado.provisorio}…”</p>
            ) : (
              <p className="text-slate-500 dark:text-slate-400">
                {dictado.escuchando
                  ? 'Decí qué es, para qué acción, la oferta, las fechas y dónde va.'
                  : 'O escribilo abajo. Después la IA lo ordena.'}
              </p>
            )}
          </div>
        </div>
      )}

      {dictado.error && (
        <p role="alert" className="flex items-start gap-2 rounded-xl bg-amber-50 px-3.5 py-2.5 text-sm text-amber-900 dark:bg-amber-500/10 dark:text-amber-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {dictado.error}
        </p>
      )}

      <div>
        <label className="etiqueta-campo" htmlFor="dictar-brief-texto">El pedido</label>
        <textarea
          id="dictar-brief-texto"
          value={texto}
          onChange={e => setTexto(e.target.value)}
          maxLength={MAX_TEXTO_BRIEF}
          rows={4}
          placeholder="Ej: necesito cenefas para el Ciberlunes, 2x1 en vinos, del 28 al 30, 40 locales…"
          className="campo h-auto min-h-[104px] resize-y py-2.5 leading-relaxed"
        />
        {texto.length > MAX_TEXTO_BRIEF - 500 && (
          <p className="mt-1 text-xs text-slate-500">{texto.length} de {MAX_TEXTO_BRIEF} caracteres</p>
        )}
      </div>

      {error && (
        <p role="alert" className="flex items-start gap-2 rounded-xl bg-rose-50 px-3.5 py-2.5 text-sm text-rose-800 dark:bg-rose-500/10 dark:text-rose-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {error}
        </p>
      )}

      <div className="flex flex-wrap items-center justify-end gap-2">
        {onCancelar && !resultado && (
          <button type="button" onClick={onCancelar} className="min-h-[44px] rounded-xl px-4 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800 sm:min-h-[40px]">
            Cancelar
          </button>
        )}
        <button
          type="button"
          onClick={ordenar}
          disabled={!sePuedeOrdenar}
          title={dictado.escuchando ? 'Pará el dictado para ordenar' : undefined}
          className={`flex min-h-[44px] items-center gap-2 rounded-xl px-4 text-sm font-semibold transition active:scale-[.98] disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-[40px] ${
            resultado
              ? 'bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-200'
              : 'bg-brand-600 text-white shadow-sm hover:bg-brand-700'
          }`}
        >
          {cargando ? <Loader2 className="h-4 w-4 animate-spin" /> : resultado ? <RotateCcw className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />}
          {cargando ? 'Ordenando…' : resultado ? 'Ordenar de nuevo' : 'Ordenar con IA'}
        </button>
      </div>

      {resultado && (
        <div ref={resultadoRef} className="animate-scale-in space-y-3.5 border-t border-slate-200 pt-4 dark:border-slate-700">
          <p className="text-xs font-bold uppercase tracking-wide text-brand-700 dark:text-brand-300">
            Pedido ordenado · {resultado.tipoNombre}
          </p>

          <label className="block">
            <span className="etiqueta-campo">Título</span>
            <input
              value={resultado.resumen}
              onChange={e => setResultado(r => r && { ...r, resumen: e.target.value })}
              maxLength={200}
              className="campo"
            />
          </label>

          <div className="grid gap-3 sm:grid-cols-2">
            {resultado.campos.map(c => {
              const falta = vacio(c.valor)
              const clases = `campo ${falta ? 'border-amber-400 bg-amber-50/60 dark:border-amber-500/60 dark:bg-amber-500/10' : ''}`
              return (
                <label key={c.clave} className={`block ${LARGOS.has(c.clave) ? 'sm:col-span-2' : ''}`}>
                  <span className="etiqueta-campo">{c.etiqueta}</span>
                  {LARGOS.has(c.clave) ? (
                    <textarea
                      value={c.valor ?? ''}
                      onChange={e => cambiarCampo(c.clave, e.target.value)}
                      rows={3}
                      maxLength={2000}
                      placeholder={c.falta}
                      className={`${clases} h-auto resize-y py-2.5`}
                    />
                  ) : (
                    <input
                      value={c.valor ?? ''}
                      onChange={e => cambiarCampo(c.clave, e.target.value)}
                      maxLength={500}
                      placeholder={c.falta}
                      className={clases}
                    />
                  )}
                </label>
              )
            })}
          </div>

          {falta.length > 0 ? (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-3 dark:border-amber-500/30 dark:bg-amber-500/10" role="status">
              <p className="mb-1.5 flex items-center gap-2 text-sm font-bold text-amber-900 dark:text-amber-200">
                <AlertTriangle className="h-4 w-4" aria-hidden /> Lo que falta
              </p>
              <ul className="flex flex-wrap gap-1.5">
                {falta.map(f => (
                  <li key={f} className="rounded-full bg-white px-2.5 py-1 text-[13px] font-medium text-amber-900 ring-1 ring-amber-200 dark:bg-amber-500/15 dark:text-amber-100 dark:ring-amber-500/30">
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="flex items-center gap-2 rounded-xl bg-emerald-50 px-3.5 py-2.5 text-sm font-semibold text-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-200" role="status">
              <CheckCircle2 className="h-4 w-4" aria-hidden /> Está todo lo que lleva un pedido de {nombreTipo.toLowerCase()}.
            </p>
          )}

          {resultado.dudas.length > 0 && (
            <div className="rounded-xl bg-slate-50 px-3.5 py-3 dark:bg-slate-800/60">
              <p className="mb-1 flex items-center gap-2 text-sm font-bold text-slate-800 dark:text-slate-100">
                <HelpCircle className="h-4 w-4 text-brand-600 dark:text-brand-300" aria-hidden /> Para confirmar
              </p>
              <ul className="list-disc space-y-0.5 pl-6 text-sm text-slate-700 dark:text-slate-300">
                {resultado.dudas.map(d => <li key={d}>{d}</li>)}
              </ul>
            </div>
          )}

          <label className="block">
            <span className="etiqueta-campo">Notas</span>
            <textarea
              value={resultado.notas ?? ''}
              onChange={e => setResultado(r => r && { ...r, notas: e.target.value })}
              rows={2}
              maxLength={1000}
              placeholder="Lo que se dijo y no entra en ningún campo"
              className="campo h-auto resize-y py-2.5"
            />
          </label>

          <div className="flex flex-wrap justify-end gap-2">
            {onCancelar && (
              <button type="button" onClick={onCancelar} className="min-h-[44px] rounded-xl px-4 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800 sm:min-h-[40px]">
                Cancelar
              </button>
            )}
            <button
              type="button"
              onClick={usar}
              className="flex min-h-[44px] items-center gap-2 rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.98] sm:min-h-[40px]"
            >
              <CheckCircle2 className="h-4 w-4" /> {etiquetaUsar}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

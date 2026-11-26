'use client'

import { useState } from 'react'
import { Check, Mic, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { DictarBrief, type BriefListo } from '@/components/ia/DictarBrief'
import { esFechaGuardable } from './CampoFecha'
import { ModalDeOpciones } from './OpcionesDelTipo'
import { ElegirAdjuntos } from './Adjuntos'
import { delEquipo, type Persona } from '@/lib/calendario/tipos'
import { useCatalogoDeTipos, useTableros } from '@/store/tiposDeTarea'
import { camposVisibles, linkValido, nombreDeTarjeta, tiposDelMundo, valorParaLeer, type TipoDeTarea } from '@/lib/calendario/tipos-de-tarea'

/**
 * El formulario de una tarea nueva: un pedido (Ivan, 24/11/2026: "sería
 * simplemente tarea nueva pum poner los banners y descripción o lo que sea
 * que estemos pidiendo"):
 *
 *   ¿Qué se pide?  Banners, Mailing, Redes… (con sus opciones) u Otra cosa
 *   ¿Quién la hace? Cualquier agencia (GET /calendario/tableros) o alguien de Tienda
 *   Detalle · Archivos · Responsable de Tienda (si la hace una agencia) · Vence
 *
 * Es el mismo en una acción del calendario (NuevaTarea, en BloqueTareas) y en
 * Tableros, para una tarjeta sin acción (NuevaTarjeta, 24/11/2026: "quizás
 * mismo en los tableros podríamos tener la opción de crear una tarjeta"). Acá
 * se llena; qué se hace con lo llenado (el store del calendario, o la API
 * directo) lo decide quien lo usa, con `onEnviar`.
 *
 * - En una acción, con un tipo el nombre se arma solo ("<Acción> - <Tipo>") y
 *   se puede cambiar; sin acción, el nombre propuesto es el del tipo.
 * - Con dos tipos a la vez son dos tareas, con el mismo detalle y archivos.
 * - Sin acción, siempre hay que elegir quién la hace: es una tarjeta, y tiene
 *   que caer en el tablero de alguien.
 */

/** Lo más largo que guarda el servidor en el detalle de una tarea (TareaNueva.descripcion). */
const MAX_DETALLE = 5000

/** El botón chico que abre el dictado, al lado del título "Detalle". */
const BOTON_DICTAR = 'flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-sm font-semibold text-brand-700 transition hover:bg-brand-50 active:scale-95 dark:text-brand-200 dark:hover:bg-brand-500/10 sm:h-8'

/**
 * El detalle de una tarea, escrito o dictado. "Dictar el pedido" abre el
 * dictado (components/ia/DictarBrief): lo ordenado por la IA cae en el texto,
 * que todavía se puede corregir antes de guardar.
 */
export function CampoDetalle({ valor, onCambiar, onDictado, id }: {
  valor: string
  onCambiar: (v: string) => void
  /** Además del texto, el pedido ordenado entero (para sacarle el título, por ejemplo). */
  onDictado?: (brief: BriefListo) => void
  id: string
}) {
  const [dictando, setDictando] = useState(false)

  function usar(brief: BriefListo) {
    onCambiar(brief.comoTexto.slice(0, MAX_DETALLE))
    onDictado?.(brief)
    setDictando(false)
  }

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <label htmlFor={id} className="etiqueta-campo mb-0">Detalle (opcional)</label>
        {!dictando && (
          <button type="button" onClick={() => setDictando(true)} className={BOTON_DICTAR}>
            <Mic className="h-4 w-4" /> Dictar el pedido
          </button>
        )}
      </div>
      {dictando ? (
        <DictarBrief etiquetaUsar="Usar en la tarea" onListo={usar} onCancelar={() => setDictando(false)} />
      ) : (
        <textarea
          id={id}
          value={valor}
          onChange={e => onCambiar(e.target.value)}
          rows={valor ? 6 : 2}
          maxLength={MAX_DETALLE}
          placeholder="Qué hay que hacer, con los datos para la agencia o el equipo"
          className="campo h-auto resize-y py-2.5 leading-relaxed"
        />
      )}
    </div>
  )
}

/** Una tarea a crear, ya con todo lo elegido. Lo mismo que lleva el alta en el
 *  servidor (TareaNueva), sin el id. */
export type PedidoDeTarea = {
  titulo: string
  /** Con un tipo: el nombre se escribió a mano (no es el que se arma solo). */
  nombrePropio: boolean
  descripcion: string | null
  asignadoA: number | null
  vence: string | null
  para: 'agencia' | 'tienda'
  agencia: string | null
  responsable: number | null
  tipo: string | null
  opciones: string[]
  detalles?: Record<string, string>
}

export function FormularioDeTarea({
  mundo, accion, personas, personasEstado, usuarioId, encabezado, idDetalle, quienInicial = '', enviando = false,
  enMarco = true, onEnviar, onCancelar,
}: {
  mundo: string | undefined
  /** El nombre de la acción. null: una tarjeta sin acción (desde Tableros). */
  accion: string | null
  personas: Persona[]
  personasEstado?: string
  usuarioId: number | null
  /** "Nueva tarea", "Nueva tarjeta". */
  encabezado: string
  idDetalle: string
  /** Quién la hace, ya elegido al abrir ("agencia:Publicis"). */
  quienInicial?: string
  enviando?: boolean
  /** Con el recuadro de color (adentro de una ficha); sin él, en una ventana. */
  enMarco?: boolean
  onEnviar: (pedidos: PedidoDeTarea[], archivos: File[]) => void
  onCancelar: () => void
}) {
  const sinAccion = accion === null
  const nombreDeLaAccion = accion ?? ''
  const catalogo = useCatalogoDeTipos()
  const tipos = tiposDelMundo(catalogo.tipos, mundo)
  const { t } = useTranslation()
  const { tableros, error: sinListaDeAgencias } = useTableros(mundo)

  const [elegidas, setElegidas] = useState<PiezaElegida[]>([])
  const [titulo, setTitulo] = useState('')
  // "agencia:Publicis", "persona:12" o "" (nadie todavía).
  const [quien, setQuien] = useState(quienInicial)
  const [responsable, setResponsable] = useState('')
  const [vence, setVence] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [archivos, setArchivos] = useState<File[]>([])

  const deAgencia = quien.startsWith('agencia:')
  const nombreAuto = elegidas.length === 1
    ? nombreDeTarjeta(nombreDeLaAccion, tipos?.find(t => t.clave === elegidas[0].clave))
    : ''
  const linkMalo = elegidas.map(p => linkMaloEn(p, tipos)).find(Boolean) ?? null
  const falta = elegidas.length === 0 && !titulo.trim() ? (sinAccion ? 'Escribí el nombre, o elegí qué se pide.' : 'Escribí qué hay que hacer, o elegí qué se pide.')
    : (elegidas.length > 0 || sinAccion) && !quien ? 'Elegí quién la hace.'
      : linkMalo
  const cuantas = Math.max(1, elegidas.length)
  const cosa = sinAccion ? ['tarjeta', 'tarjetas'] : ['tarea', 'tareas']

  function enviar(e: React.FormEvent) {
    e.preventDefault()
    if (falta || enviando) return
    const venceGuardable = esFechaGuardable(vence) ? vence : null
    const para = deAgencia ? 'agencia' as const : 'tienda' as const
    const agencia = deAgencia ? quien.slice('agencia:'.length) : null
    const asignadoA = quien.startsWith('persona:') ? Number(quien.slice('persona:'.length)) : null
    const varias = elegidas.length > 1
    const detalle = descripcion.trim() || null
    const pedidos = (elegidas.length > 0 ? elegidas : [null]).map((p): PedidoDeTarea => {
      const tipo = p ? tipos?.find(t => t.clave === p.clave) : undefined
      // Con un tipo, el nombre escrito manda; si no se escribió, el de siempre.
      const propio = !varias && titulo.trim() !== ''
      return {
        titulo: p ? (propio ? titulo.trim() : nombreDeTarjeta(nombreDeLaAccion, tipo)) : titulo.trim(),
        nombrePropio: !!p && propio,
        descripcion: detalle, asignadoA, vence: venceGuardable,
        para, agencia, responsable: deAgencia && responsable ? Number(responsable) : null,
        tipo: p?.clave ?? null, opciones: p?.opciones ?? [],
        detalles: p ? Object.fromEntries(Object.entries(p.detalles).filter(([, v]) => v.trim() !== '')) : undefined,
      }
    })
    onEnviar(pedidos, archivos)
  }

  /** Lo dictado trae un título: si todavía no hay uno ni se eligió qué se
   *  pide, se usa ese. */
  function alDictar(brief: BriefListo) {
    if (!titulo.trim() && elegidas.length === 0) setTitulo(brief.resumen.slice(0, 500))
  }

  return (
    <form
      onSubmit={enviar}
      onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); onCancelar() } }}
      className={enMarco
        ? 'mt-3 animate-scale-in space-y-3 rounded-2xl border border-brand-200 bg-brand-50/50 p-3.5 dark:border-brand-500/30 dark:bg-brand-500/[.06]'
        : 'space-y-3'}
    >
      {enMarco && <p className="text-sm font-semibold text-brand-800 dark:text-brand-200">{encabezado}</p>}

      <QueSePide
        valor={elegidas}
        onCambiar={setElegidas}
        tipos={tipos}
        error={catalogo.error}
        reintentar={catalogo.reintentar}
        otraCosa={elegidas.length === 0}
        onOtraCosa={() => setElegidas([])}
      />

      {/* El nombre: con un tipo se arma solo y se puede cambiar; con varios,
          cada una lleva el suyo; sin tipo (Otra cosa), se escribe. */}
      {elegidas.length <= 1 ? (
        <label className="block">
          <span className="etiqueta-campo">
            {elegidas.length === 1
              ? <>Nombre <span className="font-normal text-slate-500 dark:text-slate-400">(se puede cambiar)</span></>
              : sinAccion ? 'Nombre' : 'Qué hay que hacer'}
          </span>
          <input
            autoFocus
            value={titulo}
            onChange={e => setTitulo(e.target.value)}
            placeholder={nombreAuto || (sinAccion ? 'Ej: Video institucional de fin de año' : 'Ej: Arte del header desktop')}
            aria-label={elegidas.length === 1 || sinAccion ? `Nombre de la ${cosa[0]}` : 'Qué hay que hacer'}
            maxLength={500}
            className="campo"
          />
        </label>
      ) : (
        <p className="rounded-xl border border-brand-200 bg-white px-3 py-2 text-sm text-slate-700 dark:border-brand-500/30 dark:bg-slate-900 dark:text-slate-200">
          Se van a crear {elegidas.length} {cosa[1]}:{' '}
          <strong className="font-semibold text-slate-900 dark:text-slate-50">
            {elegidas.map(p => nombreDeTarjeta(nombreDeLaAccion, tipos?.find(t => t.clave === p.clave))).join(' · ')}
          </strong>
        </p>
      )}

      <label className="block">
        <span className="etiqueta-campo">¿Quién la hace?</span>
        <select value={quien} onChange={e => setQuien(e.target.value)} className="campo" aria-label="Quién la hace">
          <option value="">{elegidas.length > 0 || sinAccion ? 'Elegí quién la hace' : 'Sin asignar por ahora'}</option>
          {tableros && tableros.length > 0 && (
            <optgroup label="Agencias">
              {tableros.map(t => (
                <option key={t.nombre} value={`agencia:${t.nombre}`}>
                  {t.nombre}{t.cuentas === 0 ? ' (todavía sin usuarios)' : ''}
                </option>
              ))}
            </optgroup>
          )}
          <optgroup label="Tienda Inglesa">
            {delEquipo(personas).map(p => (
              <option key={p.id} value={`persona:${p.id}`}>{p.nombre}{p.id === usuarioId ? ' (vos)' : ''}</option>
            ))}
          </optgroup>
        </select>
        {personasEstado === 'error' && (
          <span className="mt-1 block text-xs text-amber-700 dark:text-amber-300">
            No se pudo traer la lista de personas. Se vuelve a intentar sola en unos segundos.
          </span>
        )}
        {/* Sin la lista, «¿Quién la hace?» no tiene agencias: se dice, en vez de
            parecer que la agencia no existe (H-018). */}
        {sinListaDeAgencias && (
          <span role="alert" className="mt-1 block text-xs text-amber-700 dark:text-amber-300">
            {t('calendario.quienLaHace.sinLista')}
          </span>
        )}
        {deAgencia && (
          <span className="mt-1 block text-xs text-slate-600 dark:text-slate-400">
            Le nace su tarjeta en el tablero de {quien.slice('agencia:'.length)} y le avisamos.
          </span>
        )}
      </label>

      <CampoDetalle
        id={idDetalle}
        valor={descripcion}
        onCambiar={setDescripcion}
        onDictado={alDictar}
      />
      <ElegirAdjuntos
        valor={archivos}
        onCambiar={setArchivos}
        ayuda={deAgencia ? 'Los baja también la agencia, desde su tarjeta' : undefined}
      />
      <div className="grid gap-3 sm:grid-cols-2">
        {deAgencia && (
          <label className="block">
            <span className="etiqueta-campo">Responsable de Tienda</span>
            <select value={responsable} onChange={e => setResponsable(e.target.value)} className="campo">
              <option value="">Sin asignar por ahora</option>
              {delEquipo(personas).map(p => <option key={p.id} value={p.id}>{p.nombre}{p.id === usuarioId ? ' (vos)' : ''}</option>)}
            </select>
          </label>
        )}
        <label className="block">
          <span className="etiqueta-campo">Vence el (opcional)</span>
          <input type="date" min="2000-01-01" max="2100-12-31" value={vence} onChange={e => setVence(e.target.value)} className="campo" />
        </label>
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2">
        {falta && <p className="mr-auto text-xs text-slate-600 dark:text-slate-400">{falta}</p>}
        <button type="button" onClick={onCancelar} className="min-h-[44px] rounded-xl px-4 text-sm font-semibold text-slate-600 transition hover:bg-slate-200/70 dark:text-slate-300 dark:hover:bg-slate-800 sm:min-h-[40px]">
          Cancelar
        </button>
        <button
          type="submit"
          disabled={!!falta || enviando}
          className="min-h-[44px] rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.98] disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:shadow-none dark:disabled:bg-slate-700 dark:disabled:text-slate-400 sm:min-h-[40px]"
        >
          {enviando ? 'Creando…' : cuantas > 1 ? `Crear ${cuantas} ${cosa[1]}` : `Crear ${cosa[0]}`}
        </button>
      </div>
    </form>
  )
}

/** Un tipo elegido al crear la tarea: lo tildado y los datos de más. */
type PiezaElegida = { clave: string; opciones: string[]; detalles: Record<string, string> }

/** Un link mal escrito en lo que se pide: frena crear la tarea. */
function linkMaloEn(p: PiezaElegida, tipos: TipoDeTarea[] | null): string | null {
  const tipo = tipos?.find(t => t.clave === p.clave)
  if (!tipo) return null
  const malo = camposVisibles(tipo, p.opciones).find(c => c.tipo === 'link' && p.detalles[c.clave]?.trim() && !linkValido(p.detalles[c.clave]))
  return malo ? `${tipo.nombre} · ${malo.nombre}: tiene que empezar con https://` : null
}

/**
 * ¿Qué se pide? Banners, Mailing, Redes… u Otra cosa. Tocar un tipo lo suma y
 * abre su modal con todas las opciones (Header, Slider, el CTA…); tocarlo de
 * nuevo lo vuelve a abrir. "Otra cosa" es una tarea sin tipo: se escribe qué
 * hay que hacer.
 */
function QueSePide({ valor, onCambiar, tipos, error, reintentar, otraCosa, onOtraCosa }: {
  valor: PiezaElegida[]
  onCambiar: (v: PiezaElegida[]) => void
  tipos: TipoDeTarea[] | null
  error: boolean
  reintentar: () => void
  otraCosa: boolean
  onOtraCosa: () => void
}) {
  const [editando, setEditando] = useState<string | null>(null)
  const actual = valor.find(p => p.clave === editando) ?? null
  const tipoActual = tipos?.find(t => t.clave === editando) ?? null

  function tocar(t: TipoDeTarea) {
    if (!valor.some(p => p.clave === t.clave)) onCambiar([...valor, { clave: t.clave, opciones: [], detalles: {} }])
    setEditando(t.clave)
  }
  function cambiar(clave: string, cambio: Partial<PiezaElegida>) {
    onCambiar(valor.map(p => (p.clave === clave ? { ...p, ...cambio } : p)))
  }
  const CHIP = 'flex min-h-[40px] items-center gap-1 rounded-xl border px-3 text-sm font-semibold transition active:scale-95'
  const SI = 'border-brand-600 bg-brand-600 text-white shadow-sm'
  const NO = 'border-slate-300 bg-white text-slate-700 hover:border-brand-400 hover:text-brand-700 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-brand-500/60'

  return (
    // min-w-0: un <fieldset> no se achica por debajo de su contenido, y los
    // tipos (y el resumen de cada uno) se salían por el costado de la ficha.
    <fieldset className="min-w-0">
      <legend className="etiqueta-campo">¿Qué se pide?</legend>
      {!tipos ? (
        error ? (
          <button type="button" onClick={reintentar} className="text-sm font-semibold text-brand-700 underline dark:text-brand-200">
            No se pudieron traer los tipos. Probar de nuevo
          </button>
        ) : <div className="skeleton h-10 rounded-xl" />
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {tipos.map(t => {
            const elegida = valor.some(p => p.clave === t.clave)
            return (
              <button key={t.clave} type="button" aria-pressed={elegida} onClick={() => tocar(t)} className={`${CHIP} ${elegida ? SI : NO}`}>
                {elegida && <Check className="h-3.5 w-3.5" strokeWidth={3} aria-hidden />} {t.nombre}
              </button>
            )
          })}
          <button type="button" aria-pressed={otraCosa} onClick={onOtraCosa} className={`${CHIP} ${otraCosa ? 'border-brand-600 bg-brand-50 text-brand-800 ring-2 ring-brand-500/30 dark:border-brand-400 dark:bg-brand-500/20 dark:text-brand-100' : NO}`}>
            {otraCosa && <Check className="h-3.5 w-3.5" strokeWidth={3} aria-hidden />} Otra cosa
          </button>
        </div>
      )}

      {valor.length > 0 && tipos && (
        <ul className="mt-2 space-y-1.5" aria-label="Lo que se pide">
          {valor.map(p => {
            const t = tipos.find(x => x.clave === p.clave)
            if (!t) return null
            const datos = camposVisibles(t, p.opciones).filter(c => p.detalles[c.clave]?.trim())
              .map(c => `${c.nombre}: ${valorParaLeer(c, p.detalles[c.clave])}`)
            const resumen = [...p.opciones, ...datos].join(' · ')
            return (
              <li key={p.clave} className="flex items-center gap-2 rounded-xl border border-brand-200 bg-white px-3 py-2 dark:border-brand-500/30 dark:bg-slate-900">
                <span className="min-w-0 flex-1 text-sm">
                  <span className="font-semibold text-slate-900 dark:text-slate-100">{t.nombre}</span>
                  <span className="block truncate text-xs text-slate-600 dark:text-slate-400">
                    {resumen || (t.opciones.length > 0 ? 'Todavía no elegiste nada' : 'Sin datos de más')}
                  </span>
                </span>
                <button type="button" onClick={() => setEditando(p.clave)} className="min-h-[36px] rounded-lg px-2 text-xs font-semibold text-brand-700 hover:bg-brand-50 dark:text-brand-200 dark:hover:bg-brand-500/10">
                  Cambiar
                </button>
                <button type="button" onClick={() => onCambiar(valor.filter(x => x.clave !== p.clave))} aria-label={`Sacar ${t.nombre}`}
                  className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800">
                  <X className="h-4 w-4" />
                </button>
              </li>
            )
          })}
        </ul>
      )}

      {actual && tipoActual && (
        <ModalDeOpciones
          tipo={tipoActual}
          opciones={actual.opciones}
          detalles={actual.detalles}
          onAlternar={o => cambiar(actual.clave, {
            opciones: actual.opciones.includes(o) ? actual.opciones.filter(x => x !== o) : [...actual.opciones, o],
          })}
          onAgregarOtra={texto => {
            const o = texto.trim()
            if (o && !actual.opciones.some(x => x.toLocaleLowerCase('es') === o.toLocaleLowerCase('es'))) {
              cambiar(actual.clave, { opciones: [...actual.opciones, o] })
            }
          }}
          onDetalle={(k, v) => cambiar(actual.clave, { detalles: { ...actual.detalles, [k]: v } })}
          onCerrar={() => setEditando(null)}
        />
      )}
    </fieldset>
  )
}

'use client'

import { createContext, useContext, useId, useRef, useState, type ReactNode } from 'react'
import {
  CalendarClock, Check, ChevronDown, FileText, GripVertical, LayoutTemplate, Link2, ListChecks, Mic, MoreHorizontal, Paperclip, Pencil, Plus, ShieldCheck, Sparkles, Trash2, UserRound, X,
} from 'lucide-react'
import { correrUnLugar, moverEntreHermanas } from '@/lib/calendario/orden'
import { toast } from 'sonner'
import { fechaCorta, hoyIso } from '@/lib/calendario/fechas'
import { CampoFecha, esFechaGuardable } from './CampoFecha'
import { DictarBrief, type BriefListo } from '@/components/ia/DictarBrief'
import { useCalendario } from '@/lib/calendario/store'
import { plantillasSugeridas, textoDeAncla } from '@/lib/calendario/plantillas'
import {
  ETIQUETA_ESTADO_TAREA, asignablesPara, delEquipo, mismaEmpresa,
  type BarraGuardada, type EstadoTarea, type Persona, type Tarea, nombreConEmpresa,
} from '@/lib/calendario/tipos'
import { estadoDeFase, proximoPaso } from '@/lib/calendario/entregas'
import { useVistaEntregas } from '@/store/entregas'
import { FasesCompactas } from './entregas/LineaDeFases'
import { ModalDeOpciones } from './OpcionesDelTipo'
import { AdjuntosDeLaTarea, ElegirAdjuntos } from './Adjuntos'
import { useCatalogoDeTipos, useTableros } from '@/store/tiposDeTarea'
import { camposVisibles, linkValido, nombreDeTarjeta, tiposDelMundo, valorParaLeer, type TipoDeTarea } from '@/lib/calendario/tipos-de-tarea'
import { usePermisosCalendario } from '@/lib/calendario/permisos'

/**
 * Las tareas de una acción.
 *
 * Pedido de Ivan (12/11/2026): quien lidera abre una acción, le crea tareas y
 * se las asigna a cada persona, que se entera por la campanita. Desde el
 * 24/11/2026 cada tarea es un pedido, todas en un solo nivel: "las tareas y
 * el pedido de piezas deberían ser uno... tener así dividido en tarea, pedido
 * de piezas y luego subtareas me parece al pedo y confuso" (ver NuevaTarea).
 *
 * - `gestiona` (permiso `calendario.tareas`): crea, asigna, pone fecha y borra,
 *   y usa las plantillas del mundo (ver DialogoPlantillas).
 * - Quien tiene `calendario.pedidos` crea tareas (16/11/2026: "todo el
 *   equipo tiene que poder crear tareas para agencia"): Banners, Mailing,
 *   Cenefas… con quién la hace y para cuándo. Si la hace una agencia, le
 *   nace su tarjeta en el tablero.
 * - Los demás ven todo y pueden mover el estado de las tareas que tienen
 *   asignadas, y de ninguna otra. Es lo mismo que exige el servidor.
 */

/** Las acciones donde alguien dijo "ahora no" a la plantilla sugerida. Solo
 *  en este navegador: es una comodidad, no un dato del calendario. */
const CLAVE_DESCARTADAS = 'calendario-plantillas-descartadas'

function leerDescartadas(): string[] {
  try {
    const v: unknown = JSON.parse(localStorage.getItem(CLAVE_DESCARTADAS) ?? '[]')
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
  } catch {
    return []
  }
}

function guardarDescartada(accionId: string): string[] {
  const lista = [...leerDescartadas().filter(x => x !== accionId), accionId].slice(-300)
  try { localStorage.setItem(CLAVE_DESCARTADAS, JSON.stringify(lista)) } catch { /* sin lugar: se olvida al recargar */ }
  return lista
}

const ESTADOS: EstadoTarea[] = ['pendiente', 'en-proceso', 'hecha']

/** Lo más largo que guarda el servidor en el detalle de una tarea (TareaNueva.descripcion). */
const MAX_DETALLE = 5000

/** El botón chico que abre el dictado, al lado del título "Detalle". */
const BOTON_DICTAR = 'flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-sm font-semibold text-brand-700 transition hover:bg-brand-50 active:scale-95 dark:text-brand-200 dark:hover:bg-brand-500/10 sm:h-8'

/**
 * El detalle de una tarea, escrito o dictado. "Dictar el pedido" abre el
 * dictado (components/ia/DictarBrief): lo ordenado por la IA cae en el texto,
 * que todavía se puede corregir antes de guardar.
 */
function CampoDetalle({ valor, onCambiar, onDictado, id }: {
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

/** Editar el detalle de una tarea que ya existe (quien gestiona tareas). */
function EditorDeDetalle({ tarea, onCerrar }: { tarea: Tarea; onCerrar: () => void }) {
  const cambiar = useCalendario(s => s.cambiarTarea)
  const [texto, setTexto] = useState(tarea.descripcion ?? '')

  function guardar() {
    const nuevo = texto.trim()
    if (nuevo !== (tarea.descripcion ?? '').trim()) cambiar(tarea.id, { descripcion: nuevo || null })
    onCerrar()
  }

  return (
    <div className="mt-2.5 animate-scale-in space-y-2.5" onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); onCerrar() } }}>
      <CampoDetalle id={`detalle-${tarea.id}`} valor={texto} onCambiar={setTexto} />
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCerrar} className="min-h-[44px] rounded-xl px-4 text-sm font-semibold text-slate-600 transition hover:bg-slate-200/70 dark:text-slate-300 dark:hover:bg-slate-800 sm:min-h-[40px]">
          Cancelar
        </button>
        <button type="button" onClick={guardar} className="min-h-[44px] rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.98] sm:min-h-[40px]">
          Guardar detalle
        </button>
      </div>
    </div>
  )
}

export function BloqueTareas({ accion, personas, usuarioId, gestiona, titulo = 'Tareas', herramientas, debajoDelTitulo }: {
  accion: BarraGuardada
  personas: Persona[]
  usuarioId: number | null
  gestiona: boolean
  /** "Tareas", o "Mis tareas" para la agencia. */
  titulo?: string
  /** Botones chicos a la derecha del título (en la ficha: Avisos y Fotos). */
  herramientas?: ReactNode
  /** Lo que esos botones abren, entre el título y las tareas. */
  debajoDelTitulo?: ReactNode
}) {
  const tareas = accion.tareas ?? []
  const hechas = tareas.filter(t => t.estado === 'hecha').length
  const todas = tareas.length > 0 && hechas === tareas.length
  const abrirPlantillas = useCalendario(s => s.abrirPlantillas)
  const plantillas = useCalendario(s => s.plantillas)
  const [descartadas, setDescartadas] = useState<string[]>(() => (typeof window === 'undefined' ? [] : leerDescartadas()))
  const sugeridas = gestiona && !descartadas.includes(accion.id) ? plantillasSugeridas(plantillas, accion) : []
  // Crear tareas: quien gestiona tareas y quien tiene el permiso de pedir
  // piezas (calendario.pedidos, aparte de editar desde el 17/11/2026). Una
  // cuenta externa nunca lo tiene. Es lo mismo que exige el servidor.
  const { pidePiezas: puedePedir } = usePermisosCalendario()
  const pidePiezas = gestiona || puedePedir
  // Un solo formulario abierto a la vez en todo el bloque (ver FormularioAbierto).
  const [abierto, abrir] = useState<Abierto>(null)

  return (
    <FormularioAbierto.Provider value={{ accion, pidePiezas, abierto, abrir }}>
    <section>
      {/* Una sola línea arriba (24/11/2026, "las pastillas de arriba son al
          pedo"): el título, cuántas van y, a la derecha, lo demás de la
          acción en botones chicos. Sin barra de progreso: lo dice el número. */}
      <div className="mb-3 flex flex-wrap items-center gap-x-2 gap-y-2">
        <ListChecks className="h-5 w-5 text-brand-600 dark:text-brand-300" aria-hidden />
        <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">{titulo}</h3>
        {tareas.length > 0 && (
          <span className={`text-sm tabular-nums ${todas ? 'font-semibold text-emerald-700 dark:text-emerald-300' : 'text-slate-600 dark:text-slate-400'}`}>
            {todas ? '¡Todas hechas!' : `${hechas} de ${tareas.length} hechas`}
          </span>
        )}
        {herramientas && <div className="ml-auto flex flex-wrap items-center gap-1.5">{herramientas}</div>}
      </div>
      {debajoDelTitulo}

      {sugeridas.length > 0 && (
        <SugerenciaDePlantilla
          accion={accion}
          sugeridas={sugeridas.map(p => ({ id: p.id, nombre: p.nombre, tareas: p.tareas.length }))}
          onVer={() => abrirPlantillas(accion.id)}
          onAhoraNo={() => setDescartadas(guardarDescartada(accion.id))}
        />
      )}

      {tareas.length === 0 && (
        <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-slate-300 px-5 py-8 text-center dark:border-slate-700">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-brand-50 text-brand-600 dark:bg-brand-500/15 dark:text-brand-300">
            <ListChecks className="h-5 w-5" />
          </span>
          <p className="max-w-xs text-sm text-slate-600 dark:text-slate-400">
            {gestiona
              ? 'Esta acción todavía no tiene tareas. Creá la primera (o arrancá con una plantilla): qué se pide (Banners, Redes, Mailing…), quién la hace y para cuándo.'
              : pidePiezas
                ? 'Esta acción todavía no tiene tareas. Creá la primera: qué se pide (Banners, Redes, Mailing, EMM…), quién la hace y para cuándo.'
                : 'Esta acción todavía no tiene tareas. Las crea el equipo.'}
          </p>
        </div>
      )}

      <ListaOrdenable barraId={accion.id} tareas={tareas} puede={gestiona}>
        {tareas.map(t => (
          <ItemTarea key={t.id} tarea={t} personas={personas} usuarioId={usuarioId} gestiona={gestiona} />
        ))}
      </ListaOrdenable>

      {/* El inicio es uno solo: Crear tarea, que es el pedido entero (24/11/2026).
          La plantilla sigue para quien lidera. */}
      {pidePiezas && (
        <NuevaTarea
          accionId={accion.id} personas={personas} usuarioId={usuarioId}
          alLado={gestiona ? (
            <button
              type="button"
              onClick={() => { abrir(null); abrirPlantillas(accion.id) }}
              className="flex min-h-[48px] items-center justify-center gap-2 rounded-2xl border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-brand-400 hover:text-brand-700 active:scale-[.99] dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-brand-500/60 dark:hover:text-brand-200"
            >
              <LayoutTemplate className="h-4 w-4" /> Usar plantilla
            </button>
          ) : undefined}
        />
      )}
    </section>
    </FormularioAbierto.Provider>
  )
}

/**
 * "¿Usar la plantilla Mega evento?": arriba de las tareas de una acción cuya
 * categoría tiene plantilla, para quien gestiona tareas. Se va sola cuando se
 * usa una, y con "Ahora no" no vuelve a aparecer en esa acción.
 */
function SugerenciaDePlantilla({ accion, sugeridas, onVer, onAhoraNo }: {
  accion: BarraGuardada
  sugeridas: { id: string; nombre: string; tareas: number }[]
  onVer: () => void
  onAhoraNo: () => void
}) {
  const aplicar = useCalendario(s => s.aplicarPlantilla)
  const una = sugeridas.length === 1 ? sugeridas[0] : null
  return (
    <div className="mb-4 flex animate-fade-in items-start gap-3 rounded-2xl border border-brand-200 bg-brand-50/60 p-3.5 dark:border-brand-500/30 dark:bg-brand-500/[.07]">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white text-brand-600 shadow-sm dark:bg-slate-900 dark:text-brand-300">
        <LayoutTemplate className="h-[18px] w-[18px]" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          {una ? `¿Usar la plantilla «${una.nombre}»?` : `Hay ${sugeridas.length} plantillas de ${accion.banda}`}
        </p>
        <p className="mt-0.5 text-[13px] leading-snug text-slate-600 dark:text-slate-400">
          {una
            ? `Crea sus ${una.tareas === 1 ? 'tarea' : `${una.tareas} tareas`} con la fecha ya calculada para esta acción.`
            : 'Elegí una y se crean sus tareas con la fecha ya calculada para esta acción.'}
        </p>
        <div className="mt-2.5 flex flex-wrap gap-2">
          {una && (
            <button
              type="button"
              onClick={() => aplicar(accion.id, una.id)}
              className="flex min-h-[40px] items-center gap-1.5 rounded-xl bg-brand-600 px-3.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.98] sm:min-h-[36px]"
            >
              <Sparkles className="h-4 w-4" /> Usar plantilla
            </button>
          )}
          <button
            type="button"
            onClick={onVer}
            className="flex min-h-[40px] items-center rounded-xl px-3 text-sm font-semibold text-brand-700 transition hover:bg-brand-100/70 dark:text-brand-200 dark:hover:bg-brand-500/15 sm:min-h-[36px]"
          >
            {una ? 'Ver las tareas' : 'Elegir plantilla'}
          </button>
        </div>
      </div>
      <button
        type="button"
        onClick={onAhoraNo}
        aria-label="Ahora no: no sugerir plantillas en esta acción"
        title="Ahora no"
        className="-mr-1.5 -mt-1.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-slate-500 transition hover:bg-white/70 hover:text-slate-700 active:scale-95 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}

/**
 * Qué formulario está abierto en el bloque de tareas: 'nueva' = Crear tarea
 * (desde el 24/11/2026 es el único: ya no hay subtareas ni "pedir material").
 */
type Abierto = string | null
const FormularioAbierto = createContext<{
  accion: BarraGuardada | null
  /** Crea tareas (calendario.pedidos, o quien lidera). */
  pidePiezas: boolean
  abierto: Abierto
  abrir: (a: Abierto) => void
}>({ accion: null, pidePiezas: false, abierto: null, abrir: () => {} })

/**
 * Ordenar las tareas arrastrándolas (Ivan, 20/11/2026). Se agarra la manija
 * (⋮⋮) y se suelta arriba o abajo de otra; con el teclado, la
 * manija y las flechas ↑ ↓. Va con eventos de puntero y no con el "arrastrar"
 * del navegador: así anda igual con el mouse que con el dedo. Lo puede hacer
 * quien gestiona las tareas (lo mismo exige el servidor).
 */
type Orden = {
  lista: string
  puede: boolean
  arrastrando: string | null
  sobre: { id: string; antes: boolean } | null
  empezar: (id: string) => void
  moverA: (x: number, y: number) => void
  soltar: () => void
  cancelar: () => void
  correr: (id: string, paso: -1 | 1) => void
}
const OrdenDeLaLista = createContext<Orden | null>(null)

function ListaOrdenable({ barraId, tareas, puede, children }: {
  barraId: string
  tareas: Tarea[]
  puede: boolean
  children: ReactNode
}) {
  const ordenar = useCalendario(s => s.ordenarTareas)
  const lista = useId()
  const [arrastrando, setArrastrando] = useState<string | null>(null)
  const [sobre, setSobre] = useState<Orden['sobre']>(null)
  const ids = tareas.map(t => t.id)
  const guardar = (nuevo: string[]) => {
    if (nuevo.join('|') !== ids.join('|')) ordenar(barraId, nuevo)
  }
  const terminar = () => { setArrastrando(null); setSobre(null) }
  const valor: Orden = {
    lista, puede: puede && ids.length > 1, arrastrando, sobre,
    empezar: id => { setArrastrando(id); setSobre(null) },
    moverA: (x, y) => {
      if (!arrastrando) return
      // La hermana que está debajo del dedo (o del mouse), de ESTA lista.
      const item = document.elementFromPoint(x, y)?.closest<HTMLElement>(`[data-orden-lista="${lista}"]`)
      const fila = item?.querySelector<HTMLElement>(':scope > [data-orden-fila]')
      const id = item?.dataset.ordenId
      if (!item || !fila || !id || id === arrastrando) { setSobre(null); return }
      const r = fila.getBoundingClientRect()
      setSobre({ id, antes: y < r.top + r.height / 2 })
    },
    soltar: () => {
      if (arrastrando && sobre) guardar(moverEntreHermanas(ids, arrastrando, sobre.id, sobre.antes))
      terminar()
    },
    cancelar: terminar,
    correr: (id, paso) => guardar(correrUnLugar(ids, id, paso)),
  }
  return (
    <OrdenDeLaLista.Provider value={valor}>
      <ul className="space-y-2">{children}</ul>
    </OrdenDeLaLista.Provider>
  )
}

function Manija({ tarea }: { tarea: Tarea }) {
  const orden = useContext(OrdenDeLaLista)
  if (!orden?.puede) return null
  const mia = orden.arrastrando === tarea.id
  return (
    <button
      type="button"
      data-manija
      onPointerDown={e => {
        if (e.button !== 0) return
        e.preventDefault()
        e.currentTarget.setPointerCapture(e.pointerId)
        orden.empezar(tarea.id)
      }}
      onPointerMove={e => { if (mia) orden.moverA(e.clientX, e.clientY) }}
      onPointerUp={() => { if (mia) orden.soltar() }}
      onPointerCancel={orden.cancelar}
      onKeyDown={e => {
        if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return
        e.preventDefault()
        orden.correr(tarea.id, e.key === 'ArrowUp' ? -1 : 1)
      }}
      aria-label={`Mover ${tarea.titulo}: arrastrala, o usá las flechas arriba y abajo`}
      title="Arrastrá para ordenar"
      className={`-my-1 -ml-2 -mr-1 flex h-9 w-6 shrink-0 touch-none items-center justify-center rounded-md text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-slate-300 ${mia ? 'cursor-grabbing' : 'cursor-grab'}`}
    >
      <GripVertical className="h-4 w-4" />
    </button>
  )
}

/** El nombre de la tarea, editable: Enter guarda, Esc deja como estaba. */
function TituloEditable({ tarea, onListo }: { tarea: Tarea; onListo: () => void }) {
  const cambiar = useCalendario(s => s.cambiarTarea)
  const [valor, setValor] = useState(tarea.titulo)
  // Al cerrar con Enter o Esc el campo desaparece y el navegador puede
  // mandar igual el "salí del campo": que no guarde dos veces ni guarde un Esc.
  const listo = useRef(false)
  const cerrar = (guardar: boolean) => {
    if (listo.current) return
    listo.current = true
    const titulo = valor.trim()
    if (guardar && titulo && titulo !== tarea.titulo) cambiar(tarea.id, { titulo })
    onListo()
  }
  return (
    <input
      autoFocus
      value={valor}
      maxLength={500}
      onChange={e => setValor(e.target.value)}
      onFocus={e => e.currentTarget.select()}
      onBlur={() => cerrar(true)}
      onKeyDown={e => {
        if (e.key === 'Enter') { e.preventDefault(); cerrar(true) }
        if (e.key === 'Escape') { e.preventDefault(); cerrar(false) }
      }}
      aria-label={`Nuevo nombre de ${tarea.titulo}`}
      className="w-full min-w-0 rounded-lg border border-brand-300 bg-white px-2 py-1 text-[15px] font-semibold text-slate-900 outline-none ring-brand-500/30 focus:ring-4 dark:border-brand-500/50 dark:bg-slate-900 dark:text-slate-100"
    />
  )
}

/**
 * Una tarea en la ficha de la acción: dos o tres líneas (Ivan, 24/11/2026:
 * "no está simplificado, no está inteligente ni entendible").
 *
 *   TiendaChecks Emisión - Banners            vence 26/11
 *   Publicis · 2 archivos
 *   ● Le toca a Publicis: entregar        [Abrir la tarjeta]  ⋯
 *
 * - Si la hace una agencia (tiene tarjeta) no lleva casilla ni estado: lo dice
 *   la tarjeta y queda hecha sola cuando se aprueba. El nombre abre la tarjeta,
 *   que es donde se ven el detalle y los archivos ("Lo que se pidió").
 * - Si es de Tienda sin tarjeta: casilla, y "Lucía · Pendiente".
 * - Todo lo demás (detalle, archivos, quién la hace, responsable, vence,
 *   nombre, borrar) está en el "⋯", que lo abre abajo de la fila.
 *
 * Reemplaza a la tarea minimizada/desplegada del 18/11/2026: aquella se
 * minimizaba porque abierta mostraba todo junto; ahora la fila ya es corta y
 * lo largo vive en el "⋯" o en la tarjeta.
 */
function ItemTarea({ tarea, personas, usuarioId, gestiona }: {
  tarea: Tarea
  personas: Persona[]
  usuarioId: number | null
  gestiona: boolean
}) {
  const abrirTarjeta = useVistaEntregas(s => s.abrir)
  const orden = useContext(OrdenDeLaLista)
  const [abierta, setAbierta] = useState(false)
  const [renombrando, setRenombrando] = useState(false)

  const esMia = usuarioId != null && tarea.asignadoA === usuarioId
  // La lleva por Tienda (0090): se resalta como suya, pero no la tilda (la
  // hace la agencia y queda hecha sola cuando se aprueba).
  const laLlevo = usuarioId != null && tarea.responsable === usuarioId
  // Una tarea con entregas queda hecha sola cuando se aprueba la última fase:
  // quien entrega no la tilda (lo mismo exige el servidor). Quien lidera sí,
  // desde el "⋯".
  const conTarjeta = Boolean(tarea.entrega)
  const puedeEstado = gestiona || (esMia && !conTarjeta)
  const hecha = tarea.estado === 'hecha'
  const vencida = !hecha && !!tarea.vence && tarea.vence < hoyIso()
  // Hecha ya no se mueve: no hace falta decirlo.
  const anclada = !hecha && !!tarea.ancla && tarea.anclaDias != null
  const asignado = personas.find(p => p.id === tarea.asignadoA)
  const agencia = tarea.para && tarea.para !== 'tienda' && tarea.agencia ? tarea.agencia : null
  const quien = agencia
    ? `${agencia}${tarea.para === 'fuera' ? ' (de afuera)' : ''}`
    : tarea.asignadoA == null ? 'Sin asignar' : esMia ? 'Vos' : asignado?.nombre ?? 'Otra persona'
  const archivos = tarea.archivos ?? 0

  return (
    <li
      data-orden-lista={orden?.lista} data-orden-id={tarea.id}
      className={`relative transition-opacity ${orden?.arrastrando === tarea.id ? 'opacity-50' : ''}`}
    >
      {/* Dónde cae la que se está arrastrando: una raya arriba o abajo. */}
      {orden?.sobre?.id === tarea.id && (
        <span
          aria-hidden
          className={`pointer-events-none absolute inset-x-1 z-10 h-1 rounded-full bg-brand-500 ${orden.sobre.antes ? '-top-[6px]' : '-bottom-[6px]'}`}
        />
      )}
      <div
        data-orden-fila
        className={`rounded-2xl border px-3.5 py-2.5 transition duration-300 ${
          hecha
            ? 'border-slate-300 bg-slate-50/70 dark:border-slate-700 dark:bg-slate-800/30'
            : esMia || laLlevo
              ? 'border-brand-300 bg-brand-50/60 dark:border-brand-500/40 dark:bg-brand-500/[.07]'
              : vencida
                ? 'border-rose-200 bg-white dark:border-rose-500/30 dark:bg-slate-900'
                : 'border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-900'
        }`}
      >
        <div className="flex items-start gap-3">
          <Manija tarea={tarea} />
          {!conTarjeta && <Casilla tarea={tarea} puede={puedeEstado} hecha={hecha} />}

          <div className="min-w-0 flex-1">
            {/* 1. El nombre y cuándo vence. */}
            <div className="flex items-start gap-2">
              {renombrando ? (
                <TituloEditable tarea={tarea} onListo={() => setRenombrando(false)} />
              ) : (
                <button
                  type="button"
                  onClick={() => (conTarjeta ? abrirTarjeta(tarea.id, 'ver') : setAbierta(v => !v))}
                  aria-expanded={conTarjeta ? undefined : abierta}
                  title={conTarjeta ? 'Abrir la tarjeta' : abierta ? 'Cerrar' : 'Ver el detalle y los archivos'}
                  className={`min-w-0 flex-1 break-words text-left text-[15px] font-semibold leading-snug transition-colors duration-300 hover:text-brand-700 dark:hover:text-brand-200 ${
                    hecha ? 'text-slate-500 line-through decoration-slate-300 dark:text-slate-400 dark:decoration-slate-600' : 'text-slate-900 dark:text-slate-100'
                  }`}
                >
                  {tarea.titulo}
                </button>
              )}
              {tarea.vence && (
                <span
                  className={`flex shrink-0 items-center gap-1 pt-0.5 text-[13px] font-semibold tabular-nums ${
                    vencida ? 'text-rose-700 dark:text-rose-300' : 'text-slate-600 dark:text-slate-400'
                  }`}
                  title={anclada ? `Vence ${textoDeAncla(tarea.ancla, tarea.anclaDias ?? 0)}: si la acción cambia de fecha, se mueve con ella` : undefined}
                >
                  {anclada && <Link2 className="h-3.5 w-3.5" aria-label="Se mueve con la acción" />}
                  {vencida ? 'venció' : 'vence'} {fechaCorta(tarea.vence)}
                </span>
              )}
            </div>

            {/* 2. Quién la hace, cuántos archivos y, si es de Tienda, su estado. */}
            <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-sm text-slate-600 dark:text-slate-400">
              <span className={esMia && !agencia ? 'font-semibold text-brand-800 dark:text-brand-200' : 'font-medium text-slate-700 dark:text-slate-300'}>
                {quien}
              </span>
              {laLlevo && (<>
                <span aria-hidden>·</span>
                <span className="font-semibold text-brand-800 dark:text-brand-200">la llevás vos</span>
              </>)}
              {archivos > 0 && (<>
                <span aria-hidden>·</span>
                <span className="inline-flex items-center gap-1">
                  <Paperclip className="h-3.5 w-3.5" aria-hidden />
                  {archivos} {archivos === 1 ? 'archivo' : 'archivos'}
                </span>
              </>)}
              {!conTarjeta && (<>
                <span aria-hidden>·</span>
                <EstadoDeLaTarea tarea={tarea} puede={puedeEstado} />
              </>)}
            </p>

            {/* 3. En qué está su tarjeta, y la puerta para abrirla. */}
            {tarea.entrega && <EnQueEstaLaTarjeta tarea={tarea} personas={personas} usuarioId={usuarioId} />}

            {abierta && (
              <MasDeLaTarea
                tarea={tarea} personas={personas} usuarioId={usuarioId} gestiona={gestiona}
                onRenombrar={() => setRenombrando(true)} onCerrar={() => setAbierta(false)}
              />
            )}
          </div>

          <button
            type="button"
            onClick={() => setAbierta(v => !v)}
            aria-expanded={abierta}
            aria-label={`${abierta ? 'Cerrar' : 'Más de'} ${tarea.titulo}: detalle, archivos${gestiona ? ' y editar' : ''}`}
            title={gestiona ? 'Detalle, archivos y editar' : 'Detalle y archivos'}
            className={`-my-1 -mr-1.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition active:scale-95 sm:h-9 sm:w-9 ${
              abierta
                ? 'bg-brand-100 text-brand-700 dark:bg-brand-500/20 dark:text-brand-200'
                : 'text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100'
            }`}
          >
            <MoreHorizontal className="h-5 w-5" />
          </button>
        </div>
      </div>
    </li>
  )
}

/** La casilla de una tarea de Tienda: un área de 40px para el dedo, con el cuadrado de 24 adentro. */
function Casilla({ tarea, puede, hecha }: { tarea: Tarea; puede: boolean; hecha: boolean }) {
  const cambiar = useCalendario(s => s.cambiarTarea)
  return (
    <button
      type="button"
      disabled={!puede}
      onClick={() => cambiar(tarea.id, { estado: hecha ? 'pendiente' : 'hecha' })}
      title={!puede ? 'Solo quien la tiene asignada puede tildarla' : hecha ? 'Volver a pendiente' : 'Marcar como hecha'}
      aria-label={hecha ? `Desmarcar ${tarea.titulo}` : `Marcar ${tarea.titulo} como hecha`}
      aria-pressed={hecha}
      data-tilde
      className="group/tilde -m-2 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl disabled:cursor-not-allowed"
    >
      <span className={`flex h-6 w-6 items-center justify-center rounded-md border-2 transition duration-200 group-active/tilde:scale-90 ${
        hecha
          ? 'border-emerald-500 bg-emerald-500 text-white'
          : 'border-slate-400 bg-white group-hover/tilde:border-emerald-500 group-hover/tilde:bg-emerald-50 dark:border-slate-500 dark:bg-slate-900 dark:group-hover/tilde:bg-emerald-500/10'
      } ${!puede ? 'opacity-50' : ''}`}>
        {hecha && <Check className="h-4 w-4 animate-tilde" strokeWidth={3} />}
      </span>
    </button>
  )
}

const TONO_TEXTO: Record<EstadoTarea, string> = {
  pendiente: 'text-slate-700 dark:text-slate-300',
  'en-proceso': 'text-amber-800 dark:text-amber-200',
  hecha: 'text-emerald-700 dark:text-emerald-300',
}

/** "Pendiente / En proceso / Hecha": quien puede lo cambia ahí mismo, sin pastilla. */
function EstadoDeLaTarea({ tarea, puede }: { tarea: Tarea; puede: boolean }) {
  const cambiar = useCalendario(s => s.cambiarTarea)
  if (!puede) return <span className={`font-semibold ${TONO_TEXTO[tarea.estado]}`}>{ETIQUETA_ESTADO_TAREA[tarea.estado]}</span>
  return (
    <span className="relative inline-flex items-center">
      <select
        value={tarea.estado}
        onChange={e => cambiar(tarea.id, { estado: e.target.value as EstadoTarea })}
        aria-label={`Estado de ${tarea.titulo}`}
        className={`-my-1 h-9 cursor-pointer appearance-none rounded-lg border-0 bg-transparent py-0 pl-1 pr-6 text-sm font-semibold outline-none transition hover:bg-slate-100 focus-visible:ring-2 focus-visible:ring-brand-500 dark:hover:bg-slate-800 sm:h-8 ${TONO_TEXTO[tarea.estado]}`}
      >
        {ESTADOS.map(e => <option key={e} value={e}>{ETIQUETA_ESTADO_TAREA[e]}</option>)}
      </select>
      <ChevronDown className={`pointer-events-none absolute right-1 h-3.5 w-3.5 ${TONO_TEXTO[tarea.estado]}`} aria-hidden />
    </span>
  )
}

/**
 * La tercera línea de una tarea con tarjeta: a quién le toca y la puerta a la
 * tarjeta. Con una sola fase, un punto del color de cómo está; con varias, una
 * barrita por fase (FasesCompactas), como en el tablero.
 */
function EnQueEstaLaTarjeta({ tarea, personas, usuarioId }: {
  tarea: Tarea
  personas: Persona[]
  usuarioId: number | null
}) {
  const abrir = useVistaEntregas(s => s.abrir)
  const r = tarea.entrega!
  const nombreDe = (id: number | null) => personas.find(p => p.id === id)?.nombre ?? 'alguien'
  // La hace una agencia (16/11/2026): se nombra a la agencia, no a una persona.
  const hace = tarea.para && tarea.para !== 'tienda' && tarea.agencia
    ? { tipo: tarea.para, nombre: tarea.agencia } as const : null
  const paso = proximoPaso(r, tarea.asignadoA, usuarioId, nombreDe, false, { hace })
  const meToca = paso.aQuien === 'vos'
  const fase = r.fases.find(f => f.id === r.faseActual)
  const tono = fase ? estadoDeFase(fase, r).tono : 'hecha'
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <p className={`flex min-w-0 flex-1 items-center gap-2 text-sm font-semibold ${meToca ? 'text-brand-800 dark:text-brand-100' : 'text-slate-800 dark:text-slate-200'}`}>
        {r.fases.length > 1
          ? <FasesCompactas resumen={r} />
          : <span aria-hidden className={`h-2.5 w-2.5 shrink-0 rounded-full ${PUNTO_DE_FASE[tono]}`} />}
        <span className="min-w-0">{paso.texto}</span>
      </p>
      {/* Siempre abre la tarjeta mirando (Ivan, 19/11/2026: "vos lo que
          tendrías que abrirme es la tarjeta"); entregar o revisar, desde el
          botón que está arriba de la tarjeta. */}
      <button
        type="button"
        onClick={() => abrir(tarea.id, 'ver')}
        className={`min-h-[40px] shrink-0 rounded-xl px-3.5 text-sm font-bold transition active:scale-[.98] ${
          meToca ? 'bg-brand-600 text-white shadow-sm hover:bg-brand-700' : 'bg-white text-slate-800 ring-1 ring-slate-300 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-100 dark:ring-slate-600 dark:hover:bg-slate-800'
        }`}
      >
        Abrir la tarjeta
      </button>
    </div>
  )
}

const PUNTO_DE_FASE = {
  hecha: 'bg-emerald-500',
  actual: 'bg-brand-500',
  cambios: 'bg-rose-500',
  pendiente: 'bg-slate-300 dark:bg-slate-600',
} as const

/**
 * Lo que abre el "⋯": el detalle, los archivos y, para quien gestiona las
 * tareas, todo lo de editar (quién la hace, responsable de Tienda, vence, el
 * estado de una tarea con tarjeta, el nombre y borrar). Es lo mismo que antes
 * estaba a la vista en la tarea desplegada: nada se perdió, se ordenó.
 */
function MasDeLaTarea({ tarea, personas, usuarioId, gestiona, onRenombrar, onCerrar }: {
  tarea: Tarea
  personas: Persona[]
  usuarioId: number | null
  gestiona: boolean
  onRenombrar: () => void
  onCerrar: () => void
}) {
  const cambiar = useCalendario(s => s.cambiarTarea)
  const borrar = useCalendario(s => s.borrarTarea)
  const personasEstado = useCalendario(s => s.personasEstado)
  const [editandoDetalle, setEditandoDetalle] = useState(false)
  const [confirmando, setConfirmando] = useState(false)
  const conTarjeta = Boolean(tarea.entrega)
  const hecha = tarea.estado === 'hecha'
  const vencida = !hecha && !!tarea.vence && tarea.vence < hoyIso()
  const anclada = !hecha && !!tarea.ancla && tarea.anclaDias != null
  const asignado = personas.find(p => p.id === tarea.asignadoA)
  // La hace una agencia de la plataforma: sin nadie asignado no está "sin
  // asignar", la tiene la agencia. Y pasársela a alguien de Tienda se la saca
  // del tablero (el servidor la pasa a Tienda): se pregunta antes.
  const deLaAgencia = tarea.para === 'agencia' ? (tarea.agencia || 'la agencia') : null
  // Quien la lleva por Tienda, si la hace una agencia (0090).
  const conResponsable = tarea.para === 'agencia' || tarea.para === 'fuera'
  const responsable = personas.find(p => p.id === tarea.responsable)
  // Una tarea de Tienda la lleva alguien de Tienda: las cuentas de las
  // agencias se ofrecen solo en una pieza de una agencia (19/11/2026). Quien
  // ya la tiene sigue apareciendo, para no perder de quién era.
  const asignables = asignablesPara(personas, tarea.para)

  function asignar(valor: string) {
    const id = valor ? Number(valor) : null
    const nueva = id != null ? personas.find(p => p.id === id) : undefined
    const mismaAgencia = !!nueva?.externo && mismaEmpresa(nueva.empresa, tarea.agencia)
    if (deLaAgencia && id != null && !mismaAgencia
      && !window.confirm(`Se la sacás a ${deLaAgencia}: deja de estar en su tablero y la hace ${nueva?.nombre ?? 'esa persona'}. ¿Seguís?`)) {
      return
    }
    cambiar(tarea.id, { asignadoA: id })
  }

  return (
    <div
      className="mt-3 animate-scale-in space-y-3.5 border-t border-slate-200 pt-3 dark:border-slate-700"
      onKeyDown={e => { if (e.key === 'Escape' && !editandoDetalle) { e.stopPropagation(); onCerrar() } }}
    >
      {/* El detalle: lo que se pidió. */}
      {editandoDetalle ? (
        <EditorDeDetalle tarea={tarea} onCerrar={() => setEditandoDetalle(false)} />
      ) : (
        <div>
          <p className={ROTULO}>Detalle</p>
          {tarea.descripcion
            ? <p className="whitespace-pre-line text-sm leading-relaxed text-slate-800 dark:text-slate-200">{tarea.descripcion}</p>
            : <p className="text-sm text-slate-600 dark:text-slate-400">Sin detalle.</p>}
          {gestiona && (
            <button type="button" onClick={() => setEditandoDetalle(true)} className={`${BOTON_CHICO} mt-1 -ml-2`}>
              <FileText className="h-4 w-4" /> {tarea.descripcion ? 'Editar el detalle' : 'Escribir o dictar el detalle'}
            </button>
          )}
        </div>
      )}

      {/* Los archivos del pedido (24/11/2026): el Excel, el PDF de referencias.
          Adjuntar y sacar, quien puede (lo decide el servidor). */}
      <AdjuntosDeLaTarea tareaId={tarea.id} />

      {anclada && (
        <p
          className="flex items-start gap-1.5 text-xs text-slate-600 dark:text-slate-400"
          title="Si la acción cambia de fecha, esta tarea se mueve con ella. Si le cambiás el vencimiento a mano, queda fija."
        >
          <Link2 className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
          <span>Vence {textoDeAncla(tarea.ancla, tarea.anclaDias ?? 0)} · se mueve con la acción</span>
        </p>
      )}

      {gestiona ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className={ROTULO}>Quién la hace</span>
            <span className="relative flex items-center">
              <UserRound className="pointer-events-none absolute left-3 h-4 w-4 text-slate-500 dark:text-slate-400" aria-hidden />
              <select value={tarea.asignadoA ?? ''} onChange={e => asignar(e.target.value)} aria-label={`Quién hace ${tarea.titulo}`} className="campo pl-9">
                <option value="">{deLaAgencia ? `La agencia (${deLaAgencia})` : 'Sin asignar'}</option>
                {/* Alguien que ya no abre este mundo igual se muestra: no se pierde de quién era. */}
                {/* Sin la lista de personas todavía no se sabe quién es: no se dice que ya no está. */}
                {tarea.asignadoA != null && !asignado && (
                  <option value={tarea.asignadoA}>{personasEstado === 'ok' ? 'Alguien que ya no ve este calendario' : 'Asignada'}</option>
                )}
                {asignado && !asignables.includes(asignado) && (
                  <option value={asignado.id}>{nombreConEmpresa(asignado)}</option>
                )}
                {asignables.map(p => <option key={p.id} value={p.id}>{nombreConEmpresa(p)}{p.id === usuarioId ? ' (vos)' : ''}</option>)}
              </select>
            </span>
          </label>

          {/* Responsable de Tienda (0090): quien la sigue cuando la hace una agencia. */}
          {conResponsable && (
            <label className="block">
              <span className={ROTULO}>Responsable de Tienda</span>
              <span className="relative flex items-center">
                <ShieldCheck className="pointer-events-none absolute left-3 h-4 w-4 text-slate-500 dark:text-slate-400" aria-hidden />
                <select
                  value={tarea.responsable ?? ''}
                  onChange={e => cambiar(tarea.id, { responsable: e.target.value ? Number(e.target.value) : null })}
                  aria-label={`Responsable de Tienda de ${tarea.titulo}`}
                  className="campo pl-9"
                >
                  <option value="">Sin responsable</option>
                  {tarea.responsable != null && !responsable && (
                    <option value={tarea.responsable}>{personasEstado === 'ok' ? 'Alguien que ya no ve este calendario' : 'Responsable'}</option>
                  )}
                  {delEquipo(personas).map(p => (
                    <option key={p.id} value={p.id}>{p.nombre}{p.id === usuarioId ? ' (vos)' : ''}</option>
                  ))}
                </select>
              </span>
            </label>
          )}

          <label className="block">
            <span className={ROTULO}>Vence</span>
            <span className="relative flex items-center">
              <CalendarClock className={`pointer-events-none absolute left-3 h-4 w-4 ${vencida ? 'text-rose-600 dark:text-rose-300' : 'text-slate-500 dark:text-slate-400'}`} aria-hidden />
              <CampoFecha
                valor={tarea.vence}
                onGuardar={vence => cambiar(tarea.id, { vence })}
                aria-label={`Cuándo vence ${tarea.titulo}`}
                className={`campo pl-9 ${vencida ? 'text-rose-700 dark:text-rose-300' : ''}`}
              />
            </span>
          </label>

          {/* Una tarea con tarjeta se cierra sola al aprobarse; quien lidera
              igual la puede cerrar (o reabrir) a mano. */}
          {conTarjeta && (
            <label className="block">
              <span className={ROTULO}>Estado de la tarea</span>
              <select
                value={tarea.estado}
                onChange={e => cambiar(tarea.id, { estado: e.target.value as EstadoTarea })}
                aria-label={`Estado de ${tarea.titulo}`}
                className="campo"
              >
                {ESTADOS.map(e => <option key={e} value={e}>{ETIQUETA_ESTADO_TAREA[e]}</option>)}
              </select>
            </label>
          )}
        </div>
      ) : (conResponsable && tarea.responsable != null && (
        <p className="flex items-center gap-1.5 text-sm text-slate-700 dark:text-slate-300">
          <ShieldCheck className="h-4 w-4 text-slate-500 dark:text-slate-400" aria-hidden />
          {tarea.responsable === usuarioId ? 'La llevás vos por Tienda' : `Responsable de Tienda: ${responsable?.nombre ?? 'otra persona'}`}
        </p>
      ))}

      <div className="flex flex-wrap items-center gap-1.5">
        {gestiona && (
          <button type="button" onClick={onRenombrar} className={`${BOTON_CHICO} -ml-2`}>
            <Pencil className="h-4 w-4" /> Cambiarle el nombre
          </button>
        )}
        {gestiona && (confirmando ? (
          <button
            type="button"
            autoFocus
            onClick={() => borrar(tarea.id)}
            onBlur={() => setConfirmando(false)}
            className="min-h-[40px] animate-scale-in rounded-xl bg-rose-600 px-3 text-sm font-semibold text-white shadow-sm transition hover:bg-rose-700 active:scale-95"
          >
            {/* Borrar se lleva su tarjeta: que se lea antes de confirmar. */}
            {conTarjeta ? 'Sí, borrar con sus entregas' : 'Sí, borrar'}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => setConfirmando(true)}
            className={`${BOTON_CHICO} hover:!bg-rose-50 hover:!text-rose-700 dark:hover:!bg-rose-500/10 dark:hover:!text-rose-300`}
          >
            <Trash2 className="h-4 w-4" /> Borrar
          </button>
        ))}
        <button
          type="button"
          onClick={onCerrar}
          className="ml-auto min-h-[40px] rounded-xl px-3.5 text-sm font-semibold text-slate-700 ring-1 ring-slate-300 transition hover:bg-slate-100 active:scale-[.98] dark:text-slate-200 dark:ring-slate-600 dark:hover:bg-slate-800"
        >
          Listo
        </button>
      </div>
    </div>
  )
}

/** El rótulo chico de cada parte del "⋯". */
const ROTULO = 'mb-1 block text-xs font-bold uppercase tracking-wide text-slate-600 dark:text-slate-400'

/** Los botones de texto del "⋯" (Editar el detalle, Cambiarle el nombre, Borrar). */
const BOTON_CHICO = 'flex min-h-[40px] items-center gap-1.5 rounded-xl px-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 hover:text-brand-700 active:scale-95 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-brand-200'

/**
 * Nueva tarea: un pedido, en el primer nivel (Ivan, 24/11/2026: "sería
 * simplemente tarea nueva pum poner los banners y descripción o lo que sea
 * que estemos pidiendo"). Un solo formulario:
 *
 *   ¿Qué se pide?  Banners, Mailing, Redes… (con sus opciones) u Otra cosa
 *   ¿Quién la hace? Publicis, Another Monday, Diseñadores o alguien de Tienda
 *   Detalle · Archivos · Responsable de Tienda (si la hace una agencia) · Vence
 *
 * Se crea UNA tarea; si la hace una agencia, esa misma tarea es su tarjeta en
 * el tablero. Con un tipo, el nombre se arma solo ("<Acción> - <Tipo>") y se
 * puede cambiar. Con dos tipos a la vez se crean dos tareas, una al lado de la
 * otra, con el mismo detalle y los mismos archivos.
 */
function NuevaTarea({ accionId, personas, usuarioId, alLado }: {
  accionId: string
  personas: Persona[]
  usuarioId: number | null
  /** Otro botón al lado de "Crear tarea" mientras está cerrado (Usar plantilla). */
  alLado?: React.ReactNode
}) {
  const crear = useCalendario(s => s.crearTarea)
  const adjuntar = useCalendario(s => s.adjuntar)
  const personasEstado = useCalendario(s => s.personasEstado)
  // Abierto o cerrado lo lleva el bloque (FormularioAbierto).
  const { abierto: abiertoEnElBloque, abrir, accion } = useContext(FormularioAbierto)
  const catalogo = useCatalogoDeTipos()
  const tipos = tiposDelMundo(catalogo.tipos, accion?.mundo)
  const { tableros } = useTableros(accion?.mundo)
  const abierto = abiertoEnElBloque === 'nueva'
  const setAbierto = (v: boolean) => abrir(v ? 'nueva' : null)

  const [elegidas, setElegidas] = useState<PiezaElegida[]>([])
  const [titulo, setTitulo] = useState('')
  // "agencia:Publicis", "persona:12" o "" (nadie todavía).
  const [quien, setQuien] = useState('')
  const [responsable, setResponsable] = useState('')
  const [vence, setVence] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [archivos, setArchivos] = useState<File[]>([])

  const deAgencia = quien.startsWith('agencia:')
  const nombreAuto = elegidas.length === 1
    ? nombreDeTarjeta(accion?.nombre ?? '', tipos?.find(t => t.clave === elegidas[0].clave))
    : ''
  const linkMalo = elegidas.map(p => linkMaloEn(p, tipos)).find(Boolean) ?? null
  const falta = elegidas.length === 0 && !titulo.trim() ? 'Escribí qué hay que hacer, o elegí qué se pide.'
    : elegidas.length > 0 && !quien ? 'Elegí quién la hace.'
      : linkMalo
  const cuantas = Math.max(1, elegidas.length)

  function limpiar() {
    setElegidas([]); setTitulo(''); setQuien(''); setResponsable(''); setVence(''); setDescripcion(''); setArchivos([])
  }

  function cerrar() {
    limpiar()
    setAbierto(false)
  }

  function enviar(e: React.FormEvent) {
    e.preventDefault()
    if (falta) return
    const venceGuardable = esFechaGuardable(vence) ? vence : null
    const para = deAgencia ? 'agencia' as const : 'tienda' as const
    const agencia = deAgencia ? quien.slice('agencia:'.length) : null
    const asignadoA = quien.startsWith('persona:') ? Number(quien.slice('persona:'.length)) : null
    const varias = elegidas.length > 1
    const detalle = descripcion.trim() || null
    const pedidos: (PiezaElegida | null)[] = elegidas.length > 0 ? elegidas : [null]
    for (const p of pedidos) {
      const tipo = p ? tipos?.find(t => t.clave === p.clave) : undefined
      // Con un tipo, el nombre escrito manda; si no se escribió, el de siempre.
      const propio = !varias && titulo.trim() !== ''
      const id = crear(accionId, {
        titulo: p ? (propio ? titulo.trim() : nombreDeTarjeta(accion?.nombre ?? '', tipo)) : titulo.trim(),
        nombrePropio: !!p && propio,
        descripcion: detalle, asignadoA, vence: venceGuardable,
        para, agencia, responsable: deAgencia && responsable ? Number(responsable) : null,
        tipo: p?.clave ?? null, opciones: p?.opciones ?? [],
        detalles: p ? Object.fromEntries(Object.entries(p.detalles).filter(([, v]) => v.trim() !== '')) : undefined,
        silencioso: varias,
      })
      // En la cola de la acción, detrás de su alta: cada tarea con sus archivos.
      if (id && archivos.length > 0) void adjuntar(accionId, id, archivos)
    }
    if (varias) {
      toast.success(`Se crearon ${elegidas.length} tareas, cada una con su tarjeta en el tablero.`)
    }
    cerrar()
  }

  /** Lo dictado trae un título: si todavía no hay uno ni se eligió qué se
   *  pide, se usa ese. */
  function alDictar(brief: BriefListo) {
    if (!titulo.trim() && elegidas.length === 0) setTitulo(brief.resumen.slice(0, 500))
  }

  if (!abierto) {
    return (
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <button
          type="button"
          onClick={() => setAbierto(true)}
          className="flex min-h-[48px] flex-1 items-center justify-center gap-2 rounded-2xl bg-brand-600 px-4 text-sm font-bold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.99]"
        >
          <Plus className="h-4 w-4" /> Crear tarea
        </button>
        {alLado}
      </div>
    )
  }

  return (
    <form
      onSubmit={enviar}
      onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); cerrar() } }}
      className="mt-3 animate-scale-in space-y-3 rounded-2xl border border-brand-200 bg-brand-50/50 p-3.5 dark:border-brand-500/30 dark:bg-brand-500/[.06]"
    >
      <p className="text-sm font-semibold text-brand-800 dark:text-brand-200">Nueva tarea</p>

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
            {elegidas.length === 1 ? <>Nombre <span className="font-normal text-slate-500 dark:text-slate-400">(se puede cambiar)</span></> : 'Qué hay que hacer'}
          </span>
          <input
            autoFocus
            value={titulo}
            onChange={e => setTitulo(e.target.value)}
            placeholder={nombreAuto || 'Ej: Arte del header desktop'}
            aria-label={elegidas.length === 1 ? 'Nombre de la tarea' : 'Qué hay que hacer'}
            maxLength={500}
            className="campo"
          />
        </label>
      ) : (
        <p className="rounded-xl border border-brand-200 bg-white px-3 py-2 text-sm text-slate-700 dark:border-brand-500/30 dark:bg-slate-900 dark:text-slate-200">
          Se van a crear {elegidas.length} tareas:{' '}
          <strong className="font-semibold text-slate-900 dark:text-slate-50">
            {elegidas.map(p => nombreDeTarjeta(accion?.nombre ?? '', tipos?.find(t => t.clave === p.clave))).join(' · ')}
          </strong>
        </p>
      )}

      <label className="block">
        <span className="etiqueta-campo">¿Quién la hace?</span>
        <select value={quien} onChange={e => setQuien(e.target.value)} className="campo" aria-label="Quién la hace">
          <option value="">{elegidas.length > 0 ? 'Elegí quién la hace' : 'Sin asignar por ahora'}</option>
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
        {deAgencia && (
          <span className="mt-1 block text-xs text-slate-600 dark:text-slate-400">
            Le nace su tarjeta en el tablero de {quien.slice('agencia:'.length)} y le avisamos.
          </span>
        )}
      </label>

      <CampoDetalle
        id={`detalle-nueva-${accionId}`}
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
        <button type="button" onClick={cerrar} className="min-h-[44px] rounded-xl px-4 text-sm font-semibold text-slate-600 transition hover:bg-slate-200/70 dark:text-slate-300 dark:hover:bg-slate-800 sm:min-h-[40px]">
          Cancelar
        </button>
        <button
          type="submit"
          disabled={!!falta}
          className="min-h-[44px] rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.98] disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:shadow-none dark:disabled:bg-slate-700 dark:disabled:text-slate-400 sm:min-h-[40px]"
        >
          {cuantas > 1 ? `Crear ${cuantas} tareas` : 'Crear tarea'}
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

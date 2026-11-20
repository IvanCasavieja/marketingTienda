'use client'

import { createContext, useContext, useId, useRef, useState, type ReactNode } from 'react'
import {
  CalendarClock, Check, ChevronDown, CornerDownRight, FileText, GripVertical, Layers, LayoutTemplate, Link2, ListChecks, Mic, Pencil, Plus, Sparkles, Trash2, UserRound, X,
} from 'lucide-react'
import { correrUnLugar, moverEntreHermanas } from '@/lib/calendario/orden'
import { toast } from 'sonner'
import { fechaCorta, hoyIso } from '@/lib/calendario/fechas'
import { CampoFecha, esFechaGuardable } from './CampoFecha'
import { DictarBrief, type BriefListo } from '@/components/ia/DictarBrief'
import { useCalendario } from '@/lib/calendario/store'
import { plantillasSugeridas, textoDeAncla } from '@/lib/calendario/plantillas'
import {
  ETIQUETA_ESTADO_TAREA, NIVELES_DE_TAREA, asignablesPara, delEquipo, mismaEmpresa, nivelDeTarea,
  type BarraGuardada, type EstadoTarea, type Persona, type Tarea, nombreConEmpresa,
} from '@/lib/calendario/tipos'
import { proximoPaso } from '@/lib/calendario/entregas'
import { useVistaEntregas } from '@/store/entregas'
import { FasesCompactas, faseActualTexto } from './entregas/LineaDeFases'
import { ModalDeOpciones, PedirPieza } from './PedirPieza'
import { useCatalogoDeTipos, useTableros, type Tablero } from '@/store/tiposDeTarea'
import { camposVisibles, linkValido, nombreDeTarjeta, tiposDelMundo, valorParaLeer, type TipoDeTarea } from '@/lib/calendario/tipos-de-tarea'
import { usePermisosCalendario } from '@/lib/calendario/permisos'

/**
 * Las tareas de una acción.
 *
 * Pedido de Ivan (12/11/2026): quien lidera abre una acción, le crea tareas y
 * subtareas, y se las asigna a cada persona, que se entera por la campanita.
 *
 * - `gestiona` (permiso `calendario.tareas`): crea, asigna, pone fecha y borra,
 *   y usa las plantillas del mundo (ver DialogoPlantillas).
 * - Quien tiene `calendario.pedidos` pide piezas (16/11/2026: "todo el
 *   equipo tiene que poder crear tareas para agencia"): Banners,
 *   Mailing, Cenefas… con quién la hace y para cuándo. Le nace su tarjeta en
 *   el tablero (ver PedirPieza).
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

const TONO: Record<EstadoTarea, string> = {
  pendiente: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  'en-proceso': 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-200',
  hecha: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-200',
}
const ESTADOS: EstadoTarea[] = ['pendiente', 'en-proceso', 'hecha']

/** Las pastillas de una tarea (a quién, cuándo, estado): mismo alto y mismo radio. */
const PASTILLA = 'h-9 rounded-lg border-0 text-sm font-medium outline-none transition focus-visible:ring-2 focus-visible:ring-brand-500 sm:h-8'

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

export function BloqueTareas({ accion, personas, usuarioId, gestiona, conTitulo = true }: {
  accion: BarraGuardada
  personas: Persona[]
  usuarioId: number | null
  gestiona: boolean
  /** Sin el título "Tareas": dentro de la pestaña que ya lo dice. */
  conTitulo?: boolean
}) {
  const tareas = accion.tareas ?? []
  const hechas = tareas.filter(t => t.estado === 'hecha').length
  const raices = tareas.filter(t => !t.parentId || !tareas.some(x => x.id === t.parentId))
  const todas = tareas.length > 0 && hechas === tareas.length
  const abrirPlantillas = useCalendario(s => s.abrirPlantillas)
  const plantillas = useCalendario(s => s.plantillas)
  const [descartadas, setDescartadas] = useState<string[]>(() => (typeof window === 'undefined' ? [] : leerDescartadas()))
  const sugeridas = gestiona && !descartadas.includes(accion.id) ? plantillasSugeridas(plantillas, accion) : []
  // Pedir una pieza: quien gestiona tareas y quien tiene el permiso de pedir
  // piezas (calendario.pedidos, aparte de editar desde el 17/11/2026). Una
  // cuenta externa nunca lo tiene. Es lo mismo que exige el servidor.
  const { pidePiezas: puedePedir } = usePermisosCalendario()
  const pidePiezas = gestiona || puedePedir
  // Un solo formulario abierto a la vez en todo el bloque (ver FormularioAbierto).
  const [abierto, abrir] = useState<Abierto>(null)

  return (
    <FormularioAbierto.Provider value={{ accion, pidePiezas, abierto, abrir }}>
    <section>
      {(conTitulo || tareas.length > 0) && (
        <div className="mb-3 flex items-center gap-2">
          {conTitulo && (
            <>
              <ListChecks className="h-5 w-5 text-brand-600 dark:text-brand-300" />
              <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">Tareas</h3>
            </>
          )}
          {tareas.length > 0 && (
            <span className={`text-sm tabular-nums ${todas ? 'font-semibold text-emerald-700 dark:text-emerald-300' : 'text-slate-600 dark:text-slate-400'}`}>
              {todas ? '¡Todas hechas!' : `${hechas} de ${tareas.length} hechas`}
            </span>
          )}
        </div>
      )}

      {sugeridas.length > 0 && (
        <SugerenciaDePlantilla
          accion={accion}
          sugeridas={sugeridas.map(p => ({ id: p.id, nombre: p.nombre, tareas: p.tareas.length }))}
          onVer={() => abrirPlantillas(accion.id)}
          onAhoraNo={() => setDescartadas(guardarDescartada(accion.id))}
        />
      )}

      {tareas.length > 0 && (
        <div className="mb-4 h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800" role="progressbar" aria-valuemin={0} aria-valuemax={tareas.length} aria-valuenow={hechas} aria-label="Tareas hechas">
          <div className="h-full rounded-full bg-emerald-500 transition-[width] duration-500 ease-suave" style={{ width: `${(hechas / tareas.length) * 100}%` }} />
        </div>
      )}

      {tareas.length === 0 && (
        <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-slate-300 px-5 py-8 text-center dark:border-slate-700">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-brand-50 text-brand-600 dark:bg-brand-500/15 dark:text-brand-300">
            <ListChecks className="h-5 w-5" />
          </span>
          <p className="max-w-xs text-sm text-slate-600 dark:text-slate-400">
            {gestiona
              ? 'Esta acción todavía no tiene tareas. Creá la primera (o arrancá con una plantilla) y agregale sus piezas: Banners, Redes, Mailing…'
              : pidePiezas
                ? 'Esta acción todavía no tiene tareas. Creá la primera y agregale sus piezas: Banners, Redes, Mailing, EMM…'
                : 'Esta acción todavía no tiene tareas. Las crea el equipo.'}
          </p>
        </div>
      )}

      <ListaOrdenable barraId={accion.id} tareas={raices} puede={gestiona}>
        {raices.map(t => (
          <ItemTarea
            key={t.id} tarea={t} todas={tareas} accionId={accion.id}
            personas={personas} usuarioId={usuarioId} gestiona={gestiona}
          />
        ))}
      </ListaOrdenable>

      {/* El inicio es uno solo: Crear tarea. Los materiales se piden debajo de
          cada tarea creada (17/11/2026). La plantilla sigue para quien lidera. */}
      {pidePiezas && (
        <NuevaTarea
          accionId={accion.id} parentId={null} personas={personas} usuarioId={usuarioId} etiqueta="Crear tarea"
          principal
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
 * Qué formulario está abierto en el bloque de tareas: uno solo a la vez.
 * Ivan (17/11/2026): "al crear una tarea común el cuadro de creación queda
 * abierto incluso si presiono pedir materiales". 'nueva' = Crear tarea;
 * 'material:<id>' = pedir un material de esa tarea; 'sub:<id>' = una
 * subtarea común (quien lidera).
 */
type Abierto = string | null
const FormularioAbierto = createContext<{
  accion: BarraGuardada | null
  /** Crea tareas y pide sus materiales (calendario.pedidos, o quien lidera). */
  pidePiezas: boolean
  abierto: Abierto
  abrir: (a: Abierto) => void
}>({ accion: null, pidePiezas: false, abierto: null, abrir: () => {} })

/**
 * Ordenar las tareas arrastrándolas (Ivan, 20/11/2026). Se agarra la manija
 * (⋮⋮) y se suelta arriba o abajo de otra del mismo nivel; con el teclado, la
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

function ItemTarea({ tarea, todas, accionId, personas, usuarioId, gestiona }: {
  tarea: Tarea
  todas: Tarea[]
  accionId: string
  personas: Persona[]
  usuarioId: number | null
  gestiona: boolean
}) {
  const cambiar = useCalendario(s => s.cambiarTarea)
  const borrar = useCalendario(s => s.borrarTarea)
  const personasEstado = useCalendario(s => s.personasEstado)
  const { accion, pidePiezas, abierto, abrir } = useContext(FormularioAbierto)
  const agregando = abierto === `sub:${tarea.id}`
  const pidiendoMaterial = abierto === `material:${tarea.id}`
  const [confirmando, setConfirmando] = useState(false)
  const [editandoDetalle, setEditandoDetalle] = useState(false)
  const [renombrando, setRenombrando] = useState(false)
  const orden = useContext(OrdenDeLaLista)
  // Minimizada: solo el título (Ivan, 18/11/2026: "que las tareas queden como
  // minimizadas y se muestre solo su título, porque imaginate tener varias
  // tareas con toda esa vista"). Se despliega tocándola; si se está
  // agregando algo adentro, queda abierta.
  const [abiertaAMano, setAbierta] = useState(false)
  const abierta = abiertaAMano || agregando || pidiendoMaterial || editandoDetalle || renombrando

  const hijas = todas.filter(t => t.parentId === tarea.id)
  const piezasHijas = hijas.filter(h => Boolean(h.entrega) || !!h.tipo || (!!h.para && h.para !== 'tienda')).length
  const subtareasHijas = hijas.length - piezasHijas
  const resumenHijas = [
    piezasHijas > 0 ? `${piezasHijas} ${piezasHijas === 1 ? 'pieza' : 'piezas'}` : '',
    subtareasHijas > 0 ? `${subtareasHijas} ${subtareasHijas === 1 ? 'subtarea' : 'subtareas'}` : '',
  ].filter(Boolean).join(' · ')
  const nivel = nivelDeTarea(tarea, todas)
  const esMia = usuarioId != null && tarea.asignadoA === usuarioId
  // Una tarea con entregas queda hecha sola cuando se aprueba la última fase:
  // quien entrega no la tilda (lo mismo exige el servidor). Quien lidera sí.
  const conEntregas = Boolean(tarea.entrega)
  const puedeEstado = gestiona || (esMia && !conEntregas)
  // "Crear tarea y debajo de eso poder asignar los materiales de esa tarea
  // creada" (17/11/2026): los materiales cuelgan de una tarea común, no de
  // otra pieza, y respetan el tope de niveles.
  // Una pieza (con tipo, o para una agencia) no lleva piezas adentro. Se mira
  // el tipo y no solo las entregas: recién creada, la pieza todavía no tiene
  // su resumen de entregas hasta que contesta el servidor.
  const esPieza = conEntregas || !!tarea.tipo || (!!tarea.para && tarea.para !== 'tienda')
  const puedeMaterial = pidePiezas && !esPieza && !!accion && nivel < NIVELES_DE_TAREA
  const hecha = tarea.estado === 'hecha'
  const vencida = !hecha && !!tarea.vence && tarea.vence < hoyIso()
  const asignado = personas.find(p => p.id === tarea.asignadoA)
  // Hecha ya no se mueve: no hace falta decirlo.
  const anclada = !hecha && !!tarea.ancla && tarea.anclaDias != null
  // La hace una agencia de la plataforma: sin nadie asignado no está "sin
  // asignar", la tiene la agencia. Y pasársela a alguien de Tienda se la saca
  // del tablero (el servidor la pasa a Tienda): se pregunta antes.
  const deLaAgencia = tarea.para === 'agencia' ? (tarea.agencia || 'la agencia') : null
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
      {/* Minimizada, se abre tocando cualquier parte del renglón (Ivan,
          18/11/2026: "debería ser todo clickeable, no solo la flechita"),
          menos el tilde, que sigue tildando, y la manija, que arrastra. Con
          el teclado, el título y la flecha son botones. */}
      <div
        data-orden-fila
        onClick={e => {
          if (!abierta && !(e.target as HTMLElement).closest('[data-tilde],[data-manija]')) setAbierta(true)
        }}
        className={`rounded-2xl border px-3.5 ${abierta ? 'py-3' : 'cursor-pointer py-2 hover:border-brand-300 hover:shadow-sm dark:hover:border-brand-500/40'} transition duration-300 ${
        hecha
          ? 'border-slate-300 bg-slate-50/70 dark:border-slate-700 dark:bg-slate-800/30'
          : esMia
            ? 'border-brand-300 bg-brand-50/60 dark:border-brand-500/40 dark:bg-brand-500/[.07]'
            : vencida
              ? 'border-rose-200 bg-white dark:border-rose-500/30 dark:bg-slate-900'
              : 'border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-900'
      }`}>
        <div className={`flex gap-3 ${abierta ? 'items-start' : 'items-center'}`}>
          <Manija tarea={tarea} />
          {/* El tilde: un área de 40px para el dedo, con el cuadrado de 24 adentro */}
          <button
            type="button"
            disabled={!puedeEstado}
            onClick={() => cambiar(tarea.id, { estado: hecha ? 'pendiente' : 'hecha' })}
            title={
              conEntregas && !gestiona ? 'Queda hecha sola cuando se aprueba la última fase'
                : !puedeEstado ? 'Solo quien la tiene asignada puede tildarla'
                  : hecha ? 'Volver a pendiente' : 'Marcar como hecha'
            }
            aria-label={hecha ? `Desmarcar ${tarea.titulo}` : `Marcar ${tarea.titulo} como hecha`}
            aria-pressed={hecha}
            data-tilde
            className="group/tilde -m-2 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl disabled:cursor-not-allowed"
          >
            <span className={`flex h-6 w-6 items-center justify-center rounded-md border-2 transition duration-200 group-active/tilde:scale-90 ${
              hecha
                ? 'border-emerald-500 bg-emerald-500 text-white'
                : 'border-slate-300 bg-white group-hover/tilde:border-emerald-500 group-hover/tilde:bg-emerald-50 dark:border-slate-600 dark:bg-slate-900 dark:group-hover/tilde:bg-emerald-500/10'
            } ${!puedeEstado ? 'opacity-50' : ''}`}>
              {hecha && <Check className="h-4 w-4 animate-tilde" strokeWidth={3} />}
            </span>
          </button>

          <div className="min-w-0 flex-1">
            <p className={`flex flex-wrap items-center gap-x-2 gap-y-1 text-[15px] font-semibold leading-snug transition-colors duration-300 ${
              hecha ? 'text-slate-500 line-through decoration-slate-300 dark:text-slate-400 dark:decoration-slate-600' : 'text-slate-900 dark:text-slate-100'
            }`}>
              {renombrando ? (
                <TituloEditable tarea={tarea} onListo={() => setRenombrando(false)} />
              ) : (
                <button
                  type="button"
                  onClick={() => setAbierta(!abierta)}
                  aria-expanded={abierta}
                  title={abierta ? 'Minimizar' : 'Ver la tarea entera'}
                  className="min-w-0 break-words text-left transition hover:text-brand-700 dark:hover:text-brand-200"
                >
                  {tarea.titulo}
                </button>
              )}
              {vencida && (
                <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-rose-700 no-underline dark:bg-rose-500/15 dark:text-rose-300">
                  Vencida
                </span>
              )}
              {!abierta && resumenHijas && (
                <span className="text-xs font-medium text-slate-500 no-underline dark:text-slate-400">{resumenHijas}</span>
              )}
            </p>
            {abierta && (<>
            {tarea.descripcion && !editandoDetalle && (
              <p className="mt-0.5 whitespace-pre-line text-sm text-slate-600 dark:text-slate-400">{tarea.descripcion}</p>
            )}
            {/* Una tarea de plantilla dice de dónde sale su fecha: que se
                mueva sola con la acción no tiene que sorprender a nadie. */}
            {anclada && (
              <p
                className="mt-1 flex items-start gap-1 text-xs text-slate-500 dark:text-slate-400"
                title="Si la acción cambia de fecha, esta tarea se mueve con ella. Si le cambiás el vencimiento a mano, queda fija."
              >
                <Link2 className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
                <span>Vence {textoDeAncla(tarea.ancla, tarea.anclaDias ?? 0)} · se mueve con la acción</span>
              </p>
            )}
            {editandoDetalle && <EditorDeDetalle tarea={tarea} onCerrar={() => setEditandoDetalle(false)} />}

            <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
              {gestiona ? (
                <label className="relative flex items-center">
                  <UserRound className="pointer-events-none absolute left-2.5 h-4 w-4 text-slate-500 dark:text-slate-400" aria-hidden />
                  <select
                    value={tarea.asignadoA ?? ''}
                    onChange={e => asignar(e.target.value)}
                    aria-label={`A quién se asigna ${tarea.titulo}`}
                    className={`${PASTILLA} max-w-[12rem] cursor-pointer bg-slate-100 pl-8 pr-7 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700`}
                  >
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
                </label>
              ) : (
                <span className={`flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium ${
                  esMia ? 'bg-brand-100 text-brand-800 dark:bg-brand-500/20 dark:text-brand-100' : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
                }`}>
                  <UserRound className="h-4 w-4" />
                  {tarea.asignadoA == null ? (deLaAgencia ? `La hace ${deLaAgencia}` : 'Sin asignar') : esMia ? 'La tenés vos' : asignado?.nombre ?? 'Otra persona'}
                </span>
              )}

              {gestiona ? (
                <label className="relative flex items-center">
                  <CalendarClock className={`pointer-events-none absolute left-2.5 h-4 w-4 ${vencida ? 'text-rose-600 dark:text-rose-300' : 'text-slate-500 dark:text-slate-400'}`} aria-hidden />
                  <CampoFecha
                    valor={tarea.vence}
                    onGuardar={vence => cambiar(tarea.id, { vence })}
                    aria-label={`Cuándo vence ${tarea.titulo}`}
                    className={`${PASTILLA} pl-8 pr-2 ${
                      vencida
                        ? 'bg-rose-100 text-rose-700 hover:bg-rose-200 dark:bg-rose-500/15 dark:text-rose-200'
                        : 'bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700'
                    }`}
                  />
                </label>
              ) : tarea.vence && (
                <span className={`flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium ${
                  vencida ? 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300' : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
                }`}>
                  <CalendarClock className="h-4 w-4" />
                  {vencida ? 'Venció el' : 'Vence el'} {fechaCorta(tarea.vence)}
                </span>
              )}

              <select
                value={tarea.estado}
                disabled={!puedeEstado}
                onChange={e => cambiar(tarea.id, { estado: e.target.value as EstadoTarea })}
                aria-label={`Estado de ${tarea.titulo}`}
                className={`${PASTILLA} cursor-pointer appearance-none px-3 font-semibold disabled:cursor-not-allowed disabled:opacity-70 ${TONO[tarea.estado]}`}
              >
                {ESTADOS.map(e => <option key={e} value={e}>{ETIQUETA_ESTADO_TAREA[e]}</option>)}
              </select>

              {gestiona && (
                <span className="ml-auto flex items-center gap-0.5">
                  {/* Cambiarle el nombre a una tarea ya creada (Ivan, 20/11/2026). */}
                  {!renombrando && (
                    <button
                      type="button"
                      onClick={() => setRenombrando(true)}
                      aria-label={`Cambiarle el nombre a ${tarea.titulo}`}
                      title="Cambiarle el nombre"
                      className="flex h-9 items-center gap-1 rounded-lg px-2 text-sm font-medium text-slate-500 transition hover:bg-slate-100 hover:text-brand-700 active:scale-95 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-brand-200 sm:h-8"
                    >
                      <Pencil className="h-4 w-4" /> Nombre
                    </button>
                  )}
                  {!editandoDetalle && (
                    <button
                      type="button"
                      onClick={() => setEditandoDetalle(true)}
                      aria-label={`${tarea.descripcion ? 'Editar' : 'Agregar'} el detalle de ${tarea.titulo}`}
                      title="Escribir o dictar el detalle"
                      className="flex h-9 items-center gap-1 rounded-lg px-2 text-sm font-medium text-slate-500 transition hover:bg-slate-100 hover:text-brand-700 active:scale-95 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-brand-200 sm:h-8"
                    >
                      <FileText className="h-4 w-4" /> Detalle
                    </button>
                  )}
                  {nivel < NIVELES_DE_TAREA && (
                    <button
                      type="button"
                      onClick={() => abrir(agregando ? null : `sub:${tarea.id}`)}
                      aria-expanded={agregando}
                      className="flex h-9 items-center gap-1 rounded-lg px-2 text-sm font-medium text-slate-500 transition hover:bg-slate-100 hover:text-brand-700 active:scale-95 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-brand-200 sm:h-8"
                    >
                      <Plus className="h-4 w-4" /> Subtarea
                    </button>
                  )}
                  {confirmando ? (
                    <button
                      type="button"
                      autoFocus
                      onClick={() => borrar(tarea.id)}
                      onBlur={() => setConfirmando(false)}
                      className="h-9 animate-scale-in rounded-lg bg-rose-600 px-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-rose-700 active:scale-95 sm:h-8"
                    >
                      {/* Borrar se lleva todo lo que cuelga: que se lea antes de confirmar. */}
                      {conEntregas ? 'Borrar con sus entregas' : hijas.length > 0 ? 'Borrar con sus subtareas' : 'Sí, borrar'}
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setConfirmando(true)}
                      aria-label={`Borrar ${tarea.titulo}`}
                      title="Borrar la tarea"
                      className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 transition hover:bg-rose-50 hover:text-rose-600 active:scale-95 dark:text-slate-400 dark:hover:bg-rose-500/10 dark:hover:text-rose-300 sm:h-8 sm:w-8"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </span>
              )}
            </div>

            {tarea.entrega && (
              <EntregasDeLaTarea tarea={tarea} personas={personas} usuarioId={usuarioId} />
            )}
            </>)}
          </div>
          <button
            type="button"
            onClick={() => setAbierta(!abierta)}
            aria-expanded={abierta}
            aria-label={abierta ? `Minimizar ${tarea.titulo}` : `Ver ${tarea.titulo} entera`}
            className="-my-1 -mr-1.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 active:scale-95 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200 sm:h-8 sm:w-8"
          >
            <ChevronDown className={`h-4 w-4 transition-transform duration-200 ${abierta ? 'rotate-180' : ''}`} />
          </button>
        </div>
      </div>

      {abierta && (hijas.length > 0 || agregando || puedeMaterial) && (
        <div className="ml-4 mt-2 border-l-2 border-slate-300 pl-3 dark:border-slate-700">
          {hijas.length > 0 && (
            <ListaOrdenable barraId={accionId} tareas={hijas} puede={gestiona}>
              {hijas.map(h => (
                <ItemTarea
                  key={h.id} tarea={h} todas={todas} accionId={accionId}
                  personas={personas} usuarioId={usuarioId} gestiona={gestiona}
                />
              ))}
            </ListaOrdenable>
          )}
          {agregando && (
            <NuevaTarea
              accionId={accionId} parentId={tarea.id} personas={personas} usuarioId={usuarioId}
              etiqueta="Nueva subtarea" abierta onListo={() => abrir(null)}
            />
          )}
          {/* Los materiales de esta tarea: Banners, Mailing, Cenefas… cada uno
              con su tarjeta en el tablero y sus entregas. */}
          {puedeMaterial && accion && (pidiendoMaterial ? (
            <PedirPieza
              accion={accion} parentId={tarea.id} tareaMadre={tarea.titulo}
              personas={personas} usuarioId={usuarioId} gestiona={gestiona} onListo={() => abrir(null)}
            />
          ) : (
            <button
              type="button"
              onClick={() => abrir(`material:${tarea.id}`)}
              className={`${hijas.length > 0 ? 'mt-2' : ''} flex min-h-[44px] w-full items-center gap-2 rounded-xl border border-dashed border-slate-300 px-3 text-left text-sm font-semibold text-slate-600 transition hover:border-brand-400 hover:bg-brand-50 hover:text-brand-700 active:scale-[.99] dark:border-slate-700 dark:text-slate-300 dark:hover:border-brand-500/60 dark:hover:bg-brand-500/10 dark:hover:text-brand-200`}
            >
              <Layers className="h-4 w-4 shrink-0" /> Agregar pieza a esta tarea
              <span className="truncate text-xs font-normal text-slate-500 dark:text-slate-400">Banners, Redes, Mailing, EMM, Push…</span>
            </button>
          ))}
        </div>
      )}
    </li>
  )
}

function NuevaTarea({ accionId, parentId, personas, usuarioId, etiqueta, principal = false, abierta = false, onListo, alLado }: {
  accionId: string
  parentId: string | null
  personas: Persona[]
  usuarioId: number | null
  etiqueta: string
  /** El botón de arranque del bloque: lleno, no punteado. */
  principal?: boolean
  abierta?: boolean
  onListo?: () => void
  /** Otro botón al lado de "Nueva tarea" mientras está cerrado (Usar plantilla). */
  alLado?: React.ReactNode
}) {
  const crear = useCalendario(s => s.crearTarea)
  const personasEstado = useCalendario(s => s.personasEstado)
  // Abierto o cerrado lo lleva el bloque: abrir esto cierra cualquier otro
  // formulario (pedir material, otra subtarea).
  const { abierto: abiertoEnElBloque, abrir, pidePiezas, accion } = useContext(FormularioAbierto)
  const { tipos } = useCatalogoDeTipos()
  const { tableros } = useTableros(accion?.mundo)
  const clave = parentId ? `sub:${parentId}` : 'nueva'
  const abierto = abierta || abiertoEnElBloque === clave
  const setAbierto = (v: boolean) => abrir(v ? clave : null)
  const [titulo, setTitulo] = useState('')
  const [asignadoA, setAsignadoA] = useState('')
  const [vence, setVence] = useState('')
  const [descripcion, setDescripcion] = useState('')
  // Ivan (17/11/2026): "la idea es que antes de crear la tarea ya
  // seleccionemos las piezas". Solo en la tarea principal, y para quien
  // puede pedirlas; la persona y la fecha valen para todas.
  const [piezas, setPiezas] = useState<PiezaElegida[]>([])
  const conPiezas = !parentId && pidePiezas

  const responsable = asignadoA ? Number(asignadoA) : null
  const linkMalo = piezas.map(p => faltaEnPieza(p, tipos)).find(Boolean) ?? null
  const valida = titulo.trim() !== '' && !linkMalo

  function limpiar() {
    setTitulo(''); setAsignadoA(''); setVence(''); setDescripcion(''); setPiezas([])
  }

  function cerrar() {
    limpiar()
    setAbierto(false)
    onListo?.()
  }

  function enviar(e: React.FormEvent) {
    e.preventDefault()
    if (!valida) return
    const venceGuardable = esFechaGuardable(vence) ? vence : null
    const elegidas = conPiezas ? piezas : []
    const id = crear(accionId, {
      titulo, parentId, asignadoA: responsable, vence: venceGuardable,
      descripcion: descripcion.trim() || null,
      silencioso: elegidas.length > 0,
    })
    // Sus piezas, con la misma fecha: la tarea es la acción principal y las
    // piezas cuelgan de ella. Cada una va al tablero que se eligió en su
    // modal (Publicis, Another Monday o Diseñadores) y la toma cualquiera de
    // ese tablero: no llevan persona (17/11/2026). La persona de la tarea es
    // quien la lleva por Tienda Inglesa. Van en la cola de la acción, detrás
    // del alta de la tarea, y cada una lleva el detalle de la tarea, que es
    // lo que lee quien la hace en su tarjeta.
    if (id) {
      for (const p of elegidas) {
        const tipo = tipos?.find(t => t.clave === p.clave)
        crear(accionId, {
          titulo: nombreDeTarjeta(accion?.nombre ?? '', tipo), parentId: id,
          asignadoA: null, vence: venceGuardable,
          descripcion: descripcion.trim() || null,
          para: 'agencia', agencia: p.tablero, tipo: p.clave, opciones: p.opciones,
          detalles: Object.fromEntries(Object.entries(p.detalles).filter(([, v]) => v.trim() !== '')),
          silencioso: true,
        })
      }
      if (elegidas.length > 0) {
        toast.success(`Tarea creada con ${elegidas.length} ${elegidas.length === 1 ? 'pieza' : 'piezas'}: nacieron sus tarjetas en el tablero.`)
      }
    }
    cerrar()
  }

  /** Lo dictado trae un título: si la tarea todavía no tiene, se usa ese. */
  function alDictar(brief: BriefListo) {
    if (!titulo.trim()) setTitulo(brief.resumen.slice(0, 500))
  }

  if (!abierto) {
    return (
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <button
          type="button"
          onClick={() => setAbierto(true)}
          className={principal
            ? 'flex min-h-[48px] flex-1 items-center justify-center gap-2 rounded-2xl bg-brand-600 px-4 text-sm font-bold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.99]'
            : 'flex min-h-[48px] flex-1 items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-slate-300 px-4 text-sm font-semibold text-slate-600 transition hover:border-brand-400 hover:bg-brand-50 hover:text-brand-700 active:scale-[.99] dark:border-slate-700 dark:text-slate-300 dark:hover:border-brand-500/60 dark:hover:bg-brand-500/10 dark:hover:text-brand-200'}
        >
          <Plus className="h-4 w-4" /> {etiqueta}
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
      <p className="flex items-center gap-1.5 text-sm font-semibold text-brand-800 dark:text-brand-200">
        {parentId && <CornerDownRight className="h-4 w-4" />} {etiqueta}
      </p>
      <input
        autoFocus
        value={titulo}
        onChange={e => setTitulo(e.target.value)}
        placeholder="Qué hay que hacer. Ej: Arte del header desktop"
        aria-label="Qué hay que hacer"
        maxLength={500}
        className="campo"
      />
      {conPiezas && <ElegirPiezas valor={piezas} onCambiar={setPiezas} tipos={tiposDelMundo(tipos, accion?.mundo)} tableros={tableros} />}
      <CampoDetalle
        id={`detalle-nueva-${parentId ?? accionId}`}
        valor={descripcion}
        onCambiar={setDescripcion}
        onDictado={alDictar}
      />
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="etiqueta-campo">{conPiezas ? 'Responsable de Tienda Inglesa' : 'Para quién'}</span>
          {/* Solo gente de Tienda (19/11/2026): elegir una cuenta de una
              agencia («Fer (Diseñadores)») convertía la tarea en una pieza
              de la agencia. A la agencia se le pide con una pieza. */}
          <select value={asignadoA} onChange={e => setAsignadoA(e.target.value)} className="campo">
            <option value="">Sin asignar por ahora</option>
            {delEquipo(personas).map(p => <option key={p.id} value={p.id}>{p.nombre}</option>)}
          </select>
          {personasEstado === 'error' && (
            <span className="mt-1 block text-xs text-amber-700 dark:text-amber-300">
              No se pudo traer la lista de personas. Se vuelve a intentar sola en unos segundos.
            </span>
          )}
        </label>
        <label className="block">
          <span className="etiqueta-campo">Vence el (opcional)</span>
          <input type="date" min="2000-01-01" max="2100-12-31" value={vence} onChange={e => setVence(e.target.value)} className="campo" />
        </label>
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2">
        {linkMalo && <p className="mr-auto text-xs text-amber-700 dark:text-amber-300">{linkMalo}</p>}
        <button type="button" onClick={cerrar} className="min-h-[44px] rounded-xl px-4 text-sm font-semibold text-slate-600 transition hover:bg-slate-200/70 dark:text-slate-300 dark:hover:bg-slate-800 sm:min-h-[40px]">
          Cancelar
        </button>
        <button
          type="submit"
          disabled={!valida}
          className="min-h-[44px] rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.98] disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:shadow-none dark:disabled:bg-slate-700 dark:disabled:text-slate-400 sm:min-h-[40px]"
        >
          {conPiezas && piezas.length > 0 ? `Crear tarea con ${piezas.length} ${piezas.length === 1 ? 'pieza' : 'piezas'}` : 'Crear tarea'}
        </button>
      </div>
    </form>
  )
}

/** Una pieza elegida al crear la tarea: el tipo, a qué tablero va, lo tildado
 *  y los datos de más. */
type PiezaElegida = { clave: string; tablero: string | null; opciones: string[]; detalles: Record<string, string> }

/** Lo que frena crear la tarea por una pieza: hoy, un link mal escrito. */
function faltaEnPieza(p: PiezaElegida, tipos: TipoDeTarea[] | null): string | null {
  const tipo = tipos?.find(t => t.clave === p.clave)
  if (!tipo) return null
  if (!p.tablero) return `Elegí a qué tablero va ${tipo.nombre}`
  const malo = camposVisibles(tipo, p.opciones).find(c => c.tipo === 'link' && p.detalles[c.clave]?.trim() && !linkValido(p.detalles[c.clave]))
  return malo ? `${tipo.nombre} · ${malo.nombre}: tiene que empezar con https://` : null
}

/**
 * Las piezas de la tarea, elegidas antes de crearla (17/11/2026): Banners,
 * Redes, Push… Tocar un tipo lo suma y abre su modal con todas las opciones
 * (el mismo de "Agregar pieza"); tocarlo de nuevo lo vuelve a abrir.
 */
function ElegirPiezas({ valor, onCambiar, tipos, tableros }: {
  valor: PiezaElegida[]
  onCambiar: (v: PiezaElegida[]) => void
  tipos: TipoDeTarea[] | null
  tableros: Tablero[] | null
}) {
  const [editando, setEditando] = useState<string | null>(null)
  const actual = valor.find(p => p.clave === editando) ?? null
  const tipoActual = tipos?.find(t => t.clave === editando) ?? null

  function tocar(t: TipoDeTarea) {
    if (!valor.some(p => p.clave === t.clave)) onCambiar([...valor, { clave: t.clave, tablero: null, opciones: [], detalles: {} }])
    // Siempre abre: ahí se elige a qué tablero va, y lo que se tilda.
    setEditando(t.clave)
  }
  function cambiar(clave: string, cambio: Partial<PiezaElegida>) {
    onCambiar(valor.map(p => (p.clave === clave ? { ...p, ...cambio } : p)))
  }

  return (
    // min-w-0: un <fieldset> no se achica por debajo de su contenido, y los
    // tipos (y el resumen de cada pieza) se salían por el costado de la ficha.
    <fieldset className="min-w-0">
      {/* Opcionales (18/11/2026, idea de Valentina): una tarea puede ser solo
          su nombre y su detalle, sin ninguna pieza, y sumar piezas después. */}
      <legend className="etiqueta-campo">¿Lleva piezas? <span className="font-normal text-slate-500 dark:text-slate-400">(opcional)</span></legend>
      {valor.length === 0 && (
        <p className="-mt-0.5 mb-1.5 text-xs text-slate-500 dark:text-slate-400">
          Podés crearla sin piezas, solo con el nombre y el detalle, y agregarle piezas después.
        </p>
      )}
      {!tipos ? (
        <div className="skeleton h-10 rounded-xl" />
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {tipos.map(t => {
            const elegida = valor.some(p => p.clave === t.clave)
            return (
              <button
                key={t.clave}
                type="button"
                aria-pressed={elegida}
                onClick={() => tocar(t)}
                className={`flex min-h-[40px] items-center gap-1 rounded-xl border px-3 text-sm font-semibold transition active:scale-95 ${
                  elegida
                    ? 'border-brand-600 bg-brand-600 text-white shadow-sm'
                    : 'border-slate-300 bg-white text-slate-700 hover:border-brand-400 hover:text-brand-700 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-brand-500/60'
                }`}
              >
                {elegida && <Check className="h-3.5 w-3.5" strokeWidth={3} aria-hidden />} {t.nombre}
              </button>
            )
          })}
        </div>
      )}

      {valor.length > 0 && tipos && (
        <ul className="mt-2 space-y-1.5" aria-label="Piezas elegidas">
          {valor.map(p => {
            const t = tipos.find(x => x.clave === p.clave)
            if (!t) return null
            const datos = camposVisibles(t, p.opciones).filter(c => p.detalles[c.clave]?.trim())
              .map(c => `${c.nombre}: ${valorParaLeer(c, p.detalles[c.clave])}`)
            const resumen = [p.tablero ? `→ ${p.tablero}` : '', ...p.opciones, ...datos].filter(Boolean).join(' · ')
            return (
              <li key={p.clave} className="flex items-center gap-2 rounded-xl border border-brand-200 bg-white px-3 py-2 dark:border-brand-500/30 dark:bg-slate-900">
                <span className="min-w-0 flex-1 text-sm">
                  <span className="font-semibold text-slate-900 dark:text-slate-100">{t.nombre}</span>
                  <span className="block truncate text-xs text-slate-600 dark:text-slate-400">
                    {p.tablero ? resumen : <span className="font-semibold text-amber-700 dark:text-amber-300">Falta elegir a qué tablero va</span>}
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
          tableros={tableros}
          tablero={actual.tablero}
          onTablero={nombre => cambiar(actual.clave, { tablero: nombre })}
          onCerrar={() => setEditando(null)}
        />
      )}
    </fieldset>
  )
}

/**
 * En la tarea, si lleva entregas: en qué fase va y el próximo paso, con su
 * botón. Es la puerta a la vista de entregas (encima de la ficha).
 */
function EntregasDeLaTarea({ tarea, personas, usuarioId }: {
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
  return (
    <div className={`mt-3 rounded-xl border p-2.5 ${
      meToca ? 'border-brand-200 bg-brand-50/70 dark:border-brand-500/30 dark:bg-brand-500/10' : 'border-slate-300 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/40'
    }`}>
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-medium text-slate-600 dark:text-slate-300">
        <Layers className="h-3.5 w-3.5 text-brand-600 dark:text-brand-300" aria-hidden />
        <FasesCompactas resumen={r} />
        {faseActualTexto(r)}
        {hace && <span className="font-semibold text-slate-700 dark:text-slate-200">· La hace {hace.nombre}{hace.tipo === 'fuera' ? ' (de afuera)' : ''}</span>}
      </p>
      <div className="mt-1.5 flex flex-wrap items-center gap-2">
        <p className={`min-w-0 flex-1 text-sm font-semibold ${meToca ? 'text-brand-800 dark:text-brand-100' : 'text-slate-700 dark:text-slate-200'}`}>
          {paso.texto}
        </p>
        {/* Siempre abre la tarjeta mirando (Ivan, 19/11/2026: "vos lo que
            tendrías que abrirme es la tarjeta"); entregar o revisar, desde
            el botón que está arriba de la ficha. */}
        <button
          type="button"
          onClick={() => abrir(tarea.id, 'ver')}
          className={`min-h-[40px] shrink-0 rounded-xl px-3.5 text-sm font-bold transition active:scale-[.98] ${
            meToca ? 'bg-brand-600 text-white shadow-sm hover:bg-brand-700' : 'bg-white text-slate-700 ring-1 ring-slate-300 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-200 dark:ring-slate-700 dark:hover:bg-slate-800'
          }`}
        >
          Abrir la tarjeta
        </button>
      </div>
    </div>
  )
}


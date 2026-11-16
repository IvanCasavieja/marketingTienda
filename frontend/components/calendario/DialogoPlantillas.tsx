'use client'

import { useEffect, useRef, useState } from 'react'
import {
  ArrowLeft, CalendarClock, CornerDownRight, LayoutTemplate, Pencil, Plus, Sparkles, Trash2, UserRound, X,
} from 'lucide-react'
import { esSinCategoria, mismaCategoria } from '@/lib/calendario/categorias'
import { nuevoId } from '@/lib/calendario/derivar'
import { fechaCorta } from '@/lib/calendario/fechas'
import {
  DIAS_DE_ANCLA, EJEMPLO_DE_PLANTILLA, TAREAS_POR_PLANTILLA, enOrden, plantillasParaElegir, problemaDePlantilla,
  textoDeAncla, venceAnclado,
} from '@/lib/calendario/plantillas'
import { usePermisosCalendario } from '@/lib/calendario/permisos'
import { useCalendario, useCategoriasDelMundo } from '@/lib/calendario/store'
import { nombreConEmpresa, type AnclaTarea, type BarraGuardada, type Persona, type Plantilla, type TareaDePlantilla } from '@/lib/calendario/tipos'
import { mundoDe } from '@/lib/mundos'
import { Cocarda } from './Cocarda'
import { useDialogo } from './useDialogo'
import { CLASE_MANIJA, useDeslizarParaCerrar } from './useDeslizarParaCerrar'

/**
 * Las plantillas de tareas del mundo que se mira: elegir una para la acción
 * abierta, y armarlas, cambiarlas o borrarlas (pedido del 15/11/2026).
 *
 * Una plantilla son las tareas que lleva casi siempre un tipo de acción, cada
 * una con su vencimiento relativo: "30 días antes del inicio", "1 día después
 * del fin". Al usarla en una acción se crean con la fecha ya calculada, y si
 * la acción se mueve, se mueven con ella.
 *
 * Lo abre la ficha de una acción, y solo para quien gestiona tareas
 * (`calendario.tareas`): es lo mismo que exige el servidor.
 */

type Borrador = { id: string; nombre: string; categoria: string | null; tareas: TareaDePlantilla[]; nueva: boolean }

const tareaVacia = (parentId: string | null = null): TareaDePlantilla => ({
  id: nuevoId('tp'), parentId, titulo: '', descripcion: null, asignadoA: null, ancla: 'inicio', dias: parentId ? 0 : -7,
})

/** Un botón principal (relleno) o secundario, con el alto de siempre. */
const BOTON = 'flex min-h-[44px] items-center justify-center gap-1.5 rounded-xl px-4 text-sm font-semibold transition active:scale-[.98] sm:min-h-[40px]'
const PRINCIPAL = `${BOTON} bg-brand-600 text-white shadow-sm hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:shadow-none dark:disabled:bg-slate-700 dark:disabled:text-slate-400`
const SECUNDARIO = `${BOTON} text-slate-600 hover:bg-slate-200/70 dark:text-slate-300 dark:hover:bg-slate-700`

export function DialogoPlantillas() {
  const dialogo = useCalendario(s => s.dialogoPlantillas)
  const cerrar = useCalendario(s => s.cerrarPlantillas)
  const barras = useCalendario(s => s.barras)
  const mundo = useCalendario(s => s.mundo)
  const { gestionaTareas } = usePermisosCalendario()
  const abierto = Boolean(dialogo) && gestionaTareas
  const accion = dialogo?.barraId ? barras[dialogo.barraId] ?? null : null

  // null = la lista; un borrador = el editor de esa plantilla. Atado a esta
  // vez que se abrió el diálogo: al abrirlo de nuevo arranca en la lista.
  const [edicion, setEdicion] = useState<{ de: object; borrador: Borrador } | null>(null)
  const borrador = dialogo && edicion?.de === dialogo ? edicion.borrador : null
  const setBorrador = (b: Borrador | null) => setEdicion(b && dialogo ? { de: dialogo, borrador: b } : null)

  // Escape vuelve del editor a la lista (sin guardar, como Cancelar), y desde
  // la lista cierra. Va en la captura y corta ahí: la ficha de abajo se queda.
  useEffect(() => {
    if (!abierto) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.stopPropagation()
      if (borrador) setEdicion(null)
      else cerrar()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [abierto, borrador, cerrar])

  const cajaRef = useRef<HTMLDivElement>(null)
  useDialogo(abierto, cajaRef)
  // Mientras se edita una plantilla, ni deslizar la hoja ni tocar afuera la
  // cierran: se perdería lo escrito, y una plantilla son varias tareas.
  useDeslizarParaCerrar(cajaRef, abierto && !borrador, cerrar)

  if (!abierto) return null

  return (
    // z-[60]: por encima de la ficha (z-50), desde donde se abre.
    <div className="fixed inset-0 z-[60] flex items-end justify-center sm:items-center sm:p-4">
      <div className="velo animate-fade-in" onClick={() => { if (!borrador) cerrar() }} aria-hidden />
      <div
        ref={cajaRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="plantillas-titulo"
        tabIndex={-1}
        className="relative flex max-h-[92dvh] w-full max-w-2xl animate-sheet-up flex-col overflow-hidden rounded-t-3xl bg-white shadow-panel outline-none dark:bg-slate-900 dark:ring-1 dark:ring-slate-800 sm:animate-scale-in sm:rounded-2xl"
      >
        <div aria-hidden className={CLASE_MANIJA} />
        {borrador ? (
          <EditorDePlantilla
            key={borrador.id}
            inicial={borrador}
            accion={accion}
            onVolver={() => setBorrador(null)}
          />
        ) : (
          <ListaDePlantillas
            accion={accion}
            nombreMundo={mundoDe(mundo)?.nombre ?? 'este mundo'}
            onCerrar={cerrar}
            onEditar={p => setBorrador({ ...p, tareas: p.tareas.map(t => ({ ...t })), nueva: false })}
            onNueva={() => setBorrador({
              id: nuevoId('pl'), nombre: '', nueva: true, tareas: [],
              // Desde una acción con categoría, la plantilla nueva arranca siendo de esa.
              categoria: accion && !esSinCategoria(accion.banda) && accion.seccion === 'comercial' ? accion.banda : null,
            })}
          />
        )}
      </div>
    </div>
  )
}

/** El título del diálogo, con el botón de cerrar o el de volver. */
function Encabezado({ titulo, bajada, onCerrar, onVolver }: {
  titulo: string
  bajada: string
  onCerrar?: () => void
  onVolver?: () => void
}) {
  return (
    <header className="flex shrink-0 items-start gap-2 border-b border-slate-300 px-5 pb-3.5 pt-4 dark:border-slate-700">
      {onVolver && (
        <button
          type="button"
          onClick={onVolver}
          aria-label="Volver a las plantillas sin guardar"
          title="Volver (Esc)"
          className="-ml-2 -mt-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 active:scale-95 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100 sm:h-10 sm:w-10"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
      )}
      <div className="min-w-0 flex-1">
        <h3 id="plantillas-titulo" className="text-lg font-bold text-slate-900 dark:text-slate-100">{titulo}</h3>
        <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">{bajada}</p>
      </div>
      {onCerrar && (
        <button
          type="button"
          onClick={onCerrar}
          aria-label="Cerrar"
          title="Cerrar (Esc)"
          className="-mr-2 -mt-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 active:scale-95 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200 sm:h-10 sm:w-10"
        >
          <X className="h-5 w-5" />
        </button>
      )}
    </header>
  )
}

// ---------------------------------------------------------------------------
// La lista
// ---------------------------------------------------------------------------

function ListaDePlantillas({ accion, nombreMundo, onCerrar, onEditar, onNueva }: {
  accion: BarraGuardada | null
  nombreMundo: string
  onCerrar: () => void
  onEditar: (p: Plantilla) => void
  onNueva: () => void
}) {
  const plantillas = useCalendario(s => s.plantillas)
  const lista = plantillasParaElegir(plantillas, accion?.banda ?? null)

  return (
    <>
      <Encabezado
        titulo="Plantillas de tareas"
        bajada={accion ? `Para «${accion.nombre}» · las de ${nombreMundo}` : `Las de ${nombreMundo}`}
        onCerrar={onCerrar}
      />

      <div className="flex-1 space-y-3 overflow-y-auto overscroll-contain px-5 py-5">
        {lista.length === 0 ? (
          <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-slate-300 px-5 py-8 text-center dark:border-slate-700">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-brand-50 text-brand-600 dark:bg-brand-500/15 dark:text-brand-300">
              <LayoutTemplate className="h-5 w-5" />
            </span>
            <p className="max-w-sm text-sm text-slate-600 dark:text-slate-400">
              Todavía no hay plantillas en {nombreMundo}. Una plantilla guarda las tareas que lleva siempre un tipo de
              acción, con cuántos días antes o después vence cada una, y las crea solas en cada acción.
            </p>
          </div>
        ) : (
          lista.map(p => <TarjetaDePlantilla key={p.id} plantilla={p} accion={accion} onEditar={() => onEditar(p)} />)
        )}
      </div>

      <footer className="flex shrink-0 items-center justify-between gap-2 border-t border-slate-300 bg-slate-50 px-5 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] dark:border-slate-700 dark:bg-slate-800/40">
        <button type="button" onClick={onNueva} className={`${BOTON} border border-slate-300 bg-white text-slate-800 hover:border-brand-400 hover:text-brand-700 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:hover:border-brand-500/60 dark:hover:text-brand-200`}>
          <Plus className="h-4 w-4" /> Nueva plantilla
        </button>
        <button type="button" onClick={onCerrar} className={SECUNDARIO}>Cerrar</button>
      </footer>
    </>
  )
}

function TarjetaDePlantilla({ plantilla, accion, onEditar }: {
  plantilla: Plantilla
  accion: BarraGuardada | null
  onEditar: () => void
}) {
  const aplicar = useCalendario(s => s.aplicarPlantilla)
  const borrar = useCalendario(s => s.borrarPlantilla)
  const cerrar = useCalendario(s => s.cerrarPlantillas)
  const [confirmando, setConfirmando] = useState(false)

  const tareas = enOrden(plantilla.tareas)
  const aMostrar = tareas.length > 6 ? tareas.slice(0, 5) : tareas
  const deSuCategoria = !!accion && mismaCategoria(plantilla.categoria, accion.banda)
  const yaUsada = !!accion && (accion.tareas ?? []).some(t => t.plantillaId === plantilla.id)

  return (
    <article className={`rounded-2xl border p-4 transition-colors ${
      deSuCategoria
        ? 'border-brand-300 bg-brand-50/50 dark:border-brand-500/40 dark:bg-brand-500/[.06]'
        : 'border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-900'
    }`}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <h4 className="min-w-0 break-words text-base font-bold text-slate-900 dark:text-slate-100">{plantilla.nombre}</h4>
        {plantilla.categoria
          ? <Cocarda banda={plantilla.categoria} compacta />
          : <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">Cualquier categoría</span>}
        {deSuCategoria && !yaUsada && (
          <span className="rounded-full bg-brand-600 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-white">Sugerida</span>
        )}
      </div>

      <ul className="mt-2.5 space-y-1">
        {aMostrar.map(t => (
          <li key={t.id} className={`flex items-baseline gap-2 text-sm ${t.parentId ? 'pl-5' : ''}`}>
            {t.parentId && <CornerDownRight className="h-3.5 w-3.5 shrink-0 self-center text-slate-500" aria-hidden />}
            <span className="min-w-0 flex-1 truncate text-slate-700 dark:text-slate-300">{t.titulo}</span>
            <span className="shrink-0 text-xs tabular-nums text-slate-500 dark:text-slate-400">
              {accion && t.ancla
                ? fechaCorta(venceAnclado(t.ancla, t.dias, accion.desde, accion.hasta))
                : textoDeAncla(t.ancla, t.dias)}
            </span>
          </li>
        ))}
        {tareas.length > aMostrar.length && (
          <li className="text-xs text-slate-500 dark:text-slate-400">y {tareas.length - aMostrar.length} tareas más</li>
        )}
      </ul>

      {yaUsada && (
        <p className="mt-2.5 text-xs text-slate-500 dark:text-slate-400">
          Ya la usaste en esta acción: usarla de nuevo crea sus tareas otra vez.
        </p>
      )}

      {confirmando ? (
        <div role="alertdialog" aria-label="Confirmar el borrado" className="mt-3 animate-fade-in space-y-2.5 rounded-xl border border-rose-200 bg-rose-50 p-3 dark:border-rose-500/30 dark:bg-rose-500/10">
          <p className="text-sm text-rose-900 dark:text-rose-100">
            ¿Borrar la plantilla <strong>{plantilla.nombre}</strong>? Las tareas que ya creó en las acciones se quedan.
          </p>
          <div className="flex justify-end gap-2">
            <button type="button" autoFocus onClick={() => setConfirmando(false)} className={SECUNDARIO}>No, dejarla</button>
            <button
              type="button"
              onClick={() => { setConfirmando(false); borrar(plantilla.id) }}
              className={`${BOTON} bg-rose-600 text-white shadow-sm hover:bg-rose-700`}
            >
              <Trash2 className="h-4 w-4" /> Sí, borrar
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {accion && (
            <button
              type="button"
              onClick={() => { aplicar(accion.id, plantilla.id); cerrar() }}
              className={`${PRINCIPAL} basis-full sm:basis-auto`}
            >
              <Sparkles className="h-4 w-4" /> {yaUsada ? 'Usar de nuevo' : 'Usar en esta acción'}
            </button>
          )}
          <button type="button" onClick={onEditar} className={`${SECUNDARIO} border border-slate-300 dark:border-slate-700`}>
            <Pencil className="h-4 w-4" /> Editar
          </button>
          <button
            type="button"
            onClick={() => setConfirmando(true)}
            aria-label={`Borrar la plantilla ${plantilla.nombre}`}
            title="Borrar la plantilla"
            className="ml-auto flex h-11 w-11 items-center justify-center rounded-xl text-slate-500 transition hover:bg-rose-50 hover:text-rose-600 active:scale-95 dark:text-slate-400 dark:hover:bg-rose-500/10 dark:hover:text-rose-300 sm:h-10 sm:w-10"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      )}
    </article>
  )
}

// ---------------------------------------------------------------------------
// El editor
// ---------------------------------------------------------------------------

function EditorDePlantilla({ inicial, accion, onVolver }: {
  inicial: Borrador
  accion: BarraGuardada | null
  onVolver: () => void
}) {
  const guardar = useCalendario(s => s.guardarPlantilla)
  const personas = useCalendario(s => s.personas)
  const personasEstado = useCalendario(s => s.personasEstado)
  const delMundo = useCategoriasDelMundo()
  const [nombre, setNombre] = useState(inicial.nombre)
  const [categoria, setCategoria] = useState<string | null>(inicial.categoria)
  const [tareas, setTareas] = useState<TareaDePlantilla[]>(inicial.tareas)
  const [intento, setIntento] = useState(false)

  const categorias = delMundo.filter(c => !esSinCategoria(c))
  if (categoria && !categorias.includes(categoria)) categorias.push(categoria)
  const problema = problemaDePlantilla({ nombre, tareas })
  const ordenadas = enOrden(tareas)

  function cambiar(id: string, cambios: Partial<TareaDePlantilla>) {
    setTareas(ts => ts.map(t => (t.id === id ? { ...t, ...cambios } : t)))
  }
  function quitar(id: string) {
    // Con sus subtareas: una subtarea sin su tarea no tiene dónde ir.
    setTareas(ts => ts.filter(t => t.id !== id && t.parentId !== id))
  }
  function agregar(parentId: string | null = null) {
    const nueva = tareaVacia(parentId)
    setTareas(ts => [...ts, nueva])
    // El foco va al título de la nueva, para escribir derecho.
    requestAnimationFrame(() => document.getElementById(`tp-titulo-${nueva.id}`)?.focus())
  }
  function cargarEjemplo() {
    setTareas(EJEMPLO_DE_PLANTILLA.map(t => ({ ...t, id: nuevoId('tp') })))
    if (!nombre.trim()) setNombre('Promo con cenefas en los locales')
  }

  function enviar(e: React.FormEvent) {
    e.preventDefault()
    setIntento(true)
    if (problema) return
    guardar({
      id: inicial.id, nombre: nombre.trim(), categoria,
      // En el orden en que se ven: cada tarea seguida de sus subtareas.
      tareas: ordenadas.map(t => ({ ...t, titulo: t.titulo.trim(), descripcion: t.descripcion?.trim() || null })),
    })
    onVolver()
  }

  return (
    <form onSubmit={enviar} className="flex min-h-0 flex-1 flex-col" noValidate>
      <Encabezado
        titulo={inicial.nueva ? 'Nueva plantilla' : 'Editar plantilla'}
        bajada={accion ? `Las fechas de ejemplo son las de «${accion.nombre}»` : 'Cada tarea vence contando desde el inicio o el fin de la acción'}
        onVolver={onVolver}
      />

      <div className="flex-1 space-y-5 overflow-y-auto overscroll-contain px-5 py-5">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="etiqueta-campo">Nombre</span>
            <input
              autoFocus
              value={nombre}
              onChange={e => setNombre(e.target.value)}
              maxLength={200}
              placeholder="Ej: Mega evento"
              aria-invalid={(intento && !nombre.trim()) || undefined}
              className={`campo ${intento && !nombre.trim() ? '!border-rose-400' : ''}`}
            />
          </label>
          <label className="block">
            <span className="etiqueta-campo">Para qué categoría</span>
            <select value={categoria ?? ''} onChange={e => setCategoria(e.target.value || null)} className="campo">
              <option value="">Cualquier categoría</option>
              {categorias.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
        </div>
        <p className="-mt-2 text-[13px] leading-relaxed text-slate-500 dark:text-slate-400">
          Con una categoría, la ficha de cada acción de esa categoría la sugiere. Si la acción se mueve de fecha, sus
          tareas se mueven con ella; la que alguien cambie a mano queda donde la pusieron.
        </p>

        {tareas.length === 0 ? (
          <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-slate-300 px-5 py-7 text-center dark:border-slate-700">
            <p className="max-w-sm text-sm text-slate-600 dark:text-slate-400">
              ¿Arrancás con un ejemplo? Es una promo con cenefas, del brief a la agencia hasta el retiro de los carteles.
              Después lo cambiás como quieras.
            </p>
            <div className="flex flex-col gap-2 sm:flex-row">
              <button type="button" onClick={cargarEjemplo} className={PRINCIPAL}>
                <Sparkles className="h-4 w-4" /> Empezar con un ejemplo
              </button>
              <button type="button" onClick={() => agregar()} className={`${SECUNDARIO} border border-slate-300 dark:border-slate-700`}>
                <Plus className="h-4 w-4" /> Empezar de cero
              </button>
            </div>
          </div>
        ) : (
          <div>
            <p className="etiqueta-campo">Tareas · {tareas.length}</p>
            <ul className="space-y-2">
              {ordenadas.map(t => (
                <FilaDeTarea
                  key={t.id}
                  tarea={t}
                  accion={accion}
                  personas={personas}
                  personasCargadas={personasEstado === 'ok'}
                  tieneSubtareas={tareas.some(x => x.parentId === t.id)}
                  onCambiar={c => cambiar(t.id, c)}
                  onQuitar={() => quitar(t.id)}
                  onSubtarea={() => agregar(t.id)}
                  intento={intento}
                />
              ))}
            </ul>
            {tareas.length < TAREAS_POR_PLANTILLA && (
              <button
                type="button"
                onClick={() => agregar()}
                className="mt-3 flex min-h-[48px] w-full items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-slate-300 px-4 text-sm font-semibold text-slate-600 transition hover:border-brand-400 hover:bg-brand-50 hover:text-brand-700 active:scale-[.99] dark:border-slate-700 dark:text-slate-300 dark:hover:border-brand-500/60 dark:hover:bg-brand-500/10 dark:hover:text-brand-200"
              >
                <Plus className="h-4 w-4" /> Agregar tarea
              </button>
            )}
          </div>
        )}
      </div>

      <footer className="shrink-0 border-t border-slate-300 bg-slate-50 px-5 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] dark:border-slate-700 dark:bg-slate-800/40">
        {intento && problema && (
          <p role="alert" className="mb-2 text-sm font-medium text-rose-700 dark:text-rose-300">{problema}</p>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onVolver} className={SECUNDARIO}>Cancelar</button>
          <button type="submit" className={PRINCIPAL}>Guardar plantilla</button>
        </div>
      </footer>
    </form>
  )
}

/** Cómo se elige el vencimiento: desde dónde y para qué lado, o sin fecha.
 *  Textos cortos: en el teléfono el número, "días" y esto van en una línea. */
type Cuando = 'inicio-' | 'inicio+' | 'fin-' | 'fin+' | 'sin'
const CUANDO: { valor: Cuando; texto: string }[] = [
  { valor: 'inicio-', texto: 'antes del inicio' },
  { valor: 'inicio+', texto: 'después del inicio' },
  { valor: 'fin-', texto: 'antes del fin' },
  { valor: 'fin+', texto: 'después del fin' },
  { valor: 'sin', texto: 'Sin fecha' },
]

function FilaDeTarea({
  tarea, accion, personas, personasCargadas, tieneSubtareas, onCambiar, onQuitar, onSubtarea, intento,
}: {
  tarea: TareaDePlantilla
  accion: BarraGuardada | null
  personas: Persona[]
  personasCargadas: boolean
  tieneSubtareas: boolean
  onCambiar: (c: Partial<TareaDePlantilla>) => void
  onQuitar: () => void
  onSubtarea: () => void
  intento: boolean
}) {
  // Para qué lado se cuenta. Con 0 días no se ve en `dias` (0 no tiene
  // signo): se recuerda acá lo que eligió la persona.
  const [lado, setLado] = useState<'-' | '+'>(tarea.dias > 0 ? '+' : '-')
  const cuando: Cuando = tarea.ancla ? `${tarea.ancla}${lado}` as Cuando : 'sin'
  const n = Math.abs(tarea.dias)
  // El número mientras se escribe: vacío es "todavía no puse nada", no un 0.
  const [texto, setTexto] = useState<string | null>(null)
  const [conDetalle, setConDetalle] = useState(Boolean(tarea.descripcion))
  const asignado = personas.find(p => p.id === tarea.asignadoA)
  const sinTitulo = intento && !tarea.titulo.trim()

  function elegirCuando(v: Cuando) {
    if (v === 'sin') { onCambiar({ ancla: null, dias: 0 }); return }
    const ancla = v.slice(0, -1) as AnclaTarea
    const nuevoLado = v.slice(-1) as '-' | '+'
    setLado(nuevoLado)
    onCambiar({ ancla, dias: nuevoLado === '-' ? -n : n })
  }

  function escribirDias(v: string) {
    setTexto(v)
    const num = Number(v)
    if (v === '' || !Number.isInteger(num) || num < 0) return
    const tope = Math.min(num, DIAS_DE_ANCLA)
    onCambiar({ dias: lado === '-' ? -tope : tope })
  }

  const ejemplo = accion && tarea.ancla ? fechaCorta(venceAnclado(tarea.ancla, tarea.dias, accion.desde, accion.hasta)) : null

  return (
    <li className={tarea.parentId ? 'ml-4 border-l-2 border-slate-300 pl-3 dark:border-slate-700' : ''}>
      <div className="space-y-2.5 rounded-2xl border border-slate-300 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
        <div className="flex items-start gap-2">
          {tarea.parentId && <CornerDownRight className="mt-3 h-4 w-4 shrink-0 text-slate-500" aria-hidden />}
          <input
            id={`tp-titulo-${tarea.id}`}
            value={tarea.titulo}
            onChange={e => onCambiar({ titulo: e.target.value })}
            maxLength={500}
            placeholder={tarea.parentId ? 'Subtarea. Ej: Versión mobile' : 'Qué hay que hacer. Ej: Brief a la agencia'}
            aria-label={tarea.parentId ? 'Título de la subtarea' : 'Título de la tarea'}
            aria-invalid={sinTitulo || undefined}
            className={`campo min-w-0 flex-1 font-medium ${sinTitulo ? '!border-rose-400' : ''}`}
          />
          <button
            type="button"
            onClick={onQuitar}
            aria-label={`Quitar ${tarea.titulo || 'esta tarea'}`}
            title={tieneSubtareas ? 'Quitar la tarea con sus subtareas' : 'Quitar la tarea'}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-slate-500 transition hover:bg-rose-50 hover:text-rose-600 active:scale-95 dark:text-slate-400 dark:hover:bg-rose-500/10 dark:hover:text-rose-300 sm:h-10 sm:w-10"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>

        {/* "Vence [30] días [antes del inicio]": se lee como una frase. En el
            teléfono el ejemplo de la fecha baja a su propia línea. */}
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
          <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400">
            <CalendarClock className="h-4 w-4" aria-hidden /> <span className="sr-only sm:not-sr-only">Vence</span>
          </span>
          {tarea.ancla && (
            <>
              <input
                type="number"
                inputMode="numeric"
                min={0}
                max={DIAS_DE_ANCLA}
                value={texto ?? String(n)}
                onChange={e => escribirDias(e.target.value)}
                onBlur={() => setTexto(null)}
                aria-label="Cuántos días"
                className="campo !w-16 shrink-0 !px-2 text-center tabular-nums"
              />
              <span className="text-sm text-slate-600 dark:text-slate-300">{n === 1 ? 'día' : 'días'}</span>
            </>
          )}
          <select
            value={cuando}
            onChange={e => elegirCuando(e.target.value as Cuando)}
            aria-label="Desde cuándo se cuenta"
            className="campo min-w-0 flex-1 sm:!w-auto sm:flex-none"
          >
            {CUANDO.map(c => <option key={c.valor} value={c.valor}>{c.texto}</option>)}
          </select>
          {tarea.ancla && (n === 0 || ejemplo) && (
            <span className="basis-full text-xs text-slate-500 dark:text-slate-400 sm:basis-auto">
              {n === 0 && `(${textoDeAncla(tarea.ancla, 0)})`}{n === 0 && ejemplo && ' · '}{ejemplo && `en esta acción: ${ejemplo}`}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* En el teléfono el responsable va solo en su línea: al lado de los
              botones no se leía el nombre. */}
          <label className="relative flex min-w-0 basis-full items-center sm:basis-auto">
            <UserRound className="pointer-events-none absolute left-3 h-4 w-4 text-slate-500 dark:text-slate-400" aria-hidden />
            <select
              value={tarea.asignadoA ?? ''}
              onChange={e => onCambiar({ asignadoA: e.target.value ? Number(e.target.value) : null })}
              aria-label="Responsable"
              className="campo !pl-9 sm:!w-64"
            >
              <option value="">Sin asignar</option>
              {tarea.asignadoA != null && !asignado && (
                <option value={tarea.asignadoA}>{personasCargadas ? 'Alguien que ya no ve este calendario' : 'Asignada'}</option>
              )}
              {personas.map(p => <option key={p.id} value={p.id}>{nombreConEmpresa(p)}</option>)}
            </select>
          </label>
          <span className="flex items-center gap-1">
            {!conDetalle && (
              <button
                type="button"
                onClick={() => setConDetalle(true)}
                className="flex h-11 items-center gap-1 rounded-lg px-2 text-sm font-medium text-slate-500 transition hover:bg-slate-100 hover:text-brand-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-brand-200 sm:h-9"
              >
                <Plus className="h-4 w-4" /> Detalle
              </button>
            )}
            {!tarea.parentId && (
              <button
                type="button"
                onClick={onSubtarea}
                className="flex h-11 items-center gap-1 rounded-lg px-2 text-sm font-medium text-slate-500 transition hover:bg-slate-100 hover:text-brand-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-brand-200 sm:h-9"
              >
                <Plus className="h-4 w-4" /> Subtarea
              </button>
            )}
          </span>
        </div>

        {conDetalle && (
          <textarea
            value={tarea.descripcion ?? ''}
            onChange={e => onCambiar({ descripcion: e.target.value })}
            maxLength={5000}
            rows={2}
            placeholder="Detalle (opcional)"
            aria-label="Detalle de la tarea"
            className="campo !h-auto py-2"
          />
        )}
      </div>
    </li>
  )
}

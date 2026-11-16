'use client'

import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import {
  AlertTriangle, Bell, BellPlus, CalendarDays, Check, Clock, LayoutPanelTop, Pencil, Plus, Send, X,
} from 'lucide-react'
import { BloqueTareas } from './BloqueTareas'
import { BloqueFotos } from '@/components/colocacion/BloqueFotos'
import { useLocalesDelMundo } from '@/lib/colocacion/store'
import { Cocarda, SelectorDeCategoria } from './Cocarda'
import { useDialogo } from './useDialogo'
import { CampoFecha } from './CampoFecha'
import { CLASE_MANIJA, useDeslizarParaCerrar } from './useDeslizarParaCerrar'
import { categoriasParaElegir } from '@/lib/calendario/categorias'
import { textoSobre } from '@/lib/calendario/colores'
import { diasEntre, fechaCorta, hoyIso, rangoLargo, sumarDias } from '@/lib/calendario/fechas'
import { useCalendario, useCategoriasDelMundo, useHeaderDerivado } from '@/lib/calendario/store'
import { usePermisosCalendario } from '@/lib/calendario/permisos'
import {
  ANTICIPACIONES_DE_AVISO, CATALOGO_PIEZAS, ETIQUETA_ESTADO, esPiezaDeEnvio, esPiezaHeader, tituloDeCanal,
  type AreaPieza, type Aviso, type BarraGuardada, type EstadoPieza, type Persona, type Pieza,
} from '@/lib/calendario/tipos'

const ESTADOS: EstadoPieza[] = ['pendiente', 'en-proceso', 'aprobado', 'publicado']

const TONO_ESTADO: Record<EstadoPieza, string> = {
  pendiente: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  'en-proceso': 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-200',
  aprobado: 'bg-sky-100 text-sky-800 dark:bg-sky-500/15 dark:text-sky-200',
  publicado: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-200',
}

/** Un select chico con forma de pastilla: el estado de una pieza o de un envío. */
const SELECT_ESTADO = 'h-9 cursor-pointer appearance-none rounded-full border-0 px-3 text-xs font-semibold outline-none transition focus-visible:ring-2 focus-visible:ring-brand-500 disabled:cursor-not-allowed disabled:opacity-60 sm:h-8'

/**
 * El encabezado de la ficha lleva el color de la acción. En modo oscuro, ese
 * color (que casi siempre es un pastel del Excel) se mezcla con el fondo:
 * un bloque pastel entero encandilaba. La franja de arriba sí va pura.
 */
function estiloDeEncabezado(color: string | null): CSSProperties {
  const c = color ?? '#e2e8f0'
  return { '--accion': c, '--texto-accion': textoSobre(color) } as CSSProperties
}
const ENCABEZADO =
  'shrink-0 border-t-4 border-[color:var(--accion)] bg-[var(--accion)] text-[color:var(--texto-accion)] ' +
  'dark:bg-[color-mix(in_srgb,var(--accion)_20%,#0f172a)] dark:text-white'

/** "En curso", "Arranca en 3 días", "Terminó": dónde está la acción hoy. */
function momento(desde: string, hasta: string, esEnvio: boolean): { texto: string; tono: string } {
  const hoy = hoyIso()
  if (desde > hoy) {
    const faltan = diasEntre(hoy, desde)
    const verbo = esEnvio ? 'Sale' : 'Arranca'
    return {
      texto: faltan === 1 ? `${verbo} mañana` : `${verbo} en ${faltan} días`,
      tono: faltan <= 7 ? 'bg-amber-100 text-amber-900 dark:bg-amber-400/20 dark:text-amber-100' : 'bg-white/80 text-slate-800 dark:bg-white/10 dark:text-white',
    }
  }
  if (hasta < hoy) return { texto: esEnvio ? 'Ya salió' : 'Terminó', tono: 'bg-black/10 text-current dark:bg-white/10' }
  if (esEnvio) return { texto: 'Sale hoy', tono: 'bg-emerald-100 text-emerald-900 dark:bg-emerald-400/20 dark:text-emerald-100' }
  return {
    texto: hasta === hoy ? 'En curso · termina hoy' : 'En curso',
    tono: 'bg-emerald-100 text-emerald-900 dark:bg-emerald-400/20 dark:text-emerald-100',
  }
}

/** El botón de cerrar de la ficha, sobre el color de la acción. */
function BotonCerrar({ onCerrar, refBoton }: { onCerrar: () => void; refBoton?: React.Ref<HTMLButtonElement> }) {
  return (
    <button
      ref={refBoton}
      type="button"
      onClick={onCerrar}
      className="-mr-2 -mt-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-xl transition hover:bg-black/10 active:scale-95 dark:hover:bg-white/10 sm:h-10 sm:w-10"
      aria-label="Cerrar la ficha"
      title="Cerrar (Esc)"
    >
      <X className="h-5 w-5" />
    </button>
  )
}

/** El botón de editar, una pastilla clara sobre el color de la acción. */
function BotonEditar({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mt-3.5 flex min-h-[40px] items-center gap-2 rounded-xl bg-white/85 px-3.5 text-sm font-semibold text-slate-800 shadow-sm ring-1 ring-black/5 transition hover:bg-white active:scale-[.98] dark:bg-white/10 dark:text-white dark:ring-white/10 dark:hover:bg-white/15"
    >
      <Pencil className="h-4 w-4" /> {children}
    </button>
  )
}

type Pestana = 'tareas' | 'piezas' | 'avisos' | 'fotos'

export function PanelAccion() {
  const abierta = useCalendario(s => s.abierta)
  const cerrar = useCalendario(s => s.cerrarAccion)
  const abrirEditor = useCalendario(s => s.abrirEditor)
  const agregarPieza = useCalendario(s => s.agregarPieza)
  const quitarPieza = useCalendario(s => s.quitarPieza)
  const actualizarPieza = useCalendario(s => s.actualizarPieza)
  const personas = useCalendario(s => s.personas)
  const header = useHeaderDerivado()

  const accionViva = useCalendario(s => s.accionAbierta())

  // Se guarda la última acción para que el panel tenga qué pintar mientras sale
  const [ultima, setUltima] = useState<BarraGuardada | null>(null)
  useEffect(() => {
    if (accionViva) setUltima(accionViva)
  }, [accionViva])

  useEffect(() => {
    if (!abierta) return
    const onKey = (e: KeyboardEvent) => {
      // Con el editor abierto arriba, Escape cierra el editor y no la ficha.
      if (e.key === 'Escape' && !useCalendario.getState().edicion) cerrar()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [abierta, cerrar])

  const visible = Boolean(abierta && accionViva)
  const accion = visible ? accionViva : ultima
  const { editable, user, gestionaTareas } = usePermisosCalendario()

  const cajaRef = useRef<HTMLElement>(null)
  const cerrarRef = useRef<HTMLButtonElement>(null)
  useDialogo(visible, cajaRef, cerrarRef)
  useDeslizarParaCerrar(cajaRef, visible, cerrar)

  // Qué se mira de la ficha. Arranca en las tareas: es a lo que viene la
  // mayoría (a ver qué le toca), y las piezas y los avisos quedan a un toque.
  // Salvo que se haya pedido otra: el aviso de que mandaron todas las fotos
  // abre la ficha en las fotos.
  const [pestana, setPestana] = useState<Pestana>('tareas')
  useEffect(() => {
    setPestana(useCalendario.getState().pestanaPedida === 'fotos' ? 'fotos' : 'tareas')
  }, [abierta])

  // Las fotos de colocación: las pide y las revisa quien edita el calendario,
  // en las acciones de un mundo que tiene locales con usuario (Redexpres hoy;
  // Tienda Inglesa cuando den de alta los suyos). Si la acción ya tiene un
  // pedido, la pestaña está aunque después se hayan dado de baja los locales.
  const mundo = useCalendario(s => s.mundo)
  const localesDelMundo = useLocalesDelMundo(s => s.porMundo[mundo])
  const pedirLocales = useLocalesDelMundo(s => s.pedir)
  useEffect(() => { if (editable) pedirLocales(mundo) }, [editable, mundo, pedirLocales])
  const conFotos = editable && accion?.seccion === 'comercial' &&
    (Boolean(accion?.fotos) || (localesDelMundo?.length ?? 0) > 0)
  const pestanaVista: Pestana = pestana === 'fotos' && !conFotos ? 'tareas' : pestana

  const piezas = accion?.piezas ?? []
  const tareas = accion?.tareas ?? []
  const publicadas = piezas.filter(p => p.estado === 'publicado').length

  // ¿En qué posición del header quedó esta acción? ¿O no entró? Se mira el
  // header de todas las fechas, no el del mes: la acción puede cruzar de mes.
  const tramo = accion
    ? header.tramos.find(t => t.origen.tipo === 'accion' && t.origen.accionId === accion.id)
    : undefined
  const noEntro = accion ? header.sinLugar.find(s => s.accionId === accion.id) : undefined

  const pestanas: { id: Pestana; nombre: string; n: number }[] = [
    { id: 'tareas', nombre: 'Tareas', n: tareas.length },
    { id: 'piezas', nombre: 'Piezas', n: piezas.length },
    { id: 'avisos', nombre: 'Avisos', n: (accion?.avisos ?? []).length },
    // El número es a cuántos locales se les pidió la foto.
    ...(conFotos ? [{ id: 'fotos' as const, nombre: 'Fotos', n: accion?.fotos?.locales ?? 0 }] : []),
  ]

  /** Flechas izquierda y derecha para moverse entre pestañas, como en cualquier lista de pestañas. */
  function teclaEnPestanas(e: ReactKeyboardEvent<HTMLDivElement>) {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
    e.preventDefault()
    const i = pestanas.findIndex(p => p.id === pestanaVista)
    const siguiente = pestanas[(i + (e.key === 'ArrowRight' ? 1 : pestanas.length - 1)) % pestanas.length]
    setPestana(siguiente.id)
    e.currentTarget.querySelector<HTMLButtonElement>(`#pestana-${siguiente.id}`)?.focus()
  }

  const ahora = accion ? momento(accion.desde, accion.hasta, accion.seccion === 'envio') : null

  return (
    <>
      <div
        onClick={cerrar}
        aria-hidden
        className={`velo z-40 transition-opacity duration-300 ${
          visible ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
      />
      {/* En la notebook entra por la derecha; en el teléfono sube desde abajo
          y deja ver un poco de la página arriba, como una hoja. Cerrada queda
          invisible: el teclado no la recorre. */}
      <aside
        ref={cajaRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="ficha-titulo"
        tabIndex={-1}
        className={`fixed z-50 flex flex-col overflow-hidden bg-white shadow-panel outline-none dark:bg-slate-900
          inset-x-0 bottom-0 top-3 rounded-t-3xl
          sm:inset-x-auto sm:bottom-auto sm:right-0 sm:top-0 sm:h-full sm:w-full sm:max-w-[600px] sm:rounded-none sm:border-l sm:border-slate-200 sm:dark:border-slate-800 ${
          visible ? 'hoja-abierta translate-y-0 sm:translate-x-0' : 'hoja-cerrada translate-y-full sm:translate-x-full sm:translate-y-0'
        }`}
      >
        <div aria-hidden className={CLASE_MANIJA} />
        {accion && accion.seccion === 'envio' && (
          <FichaEnvio
            envio={accion}
            editable={editable}
            personas={personas}
            usuarioId={user?.id ?? null}
            gestionaTareas={gestionaTareas}
            onCerrar={cerrar}
            cerrarRef={cerrarRef}
          />
        )}
        {accion && accion.seccion !== 'envio' && (
          <>
            <header className={`${ENCABEZADO} px-5 pb-4 pt-4 sm:px-6`} style={estiloDeEncabezado(accion.color)}>
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <CategoriaDeLaFicha accion={accion} editable={editable} />
                    {ahora && (
                      <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${ahora.tono}`}>{ahora.texto}</span>
                    )}
                  </div>
                  <h2 id="ficha-titulo" className="mt-2.5 text-2xl font-bold leading-tight tracking-tight text-balance">{accion.nombre}</h2>
                  <p className="mt-1.5 flex items-center gap-1.5 text-sm opacity-80">
                    <CalendarDays className="h-4 w-4 shrink-0" aria-hidden />
                    <span>
                      {rangoLargo(accion.desde, accion.hasta).replace(/^./, c => c.toUpperCase())}
                      {' · '}{diasEntre(accion.desde, accion.hasta) + 1} días
                    </span>
                  </p>
                </div>
                <BotonCerrar onCerrar={cerrar} refBoton={cerrarRef} />
              </div>

              {editable && (
                <BotonEditar
                  onClick={() => abrirEditor({
                    seccion: 'comercial',
                    banda: accion.banda,
                    carril: accion.carril,
                    barra: accion,
                  })}
                >
                  Editar nombre, fechas y color
                </BotonEditar>
              )}
            </header>

            <div className="flex shrink-0 items-center gap-3 border-b border-slate-200 bg-slate-50 px-5 py-2.5 text-xs dark:border-slate-800 dark:bg-slate-800/40 sm:px-6">
              <span className="font-medium tabular-nums text-slate-700 dark:text-slate-300">
                {piezas.length === 0
                  ? 'Todavía no tiene piezas cargadas'
                  : `${publicadas} de ${piezas.length} piezas publicadas`}
              </span>
              {piezas.length > 0 && (
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                  <div
                    className="h-full rounded-full bg-emerald-500 transition-[width] duration-500 ease-suave"
                    style={{ width: `${(publicadas / piezas.length) * 100}%` }}
                  />
                </div>
              )}
            </div>

            {/* Estado del header: la pieza que toca el calendario de abajo */}
            {piezas.some(esPiezaHeader) && (noEntro || tramo) && (
              <div className={`shrink-0 border-b px-5 py-2.5 text-xs sm:px-6 ${
                noEntro
                  ? 'border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200'
                  : 'border-violet-200 bg-violet-50 text-violet-900 dark:border-violet-900/60 dark:bg-violet-950/40 dark:text-violet-200'
              }`}>
                {noEntro ? (
                  <p className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>
                      Pide header pero <strong>no entró</strong>: el header ya está completo
                      {noEntro.diasLlenos.length > 0 && ` los días ${noEntro.diasLlenos.map(fechaCorta).join(', ')}`}.
                      Hay que bajar algo, y eso lo decidís vos.
                    </span>
                  </p>
                ) : tramo ? (
                  <p className="flex items-center gap-2">
                    <LayoutPanelTop className="h-4 w-4 shrink-0" />
                    <span>Ocupa la <strong>posición {tramo.posicion}</strong> del header de la home.</span>
                  </p>
                ) : null}
              </div>
            )}

            <div
              className="flex shrink-0 gap-1 overflow-x-auto border-b border-slate-200 px-3 dark:border-slate-800 sm:px-4"
              role="tablist"
              aria-label="Qué ver de la acción"
              onKeyDown={teclaEnPestanas}
            >
              {pestanas.map(t => {
                const activa = pestanaVista === t.id
                return (
                  <button
                    key={t.id}
                    id={`pestana-${t.id}`}
                    type="button"
                    role="tab"
                    aria-selected={activa}
                    aria-controls="ficha-contenido"
                    tabIndex={activa ? 0 : -1}
                    onClick={() => setPestana(t.id)}
                    className={`relative -mb-px flex min-h-[48px] items-center gap-1.5 px-3 text-sm font-semibold transition after:absolute after:inset-x-2 after:bottom-0 after:h-0.5 after:rounded-full after:transition-colors ${
                      activa
                        ? 'text-brand-700 after:bg-brand-600 dark:text-brand-200 dark:after:bg-brand-400'
                        : 'text-slate-500 after:bg-transparent hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100'
                    }`}
                  >
                    {t.nombre}
                    <span className={`min-w-[20px] rounded-full px-1.5 text-center text-xs font-bold tabular-nums transition-colors ${
                      activa ? 'bg-brand-100 text-brand-700 dark:bg-brand-500/20 dark:text-brand-200' : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
                    }`}>{t.n}</span>
                  </button>
                )
              })}
            </div>

            <div
              id="ficha-contenido"
              role="tabpanel"
              aria-labelledby={`pestana-${pestanaVista}`}
              className="flex-1 overflow-y-auto overscroll-contain px-5 py-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] sm:px-6"
            >
              <div key={pestanaVista} className="animate-fade-in">
                {pestanaVista === 'fotos' && <BloqueFotos accion={accion} />}

                {pestanaVista === 'tareas' && (
                  <BloqueTareas
                    accion={accion}
                    personas={personas}
                    usuarioId={user?.id ?? null}
                    gestiona={gestionaTareas}
                    conTitulo={false}
                  />
                )}

                {pestanaVista === 'avisos' && (
                  <BloqueAvisos
                    accion={accion}
                    editable={editable}
                    personas={personas}
                    usuarioId={user?.id ?? null}
                  />
                )}

                {pestanaVista === 'piezas' && (<>
                  <div className="space-y-6">
                    {CATALOGO_PIEZAS.map(area => (
                      <BloqueArea
                        key={area.area}
                        area={area.area}
                        titulo={area.titulo}
                        formatos={area.formatos}
                        piezas={piezas.filter(p => p.area === area.area)}
                        editable={editable}
                        inicioAccion={accion.desde}
                        onAgregar={formato => agregarPieza(area.area, formato)}
                        onQuitar={quitarPieza}
                        onEstado={(id, estado) => actualizarPieza(id, { estado })}
                        onEnvio={(id, cambios) => actualizarPieza(id, cambios)}
                      />
                    ))}
                  </div>

                  <p className="mt-6 rounded-xl bg-slate-50 px-3.5 py-3 text-[13px] leading-relaxed text-slate-600 dark:bg-slate-800/40 dark:text-slate-400">
                    Agregar <strong>Web · Home → Header</strong> baja la acción sola al calendario de
                    headers, igual que hace Retail Media con sus tres posiciones.
                  </p>
                </>)}
              </div>
            </div>
          </>
        )}
      </aside>
    </>
  )
}

/** La categoría en el encabezado de la ficha. Quien edita la toca y la cambia;
 *  los demás la ven. Es el único lugar donde se elige. */
function CategoriaDeLaFicha({ accion, editable }: { accion: BarraGuardada; editable: boolean }) {
  const cambiarCategoria = useCalendario(s => s.cambiarCategoria)
  const delMundo = useCategoriasDelMundo()
  if (!editable) return <Cocarda banda={accion.banda} sobreColor />
  return (
    <SelectorDeCategoria
      banda={accion.banda}
      opciones={categoriasParaElegir(delMundo, accion.banda)}
      onCambiar={banda => cambiarCategoria(accion.id, banda)}
    />
  )
}

// ---------------------------------------------------------------------------
// La ficha de un envío suelto
// ---------------------------------------------------------------------------

/**
 * Un mailing, un WhatsApp o una push sin una acción detrás. Su ficha es más
 * corta que la de una acción: qué es, cuándo sale, en qué estado está y sus
 * avisos. No tiene áreas ni piezas: el envío ES la pieza.
 */
function FichaEnvio({
  envio, editable, personas, usuarioId, gestionaTareas, onCerrar, cerrarRef,
}: {
  envio: BarraGuardada
  editable: boolean
  personas: Persona[]
  usuarioId: number | null
  gestionaTareas: boolean
  onCerrar: () => void
  cerrarRef: React.Ref<HTMLButtonElement>
}) {
  const abrirEditor = useCalendario(s => s.abrirEditor)
  const cambiarEstado = useCalendario(s => s.cambiarEstadoEnvio)
  const estado: EstadoPieza = envio.estado ?? 'pendiente'
  const canal = tituloDeCanal(envio.banda)
  const ahora = momento(envio.desde, envio.desde, true)

  return (
    <>
      <header className={`${ENCABEZADO} px-5 pb-4 pt-4 sm:px-6`} style={estiloDeEncabezado(envio.color)}>
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="flex items-center gap-1.5 rounded-full bg-white/85 px-2.5 py-1 text-xs font-semibold text-slate-800 dark:bg-white/10 dark:text-white">
                <Send className="h-3.5 w-3.5" /> {canal} · envío suelto
              </span>
              <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${ahora.tono}`}>{ahora.texto}</span>
            </div>
            <h2 id="ficha-titulo" className="mt-2.5 text-2xl font-bold leading-tight tracking-tight text-balance">{envio.nombre}</h2>
            <p className="mt-1.5 flex items-center gap-1.5 text-sm opacity-80">
              <Clock className="h-4 w-4 shrink-0" aria-hidden />
              <span>
                {envio.formato ? `${envio.formato} · ` : ''}
                Sale {rangoLargo(envio.desde, envio.desde)}{envio.hora ? ` a las ${envio.hora}` : ', sin hora todavía'}
              </span>
            </p>
          </div>
          <BotonCerrar onCerrar={onCerrar} refBoton={cerrarRef} />
        </div>

        {editable && (
          <BotonEditar onClick={() => abrirEditor({ seccion: 'envio', banda: envio.banda, carril: 0, barra: envio })}>
            Editar nombre, fecha, hora y color
          </BotonEditar>
        )}
      </header>

      <div className="flex shrink-0 items-center gap-3 border-b border-slate-200 bg-slate-50 px-5 py-2.5 text-xs dark:border-slate-800 dark:bg-slate-800/40 sm:px-6">
        <span className="font-medium text-slate-700 dark:text-slate-300">Estado</span>
        <select
          value={estado}
          disabled={!editable}
          aria-label="Estado del envío"
          onChange={e => cambiarEstado(envio.id, e.target.value as EstadoPieza)}
          className={`${SELECT_ESTADO} ${TONO_ESTADO[estado]}`}
        >
          {ESTADOS.map(e => <option key={e} value={e}>{ETIQUETA_ESTADO[e]}</option>)}
        </select>
        {estado === 'publicado' && <Check className="h-4 w-4 animate-tilde text-emerald-600 dark:text-emerald-400" />}
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto overscroll-contain px-5 py-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] sm:px-6">
        <BloqueTareas accion={envio} personas={personas} usuarioId={usuarioId} gestiona={gestionaTareas} />
        <BloqueAvisos accion={envio} editable={editable} personas={personas} usuarioId={usuarioId} />
        <p className="rounded-xl bg-slate-50 px-3.5 py-3 text-[13px] leading-relaxed text-slate-600 dark:bg-slate-800/40 dark:text-slate-400">
          Es un envío que no sale de ninguna acción. Los que sí son parte de una acción se cargan en
          la ficha de esa acción, en Email, WhatsApp o Push, y aparecen solos en el cronograma.
        </p>
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// Avisos
// ---------------------------------------------------------------------------

/**
 * Los avisos de la acción. No hay ninguno por defecto (pedido de Ivan,
 * 28/09/2026): los configura a mano quien carga la acción, eligiendo cuántos
 * días antes y a quién, para que cuando llegue uno sea porque vale la pena.
 */
function BloqueAvisos({
  accion, editable, personas, usuarioId,
}: {
  accion: BarraGuardada
  editable: boolean
  personas: Persona[]
  usuarioId: number | null
}) {
  const agregarAviso = useCalendario(s => s.agregarAviso)
  const quitarAviso = useCalendario(s => s.quitarAviso)
  const personasEstado = useCalendario(s => s.personasEstado)
  const avisos = accion.avisos ?? []
  const hoy = hoyIso()
  const yaArranco = hoy > accion.desde
  // Una acción "arranca"; un envío suelto "sale".
  const esEnvio = accion.seccion === 'envio'

  const [dias, setDias] = useState<number>(10)
  const [elegidos, setElegidos] = useState<number[]>([])

  // Al abrir otra acción, arranca elegido quien la está mirando.
  useEffect(() => {
    setElegidos(usuarioId != null && personas.some(p => p.id === usuarioId) ? [usuarioId] : [])
  }, [accion.id, usuarioId, personas])

  const nombreDe = (id: number) => personas.find(p => p.id === id)?.nombre
    ?? (personasEstado === 'ok' ? 'alguien que ya no ve el calendario' : 'una persona')

  function estadoDe(a: Aviso): string {
    if (yaArranco) return esEnvio ? 'el envío ya salió' : 'la acción ya arrancó'
    const fecha = sumarDias(accion.desde, -a.diasAntes)
    return hoy >= fecha ? 'ya salió' : `sale el ${fechaCorta(fecha)}`
  }

  function alternar(id: number) {
    setElegidos(v => (v.includes(id) ? v.filter(x => x !== id) : [...v, id]))
  }

  return (
    <section>
      <div className="mb-1.5 flex items-center gap-2">
        <Bell className="h-[18px] w-[18px] text-brand-600 dark:text-brand-300" />
        <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">Avisos</h3>
        {avisos.length > 0 && <span className="text-sm tabular-nums text-slate-500 dark:text-slate-400">{avisos.length}</span>}
      </div>
      <p className="mb-3 text-[13px] leading-relaxed text-slate-600 dark:text-slate-400">
        Solo salen los avisos que se configuran acá. Le llegan a la campanita de cada persona elegida,
        los días antes de que {esEnvio ? 'salga el envío' : 'arranque la acción'} que se elijan.
      </p>

      {avisos.length === 0 ? (
        <p className="flex items-center gap-2.5 rounded-xl border border-dashed border-slate-300 px-4 py-3.5 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
          <Bell className="h-4 w-4 shrink-0 text-slate-400 dark:text-slate-500" />
          {esEnvio ? 'Este envío no tiene avisos.' : 'Esta acción no tiene avisos.'}
          {!editable || yaArranco ? null : ' Configurá el primero acá abajo.'}
        </p>
      ) : (
        <ul className="space-y-2">
          {avisos.map(a => (
            <li key={a.id} className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 dark:border-slate-700 dark:bg-slate-900">
              <span className="flex h-9 w-9 shrink-0 flex-col items-center justify-center rounded-lg bg-brand-50 leading-none text-brand-700 dark:bg-brand-500/15 dark:text-brand-200">
                <span className="text-sm font-bold tabular-nums">{a.diasAntes}</span>
                <span className="text-[9px] font-semibold uppercase">días</span>
              </span>
              <div className="min-w-0 flex-1 text-sm">
                <p>
                  <span className="font-semibold text-slate-800 dark:text-slate-100">{a.diasAntes} días antes</span>
                  <span className="text-slate-500 dark:text-slate-400"> · {estadoDe(a)}</span>
                </p>
                <p className="truncate text-xs text-slate-500 dark:text-slate-400">
                  A {a.destinatarios.map(nombreDe).join(', ')}
                </p>
              </div>
              {editable && (
                <button
                  type="button"
                  onClick={() => quitarAviso(a.id)}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-400 transition hover:bg-rose-50 hover:text-rose-600 active:scale-95 dark:text-slate-500 dark:hover:bg-rose-500/10 dark:hover:text-rose-300"
                  aria-label={`Quitar el aviso de ${a.diasAntes} días antes`}
                  title="Quitar este aviso"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {editable && !yaArranco && (
        <div className="mt-4 space-y-3.5 rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/40">
          <p className="flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
            <BellPlus className="h-4 w-4 text-brand-600 dark:text-brand-300" /> Nuevo aviso
          </p>
          <label className="flex flex-wrap items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
            Avisar
            <select
              value={dias}
              onChange={e => setDias(Number(e.target.value))}
              className="campo !w-auto font-semibold"
            >
              {ANTICIPACIONES_DE_AVISO.map(n => <option key={n} value={n}>{n} días antes</option>)}
            </select>
            <span className="text-xs text-slate-500 dark:text-slate-400">
              ({hoy >= sumarDias(accion.desde, -dias) ? 'sale ahora' : `el ${fechaCorta(sumarDias(accion.desde, -dias))}`})
            </span>
          </label>

          <div>
            <p className="etiqueta-campo">A quién</p>
            {personas.length === 0 && personasEstado === 'error' ? (
              <p className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
                No se pudo traer la lista de personas. Se vuelve a intentar sola en unos segundos.
              </p>
            ) : personas.length === 0 ? (
              <div className="space-y-2" aria-label="Cargando las personas…">
                {[0, 1, 2].map(i => <div key={i} className="skeleton h-9 rounded-lg" />)}
              </div>
            ) : (
              <div className="max-h-48 overflow-y-auto rounded-xl border border-slate-200 bg-white p-1 dark:border-slate-700 dark:bg-slate-900">
                {personas.map(p => {
                  const marcado = elegidos.includes(p.id)
                  return (
                    <label
                      key={p.id}
                      className={`flex min-h-[40px] cursor-pointer items-center gap-2.5 rounded-lg px-2.5 text-sm transition ${
                        marcado ? 'bg-brand-50 text-brand-900 dark:bg-brand-500/10 dark:text-brand-100' : 'text-slate-700 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={marcado}
                        onChange={() => alternar(p.id)}
                        className="h-4 w-4 rounded border-slate-300 accent-brand-600"
                      />
                      {p.nombre}{p.id === usuarioId ? <span className="text-slate-500 dark:text-slate-400">(vos)</span> : null}
                    </label>
                  )
                })}
              </div>
            )}
          </div>

          <button
            type="button"
            disabled={elegidos.length === 0}
            onClick={() => agregarAviso(dias, elegidos)}
            className="flex min-h-[44px] w-full items-center justify-center gap-1.5 rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.98] disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:shadow-none dark:disabled:bg-slate-700 dark:disabled:text-slate-400 sm:min-h-[40px] sm:w-auto"
          >
            <Plus className="h-4 w-4" /> Agregar aviso
          </button>
        </div>
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------

function BloqueArea({
  area, titulo, formatos, piezas, editable, inicioAccion,
  onAgregar, onQuitar, onEstado, onEnvio,
}: {
  area: AreaPieza
  titulo: string
  formatos: string[]
  piezas: Pieza[]
  editable: boolean
  /** Fecha en que arranca la acción: es lo que usa un envío sin fecha propia. */
  inicioAccion: string
  onAgregar: (formato: string) => void
  onQuitar: (id: string) => void
  onEstado: (id: string, estado: EstadoPieza) => void
  onEnvio: (id: string, cambios: Partial<Pieza>) => void
}) {
  const [agregando, setAgregando] = useState(false)
  const disponibles = formatos.filter(f => !piezas.some(p => p.formato === f))

  return (
    <section>
      <div className="mb-2 flex items-center gap-2">
        <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">{titulo}</h3>
        {piezas.length > 0 && <span className="text-sm tabular-nums text-slate-500 dark:text-slate-400">{piezas.length}</span>}
        <div className="h-px flex-1 bg-slate-200 dark:bg-slate-800" />
        {editable && disponibles.length > 0 && (
          <button
            type="button"
            onClick={() => setAgregando(v => !v)}
            aria-expanded={agregando}
            className={`flex min-h-[36px] items-center gap-1 rounded-lg px-2.5 text-sm font-semibold transition active:scale-95 ${
              agregando
                ? 'bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200'
                : 'text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100'
            }`}
          >
            <Plus className={`h-4 w-4 transition-transform duration-200 ${agregando ? 'rotate-45' : ''}`} /> {agregando ? 'Listo' : 'Agregar'}
          </button>
        )}
      </div>

      {agregando && (
        <div className="mb-2.5 flex animate-scale-in flex-wrap gap-1.5 rounded-xl bg-slate-50 p-2 dark:bg-slate-800/40">
          {disponibles.map(f => (
            <button
              key={f}
              type="button"
              onClick={() => { onAgregar(f); setAgregando(false) }}
              className={`min-h-[36px] rounded-lg border px-3 text-sm font-medium transition active:scale-95 ${
                area === 'web-home' && f === 'Header'
                  ? 'border-violet-300 bg-violet-50 text-violet-800 hover:bg-violet-100 dark:border-violet-700 dark:bg-violet-950/40 dark:text-violet-200 dark:hover:bg-violet-900/40'
                  : 'border-slate-300 bg-white text-slate-700 hover:border-brand-300 hover:text-brand-700 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-brand-500/50 dark:hover:text-brand-200'
              }`}
            >
              <Plus className="-ml-0.5 mr-1 inline h-3.5 w-3.5" />
              {f}
              {area === 'web-home' && f === 'Header' && ' ↓ header'}
            </button>
          ))}
        </div>
      )}

      {piezas.length === 0 ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">Sin piezas en esta área.</p>
      ) : (
        <ul className="space-y-1.5">
          {piezas.map(p => (
            <li key={p.id} className="animate-rise rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 dark:border-slate-700 dark:bg-slate-900">
            <div className="flex items-center gap-2">
              <span className="flex min-w-0 flex-1 items-center gap-1.5 truncate text-sm font-semibold text-slate-800 dark:text-slate-200">
                {p.estado === 'publicado' && (
                  <Check className="h-4 w-4 shrink-0 animate-tilde text-emerald-600 dark:text-emerald-400" aria-label="Publicada" />
                )}
                <span className="truncate">{p.formato}</span>
                {esPiezaHeader(p) && (
                  <span className="rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-violet-700 dark:bg-violet-900/50 dark:text-violet-300">
                    header
                  </span>
                )}
              </span>
              <select
                value={p.estado}
                disabled={!editable}
                aria-label={`Estado de ${p.formato}`}
                onChange={e => onEstado(p.id, e.target.value as EstadoPieza)}
                className={`${SELECT_ESTADO} ${TONO_ESTADO[p.estado]}`}
              >
                {ESTADOS.map(e => (
                  <option key={e} value={e}>{ETIQUETA_ESTADO[e]}</option>
                ))}
              </select>
              {editable && (
                <button
                  type="button"
                  onClick={() => onQuitar(p.id)}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-400 transition hover:bg-rose-50 hover:text-rose-600 active:scale-95 dark:text-slate-500 dark:hover:bg-rose-500/10 dark:hover:text-rose-300 sm:h-8 sm:w-8"
                  aria-label={`Quitar ${p.formato}`}
                  title={`Quitar ${p.formato}`}
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>

            {/* Los envíos salen un día y a una hora: eso es lo que arma el
                cronograma. Sin fecha propia caen el día que arranca la acción.
                La fecha puede ser de otro mes que el del arranque. */}
            {esPiezaDeEnvio(p) && (
              <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-2 dark:border-slate-800">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Sale</span>
                <CampoFecha
                  valor={p.desde}
                  disabled={!editable}
                  aria-label={`Día de envío de ${p.formato}`}
                  onGuardar={dia => onEnvio(p.id, dia
                    ? { desde: dia, hasta: dia }
                    : { desde: undefined, hasta: undefined })}
                  className="campo !h-9 !w-auto !px-2 !text-sm"
                />
                <input
                  type="time"
                  value={p.hora ?? ''}
                  disabled={!editable}
                  aria-label={`Hora de envío de ${p.formato}`}
                  onChange={e => onEnvio(p.id, { hora: e.target.value || undefined })}
                  className="campo !h-9 !w-auto !px-2 !text-sm"
                />
                {p.desde == null ? (
                  <span className="text-xs text-amber-700 dark:text-amber-300">
                    sin fecha propia: sale el {fechaCorta(inicioAccion)}, con la acción
                  </span>
                ) : editable ? (
                  <button
                    type="button"
                    onClick={() => onEnvio(p.id, { desde: undefined, hasta: undefined })}
                    className="rounded px-1 text-xs text-slate-500 underline underline-offset-2 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
                  >
                    que salga con la acción
                  </button>
                ) : null}
              </div>
            )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

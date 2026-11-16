'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import {
  ArrowLeftRight, CalendarRange, ChevronLeft, ChevronRight, LayoutList, Maximize2, Minimize2, Minus,
  MoveHorizontal, Plus, Users, WifiOff,
} from 'lucide-react'
import { claveDe, diaDeHoy, diasDelMes, hoyIso, isoDe, mesSiguiente } from '@/lib/calendario/fechas'
import { SIN_CATEGORIA } from '@/lib/calendario/categorias'
import { usePermisosCalendario } from '@/lib/calendario/permisos'
import { useCalendario, type Filtro } from '@/lib/calendario/store'
import {
  ANCHO_ETIQUETA, ZOOM_POR_DEFECTO, ZOOM_TELEFONO, porcentajeZoom, sePuedeAcercar, sePuedeAlejar,
  siguienteZoom, zoomParaAncho,
} from '@/lib/calendario/rejilla'
import { mundoDe, mundosDe, type SeccionDeMundo } from '@/lib/mundos'
import { useCurrentUser } from '@/hooks/useCurrentUser'
import { BotonOutlook } from './BotonOutlook'

const MESES = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'setiembre', 'octubre', 'noviembre', 'diciembre',
]

/** Años navegables desde el select. Con las flechas se puede salir del rango. */
const ANIOS = Array.from({ length: 8 }, (_, i) => 2025 + i)

const NOMBRE_FILTRO: Record<SeccionDeMundo, string> = {
  comercial: 'Comercial',
  envios: 'Envíos',
  retail: 'Retail Media',
  header: 'Headers',
}

/** El select del mes y el del año: se leen como un título y se tocan como un botón. */
const SELECT_FECHA = 'h-11 cursor-pointer rounded-xl border-0 bg-transparent py-0 text-base font-bold text-slate-900 transition hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:bg-transparent dark:text-slate-100 dark:hover:bg-slate-800 sm:h-10'

export function BarraSuperior() {
  const mesActivo = useCalendario(s => s.mesActivo)
  const irAMes = useCalendario(s => s.irAMes)
  const zoom = useCalendario(s => s.zoom)
  const zoomElegido = useCalendario(s => s.zoomElegido)
  const setZoom = useCalendario(s => s.setZoom)
  const vista = useCalendario(s => s.vista)
  const setVista = useCalendario(s => s.setVista)
  const filtro = useCalendario(s => s.filtro)
  const setFiltro = useCalendario(s => s.setFiltro)
  const claveMundo = useCalendario(s => s.mundo)
  const dias = diasDelMes(mesActivo)
  const conexion = useCalendario(s => s.conexion)
  const sinGuardar = useCalendario(s => s.sinGuardar)
  const [pantallaCompleta, setPantallaCompleta] = useState(false)
  const filtrosRef = useRef<HTMLDivElement>(null)

  // En el teléfono los filtros se deslizan: el elegido siempre a la vista
  // (entrar con "Headers" elegido lo dejaba escondido a la derecha).
  useEffect(() => {
    const caja = filtrosRef.current
    const chip = caja?.querySelector<HTMLElement>('[aria-selected="true"]')
    if (!caja || !chip) return
    const c = caja.getBoundingClientRect()
    const b = chip.getBoundingClientRect()
    if (b.right > c.right) caja.scrollLeft += b.right - c.right + 24
    else if (b.left < c.left) caja.scrollLeft -= c.left - b.left + 24
  }, [filtro])
  const { user } = useCurrentUser()

  const mundo = mundoDe(claveMundo)
  const variosMundos = mundosDe(user).length > 1
  const secciones = mundo?.secciones ?? ['comercial', 'envios']

  const [anio, mesNum] = mesActivo.split('-').map(Number)
  const anios = ANIOS.includes(anio) ? ANIOS : [...ANIOS, anio].sort((a, b) => a - b)
  const esteMes = claveDe(hoyIso())
  const abrirEditor = useCalendario(s => s.abrirEditor)
  const { editable, gestionaTareas } = usePermisosCalendario()

  // Atajos de teclado (propuesta de diseño del 15/11/2026): ← y → cambian
  // de mes, T vuelve a hoy y N crea una acción, como el botón. No se activan
  // mientras se escribe, con una ficha o el editor abiertos, ni con
  // Ctrl/Alt/Cmd (no pisan los del navegador).
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return
      const t = e.target as HTMLElement | null
      if (t?.closest('input, textarea, select, [contenteditable="true"], [role="tablist"], [role="radiogroup"], [role="listbox"], [role="menu"], [role="dialog"]')) return
      const { abierta, edicion, mesActivo: mes } = useCalendario.getState()
      if (abierta || edicion) return
      if (e.key === 'ArrowLeft') irAMes(mesSiguiente(mes, -1))
      else if (e.key === 'ArrowRight') irAMes(mesSiguiente(mes, 1))
      else if (e.key === 't' || e.key === 'T') irAMes(claveDe(hoyIso()))
      else if ((e.key === 'n' || e.key === 'N') && editable) {
        abrirEditor({ seccion: 'comercial', banda: SIN_CATEGORIA, carril: 0, barra: null, fechaInicial: isoDe(mes, diaDeHoy(mes) ?? 1) })
      } else return
      e.preventDefault()
    }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  }, [irAMes, abrirEditor, editable])

  const ir = (a: number, m: number) => irAMes(`${a}-${String(m).padStart(2, '0')}`)

  /**
   * Achica o agranda hasta que el mes entero entre, midiendo la caja real de
   * una sección. Antes se calculaba desde `window.innerWidth`, que ignora el
   * `max-w` del contenedor y el padding, así que en pantallas anchas se
   * pasaba y seguía habiendo scroll.
   */
  function ajustarAlAncho(elegido = true) {
    const seccion = document.querySelector('#calendario section')
    if (!seccion) return
    // La columna de las categorías es más angosta en el teléfono: se mide la
    // de verdad, la que pone la variable CSS.
    const etiqueta = seccion.querySelector<HTMLElement>('[data-etiqueta]')?.offsetWidth || ANCHO_ETIQUETA
    const zoomJusto = zoomParaAncho(seccion.clientWidth, dias, etiqueta)
    // En una pantalla angosta el mes no entra a un tamaño legible: una semana
    // cómoda, y el resto con el dedo (ver ZOOM_TELEFONO).
    const angosta = seccion.clientWidth < 640
    setZoom(angosta && !elegido ? Math.max(zoomJusto, ZOOM_TELEFONO) : zoomJusto, elegido)
  }

  /**
   * Mientras nadie toque el zoom, el mes se ajusta solo al ancho de la
   * pantalla: en una notebook entra entero sin scroll, y en un monitor grande
   * las columnas se ensanchan en vez de dejar media pantalla en blanco. El
   * tamaño fijo de antes estaba pensado para un monitor de 27 pulgadas.
   */
  useEffect(() => {
    if (zoomElegido || vista !== 'tiempo') return
    const ajustar = () => ajustarAlAncho(false)
    const cuadro = requestAnimationFrame(ajustar)
    window.addEventListener('resize', ajustar)
    return () => { cancelAnimationFrame(cuadro); window.removeEventListener('resize', ajustar) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoomElegido, vista, dias, filtro])

  /**
   * Pantalla completa de verdad: el calendario se queda con toda la ventana,
   * sin el menú ni el resto del dashboard. Al entrar y al salir se reajusta el
   * zoom al ancho nuevo.
   */
  async function alternarPantallaCompleta() {
    const caja = document.getElementById('calendario-pantalla')
    if (!caja) return
    try {
      if (document.fullscreenElement) await document.exitFullscreen()
      else await caja.requestFullscreen()
    } catch {
      // Si el navegador la bloquea, al menos que el mes entre entero.
      ajustarAlAncho()
    }
  }

  useEffect(() => {
    function alCambiar() {
      setPantallaCompleta(Boolean(document.fullscreenElement))
      // El ancho recién es el nuevo después de que el navegador repinta.
      requestAnimationFrame(() => ajustarAlAncho(false))
    }
    document.addEventListener('fullscreenchange', alCambiar)
    return () => document.removeEventListener('fullscreenchange', alCambiar)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dias])

  const chips: { id: Filtro; nombre: string }[] = [
    { id: 'todo', nombre: 'Todo' },
    ...secciones.map(s => ({ id: s as Filtro, nombre: NOMBRE_FILTRO[s] })),
  ]

  const vistas = [
    { id: 'tiempo', nombre: 'Calendario', titulo: 'El mes entero, como en el Excel', Icono: CalendarRange },
    { id: 'lista', nombre: 'Lista', titulo: 'Las acciones como tarjetas', Icono: LayoutList },
    // Solo quien reparte tareas: ver la carga de cada uno antes de asignar.
    ...(gestionaTareas ? [{ id: 'equipo', nombre: 'Equipo', titulo: 'Cuántas tareas tiene cada persona por semana', Icono: Users }] as const : []),
  ] as const

  return (
    <header className="mb-4 rounded-2xl border border-slate-300 bg-white shadow-card dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-2 py-2 sm:px-5 sm:py-3.5">
        {/* En qué mundo se está parado: lo primero que tiene que quedar claro.
            En el teléfono ya lo dice la barra de arriba, con su color. */}
        <div className="hidden min-w-0 items-center gap-3 sm:flex">
          <span
            className="relative flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-xl text-white shadow-sm"
            style={{ backgroundColor: mundo?.color ?? '#475569' }}
          >
            <span className="absolute inset-0 bg-gradient-to-br from-white/25 to-transparent" aria-hidden />
            <CalendarRange className="relative h-5 w-5" />
          </span>
          <div className="min-w-0">
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Calendario</p>
            <h1 className="truncate text-lg font-bold leading-tight text-slate-900 dark:text-slate-100">
              {mundo?.nombre ?? 'Calendario'}
            </h1>
          </div>
          {variosMundos && (
            <Link
              href="/mundos"
              title="Cambiar de mundo"
              className="ml-1 flex h-9 shrink-0 items-center gap-1.5 rounded-xl border border-slate-300 px-3 text-xs font-semibold text-slate-600 transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700 active:scale-95 dark:border-slate-700 dark:text-slate-300 dark:hover:border-brand-500/40 dark:hover:bg-brand-500/10 dark:hover:text-brand-200"
            >
              <ArrowLeftRight className="h-3.5 w-3.5" />
              Cambiar
            </Link>
          )}
          <BotonOutlook compacto />
        </div>
        <h1 className="sr-only sm:hidden">Calendario de {mundo?.nombre ?? 'este mundo'}</h1>

        {/* El mes. En el teléfono ocupa la línea entera, con el mes al medio. */}
        <div className="flex w-full items-center gap-1 sm:ml-auto sm:w-auto">
          <button type="button" onClick={() => irAMes(mesSiguiente(mesActivo, -1))} className="boton-icono" aria-label="Mes anterior" title="Mes anterior (←)" aria-keyshortcuts="ArrowLeft">
            <ChevronLeft className="h-5 w-5" />
          </button>
          <div className="flex flex-1 items-center justify-center sm:flex-none">
            <select
              value={mesNum}
              onChange={e => ir(anio, Number(e.target.value))}
              className={`${SELECT_FECHA} pl-2 pr-1 capitalize`}
              aria-label="Mes"
            >
              {MESES.map((m, i) => (
                <option key={m} value={i + 1} className="capitalize">{m}</option>
              ))}
            </select>
            <select
              value={anio}
              onChange={e => ir(Number(e.target.value), mesNum)}
              className={`${SELECT_FECHA} pl-1 pr-1 tabular-nums`}
              aria-label="Año"
            >
              {anios.map(a => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <button type="button" onClick={() => irAMes(mesSiguiente(mesActivo, 1))} className="boton-icono" aria-label="Mes siguiente" title="Mes siguiente (→)" aria-keyshortcuts="ArrowRight">
            <ChevronRight className="h-5 w-5" />
          </button>
          {/* Fuera de este mes, "Hoy" se ofrece con el color de la marca: es
              la forma de volver. En este mes se apaga. */}
          <button
            type="button"
            onClick={() => irAMes(esteMes)}
            disabled={mesActivo === esteMes}
            title={mesActivo === esteMes ? 'Ya estás en este mes' : 'Volver a este mes (T)'}
            aria-keyshortcuts="T"
            className="h-11 shrink-0 rounded-xl border border-brand-200 bg-brand-50 px-3 text-sm font-semibold text-brand-700 transition hover:border-brand-300 hover:bg-brand-100 active:scale-95 disabled:border-slate-200 disabled:bg-transparent disabled:text-slate-400 disabled:active:scale-100 dark:border-brand-500/30 dark:bg-brand-500/10 dark:text-brand-200 dark:hover:bg-brand-500/20 dark:disabled:border-slate-700 dark:disabled:bg-transparent dark:disabled:text-slate-500 sm:ml-1 sm:h-9 sm:px-3.5"
          >
            Hoy
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-slate-200 px-2 py-2 dark:border-slate-800 sm:px-5 sm:py-2.5">
        {/* Cómo se mira. La primera opción decía "Mes" y, al lado del selector
            de mes, se leía como "este mes": Ivan buscó "el calendario general
            de todo" y no lo encontró (12/11/2026). En el teléfono va primero y
            ocupa todo el ancho de su línea, para que no quede un control chico
            a la derecha. */}
        <div className="segmentado order-first w-full sm:order-last sm:ml-auto sm:w-auto">
          {vistas.map(({ id, nombre, titulo, Icono }) => (
            <button
              key={id}
              type="button"
              onClick={() => setVista(id)}
              aria-pressed={vista === id}
              title={titulo}
              className="segmento"
            >
              <Icono className="h-4 w-4" /> {nombre}
            </button>
          ))}
        </div>

        {/* Qué parte se mira. Las cuatro juntas marean a quien entra por
            primera vez; de a una se entiende. */}
        <div
          ref={filtrosRef}
          className="-mx-1 flex max-w-full items-center gap-1 overflow-x-auto px-1 py-0.5 [scrollbar-width:none] max-sm:pr-8 max-sm:[mask-image:linear-gradient(to_right,black_calc(100%_-_28px),transparent)] [&::-webkit-scrollbar]:hidden"
          role="tablist"
          aria-label="Qué parte del calendario se ve"
        >
          {chips.map(c => (
            <button
              key={c.id}
              type="button"
              role="tab"
              aria-selected={filtro === c.id}
              onClick={() => setFiltro(c.id)}
              className={`min-h-[40px] shrink-0 rounded-full px-4 text-sm font-semibold transition active:scale-95 sm:min-h-[36px] sm:px-3.5 ${
                filtro === c.id
                  ? 'bg-slate-900 text-white shadow-sm dark:bg-white dark:text-slate-900'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white'
              }`}
            >
              {c.nombre}
            </button>
          ))}
        </div>

        {vista === 'tiempo' && (
          <div className="hidden items-center gap-0.5 rounded-xl border border-slate-300 p-0.5 dark:border-slate-700 md:order-last md:flex" role="group" aria-label="Tamaño del calendario">
            <button type="button" onClick={() => setZoom(siguienteZoom(zoom, -1))} disabled={!sePuedeAlejar(zoom)} title="Alejar" aria-label="Alejar" className="boton-icono">
              <Minus className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setZoom(ZOOM_POR_DEFECTO)}
              title="Volver al tamaño normal"
              className="h-9 w-12 rounded-lg text-center text-xs font-semibold tabular-nums text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
            >
              {porcentajeZoom(zoom)}%
            </button>
            <button type="button" onClick={() => setZoom(siguienteZoom(zoom, 1))} disabled={!sePuedeAcercar(zoom)} title="Acercar" aria-label="Acercar" className="boton-icono">
              <Plus className="h-4 w-4" />
            </button>
            <span className="mx-0.5 h-5 w-px bg-slate-200 dark:bg-slate-700" aria-hidden />
            <button type="button" onClick={() => ajustarAlAncho()} title="Que entre el mes entero a lo ancho" aria-label="Que entre el mes entero a lo ancho" className="boton-icono">
              <MoveHorizontal className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={alternarPantallaCompleta}
              title={pantallaCompleta ? 'Salir de pantalla completa' : 'Pantalla completa'}
              aria-label={pantallaCompleta ? 'Salir de pantalla completa' : 'Pantalla completa'}
              className="boton-icono"
            >
              {pantallaCompleta ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            </button>
          </div>
        )}
      </div>

      {conexion === 'sin-conexion' && (
        <p role="status" className="flex items-start gap-2 rounded-b-2xl border-t border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200 sm:px-5">
          <WifiOff className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>
            No hay conexión con el servidor: lo que ves puede no estar al día.{' '}
            {sinGuardar > 0
              ? <><strong>{sinGuardar === 1 ? '1 cambio tuyo espera' : `${sinGuardar} cambios tuyos esperan`}</strong> para guardarse: se guardan solos cuando vuelva. No cierres esta pestaña.</>
              : 'Se vuelve a intentar solo.'}
          </span>
        </p>
      )}
    </header>
  )
}

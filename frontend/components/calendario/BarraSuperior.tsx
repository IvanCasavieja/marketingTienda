'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import {
  ArrowLeftRight, CalendarRange, ChevronLeft, ChevronRight, LayoutList, Maximize2, Minimize2, Minus,
  MoveHorizontal, Plus,
} from 'lucide-react'
import { claveDe, diasDelMes, hoyIso, mesSiguiente } from '@/lib/calendario/fechas'
import { useCalendario, type Filtro } from '@/lib/calendario/store'
import {
  ZOOM_POR_DEFECTO, porcentajeZoom, sePuedeAcercar, sePuedeAlejar,
  siguienteZoom, zoomParaAncho,
} from '@/lib/calendario/rejilla'
import { mundoDe, mundosDe, type SeccionDeMundo } from '@/lib/mundos'
import { useCurrentUser } from '@/hooks/useCurrentUser'

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

const BOTON = 'rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 disabled:opacity-30 disabled:hover:bg-transparent dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100'

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
  const [pantallaCompleta, setPantallaCompleta] = useState(false)
  const { user } = useCurrentUser()

  const mundo = mundoDe(claveMundo)
  const variosMundos = mundosDe(user).length > 1
  const secciones = mundo?.secciones ?? ['comercial', 'envios']

  const [anio, mesNum] = mesActivo.split('-').map(Number)
  const anios = ANIOS.includes(anio) ? ANIOS : [...ANIOS, anio].sort((a, b) => a - b)
  const esteMes = claveDe(hoyIso())

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
    setZoom(zoomParaAncho(seccion.clientWidth, dias), elegido)
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

  return (
    <header className="mb-4 rounded-2xl border border-slate-200 bg-white shadow-card dark:border-slate-700 dark:bg-slate-900">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3.5 sm:px-5">
        {/* En qué mundo se está parado: lo primero que tiene que quedar claro. */}
        <div className="flex min-w-0 items-center gap-3">
          <span
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-white"
            style={{ backgroundColor: mundo?.color ?? '#475569' }}
          >
            <CalendarRange className="h-5 w-5" />
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
              className="ml-1 flex shrink-0 items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-semibold text-slate-600 transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              <ArrowLeftRight className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Cambiar</span>
            </Link>
          )}
        </div>

        {/* El mes */}
        <div className="flex items-center gap-1 sm:ml-auto">
          <button type="button" onClick={() => irAMes(mesSiguiente(mesActivo, -1))} className={BOTON} aria-label="Mes anterior">
            <ChevronLeft className="h-5 w-5" />
          </button>
          <select
            value={mesNum}
            onChange={e => ir(anio, Number(e.target.value))}
            className="cursor-pointer rounded-lg border-0 bg-transparent py-1.5 pl-1 pr-0 text-base font-bold capitalize text-slate-900 outline-none hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
            aria-label="Mes"
          >
            {MESES.map((m, i) => (
              <option key={m} value={i + 1} className="capitalize">{m}</option>
            ))}
          </select>
          <select
            value={anio}
            onChange={e => ir(Number(e.target.value), mesNum)}
            className="cursor-pointer rounded-lg border-0 bg-transparent py-1.5 text-base font-bold text-slate-900 outline-none hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
            aria-label="Año"
          >
            {anios.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
          <button type="button" onClick={() => irAMes(mesSiguiente(mesActivo, 1))} className={BOTON} aria-label="Mes siguiente">
            <ChevronRight className="h-5 w-5" />
          </button>
          <button
            type="button"
            onClick={() => irAMes(esteMes)}
            disabled={mesActivo === esteMes}
            className="ml-1 rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-40 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Hoy
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5 border-t border-slate-100 px-4 py-2.5 dark:border-slate-800 sm:px-5">
        {/* Qué parte se mira. Las cuatro juntas marean a quien entra por
            primera vez; de a una se entiende. */}
        <div className="-mx-1 flex max-w-full items-center gap-1 overflow-x-auto px-1" role="tablist" aria-label="Qué parte del calendario se ve">
          {chips.map(c => (
            <button
              key={c.id}
              type="button"
              role="tab"
              aria-selected={filtro === c.id}
              onClick={() => setFiltro(c.id)}
              className={`shrink-0 rounded-full px-3.5 py-1.5 text-sm font-semibold transition ${
                filtro === c.id
                  ? 'bg-brand-600 text-white shadow-sm'
                  : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
              }`}
            >
              {c.nombre}
            </button>
          ))}
        </div>

        <div className="ml-auto flex w-full items-center gap-2 sm:w-auto">
          {/* Cómo se mira. La primera opción decía "Mes" y, al lado del selector
              de mes, se leía como "este mes": Ivan buscó "el calendario general
              de todo" y no lo encontró (12/11/2026). En el teléfono ocupa todo
              el ancho de su línea, para que no quede un control chico a la
              derecha. */}
          <div className="flex flex-1 items-center rounded-lg bg-slate-100 p-0.5 dark:bg-slate-800 sm:flex-none">
            {([
              { id: 'tiempo', nombre: 'Calendario', titulo: 'El mes entero, como en el Excel', Icono: CalendarRange },
              { id: 'lista', nombre: 'Lista', titulo: 'Las acciones como tarjetas', Icono: LayoutList },
            ] as const).map(({ id, nombre, titulo, Icono }) => (
              <button
                key={id}
                type="button"
                onClick={() => setVista(id)}
                aria-pressed={vista === id}
                title={titulo}
                className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold transition sm:flex-none ${
                  vista === id
                    ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-slate-100'
                    : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
                }`}
              >
                <Icono className="h-4 w-4" /> {nombre}
              </button>
            ))}
          </div>

          {vista === 'tiempo' && (
            <div className="hidden items-center md:flex">
              <button type="button" onClick={() => setZoom(siguienteZoom(zoom, -1))} disabled={!sePuedeAlejar(zoom)} title="Alejar" className={BOTON}>
                <Minus className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => setZoom(ZOOM_POR_DEFECTO)}
                title="Volver al tamaño normal"
                className="w-12 rounded-lg py-1.5 text-center text-xs font-semibold tabular-nums text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
              >
                {porcentajeZoom(zoom)}%
              </button>
              <button type="button" onClick={() => setZoom(siguienteZoom(zoom, 1))} disabled={!sePuedeAcercar(zoom)} title="Acercar" className={BOTON}>
                <Plus className="h-4 w-4" />
              </button>
              <button type="button" onClick={() => ajustarAlAncho()} title="Que entre el mes entero a lo ancho" className={BOTON}>
                <MoveHorizontal className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={alternarPantallaCompleta}
                title={pantallaCompleta ? 'Salir de pantalla completa' : 'Pantalla completa'}
                aria-label={pantallaCompleta ? 'Salir de pantalla completa' : 'Pantalla completa'}
                className={BOTON}
              >
                {pantallaCompleta ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
              </button>
            </div>
          )}
        </div>
      </div>

      {conexion === 'sin-conexion' && (
        <p className="rounded-b-2xl border-t border-amber-200 bg-amber-50 px-5 py-2.5 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          No hay conexión con el servidor: lo que ves puede no estar al día y los cambios no se guardan. Se vuelve a
          intentar solo.
        </p>
      )}
    </header>
  )
}

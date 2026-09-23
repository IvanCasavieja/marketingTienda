'use client'

import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Maximize2, Minimize2, Minus, MoveHorizontal, Plus } from 'lucide-react'
import { mesSiguiente } from '@/lib/calendario/fechas'
import { useCalendario } from '@/lib/calendario/store'
import {
  ZOOM_POR_DEFECTO, porcentajeZoom, sePuedeAcercar, sePuedeAlejar,
  siguienteZoom, zoomParaAncho,
} from '@/lib/calendario/rejilla'

const MESES = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'setiembre', 'octubre', 'noviembre', 'diciembre',
]

/** Años navegables desde el select. Con las flechas se puede salir del rango. */
const ANIOS = Array.from({ length: 8 }, (_, i) => 2025 + i)

export function BarraSuperior() {
  const mesActivo = useCalendario(s => s.mesActivo)
  const irAMes = useCalendario(s => s.irAMes)
  const zoom = useCalendario(s => s.zoom)
  const setZoom = useCalendario(s => s.setZoom)
  const dias = useCalendario(s => s.meses[s.mesActivo].dias)
  const [pantallaCompleta, setPantallaCompleta] = useState(false)

  const [anio, mesNum] = mesActivo.split('-').map(Number)
  const anios = ANIOS.includes(anio) ? ANIOS : [...ANIOS, anio].sort((a, b) => a - b)

  const ir = (a: number, m: number) => irAMes(`${a}-${String(m).padStart(2, '0')}`)

  /**
   * Achica o agranda hasta que el mes entero entre, midiendo la caja real de
   * una sección. Antes se calculaba desde `window.innerWidth`, que ignora el
   * `max-w` del contenedor y el padding, así que en pantallas anchas se
   * pasaba y seguía habiendo scroll.
   */
  function ajustarAlAncho() {
    const seccion = document.querySelector('#calendario section')
    const disponible = seccion?.clientWidth ?? window.innerWidth - 32
    setZoom(zoomParaAncho(disponible, dias))
  }

  /**
   * Pantalla completa de verdad: el calendario se queda con toda la ventana,
   * sin el menú ni el resto del dashboard. Antes este botón solo ajustaba el
   * zoom, y en una pantalla donde el mes ya entraba no pasaba nada visible.
   * Al entrar y al salir se reajusta el zoom al ancho nuevo.
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
      requestAnimationFrame(ajustarAlAncho)
    }
    document.addEventListener('fullscreenchange', alCambiar)
    return () => document.removeEventListener('fullscreenchange', alCambiar)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dias])

  return (
    <header className="mb-5 rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900">
      <div className="flex flex-wrap items-center gap-3 px-4 py-3">
        <div className="min-w-0">
          <h1 className="text-base font-semibold leading-tight text-slate-900 dark:text-slate-100">Calendario</h1>
          <p className="text-xs text-slate-500 dark:text-slate-400">Marketing · Retail Media · Headers de la home</p>
        </div>

        <div className="ml-auto flex items-center gap-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-0.5">
          <button
            type="button"
            onClick={() => irAMes(mesSiguiente(mesActivo, -1))}
            className="rounded-md p-1.5 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100"
            aria-label="Mes anterior"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>

          <select
            value={mesNum}
            onChange={e => ir(anio, Number(e.target.value))}
            className="w-[108px] cursor-pointer border-0 bg-transparent px-1 py-1 text-center text-sm font-semibold capitalize text-slate-900 outline-none dark:bg-slate-900 dark:text-slate-100"
            aria-label="Mes"
          >
            {MESES.map((m, i) => (
              <option key={m} value={i + 1} className="capitalize">{m}</option>
            ))}
          </select>

          <select
            value={anio}
            onChange={e => ir(Number(e.target.value), mesNum)}
            className="cursor-pointer border-0 bg-transparent py-1 pr-1 text-sm font-semibold text-slate-900 outline-none dark:bg-slate-900 dark:text-slate-100"
            aria-label="Año"
          >
            {anios.map(a => <option key={a} value={a}>{a}</option>)}
          </select>

          <button
            type="button"
            onClick={() => irAMes(mesSiguiente(mesActivo, 1))}
            className="rounded-md p-1.5 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100"
            aria-label="Mes siguiente"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>

        <div className="flex items-center gap-0.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-0.5">
          <button
            type="button"
            onClick={() => setZoom(siguienteZoom(zoom, -1))}
            disabled={!sePuedeAlejar(zoom)}
            title="Alejar"
            className="rounded-md p-1.5 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100 disabled:opacity-30 disabled:hover:bg-transparent"
          >
            <Minus className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => setZoom(ZOOM_POR_DEFECTO)}
            title="Volver al tamaño normal"
            className="w-11 rounded-md py-1 text-center text-[11px] font-semibold tabular-nums text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            {porcentajeZoom(zoom)}%
          </button>
          <button
            type="button"
            onClick={() => setZoom(siguienteZoom(zoom, 1))}
            disabled={!sePuedeAcercar(zoom)}
            title="Acercar"
            className="rounded-md p-1.5 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100 disabled:opacity-30 disabled:hover:bg-transparent"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={ajustarAlAncho}
            title="Que entre el mes entero a lo ancho"
            className="rounded-md p-1.5 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100"
          >
            <MoveHorizontal className="h-3.5 w-3.5" />
          </button>
        </div>

        <button
          type="button"
          onClick={alternarPantallaCompleta}
          title={pantallaCompleta ? 'Salir de pantalla completa' : 'Pantalla completa'}
          aria-label={pantallaCompleta ? 'Salir de pantalla completa' : 'Pantalla completa'}
          className="rounded-lg border border-slate-200 dark:border-slate-700 p-2 text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100"
        >
          {pantallaCompleta ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
        </button>

      </div>
    </header>
  )
}

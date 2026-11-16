'use client'

import { CalendarDays, CalendarPlus, CheckCircle2, ListChecks, Mail, MessageCircle, Smartphone } from 'lucide-react'
import { esSinCategoria, nivelDeCategoria } from '@/lib/calendario/categorias'
import { textoSobre } from '@/lib/calendario/colores'
import {
  claveDe, diaDe, diasEntre, fechaCorta, hoyIso, isoDe, nombreMes, primerDiaDe, ultimoDiaDe,
} from '@/lib/calendario/fechas'
import { useCalendario, useMesActivo, type Filtro } from '@/lib/calendario/store'
import { usePermisosCalendario } from '@/lib/calendario/permisos'
import { tituloDeCanal, type BarraGuardada, type Persona } from '@/lib/calendario/tipos'
import { Cocarda } from './Cocarda'
import { HeaderHome } from './HeaderHome'
import { NuevaAccion } from './NuevaAccion'
import { CLASE_SEMAFORO, semaforoDe, type ColorSemaforo } from '@/lib/calendario/semaforo'

/**
 * El mes como una lista de tarjetas.
 *
 * Pedido de Ivan (12/11/2026): "tarjetas más grandes", que se lean en una
 * notebook y que se pueda "utilizar el calendario hasta de manera mobile". La
 * línea de tiempo necesita ancho; esto no: cada acción es una tarjeta con su
 * nombre, sus fechas y cómo viene, y en un teléfono quedan una abajo de la otra.
 *
 * Muestra lo mismo que la línea de tiempo del mes, con los mismos filtros.
 */

const ICONO_CANAL: Record<string, React.ReactNode> = {
  email: <Mail className="h-4 w-4" />,
  whatsapp: <MessageCircle className="h-4 w-4" />,
  push: <Smartphone className="h-4 w-4" />,
}

type Grupo = { id: 'curso' | 'viene' | 'paso'; titulo: string; bajada: string; barras: BarraGuardada[] }

/** En curso, lo que viene y lo que ya pasó, cada grupo en orden de fecha. */
function agrupar(barras: BarraGuardada[], hoy: string): Grupo[] {
  const porFecha = (a: BarraGuardada, b: BarraGuardada) => a.desde.localeCompare(b.desde) || a.nombre.localeCompare(b.nombre)
  const enCurso = barras.filter(b => b.desde <= hoy && b.hasta >= hoy).sort(porFecha)
  const proximas = barras.filter(b => b.desde > hoy).sort(porFecha)
  const pasadas = barras.filter(b => b.hasta < hoy).sort((a, b) => b.hasta.localeCompare(a.hasta))
  const grupos: Grupo[] = [
    { id: 'curso', titulo: 'En curso', bajada: 'Están activas hoy', barras: enCurso },
    { id: 'viene', titulo: 'Lo que viene', bajada: 'Todavía no arrancaron', barras: proximas },
    { id: 'paso', titulo: 'Ya terminaron', bajada: 'De este mes', barras: pasadas },
  ]
  return grupos.filter(g => g.barras.length > 0)
}

/** "5 al 18 de noviembre", "20/11 al 25/12": corto, para que entre en una línea. */
function rangoCorto(desde: string, hasta: string): string {
  const mes = nombreMes(claveDe(desde)).split(' ')[0]
  if (desde === hasta) return `${diaDe(desde)} de ${mes}`
  if (claveDe(desde) === claveDe(hasta)) return `${diaDe(desde)} al ${diaDe(hasta)} de ${mes}`
  return `${fechaCorta(desde)} al ${fechaCorta(hasta)}`
}

function iniciales(nombre: string): string {
  return nombre.split(/\s+/).filter(Boolean).slice(0, 2).map(p => p[0]?.toUpperCase() ?? '').join('')
}

const CLASE_PILDORA: Record<ColorSemaforo, string> = {
  verde: 'bg-emerald-50 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-200',
  amarillo: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-200',
  rojo: 'bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-200',
}

function Tarjeta({ barra, personas, hoy, onAbrir, pasada, orden }: {
  barra: BarraGuardada
  personas: Persona[]
  hoy: string
  onAbrir: () => void
  /** Ya terminó: se ve, pero un paso atrás. */
  pasada: boolean
  /** Su lugar en la lista, para que entren de a una. */
  orden: number
}) {
  const esEnvio = barra.seccion === 'envio'
  const piezas = barra.piezas ?? []
  const publicadas = piezas.filter(p => p.estado === 'publicado').length
  const tareas = barra.tareas ?? []
  const hechas = tareas.filter(t => t.estado === 'hecha').length
  const vencidas = tareas.filter(t => t.estado !== 'hecha' && t.vence && t.vence < hoy).length
  const asignados = [...new Set(tareas.map(t => t.asignadoA).filter((x): x is number => x != null))]
  const dias = diasEntre(barra.desde, barra.hasta) + 1
  const faltan = diasEntre(hoy, barra.desde)
  const porArrancar = barra.desde > hoy && faltan <= 14
  // Lo que está en curso y termina hoy o mañana también se avisa: es lo que
  // hay que mirar antes de que se pase.
  const quedan = diasEntre(hoy, barra.hasta)
  const porTerminar = !esEnvio && barra.desde <= hoy && quedan >= 0 && quedan <= 1
  // Arriba del nombre van la cocarda y el "faltan N días". Una acción sin
  // categoría que no está por arrancar no tiene ninguna de las dos, y la línea
  // no se dibuja: vacía dejaría un hueco.
  const esAccion = barra.seccion === 'comercial'
  // El semáforo, cuando avisa algo (amarillo o rojo), ya dice cuánto falta para
  // que arranque: reemplaza al "Faltan N días".
  const semaforo = esAccion ? semaforoDe(barra, hoy) : null
  const semaforoAvisa = !!semaforo && (semaforo.color !== 'verde' || semaforo.texto === 'Todo listo')
  const conPrimeraLinea = !esAccion || !esSinCategoria(barra.banda) || porArrancar || porTerminar || semaforoAvisa
  const mega = esAccion && nivelDeCategoria(barra.banda) === 'mega'

  return (
    <button
      type="button"
      onClick={onAbrir}
      style={{ animationDelay: `${Math.min(orden, 8) * 35}ms` }}
      className={`group flex w-full animate-rise overflow-hidden rounded-2xl border bg-white text-left shadow-card transition duration-200 ease-suave hover:-translate-y-0.5 hover:shadow-card-hover active:translate-y-0 active:scale-[.99] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 dark:bg-slate-900 dark:focus-visible:ring-offset-slate-950 ${
        mega
          ? 'border-slate-300 ring-1 ring-slate-900/5 hover:border-slate-400 dark:border-slate-600 dark:ring-white/5 dark:hover:border-slate-500'
          : 'border-slate-200 hover:border-brand-300 dark:border-slate-800 dark:hover:border-brand-500/50'
      } ${pasada ? 'opacity-75 hover:opacity-100' : ''}`}
    >
      <span className="w-2 shrink-0" style={{ backgroundColor: barra.color ?? '#cbd5e1' }} />
      <span className="flex min-w-0 flex-1 flex-col gap-2.5 p-4">
        {conPrimeraLinea && (
          <span className="flex flex-wrap items-center gap-2">
            {esAccion ? (
              <Cocarda banda={barra.banda} />
            ) : (
              <span
                className="inline-flex max-w-full items-center gap-1.5 truncate rounded-full px-2.5 py-1 text-xs font-semibold"
                style={{ backgroundColor: barra.color ?? '#e2e8f0', color: textoSobre(barra.color) }}
              >
                {esEnvio && ICONO_CANAL[barra.banda]}
                {esEnvio ? `${tituloDeCanal(barra.banda)} · envío` : barra.banda}
              </span>
            )}
            {semaforo && semaforoAvisa && (
              <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${CLASE_PILDORA[semaforo.color]}`}>
                <span className={`h-2 w-2 shrink-0 rounded-full ${CLASE_SEMAFORO[semaforo.color]}`} aria-hidden />
                {semaforo.texto}
              </span>
            )}
            {porArrancar && !(semaforo && semaforo.color !== 'verde') && (
              <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-800 dark:bg-amber-500/15 dark:text-amber-200">
                {faltan === 1 ? 'Arranca mañana' : `Faltan ${faltan} días`}
              </span>
            )}
            {porTerminar && (
              <span className="rounded-full bg-orange-100 px-2.5 py-1 text-xs font-semibold text-orange-800 dark:bg-orange-500/15 dark:text-orange-200">
                {quedan === 0 ? 'Termina hoy' : 'Termina mañana'}
              </span>
            )}
          </span>
        )}

        <span className="text-[17px] font-bold leading-snug text-slate-900 transition-colors group-hover:text-brand-700 dark:text-slate-100 dark:group-hover:text-brand-200">
          {barra.nombre}
        </span>

        <span className="flex items-center gap-1.5 text-sm text-slate-600 dark:text-slate-400">
          <CalendarDays className="h-4 w-4 shrink-0 text-slate-400 dark:text-slate-500" />
          {esEnvio
            ? `Sale el ${fechaCorta(barra.desde)}${barra.hora ? ` a las ${barra.hora}` : ''}`
            : `${rangoCorto(barra.desde, barra.hasta)} · ${dias === 1 ? '1 día' : `${dias} días`}`}
        </span>

        {(piezas.length > 0 || tareas.length > 0) && (
          <span className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-slate-100 pt-2.5 text-sm dark:border-slate-800">
            {piezas.length > 0 && (
              <span className="flex items-center gap-1.5 tabular-nums text-slate-600 dark:text-slate-400">
                <CheckCircle2 className={`h-4 w-4 ${publicadas === piezas.length ? 'text-emerald-500' : 'text-slate-400 dark:text-slate-500'}`} />
                {publicadas}/{piezas.length} piezas
              </span>
            )}
            {tareas.length > 0 && (
              <span className="flex items-center gap-1.5 tabular-nums text-slate-600 dark:text-slate-400">
                <ListChecks className={`h-4 w-4 ${hechas === tareas.length ? 'text-emerald-500' : 'text-slate-400 dark:text-slate-500'}`} />
                {hechas}/{tareas.length} tareas
              </span>
            )}
            {vencidas > 0 && (
              <span className="rounded-full bg-rose-100 px-2 py-0.5 text-xs font-semibold text-rose-700 dark:bg-rose-500/15 dark:text-rose-300">
                {vencidas === 1 ? '1 vencida' : `${vencidas} vencidas`}
              </span>
            )}
            {asignados.length > 0 && (
              <span className="ml-auto flex -space-x-1.5">
                {asignados.slice(0, 4).map(id => {
                  const nombre = personas.find(p => p.id === id)?.nombre ?? '?'
                  return (
                    <span
                      key={id}
                      title={nombre}
                      className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-100 text-[11px] font-bold text-brand-700 ring-2 ring-white dark:bg-brand-900 dark:text-brand-200 dark:ring-slate-900"
                    >
                      {iniciales(nombre)}
                    </span>
                  )
                })}
                {asignados.length > 4 && (
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-100 text-[11px] font-bold text-slate-600 ring-2 ring-white dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-900">
                    +{asignados.length - 4}
                  </span>
                )}
              </span>
            )}
            {/* Cuánto de las tareas está hecho, de un vistazo */}
            {tareas.length > 0 && (
              <span className="h-1 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800" aria-hidden>
                <span
                  className="block h-full rounded-full bg-emerald-500 transition-[width] duration-500 ease-suave"
                  style={{ width: `${(hechas / tareas.length) * 100}%` }}
                />
              </span>
            )}
          </span>
        )}
      </span>
    </button>
  )
}

const SECCIONES_DE: Record<Filtro, string[]> = {
  todo: ['comercial', 'envio'],
  comercial: ['comercial'],
  envios: ['envio'],
  retail: ['retail'],
  header: [],
}

export function VistaLista() {
  const mes = useMesActivo()
  const barras = useCalendario(s => s.barras)
  const personas = useCalendario(s => s.personas)
  const filtro = useCalendario(s => s.filtro)
  const abrirAccion = useCalendario(s => s.abrirAccion)
  const abrirEditor = useCalendario(s => s.abrirEditor)
  const { editable } = usePermisosCalendario()

  // Los headers no son una lista de acciones: son un conteo por día.
  if (filtro === 'header') return <HeaderHome />

  const hoy = hoyIso()
  const ini = primerDiaDe(mes.clave)
  const fin = ultimoDiaDe(mes.clave)
  const secciones = SECCIONES_DE[filtro]
  const delMes = Object.values(barras).filter(
    b => secciones.includes(b.seccion) && b.desde <= fin && b.hasta >= ini,
  )
  const grupos = agrupar(delMes, hoy)
  const diaInicial = hoy >= ini && hoy <= fin ? hoy : isoDe(mes.clave, 1)
  const conEnvios = filtro !== 'comercial'

  // Una campaña de Retail Media no tiene ficha: se edita, si se puede.
  const abrir = (b: BarraGuardada) => {
    if (b.seccion === 'retail') {
      if (editable) abrirEditor({ seccion: 'retail', banda: b.banda, carril: b.carril, barra: b })
      return
    }
    abrirAccion(b.id)
  }

  // Dónde arranca cada grupo en la lista entera, para escalonar la entrada.
  const arranque = grupos.map((_, i) => grupos.slice(0, i).reduce((n, x) => n + x.barras.length, 0))

  return (
    <div className="space-y-6">
      {editable && filtro !== 'retail' && (
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          {filtro !== 'envios' && <NuevaAccion diaInicial={diaInicial} />}
          {conEnvios && (
            // Los envíos sueltos, juntos: en el teléfono tres botones del
            // mismo ancho en una fila, con el nombre del canal solo.
            <div className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:gap-2" role="group" aria-label="Nuevo envío suelto">
              <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 sm:ml-2">Envío suelto por</span>
              <div className="flex gap-2">
              {(['email', 'whatsapp', 'push'] as const).map(canal => (
                <button
                  key={canal}
                  type="button"
                  onClick={() => abrirEditor({ seccion: 'envio', banda: canal, carril: 0, barra: null, fechaInicial: diaInicial })}
                  aria-label={`Envío por ${tituloDeCanal(canal)}`}
                  title={`Nuevo envío suelto por ${tituloDeCanal(canal)}`}
                  className="flex min-h-[44px] flex-1 items-center justify-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-brand-300 hover:text-brand-700 active:scale-[.98] dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-brand-500/50 dark:hover:text-brand-200 sm:min-h-[40px] sm:flex-none"
                >
                  {ICONO_CANAL[canal]} {tituloDeCanal(canal)}
                </button>
              ))}
              </div>
            </div>
          )}
        </div>
      )}

      {grupos.length === 0 && (
        <div className="flex flex-col items-center rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center dark:border-slate-700 dark:bg-slate-900">
          <span className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 dark:bg-brand-500/15 dark:text-brand-300">
            <CalendarPlus className="h-6 w-6" />
          </span>
          <p className="text-base font-semibold text-slate-800 dark:text-slate-100">
            No hay nada cargado en {nombreMes(mes.clave)}
          </p>
          <p className="mt-1 max-w-sm text-sm text-slate-500 dark:text-slate-400">
            {editable && filtro !== 'retail'
              ? 'Creá la primera con el botón de arriba: le ponés nombre y fechas, y lo demás se carga adentro.'
              : 'Cuando se cargue una acción va a aparecer acá.'}
          </p>
        </div>
      )}

      {grupos.map((g, gi) => (
        <section key={g.titulo} aria-labelledby={`grupo-${g.id}`}>
          <header className="mb-3 flex items-center gap-2">
            {g.id === 'curso' && (
              // Lo que pasa hoy late, apenas.
              <span className="relative flex h-2.5 w-2.5" aria-hidden>
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
              </span>
            )}
            <h2 id={`grupo-${g.id}`} className="text-base font-bold text-slate-900 dark:text-slate-100">{g.titulo}</h2>
            <span className="hidden text-sm text-slate-500 dark:text-slate-400 sm:inline">{g.bajada}</span>
            <span className="ml-auto rounded-full bg-slate-200/70 px-2.5 py-0.5 text-xs font-bold tabular-nums text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              {g.barras.length}
            </span>
          </header>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {g.barras.map((b, i) => (
              <Tarjeta
                key={b.id} barra={b} personas={personas} hoy={hoy}
                onAbrir={() => abrir(b)} pasada={g.id === 'paso'} orden={arranque[gi] + i}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}

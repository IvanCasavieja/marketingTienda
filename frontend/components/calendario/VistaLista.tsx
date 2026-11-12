'use client'

import { CalendarDays, CheckCircle2, ListChecks, Mail, MessageCircle, Plus, Smartphone } from 'lucide-react'
import { textoSobre } from '@/lib/calendario/colores'
import {
  claveDe, diaDe, diasEntre, fechaCorta, hoyIso, isoDe, nombreMes, primerDiaDe, ultimoDiaDe,
} from '@/lib/calendario/fechas'
import { useCalendario, useMesActivo, type Filtro } from '@/lib/calendario/store'
import { usePermisosCalendario } from '@/lib/calendario/permisos'
import { tituloDeCanal, type BarraGuardada, type Persona } from '@/lib/calendario/tipos'
import { HeaderHome } from './HeaderHome'

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

type Grupo = { titulo: string; bajada: string; barras: BarraGuardada[] }

/** En curso, lo que viene y lo que ya pasó, cada grupo en orden de fecha. */
function agrupar(barras: BarraGuardada[], hoy: string): Grupo[] {
  const porFecha = (a: BarraGuardada, b: BarraGuardada) => a.desde.localeCompare(b.desde) || a.nombre.localeCompare(b.nombre)
  const enCurso = barras.filter(b => b.desde <= hoy && b.hasta >= hoy).sort(porFecha)
  const proximas = barras.filter(b => b.desde > hoy).sort(porFecha)
  const pasadas = barras.filter(b => b.hasta < hoy).sort((a, b) => b.hasta.localeCompare(a.hasta))
  return [
    { titulo: 'En curso', bajada: 'Están activas hoy', barras: enCurso },
    { titulo: 'Lo que viene', bajada: 'Todavía no arrancaron', barras: proximas },
    { titulo: 'Ya terminaron', bajada: 'De este mes', barras: pasadas },
  ].filter(g => g.barras.length > 0)
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

function Tarjeta({ barra, personas, hoy, onAbrir }: {
  barra: BarraGuardada
  personas: Persona[]
  hoy: string
  onAbrir: () => void
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

  return (
    <button
      type="button"
      onClick={onAbrir}
      className="group flex w-full overflow-hidden rounded-2xl border border-slate-200 bg-white text-left shadow-card transition hover:border-brand-300 hover:shadow-card-hover dark:border-slate-700 dark:bg-slate-900"
    >
      <span className="w-2 shrink-0" style={{ backgroundColor: barra.color ?? '#cbd5e1' }} />
      <span className="flex min-w-0 flex-1 flex-col gap-2.5 p-4">
        <span className="flex flex-wrap items-center gap-2">
          <span
            className="inline-flex max-w-full items-center gap-1.5 truncate rounded-full px-2.5 py-1 text-xs font-semibold"
            style={{ backgroundColor: barra.color ?? '#e2e8f0', color: textoSobre(barra.color) }}
          >
            {esEnvio && ICONO_CANAL[barra.banda]}
            {esEnvio ? `${tituloDeCanal(barra.banda)} · envío` : barra.banda}
          </span>
          {barra.desde > hoy && faltan <= 14 && (
            <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
              {faltan === 1 ? 'Arranca mañana' : `Faltan ${faltan} días`}
            </span>
          )}
        </span>

        <span className="text-[17px] font-bold leading-snug text-slate-900 group-hover:text-brand-700 dark:text-slate-100">
          {barra.nombre}
        </span>

        <span className="flex items-center gap-1.5 text-sm text-slate-600 dark:text-slate-400">
          <CalendarDays className="h-4 w-4 shrink-0 text-slate-400" />
          {esEnvio
            ? `Sale el ${fechaCorta(barra.desde)}${barra.hora ? ` a las ${barra.hora}` : ''}`
            : `${rangoCorto(barra.desde, barra.hasta)} · ${dias === 1 ? '1 día' : `${dias} días`}`}
        </span>

        {(piezas.length > 0 || tareas.length > 0) && (
          <span className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-slate-100 pt-2.5 text-sm dark:border-slate-800">
            {piezas.length > 0 && (
              <span className="flex items-center gap-1.5 text-slate-600 dark:text-slate-400">
                <CheckCircle2 className={`h-4 w-4 ${publicadas === piezas.length ? 'text-emerald-500' : 'text-slate-400'}`} />
                {publicadas}/{piezas.length} piezas
              </span>
            )}
            {tareas.length > 0 && (
              <span className="flex items-center gap-1.5 text-slate-600 dark:text-slate-400">
                <ListChecks className={`h-4 w-4 ${hechas === tareas.length ? 'text-emerald-500' : 'text-slate-400'}`} />
                {hechas}/{tareas.length} tareas
              </span>
            )}
            {vencidas > 0 && (
              <span className="rounded-full bg-rose-100 px-2 py-0.5 text-xs font-semibold text-rose-700 dark:bg-rose-950/50 dark:text-rose-300">
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

  // Una campaña de Retail Media no tiene ficha: se edita, si se puede.
  const abrir = (b: BarraGuardada) => {
    if (b.seccion === 'retail') {
      if (editable) abrirEditor({ seccion: 'retail', banda: b.banda, carril: b.carril, barra: b })
      return
    }
    abrirAccion(b.id)
  }

  const primeraBanda = mes.comercial[0]?.id

  return (
    <div className="space-y-6">
      {editable && filtro !== 'retail' && (
        <div className="flex flex-wrap gap-2">
          {filtro !== 'envios' && primeraBanda && (
            <NuevaAccion bandas={mes.comercial.map(b => b.id)} diaInicial={diaInicial} />
          )}
          {filtro !== 'comercial' && (['email', 'whatsapp', 'push'] as const).map(canal => (
            <button
              key={canal}
              type="button"
              onClick={() => abrirEditor({ seccion: 'envio', banda: canal, carril: 0, barra: null, fechaInicial: diaInicial })}
              className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-brand-300 hover:text-brand-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
            >
              {ICONO_CANAL[canal]} Envío por {tituloDeCanal(canal)}
            </button>
          ))}
        </div>
      )}

      {grupos.length === 0 && (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center dark:border-slate-700 dark:bg-slate-900">
          <p className="text-base font-semibold text-slate-700 dark:text-slate-200">
            No hay nada cargado en {nombreMes(mes.clave)}
          </p>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            {editable ? 'Creá la primera acción con el botón de arriba.' : 'Cuando se cargue una acción va a aparecer acá.'}
          </p>
        </div>
      )}

      {grupos.map(g => (
        <section key={g.titulo}>
          <header className="mb-3 flex items-baseline gap-2">
            <h2 className="text-base font-bold text-slate-900 dark:text-slate-100">{g.titulo}</h2>
            <span className="text-sm text-slate-500 dark:text-slate-400">{g.bajada}</span>
            <span className="ml-auto rounded-full bg-slate-200/70 px-2.5 py-0.5 text-xs font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              {g.barras.length}
            </span>
          </header>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {g.barras.map(b => (
              <Tarjeta key={b.id} barra={b} personas={personas} hoy={hoy} onAbrir={() => abrir(b)} />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}

/** Crear una acción desde la lista: primero se elige de qué tipo es. */
function NuevaAccion({ bandas, diaInicial }: { bandas: string[]; diaInicial: string }) {
  const abrirEditor = useCalendario(s => s.abrirEditor)
  return (
    <label className="flex items-center gap-2 rounded-xl bg-brand-600 py-1 pl-3.5 pr-1 text-sm font-semibold text-white shadow-sm">
      <Plus className="h-4 w-4" /> Nueva acción
      <select
        value=""
        onChange={e => {
          if (e.target.value) abrirEditor({ seccion: 'comercial', banda: e.target.value, carril: 0, barra: null, fechaInicial: diaInicial })
        }}
        className="max-w-[12rem] cursor-pointer rounded-lg border-0 bg-white/15 py-1.5 pl-2 pr-7 text-sm font-semibold text-white outline-none [&>option]:text-slate-900"
        aria-label="Tipo de la acción nueva"
      >
        <option value="">de qué tipo…</option>
        {bandas.map(b => <option key={b} value={b}>{b}</option>)}
      </select>
    </label>
  )
}

'use client'

import { useState } from 'react'
import { CalendarDays, Eye, EyeOff, Star } from 'lucide-react'
import { CabeceraDias, EtiquetaBanda, FilaRejilla, useAnchoTotal } from './Rejilla'
import { MarcoScroll } from './MarcoScroll'
import { NuevaAccion } from './NuevaAccion'
import { Seccion } from './Seccion'
import { esBandaRetirada, esSinCategoria, nivelDeCategoria } from '@/lib/calendario/categorias'
import { diaDeHoy, hoyIso, isoDe } from '@/lib/calendario/fechas'
import { semaforoDe } from '@/lib/calendario/semaforo'
import { useCalendario, useMesActivo } from '@/lib/calendario/store'
import { usePermisosCalendario } from '@/lib/calendario/permisos'

export function CalendarioComercial() {
  const mes = useMesActivo()
  const abrirEditor = useCalendario(s => s.abrirEditor)
  const abrirAccion = useCalendario(s => s.abrirAccion)
  const ancho = useAnchoTotal(mes.dias)
  const hoy = diaDeHoy(mes.clave)
  const { editable } = usePermisosCalendario()
  const barras = useCalendario(s => s.barras)

  /** "2/5": cuántas tareas de la acción están hechas. Sin tareas, nada. */
  const tareasDe = (id: string) => {
    const tareas = barras[id]?.tareas ?? []
    if (tareas.length === 0) return null
    return `${tareas.filter(t => t.estado === 'hecha').length}/${tareas.length}`
  }

  // En un mes se usan pocas categorías: la mayoría de las filas quedan vacías
  // y hay que recorrerlas para encontrar algo. Se pueden esconder las que no
  // tienen nada este mes; para cargar en una vacía se vuelven a ver.
  const [soloConAcciones, setSoloConAcciones] = useState(false)
  const bandas = soloConAcciones
    ? mes.comercial.filter(b => b.filas.some(f => f.length > 0))
    : mes.comercial
  const vacias = mes.comercial.length - mes.comercial.filter(b => b.filas.some(f => f.length > 0)).length

  const acciones = mes.comercial.reduce((n, b) => n + b.filas.reduce((m, f) => m + f.length, 0), 0)

  return (
    <Seccion
      icono={<CalendarDays className="h-4 w-4" />}
      titulo="Calendario comercial"
      bajada="Las acciones por categoría. Tocá una acción para ver sus tareas, sus piezas y sus avisos."
      contador={`${acciones} acciones`}
      acciones={vacias > 0 || editable ? (
        <div className="flex w-full items-center gap-2 sm:w-auto">
          {vacias > 0 && (
            <button
              type="button"
              onClick={() => setSoloConAcciones(v => !v)}
              aria-pressed={soloConAcciones}
              title={soloConAcciones
                ? (vacias === 1 ? 'Ver la categoría vacía' : `Ver las ${vacias} categorías vacías`)
                : 'Ocultar categorías vacías'}
              className={`flex min-h-[44px] shrink-0 items-center gap-1.5 rounded-xl border px-3 text-xs font-semibold transition active:scale-[.98] sm:min-h-[40px] ${
                soloConAcciones
                  ? 'border-brand-200 bg-brand-50 text-brand-700 hover:bg-brand-100 dark:border-brand-500/30 dark:bg-brand-500/10 dark:text-brand-200'
                  : 'border-slate-300 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800'
              }`}
            >
              {soloConAcciones ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
              {/* En el teléfono, corto: que entre al lado de "Nueva acción" */}
              <span className="sm:hidden">{soloConAcciones ? `Ver vacías (${vacias})` : 'Ocultar vacías'}</span>
              <span className="hidden sm:inline">
                {soloConAcciones
                  ? (vacias === 1 ? 'Ver la categoría vacía' : `Ver las ${vacias} categorías vacías`)
                  : 'Ocultar categorías vacías'}
              </span>
            </button>
          )}
          {/* "Nueva acción y punto" también acá, no solo en la lista: nace sin
              categoría y se abre su ficha. El + de cada fila sigue creando en
              esa categoría, sin abrirla, para cargar varias seguidas. */}
          {editable && <NuevaAccion diaInicial={isoDe(mes.clave, hoy ?? 1)} />}
        </div>
      ) : undefined}
    >
      <MarcoScroll ancho={ancho}>
          <CabeceraDias mes={mes} hoy={hoy} titulo="Categoría" />

          {bandas.map(banda => {
            const sin = esSinCategoria(banda.id)
            // Una fila retirada (Tienda Farma, que ahora tiene su mundo) se ve
            // mientras le queden acciones, pero ya no se le carga nada nuevo:
            // ni el + ni el clic en un día vacío.
            const retirada = esBandaRetirada(banda.id)
            const seCarga = editable && !retirada
            // La fila dice lo mismo que la cocarda: MEGA EVENTO con su
            // estrella, Mailing GRAL y Especiales con un punto de la marca, y
            // el resto sin nada.
            const nivel = nivelDeCategoria(banda.id)
            return (
              <div key={banda.id} className="flex">
                <EtiquetaBanda
                  filas={banda.filas.length}
                  tono={sin || retirada ? 'grupo' : nivel === 'mega' ? 'destacada' : 'normal'}
                  titulo={banda.nombre}
                  extra={retirada
                    ? <span className="text-[10px] font-semibold uppercase leading-none tracking-wide text-slate-500 dark:text-slate-400">Ya no se usa</span>
                    : undefined}
                  onAgregar={seCarga
                    ? () => abrirEditor({ seccion: 'comercial', banda: banda.id, carril: 0, barra: null, fechaInicial: isoDe(mes.clave, hoy ?? 1) })
                    : undefined}
                  tituloAgregar={sin ? 'Nueva acción sin categoría' : `Nueva acción en ${banda.nombre}`}
                >
                  {nivel === 'mega' ? (
                    <span className="flex items-center gap-1.5">
                      <Star className="h-3.5 w-3.5 shrink-0 fill-amber-400 text-amber-400" aria-hidden />
                      <span className="min-w-0">{banda.nombre}</span>
                    </span>
                  ) : nivel === 'general' || nivel === 'especial' ? (
                    <span className="flex items-center gap-1.5">
                      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" aria-hidden />
                      <span className="min-w-0">{banda.nombre}</span>
                    </span>
                  ) : sin ? (
                    <span className="italic">{banda.nombre}</span>
                  ) : banda.nombre}
                </EtiquetaBanda>
                <div className="flex-1">
                  {banda.filas.map((fila, i) => (
                    <FilaRejilla
                      interna={i < banda.filas.length - 1}
                      key={i}
                      mes={mes}
                      fila={fila}
                      hoy={hoy}
                      editable
                      onBarra={b => abrirAccion(b.id)}
                      detalleDe={b => tareasDe(b.id)}
                      semaforoDe={b => semaforoDe(barras[b.id], hoyIso())}
                      onDiaVacio={seCarga
                        ? d => abrirEditor({ seccion: 'comercial', banda: banda.id, carril: i, barra: null, fechaInicial: isoDe(mes.clave, d) })
                        : undefined}
                    />
                  ))}
                </div>
              </div>
            )
          })}
      </MarcoScroll>
    </Seccion>
  )
}

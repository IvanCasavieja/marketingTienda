'use client'

import { useEffect, useRef, useState } from 'react'
import { ArrowRightLeft, Building2, CalendarClock, FileImage, RotateCcw, UserRound } from 'lucide-react'
import { proximoPaso, tipoDePieza, type Columna, type Tarjeta } from '@/lib/calendario/entregas'
import { defColumna, queHaceMover, quienLaHaceTexto, textoDeFecha } from '@/lib/calendario/tablero'
import { mundoDe } from '@/lib/mundos'
import { useVistaEntregas } from '@/store/entregas'
import { FasesCompactas } from './LineaDeFases'
import { Miniatura } from './ImagenConMarcas'

/**
 * Una tarjeta del tablero (y de "Mis tareas" y el buscador): qué pieza es, de
 * qué acción (con el color de su mundo), para cuándo, quién la hace y —lo
 * importante— a quién le toca. Tocarla abre su detalle (brief, versiones,
 * marcas, entregar, revisar).
 *
 * En el tablero además se arrastra (ver app/(dashboard)/entregas/page.tsx) y
 * tiene "Mover a…", que hace lo mismo sin arrastrar: en el teléfono es lo más
 * cómodo, y con el teclado, lo único.
 */
export function TarjetaEntrega({
  tarjeta, usuarioId, hoy, orden = 0, onMoverA, onPointerDown, arrastrandose = false, fantasma = false, mostrarQuien = true,
}: {
  tarjeta: Tarjeta
  usuarioId: number | null
  hoy: string
  orden?: number
  /** Con esto, la tarjeta ofrece "Mover a…" (las columnas que el servidor dice que puede). */
  onMoverA?: (a: Columna) => void
  /** Para arrastrarla (el tablero). */
  onPointerDown?: (e: React.PointerEvent<HTMLDivElement>) => void
  /** Es la que se está arrastrando: queda su lugar marcado. */
  arrastrandose?: boolean
  /** La copia que sigue al puntero mientras se arrastra. */
  fantasma?: boolean
  /** Quién la hace. La agencia no necesita leer su propio nombre en cada tarjeta. */
  mostrarQuien?: boolean
}) {
  const abrir = useVistaEntregas(s => s.abrir)
  const r = tarjeta.entrega
  const nombreDe = (id: number | null) => (id != null && id === r.aprobadorDeTurno ? tarjeta.turno : tarjeta.responsable) ?? 'alguien'
  // `false` y no `puedo.decidir`: quien tiene calendario.tareas puede decidir
  // CUALQUIERA como respaldo, y con eso todas las tarjetas le decían "Te toca:
  // revisar". A quien le toca de verdad lo reconoce proximoPaso por el turno.
  const paso = proximoPaso(r, tarjeta.asignadoA, usuarioId, nombreDe, false, {
    entregoYo: tarjeta.puedo?.entregar, hace: tarjeta.hace,
  })
  const meToca = paso.aQuien === 'vos'
  const fecha = textoDeFecha(tarjeta, hoy)
  const mundo = mundoDe(tarjeta.accion.mundo)
  const quien = mostrarQuien ? quienLaHaceTexto(tarjeta.hace) : null
  const destinos = tarjeta.puedo?.mover ?? []
  const terminada = tarjeta.columna === 'finalizado' || tarjeta.columna === 'archivado'

  return (
    <li
      style={fantasma ? undefined : { animationDelay: `${Math.min(orden, 8) * 25}ms` }}
      className={fantasma ? '' : 'animate-rise'}
    >
      <div
        onPointerDown={onPointerDown}
        data-tarjeta={tarjeta.tareaId}
        className={`group relative rounded-2xl border bg-white shadow-card transition-[box-shadow,transform,opacity] dark:bg-slate-900 ${
          arrastrandose ? 'opacity-40 ring-2 ring-dashed ring-slate-400 dark:ring-slate-500' : ''
        } ${fantasma ? 'rotate-[1.5deg] shadow-2xl ring-2 ring-brand-400' : 'hover:shadow-card-hover'} ${
          meToca && !terminada ? 'border-brand-400 dark:border-brand-500/60' : 'border-slate-300 dark:border-slate-700'
        } ${onPointerDown ? 'cursor-grab touch-pan-y select-none [-webkit-touch-callout:none] active:cursor-grabbing' : ''}`}
      >
        {/* El color del mundo, como un lomo a la izquierda. */}
        <span aria-hidden className="absolute inset-y-2 left-0 w-1 rounded-r-full" style={{ backgroundColor: mundo?.color ?? '#94a3b8' }} />
        <button
          type="button"
          onClick={() => abrir(tarjeta.tareaId, paso.accion === 'revisar' ? 'revisar' : paso.accion === 'entregar' ? 'entregar' : 'ver')}
          className="flex w-full flex-col gap-2 rounded-2xl py-3 pl-4 pr-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
        >
          <span className="flex min-w-0 items-center gap-1.5 text-xs font-medium text-slate-600 dark:text-slate-300">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full ring-1 ring-inset ring-black/10 dark:ring-white/40" style={{ backgroundColor: tarjeta.accion.color ?? mundo?.color ?? '#cbd5e1' }} />
            <span className="truncate" title={mundo ? `${tarjeta.accion.nombre} · ${mundo.nombre}` : tarjeta.accion.nombre}>{tarjeta.accion.nombre}</span>
          </span>

          <span className="flex items-start gap-2.5">
            <span className="min-w-0 flex-1 text-[15px] font-semibold leading-snug text-slate-900 line-clamp-3 dark:text-slate-50">
              {tarjeta.titulo}
            </span>
            {tarjeta.miniatura ? (
              <Miniatura imagenId={tarjeta.miniatura} etiqueta={`La última versión de ${tarjeta.titulo}`} className="h-12 w-12" perezosa />
            ) : !tarjeta.tipo ? (
              <span className="flex h-12 w-12 shrink-0 flex-col items-center justify-center gap-0.5 rounded-lg bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400" aria-hidden>
                <FileImage className="h-4 w-4" />
                <span className="text-[8px] font-bold uppercase">{tipoDePieza(r.tipoPieza).nombre.slice(0, 7)}</span>
              </span>
            ) : null}
          </span>

          {(tarjeta.opciones?.length ?? 0) > 0 && (
            <span className="line-clamp-2 text-xs text-slate-600 dark:text-slate-300">{tarjeta.opciones!.join(' · ')}</span>
          )}

          {fecha && (
            <span className={`flex items-start gap-1.5 text-xs font-medium ${fecha.vencida ? 'text-rose-700 dark:text-rose-300' : 'text-slate-600 dark:text-slate-300'}`}>
              <CalendarClock className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
              <span>{fecha.vencida ? `Venció · ${fecha.texto}` : fecha.texto}</span>
            </span>
          )}

          <span className="flex flex-wrap items-center gap-1.5">
            {tarjeta.volvioConCambios && (
              <span className="flex items-center gap-1 rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-bold text-rose-800 dark:bg-rose-500/20 dark:text-rose-200">
                <RotateCcw className="h-3 w-3" aria-hidden /> Volvió con cambios
              </span>
            )}
            {r.ronda > 0 && (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                Ronda {r.ronda}
              </span>
            )}
            {r.fases.length > 1 && <FasesCompactas resumen={r} />}
          </span>

          {!terminada && (
            <span className={`rounded-lg px-2 py-1.5 text-xs font-semibold leading-snug ${
              meToca ? 'bg-brand-50 text-brand-800 dark:bg-brand-500/15 dark:text-brand-100' : 'bg-slate-50 text-slate-700 dark:bg-slate-800/70 dark:text-slate-200'
            }`}>
              {paso.texto}
            </span>
          )}
        </button>

        {(quien || (onMoverA && destinos.length > 0)) && (
          <div className="flex items-center gap-2 border-t border-slate-200 py-1.5 pl-4 pr-1.5 dark:border-slate-800">
            {quien && (
              <span className="flex min-w-0 flex-1 items-center gap-1 text-xs text-slate-600 dark:text-slate-300">
                {tarjeta.hace?.tipo === 'tienda' ? <UserRound className="h-3.5 w-3.5 shrink-0" /> : <Building2 className="h-3.5 w-3.5 shrink-0" />}
                <span className="truncate">{quien}</span>
              </span>
            )}
            {onMoverA && destinos.length > 0 && !fantasma && (
              <MoverA tarjeta={tarjeta} destinos={destinos} onMoverA={onMoverA} />
            )}
          </div>
        )}
      </div>
    </li>
  )
}

/** "Mover a…": las columnas a las que la puede llevar quien mira, con lo que
 *  hace cada una ("Pedir cambios", "Aprobar"). Es lo mismo que arrastrar. */
function MoverA({ tarjeta, destinos, onMoverA }: { tarjeta: Tarjeta; destinos: Columna[]; onMoverA: (a: Columna) => void }) {
  const [abierto, setAbierto] = useState(false)
  const caja = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!abierto) return
    const fuera = (e: PointerEvent) => { if (!caja.current?.contains(e.target as Node)) setAbierto(false) }
    const tecla = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); setAbierto(false) } }
    document.addEventListener('pointerdown', fuera)
    window.addEventListener('keydown', tecla, true)
    return () => { document.removeEventListener('pointerdown', fuera); window.removeEventListener('keydown', tecla, true) }
  }, [abierto])
  return (
    <div ref={caja} className="relative ml-auto" onPointerDown={e => e.stopPropagation()}>
      <button
        type="button"
        onClick={() => setAbierto(v => !v)}
        aria-expanded={abierto}
        aria-haspopup="menu"
        aria-label={`Mover a… (${tarjeta.titulo})`}
        title="Mover a otra columna"
        className="flex min-h-[36px] items-center gap-1 rounded-lg px-2 text-xs font-semibold text-slate-700 transition hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
      >
        <ArrowRightLeft className="h-3.5 w-3.5" aria-hidden />
        {/* En la notebook las columnas son angostas y se arrastra: el ícono
            alcanza (y deja leer quién la hace). En el teléfono, con texto. */}
        <span className="md:sr-only 2xl:not-sr-only">Mover</span>
      </button>
      {abierto && (
        <div role="menu" aria-label={`Mover ${tarjeta.titulo}`}
          className="absolute bottom-full right-0 z-20 mb-1 w-56 animate-scale-in overflow-hidden rounded-xl border border-slate-300 bg-white py-1 shadow-panel dark:border-slate-700 dark:bg-slate-900">
          {destinos.map(a => (
            <button
              key={a}
              type="button"
              role="menuitem"
              onClick={() => { setAbierto(false); onMoverA(a) }}
              className="flex min-h-[44px] w-full items-center gap-2.5 px-3 text-left text-sm text-slate-800 transition hover:bg-slate-100 dark:text-slate-100 dark:hover:bg-slate-800"
            >
              <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${defColumna(a).punto}`} aria-hidden />
              <span className="min-w-0">
                <span className="block font-semibold">{defColumna(a).titulo}</span>
                <span className="block text-xs text-slate-500 dark:text-slate-400">{queHaceMover(tarjeta.columna, a)}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

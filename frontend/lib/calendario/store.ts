'use client'

import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { construirMes, derivarHeader, nuevoId } from './derivar'
import { SEED_VERSION } from './seed'
import { ZOOM_POR_DEFECTO, limitarZoom } from './rejilla'

export { ZOOMS, ZOOM_POR_DEFECTO } from './rejilla'
import type {
  AreaPieza, Barra, EstadoPieza, Mes, Notificacion, Pieza, Seccion,
} from './tipos'

export { construirMes, derivarHeader, accionesDe, ocupacionHeader } from './derivar'
export type { EstadoDia, OcupacionDia } from './derivar'

// ---------------------------------------------------------------------------
// Quien lleva Retail Media: se le avisa cuando le mueven las posiciones.
// Es un nombre fijo porque la notificacion todavia vive en memoria; cuando
// pase a ser un POST va a ser el id del usuario que tenga ese rol.
// ---------------------------------------------------------------------------
export const DUENO_RETAIL = 'Macarena'

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export type Edicion = {
  seccion: Seccion
  bandaId: string
  filaIdx: number
  /** null = alta de una barra nueva */
  barra: Barra | null
  diaInicial?: number
}

/** Dónde vive una acción dentro del calendario comercial. */
export type Ubicacion = { bandaId: string; filaIdx: number; barraId: string }



type Estado = {
  meses: Record<string, Mes>
  mesActivo: string
  notificaciones: Notificacion[]
  edicion: Edicion | null
  abierta: Ubicacion | null
  /** Ancho de cada día en px. Sube y baja con el control de zoom. */
  zoom: number
  /** Firma del Excel con el que se armaron los meses guardados. */
  seedVersion: string

  mes: () => Mes
  accionAbierta: () => Barra | null
  irAMes: (clave: string) => void
  setZoom: (px: number) => void

  abrirEditor: (e: Edicion) => void
  cerrarEditor: () => void
  abrirAccion: (u: Ubicacion) => void
  cerrarAccion: () => void

  guardarBarra: (datos: Pick<Barra, 'nombre' | 'desde' | 'hasta' | 'color'>) => void
  borrarBarra: () => void
  /** `autor` es el nombre del usuario logueado: firma la notificacion. */
  moverPosicionesRM: (posiciones: number[], autor: string) => void
  marcarLeidas: () => void

  agregarPieza: (area: AreaPieza, formato: string) => void
  quitarPieza: (piezaId: string) => void
  actualizarPieza: (piezaId: string, cambios: Partial<Pieza>) => void
}

/** Marca el mes como editado a mano: deja de rehacerse cuando cambia el Excel. */
function tocado(mes: Mes): Mes {
  return mes.tocado ? mes : { ...mes, tocado: true }
}

/** Aplica un cambio sobre las piezas de la acción abierta y re-deriva. */
function conPiezas(mes: Mes, u: Ubicacion, fn: (piezas: Pieza[]) => Pieza[]): Mes {
  const comercial = mes.comercial.map(banda =>
    banda.id !== u.bandaId ? banda : {
      ...banda,
      filas: banda.filas.map((fila, i) =>
        i !== u.filaIdx ? fila : fila.map(b =>
          b.id !== u.barraId ? b : { ...b, piezas: fn(b.piezas ?? []) })),
    })
  return derivarHeader(tocado({ ...mes, comercial }))
}

export const useCalendario = create<Estado>()(
  persist(
    (set, get) => ({
      meses: { '2026-09': construirMes('2026-09'), '2026-10': construirMes('2026-10') },
      mesActivo: '2026-09',
      notificaciones: [],
      edicion: null,
      abierta: null,
      zoom: ZOOM_POR_DEFECTO,
      seedVersion: SEED_VERSION,

      mes: () => get().meses[get().mesActivo],

      accionAbierta: () => {
        const { abierta, meses, mesActivo } = get()
        if (!abierta) return null
        const banda = meses[mesActivo]?.comercial.find(b => b.id === abierta.bandaId)
        return banda?.filas[abierta.filaIdx]?.find(b => b.id === abierta.barraId) ?? null
      },

      irAMes: clave => set(s => ({
        mesActivo: clave,
        abierta: null,
        meses: s.meses[clave] ? s.meses : { ...s.meses, [clave]: construirMes(clave) },
      })),

      setZoom: px => set({ zoom: limitarZoom(px) }),
      abrirEditor: e => set({ edicion: e }),
      cerrarEditor: () => set({ edicion: null }),
      abrirAccion: u => set({ abierta: u }),
      cerrarAccion: () => set({ abierta: null }),
      marcarLeidas: () => set(s => ({ notificaciones: s.notificaciones.map(n => ({ ...n, leida: true })) })),

      guardarBarra: datos => {
        const { edicion, mesActivo } = get()
        if (!edicion) return
        set(s => {
          const mes = s.meses[mesActivo]
          const bandas = mes[edicion.seccion].map(banda => {
            if (banda.id !== edicion.bandaId) return banda
            return {
              ...banda,
              filas: banda.filas.map((fila, i) => {
                if (i !== edicion.filaIdx) return fila
                if (edicion.barra) {
                  return fila.map(b => (b.id === edicion.barra!.id ? { ...b, ...datos } : b))
                }
                const nueva: Barra = { id: nuevoId('br'), ...datos, piezas: [] }
                if (edicion.seccion === 'header') nueva.origen = { tipo: 'manual' }
                return [...fila, nueva].sort((a, b) => a.desde - b.desde)
              }),
            }
          })
          return {
            meses: { ...s.meses, [mesActivo]: derivarHeader(tocado({ ...mes, [edicion.seccion]: bandas })) },
            edicion: null,
          }
        })
      },

      borrarBarra: () => {
        const { edicion, mesActivo } = get()
        if (!edicion?.barra) return
        set(s => {
          const mes = s.meses[mesActivo]
          const bandas = mes[edicion.seccion].map(banda =>
            banda.id !== edicion.bandaId ? banda : {
              ...banda,
              filas: banda.filas.map((fila, i) =>
                i === edicion.filaIdx ? fila.filter(b => b.id !== edicion.barra!.id) : fila),
            })
          return {
            meses: { ...s.meses, [mesActivo]: derivarHeader(tocado({ ...mes, [edicion.seccion]: bandas })) },
            edicion: null,
            abierta: s.abierta?.barraId === edicion.barra!.id ? null : s.abierta,
          }
        })
      },

      moverPosicionesRM: (posiciones, autor) => {
        const { mesActivo, meses } = get()
        const antes = meses[mesActivo].posicionesRM
        if (antes.join() === posiciones.join()) return

        set(s => ({
          meses: {
            ...s.meses,
            [mesActivo]: derivarHeader(tocado({ ...s.meses[mesActivo], posicionesRM: posiciones })),
          },
          notificaciones: [{
            id: nuevoId('ntf'),
            tipo: 'calendario_header',
            mensaje: `${autor} movió las posiciones de Retail Media en ${mesActivo}: ${antes.join(', ')} → ${posiciones.join(', ')}`,
            leida: false,
            origen_tipo: 'header_posiciones_rm',
            origen_ref: `${mesActivo}:${posiciones.join('-')}`,
            destinatario: DUENO_RETAIL,
            created_at: new Date().toISOString(),
          }, ...s.notificaciones],
        }))
      },

      agregarPieza: (area, formato) => {
        const { abierta, mesActivo } = get()
        if (!abierta) return
        set(s => ({
          meses: {
            ...s.meses,
            [mesActivo]: conPiezas(s.meses[mesActivo], abierta, piezas =>
              piezas.some(p => p.area === area && p.formato === formato)
                ? piezas
                : [...piezas, { id: nuevoId('pz'), area, formato, estado: 'pendiente' as EstadoPieza }]),
          },
        }))
      },

      quitarPieza: piezaId => {
        const { abierta, mesActivo } = get()
        if (!abierta) return
        set(s => ({
          meses: {
            ...s.meses,
            [mesActivo]: conPiezas(s.meses[mesActivo], abierta, p => p.filter(x => x.id !== piezaId)),
          },
        }))
      },

      actualizarPieza: (piezaId, cambios) => {
        const { abierta, mesActivo } = get()
        if (!abierta) return
        set(s => ({
          meses: {
            ...s.meses,
            [mesActivo]: conPiezas(s.meses[mesActivo], abierta, p =>
              p.map(x => (x.id === piezaId ? { ...x, ...cambios } : x))),
          },
        }))
      },
    }),
    {
      name: 'calendario-mktg',
      version: 1,
      storage: createJSONStorage(() => localStorage),
      // El servidor no tiene localStorage: se rehidrata a mano al montar,
      // asi no hay diferencia entre lo que pinta el server y lo que pinta el cliente.
      skipHydration: true,
      /**
       * Al volver del guardado: si los Excel se reimportaron desde la última
       * vez, se rehacen los meses que nadie tocó, para que el dato nuevo
       * aparezca solo. Los meses con ediciones a mano se respetan.
       */
      merge: (guardado, actual) => {
        const g = guardado as Partial<Estado> | undefined
        if (!g) return actual
        const mismosDatos = g.seedVersion === SEED_VERSION
        const meses = Object.fromEntries(
          Object.entries(g.meses ?? {}).map(([clave, mes]) =>
            [clave, mismosDatos || mes.tocado ? mes : construirMes(clave)]),
        )
        return { ...actual, ...g, meses, seedVersion: SEED_VERSION }
      },
      partialize: s => ({
        meses: s.meses,
        seedVersion: SEED_VERSION,
        mesActivo: s.mesActivo,
        zoom: s.zoom,
        notificaciones: s.notificaciones,
      }),
    },
  ),
)

'use client'

import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { calendarioApi } from '@/lib/api'
import { construirMes, derivarHeader, nuevoId } from './derivar'
import { SEED_VERSION } from './seed'
import { ZOOM_POR_DEFECTO, limitarZoom } from './rejilla'

export { ZOOMS, ZOOM_POR_DEFECTO } from './rejilla'
import type {
  AreaPieza, Barra, EstadoPieza, Mes, Pieza, Seccion,
} from './tipos'

export { construirMes, derivarHeader, accionesDe, ocupacionHeader } from './derivar'
export type { EstadoDia, OcupacionDia } from './derivar'

// ---------------------------------------------------------------------------
// Guardado contra el servidor
// ---------------------------------------------------------------------------
// El calendario vivia en localStorage: cada navegador tenia su copia y el
// servidor no sabia que existiera ninguna accion, asi que no podia avisar nada
// con anticipacion. Ahora cada cambio sube, con un respiro para no mandar un
// PUT por cada tecla al arrastrar una barra. localStorage queda como caché
// para que la pantalla no arranque en blanco.
const ESPERA_ANTES_DE_GUARDAR = 800

const pendientes = new Map<string, ReturnType<typeof setTimeout>>()

function subirMes(clave: string, mes: Mes) {
  clearTimeout(pendientes.get(clave))
  pendientes.set(clave, setTimeout(() => {
    pendientes.delete(clave)
    calendarioApi.guardarMes(clave, mes).catch(() => {
      // Si falla, lo guardado en el navegador sigue estando: no se pierde el
      // trabajo, y el proximo cambio reintenta con el mes entero.
    })
  }, ESPERA_ANTES_DE_GUARDAR))
}

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
  /** Trae del servidor lo guardado y pisa la copia local. */
  traerDelServidor: () => Promise<void>

  abrirEditor: (e: Edicion) => void
  cerrarEditor: () => void
  abrirAccion: (u: Ubicacion) => void
  cerrarAccion: () => void

  guardarBarra: (datos: Pick<Barra, 'nombre' | 'desde' | 'hasta' | 'color'>) => void
  borrarBarra: () => void
  /** Avisa por las notificaciones de la plataforma a quien lleva Retail Media. */
  moverPosicionesRM: (posiciones: number[]) => void

  agregarPieza: (area: AreaPieza, formato: string) => void
  quitarPieza: (piezaId: string) => void
  actualizarPieza: (piezaId: string, cambios: Partial<Pieza>) => void
}

/** Deja el mes listo para guardar y lo sube. Todo cambio pasa por aca. */
function guardado(clave: string, mes: Mes): Mes {
  subirMes(clave, mes)
  return mes
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
        // Un mes que se abre por primera vez se sube armado: asi el aviso de
        // los 10 dias lo ve sin que nadie tenga que editarlo.
        meses: s.meses[clave] ? s.meses : { ...s.meses, [clave]: guardado(clave, construirMes(clave)) },
      })),

      setZoom: px => set({ zoom: limitarZoom(px) }),

      traerDelServidor: async () => {
        try {
          const { data } = await calendarioApi.traerMeses()
          if (!data || Object.keys(data).length === 0) {
            // Primera vez: todavia no hay nada guardado. Se sube lo que hay en
            // esta maquina para que el servidor arranque con algo real.
            for (const [clave, mes] of Object.entries(get().meses)) subirMes(clave, mes)
            return
          }
          // Lo del servidor manda: es lo que ve el resto del equipo.
          set(s => ({ meses: { ...s.meses, ...(data as Record<string, Mes>) } }))
        } catch {
          // Sin servidor se sigue trabajando con la copia local.
        }
      },
      abrirEditor: e => set({ edicion: e }),
      cerrarEditor: () => set({ edicion: null }),
      abrirAccion: u => set({ abierta: u }),
      cerrarAccion: () => set({ abierta: null }),

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
            meses: { ...s.meses, [mesActivo]: guardado(mesActivo, derivarHeader(tocado({ ...mes, [edicion.seccion]: bandas }))) },
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
            meses: { ...s.meses, [mesActivo]: guardado(mesActivo, derivarHeader(tocado({ ...mes, [edicion.seccion]: bandas }))) },
            edicion: null,
            abierta: s.abierta?.barraId === edicion.barra!.id ? null : s.abierta,
          }
        })
      },

      moverPosicionesRM: posiciones => {
        const { mesActivo, meses } = get()
        const antes = meses[mesActivo].posicionesRM
        if (antes.join() === posiciones.join()) return

        set(s => {
          const mes = derivarHeader(tocado({ ...s.meses[mesActivo], posicionesRM: posiciones }))
          subirMes(mesActivo, mes)
          return { meses: { ...s.meses, [mesActivo]: mes } }
        })
        // El aviso va a las notificaciones de la plataforma, no a una bandeja
        // propia del calendario: la campanita del menu ya existe y es por
        // persona. Le llega a quien tenga calendario.retail_media.
        calendarioApi.avisarRetail(mesActivo, antes, posiciones).catch(() => {})
      },

      agregarPieza: (area, formato) => {
        const { abierta, mesActivo } = get()
        if (!abierta) return
        set(s => ({
          meses: {
            ...s.meses,
            [mesActivo]: guardado(mesActivo, conPiezas(s.meses[mesActivo], abierta, piezas =>
              piezas.some(p => p.area === area && p.formato === formato)
                ? piezas
                : [...piezas, { id: nuevoId('pz'), area, formato, estado: 'pendiente' as EstadoPieza }])),
          },
        }))
      },

      quitarPieza: piezaId => {
        const { abierta, mesActivo } = get()
        if (!abierta) return
        set(s => ({
          meses: {
            ...s.meses,
            [mesActivo]: guardado(mesActivo, conPiezas(s.meses[mesActivo], abierta, p => p.filter(x => x.id !== piezaId))),
          },
        }))
      },

      actualizarPieza: (piezaId, cambios) => {
        const { abierta, mesActivo } = get()
        if (!abierta) return
        set(s => ({
          meses: {
            ...s.meses,
            [mesActivo]: guardado(mesActivo, conPiezas(s.meses[mesActivo], abierta, p =>
              p.map(x => (x.id === piezaId ? { ...x, ...cambios } : x)))),
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
      }),
    },
  ),
)

'use client'

import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { toast } from 'sonner'
import { calendarioApi } from '@/lib/api'
import { carrilLibre, headerDerivado, nuevoId, vistaDelMes } from './derivar'
import { claveDe, hoyIso } from './fechas'
import { ZOOM_POR_DEFECTO, limitarZoom } from './rejilla'

export { ZOOMS, ZOOM_POR_DEFECTO } from './rejilla'
import { SECCIONES_CON_FICHA, conDescendientes, formatosDeCanal } from './tipos'
import type {
  AreaPieza, Aviso, BarraGuardada, EstadoPieza, EstadoTarea, Mes, Persona, Pieza, Seccion, Tarea,
} from './tipos'
import { BANDAS_COMERCIAL, BANDAS_RETAIL, type BandaCatalogo } from './catalogo'
import { MUNDO_POR_DEFECTO, mundoDe } from '@/lib/mundos'

export {
  construirMes, derivarHeaders, accionesDe, ocupacionHeader,
  enviosDelMes, filasDeEnvios, headerEnFecha,
} from './derivar'
export type { EstadoDia, OcupacionDia, Envio, PosicionEnFecha, HeaderDerivado } from './derivar'

// ---------------------------------------------------------------------------
// Guardado contra el servidor
// ---------------------------------------------------------------------------
// Hasta el 28/09/2026 cada cambio subia el MES ENTERO: dos personas editando
// el mismo mes se pisaban y ganaba la ultima que guardaba. Ahora cada cambio
// viaja solo (una barra, una pieza, un aviso) y el servidor escribe solo eso.
//
// Para ver lo que hacen los demas, cada tanto se le pregunta al servidor si la
// revision cambio (ver sincronizar). Si cambio, se trae todo y se reemplaza lo
// local. Mientras haya un cambio propio en viaje no se reemplaza nada: la
// respuesta podria ser de antes de ese cambio y lo haria "desaparecer".

/** Cuantos cambios propios estan en viaje. */
let enVuelo = 0
/** La revision mas alta que devolvio un cambio propio: nada mas viejo se aplica. */
let revMinima = 0

/** Cada cuanto se pregunta si alguien cambio algo. */
export const SEGUNDOS_ENTRE_REVISIONES = 15

type Escrito = { rev?: number; enviadosAhora?: number; yaExistia?: boolean; avisados?: number }

/** Como se mira el mes: la linea de tiempo de siempre, o una lista de tarjetas. */
export type Vista = 'tiempo' | 'lista'
/** Que parte del calendario se ve. 'todo' = las cuatro, una abajo de la otra. */
export type Filtro = 'todo' | 'comercial' | 'envios' | 'retail' | 'header'

/** Lo que se carga de una tarea nueva. */
export type DatosTarea = {
  titulo: string
  parentId?: string | null
  asignadoA?: number | null
  vence?: string | null
  descripcion?: string | null
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export type Edicion = {
  seccion: Seccion
  /** A que banda va (o esta) la barra. */
  banda: string
  /** El renglon donde se hizo clic. Si esta ocupado en las fechas elegidas,
   *  la barra va al primero libre. */
  carril: number
  /** null = alta de una barra nueva */
  barra: BarraGuardada | null
  /** 'YYYY-MM-DD' del dia donde se hizo clic, para el alta. */
  fechaInicial?: string
}

/** Lo que se carga en el editor. Formato y hora solo en los envíos sueltos. */
export type DatosBarra = Pick<BarraGuardada, 'nombre' | 'desde' | 'hasta' | 'color'> &
  Partial<Pick<BarraGuardada, 'formato' | 'hora'>>

type Estado = {
  /** El mundo cuyas barras estan cargadas. Cada mundo es un calendario aparte. */
  mundo: string
  barras: Record<string, BarraGuardada>
  posicionesRM: Record<string, number[]>
  /** La revision del servidor que tenemos. null = hay que traer todo. */
  rev: number | null
  conexion: 'cargando' | 'ok' | 'sin-conexion'
  /** A quien se le puede mandar un aviso. */
  personas: Persona[]
  mesActivo: string
  edicion: Edicion | null
  /** El id de la accion con la ficha abierta. */
  abierta: string | null
  /** Ancho de cada día en px. Sube y baja con el control de zoom. */
  zoom: number
  /** false = nadie toco el zoom: el mes se ajusta solo al ancho de la pantalla. */
  zoomElegido: boolean
  vista: Vista
  filtro: Filtro

  accionAbierta: () => BarraGuardada | null
  irAMes: (clave: string) => void
  /** `elegido` = lo pidio la persona (y entonces ya no se ajusta solo). */
  setZoom: (px: number, elegido?: boolean) => void
  setVista: (v: Vista) => void
  setFiltro: (f: Filtro) => void
  /** Pasa a otro mundo: tira lo cargado y trae lo de ese. */
  usarMundo: (clave: string) => void
  /** Trae del servidor lo que haya cambiado y pisa la copia local. */
  sincronizar: () => Promise<void>
  traerPersonas: () => Promise<void>

  abrirEditor: (e: Edicion) => void
  cerrarEditor: () => void
  abrirAccion: (id: string) => void
  cerrarAccion: () => void

  guardarBarra: (datos: DatosBarra) => void
  borrarBarra: () => void
  /** Guarda las posiciones y avisa a quien lleva Retail Media. */
  moverPosicionesRM: (posiciones: number[]) => void

  agregarPieza: (area: AreaPieza, formato: string) => void
  quitarPieza: (piezaId: string) => void
  actualizarPieza: (piezaId: string, cambios: Partial<Pick<Pieza, 'estado' | 'desde' | 'hasta' | 'hora'>>) => void

  agregarAviso: (diasAntes: number, destinatarios: number[]) => void
  quitarAviso: (avisoId: string) => void

  /** El estado de un envío suelto (pendiente → publicado), desde su ficha. */
  cambiarEstadoEnvio: (id: string, estado: EstadoPieza) => void

  /** Una tarea (o subtarea) en la accion `barraId`. */
  crearTarea: (barraId: string, datos: DatosTarea) => void
  cambiarTarea: (tareaId: string, cambios: Partial<Pick<Tarea, 'titulo' | 'descripcion' | 'estado' | 'asignadoA' | 'vence'>>) => void
  /** Borra la tarea y todo lo que cuelga de ella. */
  borrarTarea: (tareaId: string) => void
}

/** Lo que llega del servidor, con las listas que el front da por sentadas. */
function normalizar(b: BarraGuardada): BarraGuardada {
  if (b.seccion === 'comercial') return { ...b, piezas: b.piezas ?? [], avisos: b.avisos ?? [], tareas: b.tareas ?? [] }
  if (b.seccion === 'envio') return { ...b, avisos: b.avisos ?? [], tareas: b.tareas ?? [], estado: b.estado ?? 'pendiente' }
  return b
}

/** La accion que tiene una pieza o un aviso. */
function duenaDe(barras: Record<string, BarraGuardada>, pred: (b: BarraGuardada) => boolean) {
  return Object.values(barras).find(pred) ?? null
}

export const useCalendario = create<Estado>()(
  persist(
    (set, get) => {
      /**
       * Manda un cambio. Lo local ya se cambio antes de llamar a esto, asi la
       * pantalla no espera al servidor. Si el servidor dice que no (la accion
       * la borro otra persona, se cayo la conexion), se avisa y se trae lo que
       * haya de verdad.
       */
      async function escribir(llamada: () => Promise<{ data: Escrito }>): Promise<Escrito | null> {
        enVuelo++
        try {
          const { data } = await llamada()
          if (data?.yaExistia) {
            // El servidor no escribió nada (otra persona ya había agregado lo
            // mismo, o era un reintento): lo local puede tener un id que allá
            // no existe. Se trae todo.
            set({ rev: null })
          } else if (data?.rev != null) {
            revMinima = Math.max(revMinima, data.rev)
            // Si nadie escribio en el medio, lo local ya ES esa revision: no
            // hace falta volver a bajarse todo.
            const { rev } = get()
            if (rev != null && data.rev === rev + 1) set({ rev: data.rev })
          }
          return data
        } catch (e) {
          const detalle = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
          toast.error(typeof detalle === 'string'
            ? detalle
            : 'No se pudo guardar el cambio. Se recargó el calendario con lo último guardado.')
          set({ rev: null })
          return null
        } finally {
          enVuelo--
          if (get().rev === null) void get().sincronizar()
        }
      }

      function cambiarBarraLocal(id: string, fn: (b: BarraGuardada) => BarraGuardada) {
        set(s => {
          const b = s.barras[id]
          return b ? { barras: { ...s.barras, [id]: fn(b) } } : {}
        })
      }

      return {
        mundo: MUNDO_POR_DEFECTO,
        barras: {},
        posicionesRM: {},
        rev: null,
        conexion: 'cargando',
        personas: [],
        mesActivo: claveDe(hoyIso()),
        edicion: null,
        abierta: null,
        zoom: ZOOM_POR_DEFECTO,
        zoomElegido: false,
        vista: 'tiempo',
        filtro: 'todo',

        accionAbierta: () => {
          const { abierta, barras } = get()
          const b = abierta ? barras[abierta] : undefined
          return b && SECCIONES_CON_FICHA.includes(b.seccion) ? b : null
        },

        irAMes: clave => set({ mesActivo: clave, abierta: null }),

        setZoom: (px, elegido = true) => set(s => ({ zoom: limitarZoom(px), zoomElegido: elegido || s.zoomElegido })),
        setVista: vista => set({ vista }),
        setFiltro: filtro => set({ filtro }),

        usarMundo: clave => {
          if (get().mundo === clave) return
          // Lo de otro mundo no se mezcla ni un instante: se tira todo y se
          // trae lo de este. La revision es de todos los mundos juntos, asi
          // que tambien se olvida.
          revMinima = 0
          set({
            mundo: clave, barras: {}, posicionesRM: {}, rev: null, personas: [],
            abierta: null, edicion: null, conexion: 'cargando',
            // Un mundo sin Retail Media ni headers no puede quedar filtrado en ellos.
            filtro: 'todo',
          })
          void get().sincronizar()
          void get().traerPersonas()
        },

        sincronizar: async () => {
          if (enVuelo > 0) return
          const mundo = get().mundo
          try {
            const { data } = await calendarioApi.traerDatos(mundo, get().rev)
            // Mientras viajaba se paso a otro mundo: esto ya no es lo que se mira.
            if (get().mundo !== mundo) return
            // Alguien de acá escribio mientras tanto: esto puede ser de antes.
            if (enVuelo > 0) return
            if (data.sinCambios) {
              if (get().conexion !== 'ok') set({ conexion: 'ok' })
              return
            }
            const actual = get().rev
            if (data.rev < revMinima || (actual != null && data.rev < actual)) return
            const barras: Record<string, BarraGuardada> = {}
            for (const b of data.barras ?? []) barras[b.id] = normalizar(b as BarraGuardada)
            set({ barras, posicionesRM: data.posicionesRM ?? {}, rev: data.rev, conexion: 'ok' })
          } catch {
            set({ conexion: 'sin-conexion' })
          }
        },

        traerPersonas: async () => {
          const mundo = get().mundo
          try {
            const { data } = await calendarioApi.personas(mundo)
            if (get().mundo === mundo) set({ personas: data })
          } catch {
            // Sin la lista no se pueden elegir destinatarios; lo demas anda.
          }
        },

        abrirEditor: e => set({ edicion: e }),
        cerrarEditor: () => set({ edicion: null }),
        abrirAccion: id => set({ abierta: id }),
        cerrarAccion: () => set({ abierta: null }),

        guardarBarra: datos => {
          const { edicion, barras } = get()
          if (!edicion) return
          const lista = Object.values(barras)

          const esEnvio = edicion.seccion === 'envio'

          if (!edicion.barra) {
            const id = nuevoId('br')
            // Un envío suelto no tiene renglón propio: el cronograma los
            // acomoda por día, así que siempre va en el 0.
            const carril = esEnvio ? 0 : carrilLibre(lista, edicion.seccion, edicion.banda, datos.desde, datos.hasta, edicion.carril)
            const nueva: BarraGuardada = normalizar({
              id, mundo: get().mundo, seccion: edicion.seccion, banda: edicion.banda, carril,
              nombre: datos.nombre, color: datos.color, desde: datos.desde, hasta: datos.hasta,
              ...(esEnvio ? { formato: datos.formato ?? null, hora: datos.hora, estado: 'pendiente' as EstadoPieza } : {}),
            })
            set(s => ({ barras: { ...s.barras, [id]: nueva }, edicion: null }))
            void escribir(() => calendarioApi.crearBarra({
              id, mundo: nueva.mundo, seccion: nueva.seccion, banda: nueva.banda, carril,
              nombre: datos.nombre, color: datos.color, desde: datos.desde, hasta: datos.hasta,
              ...(esEnvio ? { formato: datos.formato ?? null, hora: datos.hora ?? null } : {}),
            }))
            return
          }

          const original = barras[edicion.barra.id]
          if (!original) {
            set({ edicion: null })
            toast.error('Esta barra ya no existe: la borró otra persona.')
            return
          }
          // Solo viaja lo que la persona tocó en el editor. Se compara contra
          // la barra COMO ESTABA AL ABRIR el editor, no contra la de ahora: si
          // mientras tanto otro le cambió el nombre y acá solo se movió la
          // fecha, el nombre del otro queda.
          const abierta = edicion.barra
          const cambios: Partial<BarraGuardada> = {}
          if (datos.nombre !== abierta.nombre) cambios.nombre = datos.nombre
          if (datos.color !== abierta.color) cambios.color = datos.color
          if (datos.desde !== abierta.desde) cambios.desde = datos.desde
          if (datos.hasta !== abierta.hasta) cambios.hasta = datos.hasta
          if (esEnvio) {
            // Un envío sin formato se ve con el primero de su canal, y el editor
            // arranca con ese mismo: si la persona no lo tocó, no es un cambio.
            const formatoAntes = abierta.formato || formatosDeCanal(abierta.banda)[0] || null
            if ((datos.formato ?? null) !== formatoAntes) cambios.formato = datos.formato ?? null
            if ((datos.hora ?? undefined) !== (abierta.hora ?? undefined)) cambios.hora = datos.hora
          } else if (cambios.desde || cambios.hasta) {
            const desde = cambios.desde ?? original.desde
            const hasta = cambios.hasta ?? original.hasta
            const carril = carrilLibre(lista, original.seccion, original.banda, desde, hasta, original.carril, original.id)
            if (carril !== original.carril) cambios.carril = carril
          }
          set({ edicion: null })
          if (Object.keys(cambios).length === 0) return
          cambiarBarraLocal(original.id, b => {
            const nueva = { ...b, ...cambios }
            if (nueva.hora === undefined) delete nueva.hora
            return nueva
          })
          // Sacar la hora es mandarla en null: un undefined ni siquiera viaja.
          const payload: Record<string, unknown> = { ...cambios }
          if ('hora' in cambios && cambios.hora === undefined) payload.hora = null
          void escribir(() => calendarioApi.cambiarBarra(original.id, payload))
        },

        borrarBarra: () => {
          const { edicion } = get()
          if (!edicion?.barra) return
          const id = edicion.barra.id
          set(s => {
            const barras = { ...s.barras }
            delete barras[id]
            return { barras, edicion: null, abierta: s.abierta === id ? null : s.abierta }
          })
          void escribir(() => calendarioApi.borrarBarra(id))
        },

        moverPosicionesRM: posiciones => {
          const { mesActivo, posicionesRM } = get()
          const antes = vistaDelMes(mesActivo, get().barras, posicionesRM).posicionesRM
          if (antes.join() === posiciones.join()) return
          set(s => ({ posicionesRM: { ...s.posicionesRM, [mesActivo]: posiciones } }))
          void escribir(() => calendarioApi.moverPosicionesRM(mesActivo, posiciones))
        },

        agregarPieza: (area, formato) => {
          const accion = get().accionAbierta()
          if (!accion) return
          if ((accion.piezas ?? []).some(p => p.area === area && p.formato === formato)) return
          const pieza: Pieza = { id: nuevoId('pz'), area, formato, estado: 'pendiente' as EstadoPieza }
          cambiarBarraLocal(accion.id, b => ({ ...b, piezas: [...(b.piezas ?? []), pieza] }))
          void escribir(() => calendarioApi.agregarPieza(accion.id, pieza))
        },

        quitarPieza: piezaId => {
          const duena = duenaDe(get().barras, b => (b.piezas ?? []).some(p => p.id === piezaId))
          if (!duena) return
          cambiarBarraLocal(duena.id, b => ({ ...b, piezas: (b.piezas ?? []).filter(p => p.id !== piezaId) }))
          void escribir(() => calendarioApi.quitarPieza(piezaId))
        },

        actualizarPieza: (piezaId, cambios) => {
          const duena = duenaDe(get().barras, b => (b.piezas ?? []).some(p => p.id === piezaId))
          if (!duena) return
          cambiarBarraLocal(duena.id, b => ({
            ...b,
            piezas: (b.piezas ?? []).map(p => {
              if (p.id !== piezaId) return p
              const nueva = { ...p, ...cambios }
              // undefined = "sin fecha propia": se saca la clave, no se guarda vacía
              for (const k of ['desde', 'hasta', 'hora'] as const) if (nueva[k] === undefined) delete nueva[k]
              return nueva
            }),
          }))
          // Para el servidor, borrar la fecha es mandarla en null: un undefined
          // ni siquiera viaja en el JSON.
          const payload: Record<string, unknown> = {}
          for (const [k, v] of Object.entries(cambios)) payload[k] = v === undefined ? null : v
          void escribir(() => calendarioApi.cambiarPieza(piezaId, payload))
        },

        agregarAviso: (diasAntes, destinatarios) => {
          const accion = get().accionAbierta()
          if (!accion || destinatarios.length === 0) return
          const aviso: Aviso = { id: nuevoId('av'), diasAntes, destinatarios, creadoPor: null }
          cambiarBarraLocal(accion.id, b => ({
            ...b,
            avisos: [...(b.avisos ?? []), aviso].sort((x, y) => y.diasAntes - x.diasAntes),
          }))
          void escribir(() => calendarioApi.configurarAviso(accion.id, {
            id: aviso.id, diasAntes, destinatarios,
          })).then(r => {
            if (r?.enviadosAhora) {
              toast.success('La fecha de ese aviso ya pasó, así que salió ahora.')
            }
          })
        },

        quitarAviso: avisoId => {
          const duena = duenaDe(get().barras, b => (b.avisos ?? []).some(a => a.id === avisoId))
          if (!duena) return
          cambiarBarraLocal(duena.id, b => ({ ...b, avisos: (b.avisos ?? []).filter(a => a.id !== avisoId) }))
          void escribir(() => calendarioApi.quitarAviso(avisoId))
        },

        cambiarEstadoEnvio: (id, estado) => {
          const envio = get().barras[id]
          if (!envio || envio.seccion !== 'envio' || envio.estado === estado) return
          cambiarBarraLocal(id, b => ({ ...b, estado }))
          void escribir(() => calendarioApi.cambiarBarra(id, { estado }))
        },

        crearTarea: (barraId, datos) => {
          const titulo = datos.titulo.trim()
          if (!titulo || !get().barras[barraId]) return
          const tarea: Tarea = {
            id: nuevoId('ta'), parentId: datos.parentId ?? null, titulo,
            descripcion: datos.descripcion?.trim() || null, estado: 'pendiente' as EstadoTarea,
            asignadoA: datos.asignadoA ?? null, vence: datos.vence || null, creadoPor: null,
          }
          cambiarBarraLocal(barraId, b => ({ ...b, tareas: [...(b.tareas ?? []), tarea] }))
          void escribir(() => calendarioApi.crearTarea(barraId, {
            id: tarea.id, parentId: tarea.parentId, titulo, descripcion: tarea.descripcion,
            asignadoA: tarea.asignadoA, vence: tarea.vence,
          })).then(r => {
            if (r?.avisados) toast.success('Tarea creada. Le llegó el aviso a quien la tiene asignada.')
          })
        },

        cambiarTarea: (tareaId, cambios) => {
          const duena = duenaDe(get().barras, b => (b.tareas ?? []).some(t => t.id === tareaId))
          if (!duena) return
          cambiarBarraLocal(duena.id, b => ({
            ...b, tareas: (b.tareas ?? []).map(t => (t.id === tareaId ? { ...t, ...cambios } : t)),
          }))
          void escribir(() => calendarioApi.cambiarTarea(tareaId, cambios))
        },

        borrarTarea: tareaId => {
          const duena = duenaDe(get().barras, b => (b.tareas ?? []).some(t => t.id === tareaId))
          if (!duena) return
          const fuera = conDescendientes(tareaId, duena.tareas ?? [])
          cambiarBarraLocal(duena.id, b => ({ ...b, tareas: (b.tareas ?? []).filter(t => !fuera.has(t.id)) }))
          void escribir(() => calendarioApi.borrarTarea(tareaId))
        },
      }
    },
    {
      // Clave nueva a proposito: lo guardado con la anterior ('calendario-mktg')
      // era el mes entero, con otra forma. Se deja como estaba, no se borra.
      // v3: lo guardado ahora es de UN mundo (y dice de cual). La v2 era el
      // unico calendario que habia; se deja como estaba, no se borra.
      name: 'calendario-mktg-v3',
      version: 1,
      storage: createJSONStorage(() => localStorage),
      // El servidor no tiene localStorage: se rehidrata a mano al montar,
      // asi no hay diferencia entre lo que pinta el server y lo que pinta el cliente.
      skipHydration: true,
      // La copia local es solo para pintar al instante: la revision NO se
      // guarda, asi al abrir siempre se trae todo del servidor y un cambio que
      // quedo a medio subir al cerrar la pestaña no queda como si existiera.
      partialize: s => ({
        mundo: s.mundo,
        barras: s.barras,
        posicionesRM: s.posicionesRM,
        mesActivo: s.mesActivo,
        zoom: s.zoom,
        zoomElegido: s.zoomElegido,
        vista: s.vista,
        filtro: s.filtro,
      }),
    },
  ),
)

const CATALOGOS_TI = { comercial: BANDAS_COMERCIAL, retail: BANDAS_RETAIL }
const catalogosPorMundo = new Map<string, { comercial: BandaCatalogo[]; retail: BandaCatalogo[] }>()

/** Los tipos de accion con los que arranca cada mundo (ver lib/mundos.ts). */
export function catalogosDe(mundo: string) {
  const bandas = mundoDe(mundo)?.bandas
  if (!bandas) return CATALOGOS_TI
  let hecho = catalogosPorMundo.get(mundo)
  if (!hecho) {
    hecho = { comercial: bandas.map(nombre => ({ nombre })), retail: [] }
    catalogosPorMundo.set(mundo, hecho)
  }
  return hecho
}

/** El mes que se esta mirando. Todas las secciones reciben el mismo objeto. */
export function useMesActivo(): Mes {
  const barras = useCalendario(s => s.barras)
  const posicionesRM = useCalendario(s => s.posicionesRM)
  const clave = useCalendario(s => s.mesActivo)
  const mundo = useCalendario(s => s.mundo)
  return vistaDelMes(clave, barras, posicionesRM, catalogosDe(mundo))
}

/** El header de todas las fechas (para saber en qué posición quedó una acción). */
export function useHeaderDerivado() {
  const barras = useCalendario(s => s.barras)
  const posicionesRM = useCalendario(s => s.posicionesRM)
  return headerDerivado(barras, posicionesRM)
}

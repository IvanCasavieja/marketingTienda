'use client'

import { create } from 'zustand'
import { persist, type PersistStorage, type StorageValue } from 'zustand/middleware'
import { toast } from 'sonner'
import { calendarioApi, entregasApi, type CalendarioCopia } from '@/lib/api'
import type { ResumenEntrega, TipoPieza } from './entregas'
import { esSinCategoria } from './categorias'
import { rangoDeLaCopia } from './copiar'
import { carrilLibre, headerDerivado, nuevoId, vistaDelMes } from './derivar'
import { claveDe, hoyIso, mesSiguiente, primerDiaDe, ultimoDiaDe } from './fechas'
import { ZOOM_POR_DEFECTO, limitarZoom } from './rejilla'

export { ZOOMS, ZOOM_POR_DEFECTO } from './rejilla'
import { SECCIONES_CON_FICHA, conDescendientes, formatosDeCanal } from './tipos'
import type {
  AnclaTarea, AreaPieza, Aviso, BarraGuardada, EstadoPieza, EstadoTarea, Mes, Persona, Pieza, Plantilla, Seccion, Tarea,
} from './tipos'
import { conCambios, moverAncladas, tareasDesdePlantilla, venceAnclado, type CambiosDeTarea } from './plantillas'
import { BANDAS_COMERCIAL, BANDAS_RETAIL, type BandaCatalogo } from './catalogo'
import { MUNDO_POR_DEFECTO, mundoDe, useMundoElegido } from '@/lib/mundos'

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
/** La última escritura en viaje de cada acción: la siguiente de esa misma
 *  acción espera a que termine (ver escribir). */
const colas = new Map<string, Promise<void>>()

type Llamada = () => Promise<{ data: Escrito }>
/**
 * Los cambios que no llegaron al servidor por un problema de conexión (sin
 * red, servidor caído, una demora de más de 15 s). Antes se daban por
 * perdidos sin decirlo: la pantalla los mostraba guardados y al volver la
 * conexión desaparecían. Ahora se reintentan en orden en cada revisión (cada
 * 15 s, o al volver a la pestaña), y mientras quede alguno lo de la pantalla
 * no se pisa con lo del servidor. Viven en memoria: si se cierra la pestaña
 * se pierden, y por eso el navegador pregunta antes de cerrarla.
 */
const pendientes: { llamada: Llamada; de?: string }[] = []
let reintentando: Promise<void> | null = null
/** La revisión que está en viaje, para no pedir dos veces lo mismo. */
let sincronizando: { mundo: string; promesa: Promise<void> } | null = null

/** Si el error es de conexión (se reintenta) y no un "no" del servidor. */
function esDeConexion(e: unknown): boolean {
  const r = (e as { response?: { status?: number } })?.response
  // 507 = la base está casi llena (services/espacio.py): reintentar no lo
  // arregla, y el cambio quedaría pendiente para siempre. Es un "no".
  if (r?.status === 507) return false
  return !r || (r.status ?? 0) >= 500 || r.status === 408 || r.status === 429
}

function detalleDe(e: unknown): string | null {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === 'string' ? d : null
}

if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', ev => {
    if (pendientes.length === 0) return
    ev.preventDefault()
    ev.returnValue = ''
  })
}

/** Cada cuanto se pregunta si alguien cambio algo. */
export const SEGUNDOS_ENTRE_REVISIONES = 15

type Escrito = {
  rev?: number; enviadosAhora?: number; yaExistia?: boolean; avisados?: number
  /** Al mover una acción: cuántas tareas de plantilla se corrieron con ella. */
  tareasMovidas?: number
  /** Al aplicar una plantilla: cuántas tareas creó y cuántas quedaron sin asignar. */
  creadas?: number; sinAsignar?: number
  entrega?: ResumenEntrega
}

/** Como se mira el mes: la linea de tiempo de siempre, o una lista de tarjetas. */
export type Vista = 'tiempo' | 'lista' | 'equipo'
/** Que parte del calendario se ve. 'todo' = las cuatro, una abajo de la otra. */
export type Filtro = 'todo' | 'comercial' | 'envios' | 'retail' | 'header'

/** Lo que se carga para que una tarea lleve entregas por fases. */
export type DatosEntregas = {
  tipoPieza: TipoPieza
  brief: Record<string, string | number>
  aprobadores: number[]
  fases: { id?: string | null; nombre: string }[]
}

/** Lo que se carga de una tarea nueva. */
export type DatosTarea = {
  titulo: string
  parentId?: string | null
  asignadoA?: number | null
  vence?: string | null
  descripcion?: string | null
  /** Quién la hace (16/11/2026): Tienda, una agencia de la plataforma o una de afuera. */
  para?: 'tienda' | 'agencia' | 'fuera'
  agencia?: string | null
  /** El tipo de tarea (una pieza: nace su tarjeta) con lo tildado y los datos de más. */
  tipo?: string | null
  opciones?: string[]
  detalles?: Record<string, string | number>
  /** "N días antes del inicio": el vencimiento se mueve con la acción. */
  ancla?: AnclaTarea | null
  anclaDias?: number | null
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
  /** Cuántos cambios propios esperan a que vuelva la conexión (ver pendientes). */
  sinGuardar: number
  /** A quien se le puede mandar un aviso. */
  personas: Persona[]
  /** Si la lista de personas llegó. Con 'error' se reintenta en cada revisión. */
  personasEstado: 'cargando' | 'ok' | 'error'
  mesActivo: string
  edicion: Edicion | null
  /** El id de la accion con la ficha abierta. */
  abierta: string | null
  /** Las plantillas de tareas del mundo (vienen con /datos). */
  plantillas: Plantilla[]
  /** El diálogo de plantillas, si está abierto: desde la ficha de `barraId`
   *  (para aplicar una ahí), o con null para solo armarlas y editarlas. */
  dialogoPlantillas: { barraId: string | null } | null
  /** La pestaña con la que se pidió abrir la ficha (un aviso de la campanita
   *  lleva a las fotos). null = la de siempre. */
  pestanaPedida: string | null
  /** Ancho de cada día en px. Sube y baja con el control de zoom. */
  zoom: number
  /** false = nadie toco el zoom: el mes se ajusta solo al ancho de la pantalla. */
  zoomElegido: boolean
  vista: Vista
  filtro: Filtro
  /**
   * Lo que la persona marcó para no perderse, como en un Excel (pedido del
   * 16/11/2026): un día (la columna entera) y una fila. Es solo de su
   * pantalla: no se guarda ni se le manda a nadie.
   */
  diaMarcado: string | null
  /** `seccion:categoría`, por ejemplo `comercial:Mailing GRAL`. */
  filaMarcada: string | null
  /** Esconder las categorías sin nada este mes. Cada uno lo deja como le sirve. */
  ocultarVacias: boolean

  accionAbierta: () => BarraGuardada | null
  irAMes: (clave: string) => void
  /** Marca ese día; si ya estaba marcado, lo desmarca. */
  marcarDia: (iso: string) => void
  /** Marca esa fila; si ya estaba marcada, la desmarca. */
  marcarFila: (clave: string) => void
  quitarMarcas: () => void
  setOcultarVacias: (v: boolean) => void
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
  abrirAccion: (id: string, pestana?: string | null) => void
  cerrarAccion: () => void
  /**
   * Lleva a una acción y abre su ficha, en su mes, aunque todavía no esté en
   * pantalla (recién creada por otro, o una copia que era un reintento) o sea
   * de otro mundo. Devuelve false si no está o la persona no abre ese mundo.
   */
  irAAccion: (id: string, pestana?: string | null) => Promise<boolean>

  guardarBarra: (datos: DatosBarra) => void
  borrarBarra: () => void
  /**
   * Copia la acción `origenId` a otra fecha, con sus piezas, tareas y
   * avisos (ver lib/calendario/copiar.ts). Espera al servidor, que es quien
   * arma lo que cuelga de ella. Devuelve lo que contestó, con el id de la
   * nueva, o null si no se pudo (ya se avisó por qué) o quedó pendiente de
   * la conexión.
   */
  copiarAccion: (origenId: string, datos: { desde: string; nombre: string }) => Promise<(CalendarioCopia & { id: string }) | null>
  /** Le pone o le cambia la categoría a una acción: pasa a esa fila del calendario. */
  cambiarCategoria: (id: string, banda: string) => void
  /** Guarda las posiciones y avisa a quien lleva Retail Media. */
  moverPosicionesRM: (posiciones: number[]) => void

  agregarPieza: (area: AreaPieza, formato: string) => void
  quitarPieza: (piezaId: string) => void
  actualizarPieza: (piezaId: string, cambios: Partial<Pick<Pieza, 'estado' | 'desde' | 'hasta' | 'hora'>>) => void

  agregarAviso: (diasAntes: number, destinatarios: number[]) => void
  quitarAviso: (avisoId: string) => void

  /** El estado de un envío suelto (pendiente → publicado), desde su ficha. */
  cambiarEstadoEnvio: (id: string, estado: EstadoPieza) => void

  /** Una tarea (o subtarea) en la accion `barraId`. Devuelve su id. */
  crearTarea: (barraId: string, datos: DatosTarea) => string | null
  /** Que una tarea lleve entregas por fases. Va en la cola de su acción, así
   *  sale después del alta de la tarea aunque se pidan seguidas. */
  configurarEntregas: (barraId: string, tareaId: string, datos: DatosEntregas) => Promise<boolean>
  cambiarTarea: (tareaId: string, cambios: CambiosDeTarea) => void
  /** Borra la tarea y todo lo que cuelga de ella. */
  borrarTarea: (tareaId: string) => void

  abrirPlantillas: (barraId: string | null) => void
  cerrarPlantillas: () => void
  /** Crea o reemplaza entera una plantilla del mundo que se mira. */
  guardarPlantilla: (p: Plantilla) => void
  borrarPlantilla: (id: string) => void
  /** Crea en la acción las tareas de la plantilla, con su fecha calculada. */
  aplicarPlantilla: (barraId: string, plantillaId: string) => void
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

/** Las acciones que tocan el mes `clave` o los dos de cada lado. */
function cercaDe(barras: Record<string, BarraGuardada>, clave: string): Record<string, BarraGuardada> {
  const desde = primerDiaDe(mesSiguiente(clave, -2))
  const hasta = ultimoDiaDe(mesSiguiente(clave, 2))
  const out: Record<string, BarraGuardada> = {}
  for (const [id, b] of Object.entries(barras)) {
    if (b.desde <= hasta && b.hasta >= desde) out[id] = b
  }
  return out
}

/**
 * La copia del calendario en el navegador (localStorage). Dos cosas que la
 * de zustand por defecto no hace:
 * - escribe un rato después del último cambio, no en cada uno (abrir y cerrar
 *   la ficha o hacer zoom reescribía todo), y antes de cerrar la pestaña;
 * - si el navegador no deja guardar (almacenamiento lleno, modo privado), no
 *   pasa nada: la copia es solo para pintar rápido. Antes ese error cortaba
 *   la escritura al servidor.
 */
const copiaDelNavegador: PersistStorage<unknown> = (() => {
  let porGuardar: { nombre: string; valor: StorageValue<unknown> } | null = null
  let timer: ReturnType<typeof setTimeout> | null = null
  const guardarYa = () => {
    if (timer) { clearTimeout(timer); timer = null }
    if (!porGuardar) return
    const { nombre, valor } = porGuardar
    porGuardar = null
    try {
      localStorage.setItem(nombre, JSON.stringify(valor))
    } catch {
      // Sin lugar: se borra la copia vieja para que no quede desactualizada.
      try { localStorage.removeItem(nombre) } catch { /* nada que hacer */ }
    }
  }
  if (typeof window !== 'undefined') window.addEventListener('pagehide', guardarYa)
  return {
    getItem: nombre => {
      try {
        const texto = localStorage.getItem(nombre)
        return texto ? (JSON.parse(texto) as StorageValue<unknown>) : null
      } catch {
        return null
      }
    },
    setItem: (nombre, valor) => {
      porGuardar = { nombre, valor }
      if (timer) clearTimeout(timer)
      timer = setTimeout(guardarYa, 800)
    },
    removeItem: nombre => {
      porGuardar = null
      try { localStorage.removeItem(nombre) } catch { /* nada que hacer */ }
    },
  }
})()

export const useCalendario = create<Estado>()(
  persist(
    (set, get) => {
      /**
       * Manda un cambio. Lo local ya se cambio antes de llamar a esto, asi la
       * pantalla no espera al servidor. Si el servidor dice que no (la accion
       * la borro otra persona, se cayo la conexion), se avisa y se trae lo que
       * haya de verdad.
       */
      /** Lo que hace falta después de que una escritura salió bien. */
      function registrar(data: Escrito | undefined) {
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
      }

      function dejarPendiente(llamada: Llamada, de?: string) {
        pendientes.push({ llamada, de })
        set({ sinGuardar: pendientes.length, conexion: 'sin-conexion' })
        toast.error(
          pendientes.length === 1
            ? 'Sin conexión con el servidor: el cambio quedó pendiente y se guarda solo cuando vuelva. No cierres esta pestaña.'
            : `Sin conexión con el servidor: ${pendientes.length} cambios pendientes. Se guardan solos cuando vuelva.`,
          { id: 'calendario-sin-guardar', duration: 10_000 },
        )
      }

      /** Manda los pendientes, en orden. Corta en el primero que sigue sin conexión. */
      function reintentar(): Promise<void> {
        if (reintentando) return reintentando
        if (pendientes.length === 0) return Promise.resolve()
        const promesa = (async () => {
          let guardados = 0
          while (pendientes.length > 0) {
            try {
              const { data } = await pendientes[0].llamada()
              pendientes.shift()
              guardados++
              if (data?.rev != null) revMinima = Math.max(revMinima, data.rev)
            } catch (e) {
              if (esDeConexion(e)) break
              // El servidor dijo que no (por ejemplo, otra persona borró esa
              // acción): ese cambio no se puede guardar y se descarta.
              pendientes.shift()
              toast.error(detalleDe(e) ?? 'Un cambio pendiente no se pudo guardar.')
            }
          }
          set({ sinGuardar: pendientes.length })
          if (pendientes.length === 0) {
            if (guardados > 0) {
              toast.success(guardados === 1 ? 'Volvió la conexión: se guardó el cambio pendiente.' : `Volvió la conexión: se guardaron ${guardados} cambios pendientes.`,
                { id: 'calendario-sin-guardar' })
            }
            // Lo de la pantalla puede no ser exactamente lo del servidor: se trae todo.
            set({ rev: null })
          }
        })()
        reintentando = promesa.finally(() => { reintentando = null })
        return reintentando
      }

      async function escribir<T extends Escrito>(
        llamada: () => Promise<{ data: T }>, de?: string,
      ): Promise<T | null> {
        // Con cambios esperando a la conexión, este va detrás de ellos: si
        // saliera antes, un "ponerle categoría" podría llegar antes que el alta
        // de la acción.
        if (pendientes.length > 0) {
          dejarPendiente(llamada, de)
          void reintentar()
          return null
        }
        enVuelo++
        // Los cambios de una misma acción salen de a uno y en orden. Sin esto,
        // crear una acción y enseguida ponerle la categoría o cargarle una
        // tarea podía llegar al servidor antes que el alta, y el servidor
        // contestaba que la acción no existía.
        const anterior = de ? colas.get(de) : undefined
        let soltar: () => void = () => {}
        const turno = new Promise<void>(resolver => { soltar = resolver })
        if (de) colas.set(de, turno)
        try {
          if (anterior) await anterior
          // Si mientras esperaba su turno otro cambio quedó sin conexión, este
          // va detrás.
          if (pendientes.length > 0) {
            dejarPendiente(llamada, de)
            return null
          }
          const { data } = await llamada()
          registrar(data)
          return data
        } catch (e) {
          if (esDeConexion(e)) {
            // Lo de la pantalla queda como está: es lo que se quiso guardar.
            dejarPendiente(llamada, de)
            return null
          }
          // El servidor dijo que no: se avisa por qué y se vuelve a lo guardado.
          toast.error(detalleDe(e) ?? 'No se pudo guardar el cambio. Se vuelve a mostrar lo último guardado.')
          set({ rev: null })
          return null
        } finally {
          soltar()
          if (de && colas.get(de) === turno) colas.delete(de)
          enVuelo--
          if (get().rev === null && pendientes.length === 0) void get().sincronizar()
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
        sinGuardar: 0,
        personas: [],
        personasEstado: 'cargando',
        mesActivo: claveDe(hoyIso()),
        edicion: null,
        abierta: null,
        plantillas: [],
        dialogoPlantillas: null,
        pestanaPedida: null,
        zoom: ZOOM_POR_DEFECTO,
        zoomElegido: false,
        vista: 'tiempo',
        filtro: 'todo',
        diaMarcado: null,
        filaMarcada: null,
        ocultarVacias: false,

        marcarDia: iso => set(s => ({ diaMarcado: s.diaMarcado === iso ? null : iso })),
        marcarFila: clave => set(s => ({ filaMarcada: s.filaMarcada === clave ? null : clave })),
        quitarMarcas: () => set({ diaMarcado: null, filaMarcada: null }),
        setOcultarVacias: ocultarVacias => set({ ocultarVacias }),

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
          // trae lo de este. La revision que se tenia era de ese otro mundo,
          // asi que tambien se olvida.
          revMinima = 0
          set({
            mundo: clave, barras: {}, posicionesRM: {}, rev: null, personas: [], personasEstado: 'cargando',
            abierta: null, edicion: null, conexion: 'cargando', plantillas: [], dialogoPlantillas: null,
            // Un mundo sin Retail Media ni headers no puede quedar filtrado en ellos.
            filtro: 'todo',
            // Las filas son otras: la marca de este mundo no dice nada en aquel.
            diaMarcado: null, filaMarcada: null,
          })
          void get().sincronizar()
          void get().traerPersonas()
        },

        sincronizar: () => {
          if (enVuelo > 0) return Promise.resolve()
          const mundo = get().mundo
          // Si ya hay una revisión en viaje para este mundo, es la misma
          // pregunta: se espera esa (al cambiar de mundo o al volver a la
          // pestaña salían dos juntas).
          if (sincronizando?.mundo === mundo) return sincronizando.promesa
          const promesa = (async () => {
            // Primero lo que quedó sin guardar. Si sigue sin conexión, no se
            // trae nada: pisaría en pantalla lo que todavía no se guardó.
            if (pendientes.length > 0) {
              await reintentar()
              if (pendientes.length > 0) {
                set({ conexion: 'sin-conexion' })
                return
              }
            }
            try {
              const { data } = await calendarioApi.traerDatos(mundo, get().rev)
              // Mientras viajaba se paso a otro mundo: esto ya no es lo que se mira.
              if (get().mundo !== mundo) return
              // Alguien de acá escribio mientras tanto: esto puede ser de antes.
              if (enVuelo > 0 || pendientes.length > 0) return
              if (get().personasEstado === 'error') void get().traerPersonas()
              // A una cuenta externa (la agencia) la revisión no es el contador
              // de todo el calendario sino la huella de lo que ella ve
              // (backend/app/core/externos.py): no crece, así que no se compara
              // con "mayor" o "menor". Lo que sí vale igual: si cambió, se trae.
              const opaca = !!data.opaca
              if (data.sinCambios) {
                // "Sin cambios" ahora es por mundo: el contador pudo subir por
                // cambios en OTRO mundo y lo de acá sigue siendo eso. Ponerse al
                // día evita bajarse todo después de un guardado propio (que
                // compara con rev + 1).
                const actual = get().rev
                if (!opaca && actual != null && data.rev > actual) set({ rev: data.rev })
                if (get().conexion !== 'ok') set({ conexion: 'ok' })
                return
              }
              const actual = get().rev
              if (!opaca && (data.rev < revMinima || (actual != null && data.rev < actual))) return
              const barras: Record<string, BarraGuardada> = {}
              for (const b of data.barras ?? []) barras[b.id] = normalizar(b as BarraGuardada)
              set({
                barras, posicionesRM: data.posicionesRM ?? {}, plantillas: (data.plantillas ?? []) as Plantilla[],
                rev: data.rev, conexion: 'ok',
              })
            } catch {
              set({ conexion: 'sin-conexion' })
            }
          })()
          const enCurso = { mundo, promesa: promesa.finally(() => { if (sincronizando === enCurso) sincronizando = null }) }
          sincronizando = enCurso
          return enCurso.promesa
        },

        traerPersonas: async () => {
          const mundo = get().mundo
          try {
            const { data } = await calendarioApi.personas(mundo)
            if (get().mundo === mundo) set({ personas: data, personasEstado: 'ok' })
          } catch {
            // Sin la lista no se pueden elegir destinatarios ni ver a quién
            // está asignada cada tarea: se dice, y se reintenta en la próxima
            // revisión (ver sincronizar).
            if (get().mundo === mundo) set({ personasEstado: 'error' })
          }
        },

        abrirEditor: e => set({ edicion: e }),
        cerrarEditor: () => set({ edicion: null }),
        abrirAccion: (id, pestana = null) => set({ abierta: id, pestanaPedida: pestana }),
        cerrarAccion: () => set({ abierta: null }),

        // Antes vivía en la página (lo usaba solo `/calendario?accion=`). Está
        // acá para que también lo use la copia: navegar con el router a la
        // misma página cambiando solo `?accion=` no se completaba nunca (visto
        // con Next 16 el 15/11/2026), y la copia se quedaba en la original.
        irAAccion: async (id, pestana = null) => {
          const abrir = () => {
            const accion = get().barras[id]
            if (!accion) return false
            get().irAMes(claveDe(accion.desde))
            get().abrirAccion(accion.id, pestana)
            return true
          }
          if (abrir()) return true
          // Si no está en lo que ya hay, primero se pregunta al servidor: puede
          // ser una acción recién creada que todavía no llegó, o de otro mundo.
          // Recién si tampoco está ahí, la borraron.
          try {
            const { data } = await calendarioApi.ubicar(id)
            if (data.mundo !== get().mundo) {
              useMundoElegido.getState().elegir(data.mundo)
              get().usarMundo(data.mundo)
            }
          } catch {
            // No está, o es de un mundo que la persona no abre: lo dice quien llamó.
          }
          await get().sincronizar()
          return abrir()
        },

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
            // Una acción creada "y punto", sin categoría, se abre sola: lo que
            // sigue es ponerle adentro la categoría y las tareas (pedido de
            // Ivan, 12/11/2026). Si se creó en la fila de una categoría ya
            // quedó donde va, y no se abre: ahí se suelen cargar varias seguidas.
            const abrirla = edicion.seccion === 'comercial' && esSinCategoria(edicion.banda)
            set(s => {
              // Si sus fechas no tocan el mes que se mira, se pasa al suyo: al
              // cerrar la ficha tiene que estar a la vista.
              const seVe = nueva.desde <= ultimoDiaDe(s.mesActivo) && nueva.hasta >= primerDiaDe(s.mesActivo)
              return {
                barras: { ...s.barras, [id]: nueva },
                edicion: null,
                ...(abrirla ? { abierta: id, mesActivo: seVe ? s.mesActivo : claveDe(nueva.desde) } : {}),
              }
            })
            void escribir(() => calendarioApi.crearBarra({
              id, mundo: nueva.mundo, seccion: nueva.seccion, banda: nueva.banda, carril,
              nombre: datos.nombre, color: datos.color, desde: datos.desde, hasta: datos.hasta,
              ...(esEnvio ? { formato: datos.formato ?? null, hora: datos.hora ?? null } : {}),
            }), id)
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
            // Las tareas de plantilla se corren con la acción, como hace el
            // servidor en el mismo cambio: se ven en su fecha nueva ya.
            if ((cambios.desde || cambios.hasta) && b.tareas?.length) {
              nueva.tareas = moverAncladas(b.tareas, nueva.desde, nueva.hasta)
            }
            return nueva
          })
          // Sacar la hora es mandarla en null: un undefined ni siquiera viaja.
          const payload: Record<string, unknown> = { ...cambios }
          if ('hora' in cambios && cambios.hora === undefined) payload.hora = null
          void escribir(() => calendarioApi.cambiarBarra(original.id, payload), original.id).then(r => {
            // Que se movieron solas no es obvio: se dice, al moverla.
            const n = r?.tareasMovidas ?? 0
            if (n > 0) {
              toast.success(n === 1
                ? 'Se movió 1 tarea de plantilla con la acción.'
                : `Se movieron ${n} tareas de plantilla con la acción.`)
            }
          })
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
          void escribir(() => calendarioApi.borrarBarra(id), id)
        },

        copiarAccion: async (origenId, { desde, nombre }) => {
          const origen = get().barras[origenId]
          if (!origen) return null
          // El id lo pone el front, como al crear una acción: si la conexión
          // se corta y el cambio queda pendiente, el reintento manda el mismo
          // y el servidor no la duplica.
          const id = nuevoId('br')
          const { hasta } = rangoDeLaCopia(origen, desde)
          // El renglón libre en las fechas nuevas, como al crear (un envío
          // suelto no tiene renglón propio).
          const carril = origen.seccion === 'envio'
            ? 0
            : carrilLibre(Object.values(get().barras), origen.seccion, origen.banda, desde, hasta, origen.carril)
          const mundo = get().mundo
          // Detrás de lo que esté en viaje de la original (una pieza recién
          // agregada): la copia la tiene que llevar.
          const r = await escribir(async () => {
            const res = await calendarioApi.copiarBarra(origenId, { id, desde, nombre, carril })
            // La acción nueva llega entera y se pone en pantalla ANTES de
            // anotar la revisión (ver registrar): si no, la revisión diría
            // que lo local está al día sin tenerla.
            const b = res.data.barra as BarraGuardada | undefined
            if (b && get().mundo === mundo) set(s => ({ barras: { ...s.barras, [b.id]: normalizar(b) } }))
            return res
          }, origenId)
          return r ? { ...r, id } : null
        },

        cambiarCategoria: (id, banda) => {
          const accion = get().barras[id]
          if (!accion || accion.seccion !== 'comercial' || !banda || accion.banda === banda) return
          // El renglón que tenía no significa nada en la fila nueva: va al
          // primero que esté libre en todas sus fechas. La fila y el renglón
          // viajan juntos, en un solo cambio.
          const carril = carrilLibre(Object.values(get().barras), 'comercial', banda, accion.desde, accion.hasta, 0, id)
          cambiarBarraLocal(id, b => ({ ...b, banda, carril }))
          void escribir(() => calendarioApi.cambiarBarra(id, { banda, carril }), id)
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
          void escribir(() => calendarioApi.agregarPieza(accion.id, pieza), accion.id)
        },

        quitarPieza: piezaId => {
          const duena = duenaDe(get().barras, b => (b.piezas ?? []).some(p => p.id === piezaId))
          if (!duena) return
          cambiarBarraLocal(duena.id, b => ({ ...b, piezas: (b.piezas ?? []).filter(p => p.id !== piezaId) }))
          void escribir(() => calendarioApi.quitarPieza(piezaId), duena.id)
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
          void escribir(() => calendarioApi.cambiarPieza(piezaId, payload), duena.id)
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
          }), accion.id).then(r => {
            if (r?.enviadosAhora) {
              toast.success('La fecha de ese aviso ya pasó, así que salió ahora.')
            }
          })
        },

        quitarAviso: avisoId => {
          const duena = duenaDe(get().barras, b => (b.avisos ?? []).some(a => a.id === avisoId))
          if (!duena) return
          cambiarBarraLocal(duena.id, b => ({ ...b, avisos: (b.avisos ?? []).filter(a => a.id !== avisoId) }))
          void escribir(() => calendarioApi.quitarAviso(avisoId), duena.id)
        },

        cambiarEstadoEnvio: (id, estado) => {
          const envio = get().barras[id]
          if (!envio || envio.seccion !== 'envio' || envio.estado === estado) return
          cambiarBarraLocal(id, b => ({ ...b, estado }))
          void escribir(() => calendarioApi.cambiarBarra(id, { estado }), id)
        },

        crearTarea: (barraId, datos) => {
          const titulo = datos.titulo.trim()
          const accion = get().barras[barraId]
          if (!titulo || !accion) return null
          const pieza = Boolean(datos.tipo) || datos.para === 'agencia' || datos.para === 'fuera'
          const vence = datos.ancla ? venceAnclado(datos.ancla, datos.anclaDias ?? 0, accion.desde, accion.hasta) : datos.vence || null
          const tarea: Tarea = {
            id: nuevoId('ta'), parentId: datos.parentId ?? null, titulo,
            descripcion: datos.descripcion?.trim() || null, estado: 'pendiente' as EstadoTarea,
            asignadoA: datos.asignadoA ?? null, vence, creadoPor: null,
            ancla: datos.ancla ?? null, anclaDias: datos.ancla ? datos.anclaDias ?? 0 : null,
            para: datos.para ?? 'tienda', agencia: datos.agencia ?? null, tipo: datos.tipo ?? null,
            opciones: datos.opciones ?? [],
          }
          cambiarBarraLocal(barraId, b => ({ ...b, tareas: [...(b.tareas ?? []), tarea] }))
          void escribir(() => calendarioApi.crearTarea(barraId, {
            id: tarea.id, parentId: tarea.parentId, titulo: datos.tipo ? '' : titulo, descripcion: tarea.descripcion,
            asignadoA: tarea.asignadoA, vence: datos.ancla ? null : tarea.vence,
            para: datos.para ?? 'tienda', agencia: datos.agencia ?? null,
            tipo: datos.tipo ?? null, opciones: datos.opciones ?? null, detalles: datos.detalles ?? null,
            ancla: datos.ancla ?? null, anclaDias: datos.ancla ? datos.anclaDias ?? 0 : null,
          }), barraId).then(r => {
            if (!r) return
            const res = r as { titulo?: string; vence?: string | null; entrega?: Tarea['entrega']; para?: Tarea['para']; agencia?: string | null }
            // Lo que armó el servidor (el nombre "<Acción> - <Tipo>", la
            // tarjeta en Ingresado) reemplaza lo de la pantalla.
            if (res.titulo || res.entrega) {
              cambiarBarraLocal(barraId, b => ({
                ...b,
                tareas: (b.tareas ?? []).map(t => (t.id === tarea.id ? {
                  ...t, titulo: res.titulo || t.titulo, vence: res.vence ?? t.vence, entrega: res.entrega ?? t.entrega,
                  para: res.para ?? t.para, agencia: res.agencia ?? t.agencia,
                } : t)),
              }))
            }
            if (pieza) {
              toast.success(r.avisados
                ? 'Listo: nació su tarjeta en el tablero, en «Ingresado». Le avisamos a quien la hace.'
                : 'Listo: nació su tarjeta en el tablero, en «Ingresado».')
            } else if (r.avisados) toast.success('Tarea creada. Le llegó el aviso a quien la tiene asignada.')
          })
          return tarea.id
        },

        configurarEntregas: async (barraId, tareaId, datos) => {
          const r = await escribir(() => entregasApi.configurar(tareaId, datos), barraId)
          if (!r?.entrega) return false
          const entrega = r.entrega
          cambiarBarraLocal(barraId, b => ({
            ...b, tareas: (b.tareas ?? []).map(t => (t.id === tareaId ? { ...t, entrega } : t)),
          }))
          return true
        },

        cambiarTarea: (tareaId, cambios) => {
          const duena = duenaDe(get().barras, b => (b.tareas ?? []).some(t => t.id === tareaId))
          if (!duena) return
          // Lo mismo que hace el servidor: una fecha puesta a mano suelta la
          // tarea de la acción; reabrir una hecha la vuelve a su fecha.
          cambiarBarraLocal(duena.id, b => ({
            ...b, tareas: (b.tareas ?? []).map(t => (t.id === tareaId ? conCambios(t, cambios, b.desde, b.hasta) : t)),
          }))
          void escribir(() => calendarioApi.cambiarTarea(tareaId, cambios), duena.id)
        },

        borrarTarea: tareaId => {
          const duena = duenaDe(get().barras, b => (b.tareas ?? []).some(t => t.id === tareaId))
          if (!duena) return
          const fuera = conDescendientes(tareaId, duena.tareas ?? [])
          cambiarBarraLocal(duena.id, b => ({ ...b, tareas: (b.tareas ?? []).filter(t => !fuera.has(t.id)) }))
          void escribir(() => calendarioApi.borrarTarea(tareaId), duena.id)
        },

        abrirPlantillas: barraId => set({ dialogoPlantillas: { barraId } }),
        cerrarPlantillas: () => set({ dialogoPlantillas: null }),

        guardarPlantilla: p => {
          const mundo = get().mundo
          const plantilla: Plantilla = { ...p, mundo }
          set(s => ({
            plantillas: [...s.plantillas.filter(x => x.id !== p.id), plantilla]
              .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es')),
          }))
          void escribir(() => calendarioApi.guardarPlantilla(p.id, {
            mundo, nombre: p.nombre, categoria: p.categoria, tareas: p.tareas,
          }), p.id).then(r => {
            if (r) toast.success(`Plantilla «${p.nombre}» guardada.`)
          })
        },

        borrarPlantilla: id => {
          set(s => ({ plantillas: s.plantillas.filter(p => p.id !== id) }))
          void escribir(() => calendarioApi.borrarPlantilla(id), id)
        },

        aplicarPlantilla: (barraId, plantillaId) => {
          const accion = get().barras[barraId]
          const plantilla = get().plantillas.find(p => p.id === plantillaId)
          if (!accion || !plantilla) return
          const { tareas, ids } = tareasDesdePlantilla(plantilla, accion, () => nuevoId('ta'))
          cambiarBarraLocal(barraId, b => ({ ...b, tareas: [...(b.tareas ?? []), ...tareas] }))
          // Si la plantilla se acaba de guardar, se aplica cuando el servidor
          // ya la tiene: si no, contestaría que no existe.
          const guardandola = colas.get(plantillaId)
          void escribir(async () => {
            if (guardandola) await guardandola
            return calendarioApi.aplicarPlantilla(barraId, { plantillaId, ids })
          }, barraId).then(r => {
            if (!r || r.yaExistia) return
            const creadas = r.creadas ?? tareas.length
            const partes = [creadas === 1
              ? `Se creó 1 tarea de «${plantilla.nombre}».`
              : `Se crearon ${creadas} tareas de «${plantilla.nombre}».`]
            if (r.avisados) {
              partes.push(r.avisados === 1
                ? 'Le llegó un aviso a la persona responsable.'
                : `Les llegó un aviso a las ${r.avisados} personas responsables.`)
            }
            if (r.sinAsignar) {
              partes.push(r.sinAsignar === 1
                ? 'Una quedó sin asignar: su responsable ya no ve este calendario.'
                : `${r.sinAsignar} quedaron sin asignar: su responsable ya no ve este calendario.`)
              // Acá se mostraban asignadas: se trae lo que quedó de verdad.
              set({ rev: null })
              void get().sincronizar()
            }
            toast.success(partes.join(' '))
          })
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
      storage: copiaDelNavegador,
      // El servidor no tiene localStorage: se rehidrata a mano al montar,
      // asi no hay diferencia entre lo que pinta el server y lo que pinta el cliente.
      skipHydration: true,
      // La copia local es solo para pintar al instante: la revision NO se
      // guarda, asi al abrir siempre se trae todo del servidor y un cambio que
      // quedo a medio subir al cerrar la pestaña no queda como si existiera.
      //
      // Solo las acciones de los meses cerca del que se mira: es para pintar
      // al instante, y con el mundo entero (1,4 KB por acción) un calendario
      // grande llenaba el almacenamiento del navegador.
      partialize: s => ({
        mundo: s.mundo,
        barras: cercaDe(s.barras, s.mesActivo),
        posicionesRM: s.posicionesRM,
        mesActivo: s.mesActivo,
        zoom: s.zoom,
        zoomElegido: s.zoomElegido,
        vista: s.vista,
        filtro: s.filtro,
        ocultarVacias: s.ocultarVacias,
      }),
    },
  ),
)

const CATALOGOS_TI = { comercial: BANDAS_COMERCIAL, retail: BANDAS_RETAIL }
const catalogosPorMundo = new Map<string, { comercial: BandaCatalogo[]; retail: BandaCatalogo[] }>()

/** Las categorías con las que arranca cada mundo (ver lib/mundos.ts). */
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

/** Las categorías del mundo que se mira, en el orden del calendario. */
export function useCategoriasDelMundo(): string[] {
  const mundo = useCalendario(s => s.mundo)
  return catalogosDe(mundo).comercial.map(c => c.nombre)
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

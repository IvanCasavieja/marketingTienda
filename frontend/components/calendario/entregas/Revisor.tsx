'use client'

import { useEffect, useState, useSyncExternalStore } from 'react'
import {
  Check, Columns2, ExternalLink, Link2, Loader2, Lock, MousePointerClick, RotateCcw, ShieldCheck, Sparkles, Trash2,
} from 'lucide-react'
import { toast } from 'sonner'
import { entregasApi } from '@/lib/api'
import {
  fechaYHora, type DetalleEntregas, type Marca, type TipoDecision, type Version,
} from '@/lib/calendario/entregas'
import {
  VEREDICTO_IA, cambiosPorMarca, marcaDesdeObservacion, textoConArchivo, tieneLugar,
  type ObservacionIA, type RevisionIA, type VeredictoIA,
} from '@/lib/calendario/revision-ia'
import { ImagenConMarcas, Miniatura, type Pin } from './ImagenConMarcas'
import { LoQueFalta } from './LoQueFalta'
import { PanelRevisionIA } from './PanelRevisionIA'

/** Una marca que se está poniendo. `observacionIA`: si salió de lo que vio la IA. */
type Nueva = { clave: string; imagenId: string; x: number; y: number; texto: string; observacionIA?: string }

// Mientras la IA mira la pieza, se vuelve a preguntar cada tanto: una
// revisión tarda entre unos segundos y un par de minutos. Después de eso, si
// sigue "pendiente", se deja de preguntar (el servidor la da por perdida a
// los 10 minutos y no muestra nada).
const CADA_MS = 5_000
const MAX_VUELTAS = 36

// Lo que dice la IA de cada marca de la ronda anterior (19/11/2026): verde si
// se ve hecho, rojo suave si falta, gris si no se puede saber. Chico y con
// buen contraste en claro y en oscuro.
const COLOR_VEREDICTO: Record<VeredictoIA, string> = {
  hecho: 'bg-emerald-50 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300',
  falta: 'bg-rose-50 text-rose-800 dark:bg-rose-500/15 dark:text-rose-300',
  dudoso: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
}

// La notebook (lg de Tailwind): la imagen a la izquierda y todo lo demás a la
// derecha. Ahí lo de la IA va arriba de la columna de la derecha, al lado de
// la imagen: arriba de la imagen la empujaba media pantalla para abajo y el
// pin de algo que está abajo en la pieza (los legales) quedaba fuera de la
// vista. En el teléfono, una columna sola: va arriba de la imagen.
const NOTEBOOK = '(min-width: 1024px)'
function useEsNotebook(): boolean {
  return useSyncExternalStore(
    avisar => {
      const m = window.matchMedia(NOTEBOOK)
      m.addEventListener('change', avisar)
      return () => m.removeEventListener('change', avisar)
    },
    () => window.matchMedia(NOTEBOOK).matches,
    () => false,
  )
}

function detalleDeError(e: unknown): string | null {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === 'string' ? d : null
}

/** Los pins que ya tiene una versión (de otros aprobadores, o pedidos en la ronda anterior). */
function pinesDe(marcas: Marca[], imagenId: string): Pin[] {
  return marcas.filter(m => m.imagenId === imagenId).map(m => ({
    clave: m.id, numero: m.numero, x: m.x, y: m.y, texto: m.texto,
    tono: m.corregida ? 'corregida' : 'cambio',
  }))
}

/**
 * Revisar una versión: la imagen grande, tocar donde hay que cambiar algo
 * (queda un pin numerado con su texto) y decidir. Se puede comparar con la
 * versión anterior: lado a lado en la notebook, con pestañas en el teléfono.
 *
 * Dos botones y nada más (19/11/2026: se sacó «Aprobado con cambios», que
 * confundía): sin marcas, «Aprobar»; con marcas, «Pedir cambios» y la pieza
 * vuelve a la agencia. La línea de arriba de los botones dice cuál va.
 *
 * Lo que encontró la IA no aparece solo (Ivan, 19/11/2026: "quizás está
 * demasiado inteligencia artificial y puede llegar a provocar confusión"):
 * hay un botón discreto arriba, "Ver lo que encontró la IA (3)", y recién al
 * tocarlo se muestra la lista. Cuándo se calcula no cambió (el servidor, al
 * entregar): acá solo cambió cuándo se muestra.
 *
 * Lo único de la IA que se ve sin tocar ese botón es, en «Lo que se pidió en
 * la ronda N», si se ve hecho lo que pedía cada marca (19/11/2026, Ivan:
 * "debería de hacerlo"): una etiqueta chica al lado de cada una, con la nota
 * abajo. Es justo el control que hace quien aprueba.
 */
export function Revisor({ detalle, version, anterior, onListo, onCancelar }: {
  detalle: DetalleEntregas
  version: Version
  anterior: Version | null
  onListo: () => void
  onCancelar: () => void
}) {
  const fase = detalle.fases.find(f => f.id === version.faseId)
  const nombre = (id: number | null) => (id != null ? detalle.personas[String(id)] : null) ?? 'Alguien'
  const [activa, setActiva] = useState(version.imagenes[0]?.id ?? '')
  const [nuevas, setNuevas] = useState<Nueva[]>([])
  const [elegido, setElegido] = useState<string | null>(null)
  const [comentario, setComentario] = useState('')
  const [notaInterna, setNotaInterna] = useState('')
  const [comparar, setComparar] = useState(false)
  const [ladoMovil, setLadoMovil] = useState<'anterior' | 'nueva'>('nueva')
  const [enviando, setEnviando] = useState<TipoDecision | null>(null)
  const [confirmandoSalir, setConfirmandoSalir] = useState(false)
  // Lo que encontró la IA. Solo se pide si el servidor dice que esta persona
  // lo puede ver (aprobadores y quien gestiona; nunca quien entrega).
  const verIA = !!detalle.puedo.verRevisionIA
  const [revisionIA, setRevisionIA] = useState<RevisionIA | null>(null)
  const [obsElegida, setObsElegida] = useState<string | null>(null)
  // Si la persona pidió ver la lista de la IA (cerrada hasta que la toque).
  const [mostrarIA, setMostrarIA] = useState(false)
  // Las observaciones que se pasaron al comentario (ronda sin imágenes: no hay dónde marcar).
  const [pasadas, setPasadas] = useState<string[]>([])

  useEffect(() => {
    if (!verIA) return
    let vivo = true
    let vueltas = 0
    let reloj: ReturnType<typeof setTimeout> | null = null
    const pedir = () => {
      entregasApi.revisionIA(version.id)
        .then(({ data }) => {
          if (!vivo) return
          setRevisionIA(data)
          if (data.estado === 'pendiente' && ++vueltas < MAX_VUELTAS) reloj = setTimeout(pedir, CADA_MS)
          else if (data.estado === 'pendiente') setRevisionIA({ estado: 'nada', observaciones: [] })
        })
        // Si no se puede traer, no se muestra nada: la revisión sigue como siempre.
        .catch(() => { if (vivo) setRevisionIA(null) })
    }
    pedir()
    return () => { vivo = false; if (reloj) clearTimeout(reloj) }
  }, [verIA, version.id])

  const esNotebook = useEsNotebook()

  // Al tocar una observación, que se vea el pin: si quedó fuera de la vista
  // (en el teléfono la lista está arriba de la imagen), se lleva al medio. Se
  // busca unas veces porque si es de otra imagen, el pin aparece cuando carga.
  useEffect(() => {
    if (!obsElegida) return
    let intentos = 0
    let reloj: ReturnType<typeof setTimeout>
    const buscar = () => {
      const pin = document.querySelector(`[data-pin="ia-${obsElegida}"]`)
      if (!pin) { if (++intentos < 15) reloj = setTimeout(buscar, 100); return }
      const caja = pin.getBoundingClientRect()
      const vista = pin.closest('.overflow-y-auto')?.getBoundingClientRect()
      if (vista && (caja.top < vista.top || caja.bottom > vista.bottom)) {
        pin.scrollIntoView({ block: 'center', behavior: 'smooth' })
      }
    }
    reloj = setTimeout(buscar, 50)
    return () => clearTimeout(reloj)
  }, [obsElegida])

  const ordenActiva = version.imagenes.find(i => i.id === activa)?.orden ?? 0
  const imagenAnterior = anterior
    ? (anterior.imagenes.find(i => i.orden === ordenActiva) ?? anterior.imagenes[0])?.id ?? null
    : null
  const siguienteNumero = Math.max(0, ...version.marcas.map(m => m.numero)) + 1
  const numeroDe = (i: number) => siguienteNumero + i
  const pinesNuevos: Pin[] = nuevas.flatMap((n, i) => (n.imagenId === activa
    ? [{ clave: n.clave, numero: numeroDe(i), x: n.x, y: n.y, tono: 'nuevo' as const, texto: n.texto }]
    : []))
  // Las observaciones de la IA que ya se hicieron marca en esta revisión: id -> número de la marca.
  const convertidas: Record<string, number> = Object.fromEntries(
    nuevas.flatMap((n, i) => (n.observacionIA ? [[n.observacionIA, numeroDe(i)]] : [])),
  )
  // Dónde vio la IA lo que se tocó en la lista: un pin violeta que no es una
  // marca. Si ya se hizo marca, se ve la marca y no hace falta.
  // Con la lista cerrada, el pin tampoco: la IA no aparece sola.
  const observacion = mostrarIA ? (revisionIA?.observaciones.find(o => o.id === obsElegida) ?? null) : null
  const pinIA: Pin[] = observacion && observacion.imagenId === activa && observacion.estado !== 'marca'
    && convertidas[observacion.id] == null && tieneLugar(observacion, version.imagenes)
    ? [{ clave: `ia-${observacion.id}`, numero: 0, x: observacion.x as number, y: observacion.y as number, tono: 'ia', texto: observacion.texto }]
    : []
  const pinesActuales = [...pinesDe(version.marcas, activa), ...pinesNuevos, ...pinIA]
  const hayMarcas = nuevas.length > 0
  const hayAlgo = hayMarcas || comentario.trim() !== '' || notaInterna.trim() !== ''
  // Para pedir cambios hace falta algo que quien entrega VEA: una marca o el
  // comentario. La nota interna no cuenta (el servidor la rechaza igual:
  // quien entrega no sabría qué cambiar).
  const hayParaQuienEntrega = hayMarcas || comentario.trim() !== ''
  const sinTexto = nuevas.findIndex(n => !n.texto.trim())
  // Lo que se pidió en la ronda anterior y si la agencia dice que lo corrigió.
  const pedidoAntes = anterior?.faseId === version.faseId ? anterior.marcas : []
  // Y lo que ve la IA de cada una (vacío si esta persona no ve la revisión:
  // entonces no se la pide).
  const iaDeCadaMarca = cambiosPorMarca(revisionIA)
  const respaldoDe = detalle.puedo.comoRespaldo ? detalle.resumen.aprobadorDeTurno : null
  // El botón que abre lo de la IA: qué dice según cómo viene la revisión.
  const hayIA = verIA && !!revisionIA && revisionIA.estado !== 'nada'
  // Mientras la IA mira, se dice eso (no "Revisar con IA", que promete una
  // acción: la revisión ya arrancó sola al entregar).
  const textoBotonIA = !revisionIA || revisionIA.estado === 'pendiente'
    ? 'La IA está revisando…'
    : revisionIA.observaciones.length === 0
      ? 'Ver la revisión de la IA'
      : `Ver lo que encontró la IA (${revisionIA.observaciones.length})`

  function hayLugarParaOtraMarca(): boolean {
    if (nuevas.length + version.marcas.length >= detalle.limites.marcas) {
      toast.error(`Son demasiadas marcas en una ronda (hasta ${detalle.limites.marcas}).`)
      return false
    }
    return true
  }

  const nuevaClave = () => `n${Date.now()}${Math.random().toString(36).slice(2, 6)}`

  function poner(x: number, y: number) {
    if (!hayLugarParaOtraMarca()) return
    const clave = nuevaClave()
    setNuevas(prev => [...prev, { clave, imagenId: activa, x, y, texto: '' }])
    setElegido(clave)
  }

  /** Tocar una observación de la IA: se va a su imagen y se ve dónde la vio. */
  function elegirObservacion(o: ObservacionIA) {
    if (obsElegida === o.id) { setObsElegida(null); return }
    setObsElegida(o.id)
    if (o.imagenId && version.imagenes.some(i => i.id === o.imagenId)) setActiva(o.imagenId)
    // Comparando en el teléfono, la que tiene el pin es la de ahora.
    setLadoMovil('nueva')
    setElegido(`ia-${o.id}`)
  }

  /** "Hacer marca": una marca normal, del aprobador, con el texto de la IA
   *  (que puede corregir antes de mandar). Se manda con la decisión. */
  function convertir(o: ObservacionIA) {
    if (version.imagenes.length === 0) {
      // La ronda vino solo con el link (y la IA lo pudo bajar): no hay imagen
      // donde marcar, así que va al comentario, que la agencia sí ve.
      setComentario(prev => `${prev.trim() ? `${prev.trimEnd()}\n` : ''}- ${textoConArchivo(o)}`)
      setPasadas(prev => (prev.includes(o.id) ? prev : [...prev, o.id]))
      setObsElegida(null)
      return
    }
    if (!hayLugarParaOtraMarca()) return
    const m = marcaDesdeObservacion(o, version.imagenes, activa)
    const clave = nuevaClave()
    setNuevas(prev => [...prev, { clave, ...m, observacionIA: o.id }])
    setActiva(m.imagenId)
    setObsElegida(null)
    setElegido(clave)
  }

  function deshacerConversion(o: ObservacionIA) {
    setNuevas(prev => prev.filter(n => n.observacionIA !== o.id))
  }

  /** Descartar queda guardado ya (el siguiente de la cadena la ve descartada). */
  async function descartarObservacion(o: ObservacionIA, descartada: boolean) {
    try {
      const { data } = await entregasApi.descartarObservacionIA(version.id, o.id, descartada)
      setRevisionIA(prev => (prev ? { ...prev, observaciones: prev.observaciones.map(x => (x.id === o.id ? data : x)) } : prev))
      if (descartada && obsElegida === o.id) setObsElegida(null)
    } catch (e) {
      toast.error(detalleDeError(e) ?? 'No se pudo guardar. Probá de nuevo.')
    }
  }

  async function decidir(decision: TipoDecision) {
    if (enviando) return
    if (sinTexto !== -1) {
      toast.error(`Escribí qué hay que cambiar en la marca ${numeroDe(sinTexto)}.`)
      return
    }
    setEnviando(decision)
    try {
      const { data } = await entregasApi.decidir(version.id, {
        decision,
        comentario: comentario.trim() || null,
        marcas: nuevas.map(n => ({
          imagenId: n.imagenId, x: n.x, y: n.y, texto: n.texto.trim(), observacionIA: n.observacionIA ?? null,
        })),
        notaInterna: notaInterna.trim() || null,
      })
      const texto = decision === 'cambios'
        ? 'Listo: volvió a la agencia con tus marcas.'
        : data.resultado === 'aprobada'
          ? (data.entrega?.momento === 'aprobada' ? '¡Aprobada! Era la última fase: la tarea quedó hecha.' : `Aprobaste ${fase?.nombre ?? 'la fase'}: ahora le toca a la agencia la siguiente.`)
          : 'Aprobaste tu parte: ahora la revisa el siguiente de la cadena.'
      toast.success(texto)
      onListo()
    } catch (e) {
      toast.error(detalleDeError(e) ?? 'No se pudo guardar la decisión. Probá de nuevo.')
      setEnviando(null)
    }
  }

  function cancelar() {
    if (hayAlgo && !confirmandoSalir) { setConfirmandoSalir(true); return }
    onCancelar()
  }

  // Una ronda puede venir solo con un link (16/11/2026: "imágenes y/o un
  // link"): no hay dónde marcar, se revisa en el link y se escribe qué cambiar.
  const sinImagenes = version.imagenes.length === 0
  const imagenNueva = sinImagenes ? (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-5 py-8 text-center dark:border-slate-700 dark:bg-slate-800/40">
      <Link2 className="h-6 w-6 text-brand-600 dark:text-brand-300" aria-hidden />
      <p className="max-w-sm text-sm text-slate-700 dark:text-slate-200">
        Esta ronda vino con un link, sin imágenes. Abrilo para revisarla y, si hay que cambiar algo, escribilo abajo.
      </p>
      {version.link && (
        <a href={version.link} target="_blank" rel="noopener noreferrer"
          className="flex min-h-[44px] items-center gap-2 rounded-xl bg-brand-600 px-4 text-sm font-bold text-white shadow-sm hover:bg-brand-700">
          <ExternalLink className="h-4 w-4" /> Abrir los materiales
        </a>
      )}
    </div>
  ) : (
    <ImagenConMarcas
      imagenId={activa}
      pines={pinesActuales}
      onTocar={enviando ? undefined : poner}
      elegido={elegido}
      onElegirPin={clave => {
        setElegido(clave)
        // Tocar una marca hecha desde la IA no cambia la lista; tocar otra cosa
        // que no sea el pin de la IA deja de mostrarlo.
        if (!clave.startsWith('ia-')) setObsElegida(null)
      }}
      // La caja ocupa casi toda la pantalla (19/11/2026): la imagen, grande.
      claseImagen={comparar ? 'max-h-[60vh]' : 'max-h-[70vh]'}
      etiqueta={`Ronda ${version.ronda}, imagen ${ordenActiva + 1}`}
    />
  )
  const panelIA = hayIA && mostrarIA ? (
    <PanelRevisionIA
      revision={revisionIA}
      imagenes={version.imagenes}
      elegida={obsElegida}
      convertidas={convertidas}
      pasadas={pasadas}
      deshabilitado={!!enviando}
      onElegir={elegirObservacion}
      onConvertir={convertir}
      onDeshacer={deshacerConversion}
      onDescartar={descartarObservacion}
      onCerrar={() => { setMostrarIA(false); setObsElegida(null) }}
    />
  ) : null
  const imagenVieja = imagenAnterior && anterior ? (
    <ImagenConMarcas
      imagenId={imagenAnterior}
      pines={pinesDe(anterior.marcas, imagenAnterior)}
      claseImagen="max-h-[60vh]"
      etiqueta={`La versión anterior (ronda ${anterior.ronda})`}
    />
  ) : null

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto overscroll-contain px-4 py-4 sm:px-6">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">Revisar la ronda {version.ronda} de {fase?.nombre}</h3>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              La subió {nombre(version.subidaPor)} · {fechaYHora(version.fecha)}
            </p>
            {/* Las piezas del pedido que no vinieron en esta ronda, y por qué
                (21/11/2026): una línea discreta, para revisar sabiéndolo. */}
            <LoQueFalta detalle={detalle} version={version} className="mt-1" />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {hayIA && (
              <button
                type="button"
                onClick={() => setMostrarIA(v => !v)}
                aria-expanded={mostrarIA}
                aria-controls="revision-ia"
                className={`flex min-h-[40px] items-center gap-1.5 rounded-xl px-3 text-sm font-semibold transition active:scale-95 ${
                  mostrarIA ? 'bg-violet-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700'
                }`}
              >
                <Sparkles className="h-4 w-4" /> {mostrarIA ? 'Ocultar lo de la IA' : textoBotonIA}
              </button>
            )}
            {anterior && (
              <button
                type="button"
                onClick={() => setComparar(v => !v)}
                aria-pressed={comparar}
                className={`flex min-h-[40px] items-center gap-1.5 rounded-xl px-3 text-sm font-semibold transition active:scale-95 ${
                  comparar ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700'
                }`}
              >
                <Columns2 className="h-4 w-4" /> {comparar ? 'Dejar de comparar' : `Comparar con ${anterior.faseId === version.faseId ? `la ronda ${anterior.ronda}` : 'la fase anterior'}`}
              </button>
            )}
          </div>
        </div>

        {respaldoDe != null && (
          <p className="flex items-start gap-2 rounded-xl border border-violet-200 bg-violet-50 px-3 py-2 text-sm text-violet-900 dark:border-violet-500/30 dark:bg-violet-500/10 dark:text-violet-200">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
            Le tocaba a {nombre(respaldoDe)}. Decidís vos como respaldo: queda anotado.
          </p>
        )}

        {/* En la notebook, la imagen a la izquierda y las marcas a la derecha,
            a la vista mientras se toca; en el teléfono, una abajo de la otra. */}
        <div className="space-y-4 lg:grid lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start lg:gap-6 lg:space-y-0">
          <div className="space-y-3">
        {!esNotebook && panelIA}
        {comparar && imagenVieja ? (
          <>
            {/* En el teléfono no entran dos lado a lado: pestañas. */}
            <div className="segmentado sm:hidden" role="tablist" aria-label="Qué versión ver">
              <button type="button" role="tab" aria-selected={ladoMovil === 'anterior'} onClick={() => setLadoMovil('anterior')} className="segmento">
                Antes · ronda {anterior?.ronda}
              </button>
              <button type="button" role="tab" aria-selected={ladoMovil === 'nueva'} onClick={() => setLadoMovil('nueva')} className="segmento">
                Ahora · ronda {version.ronda}
              </button>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <figure className={ladoMovil === 'anterior' ? '' : 'hidden sm:block'}>
                <figcaption className="mb-1.5 text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  Antes · {anterior?.faseId === version.faseId ? `ronda ${anterior?.ronda}` : 'fase anterior'}
                </figcaption>
                {imagenVieja}
              </figure>
              <figure className={ladoMovil === 'nueva' ? '' : 'hidden sm:block'}>
                <figcaption className="mb-1.5 text-xs font-bold uppercase tracking-wide text-brand-700 dark:text-brand-200">Ahora · ronda {version.ronda}</figcaption>
                {imagenNueva}
              </figure>
            </div>
          </>
        ) : imagenNueva}

        {version.imagenes.length > 1 && (
          <div className="flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Imágenes de esta ronda">
            {version.imagenes.map((im, i) => {
              const cuantas = nuevas.filter(n => n.imagenId === im.id).length
              return (
                <button
                  key={im.id}
                  type="button"
                  role="tab"
                  aria-selected={im.id === activa}
                  onClick={() => setActiva(im.id)}
                  className={`relative shrink-0 rounded-xl p-0.5 transition ${im.id === activa ? 'ring-2 ring-brand-600' : 'opacity-70 hover:opacity-100'}`}
                >
                  <Miniatura imagenId={im.id} etiqueta={`Imagen ${i + 1}`} className="h-16 w-16" />
                  {cuantas > 0 && (
                    <span className="absolute -right-1 -top-1 flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-brand-600 px-1 text-[11px] font-bold text-white">{cuantas}</span>
                  )}
                </button>
              )
            })}
          </div>
        )}

        {!sinImagenes && (
          <p className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
            <MousePointerClick className="h-4 w-4 shrink-0 text-brand-600 dark:text-brand-300" />
            Tocá la imagen donde hay que cambiar algo: queda una marca numerada.
          </p>
        )}
          </div>

          <div className="space-y-4">
        {esNotebook && panelIA}
        {(version.comentario || version.link) && (
          <div className="rounded-xl bg-slate-50 px-3.5 py-2.5 text-sm text-slate-700 dark:bg-slate-800/50 dark:text-slate-300">
            {version.comentario && <p className="whitespace-pre-line">«{version.comentario}»</p>}
            {version.link && (
              <a href={version.link} target="_blank" rel="noopener noreferrer" className="mt-1 inline-block break-all font-semibold text-brand-700 underline underline-offset-2 dark:text-brand-200">
                Abrir el original
              </a>
            )}
          </div>
        )}

        {/* Lo que se pidió en la ronda anterior, para controlar que esté.
            Desde el 19/11/2026 la agencia ya no tilda qué corrigió: la lista
            va sin tilde, numerada como las marcas. Si una ronda vieja trae
            tildes, se muestran. Al lado de cada marca, lo que ve la IA en
            esta ronda («IA: hecho», «IA: falta», «IA: dudoso») y su nota
            abajo, chiquita; la agencia no lo ve (el servidor no se lo da). */}
        {pedidoAntes.length > 0 && (
          <section className="rounded-xl border border-slate-300 p-3 dark:border-slate-700">
            <h4 className="mb-1.5 text-sm font-bold text-slate-900 dark:text-slate-100">Lo que se pidió en la ronda {anterior?.ronda}</h4>
            <ul className="space-y-1">
              {pedidoAntes.map(m => {
                const dice = version.corregidas.includes(m.id)
                const ia = iaDeCadaMarca.get(m.id)
                return (
                  <li key={m.id} className="flex items-start gap-2 text-sm">
                    <span className={`mt-0.5 flex h-5 min-w-[1.25rem] shrink-0 items-center justify-center rounded-full px-1 text-[11px] font-bold ${dice ? 'bg-emerald-500 text-white' : 'bg-brand-600 text-white'}`}>
                      {dice ? <Check className="h-3.5 w-3.5" strokeWidth={3} /> : m.numero}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-start justify-between gap-2">
                        <span className="min-w-0 text-slate-700 dark:text-slate-300">
                          {m.texto}
                          {dice && <span className="ml-1.5 text-xs font-semibold text-emerald-700 dark:text-emerald-300">dice que lo corrigió</span>}
                        </span>
                        {ia && (
                          <span
                            title="Lo que ve la IA en esta ronda. Es una ayuda: se puede equivocar."
                            className={`mt-0.5 shrink-0 whitespace-nowrap rounded-full px-1.5 py-px text-[11px] font-semibold ${COLOR_VEREDICTO[ia.veredicto]}`}
                          >
                            {VEREDICTO_IA[ia.veredicto]}
                          </span>
                        )}
                      </span>
                      {ia?.nota && <span className="mt-0.5 block text-xs text-slate-600 dark:text-slate-400">{ia.nota}</span>}
                    </span>
                  </li>
                )
              })}
            </ul>
          </section>
        )}

        {/* Marcas que ya trae esta misma ronda: solo pasa con rondas de antes
            del 19/11/2026, cuando un aprobador de la cadena podía «aprobar
            con cambios». Sin esta lista, sus pines quedaban sin texto. */}
        {version.marcas.length > 0 && (
          <section className="rounded-xl border border-slate-300 p-3 dark:border-slate-700">
            <h4 className="mb-1.5 text-sm font-bold text-slate-900 dark:text-slate-100">Ya marcado en esta ronda</h4>
            <ul className="space-y-1">
              {version.marcas.map(m => (
                <li key={m.id} className="flex items-start gap-2 text-sm">
                  <span className="mt-0.5 flex h-5 min-w-[1.25rem] shrink-0 items-center justify-center rounded-full bg-brand-600 px-1 text-[11px] font-bold text-white">
                    {m.numero}
                  </span>
                  <span className="min-w-0 text-slate-700 dark:text-slate-300">{m.texto}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {nuevas.length === 0 && (
          <p className="hidden rounded-xl border border-dashed border-slate-300 px-3 py-4 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400 lg:block">
            Tus marcas van a aparecer acá, para escribir qué hay que cambiar.
          </p>
        )}

        {nuevas.length > 0 && (
          <ol className="space-y-2" aria-label="Tus marcas">
            {nuevas.map((n, i) => (
              <li key={n.clave} className={`flex items-start gap-2 rounded-xl border p-2 transition ${elegido === n.clave ? 'border-brand-400 bg-brand-50/60 dark:border-brand-500/50 dark:bg-brand-500/10' : 'border-slate-300 dark:border-slate-700'}`}>
                <button
                  type="button"
                  onClick={() => { setActiva(n.imagenId); setElegido(n.clave) }}
                  className="relative mt-1.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white"
                  aria-label={`Ver la marca ${numeroDe(i)} en la imagen${n.observacionIA ? ' (la armaste con lo que vio la IA)' : ''}`}
                  title={n.observacionIA ? 'La armaste con lo que vio la IA: es tu marca, corregila si hace falta' : undefined}
                >
                  {numeroDe(i)}
                  {/* Una marca hecha con lo que vio la IA: para quien revisa,
                      no para la agencia (a ella le llega como una marca más). */}
                  {n.observacionIA && (
                    <span className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-violet-600 ring-2 ring-white dark:ring-slate-900" aria-hidden>
                      <Sparkles className="h-2.5 w-2.5" />
                    </span>
                  )}
                </button>
                <textarea
                  // La que viene de la IA ya trae texto: sin abrir el teclado.
                  autoFocus={i === nuevas.length - 1 && !n.observacionIA}
                  value={n.texto}
                  onFocus={() => setElegido(n.clave)}
                  onChange={e => setNuevas(prev => prev.map(x => (x.clave === n.clave ? { ...x, texto: e.target.value } : x)))}
                  placeholder="Qué hay que cambiar acá"
                  aria-label={`Qué hay que cambiar en la marca ${numeroDe(i)}`}
                  rows={2}
                  maxLength={1000}
                  className="campo !h-auto min-h-[44px] flex-1 py-2"
                />
                <button
                  type="button"
                  onClick={() => setNuevas(prev => prev.filter(x => x.clave !== n.clave))}
                  className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-500 transition hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-500/10"
                  aria-label={`Borrar la marca ${numeroDe(i)}`}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ol>
        )}

        <label className="block">
          <span className="etiqueta-campo">Comentario para la agencia (opcional)</span>
          <textarea
            value={comentario}
            onChange={e => setComentario(e.target.value)}
            rows={2}
            maxLength={5000}
            placeholder="Algo general, que no va en un punto de la imagen"
            className="campo !h-auto py-2"
          />
        </label>

        {/* La nota interna (como los comentarios internos de Basecamp): la
            ve el equipo en la historia de la tarea; a la agencia el servidor
            no se la manda nunca. */}
        <label className="mt-3 block">
          <span className="etiqueta-campo flex items-center gap-1.5">
            <Lock className="h-3.5 w-3.5 text-amber-600 dark:text-amber-300" aria-hidden />
            Nota interna (opcional)
          </span>
          <textarea
            value={notaInterna}
            onChange={e => setNotaInterna(e.target.value)}
            rows={2}
            maxLength={5000}
            placeholder="Solo la ve el equipo: la agencia no"
            className="campo !h-auto border-amber-200 bg-amber-50/40 py-2 dark:border-amber-500/25 dark:bg-amber-500/5"
          />
        </label>
          </div>
        </div>
      </div>

      <div className="shrink-0 border-t border-slate-300 bg-white px-4 pb-[max(.75rem,env(safe-area-inset-bottom))] pt-2.5 dark:border-slate-700 dark:bg-slate-900 sm:px-6">
        {confirmandoSalir ? (
          <div className="flex flex-wrap items-center gap-2 py-1">
            <p className="flex-1 text-sm font-semibold text-slate-800 dark:text-slate-100">
              Tenés {hayMarcas ? (nuevas.length === 1 ? '1 marca' : `${nuevas.length} marcas`) : 'un comentario'} sin mandar. ¿Salir igual?
            </p>
            <button type="button" onClick={() => setConfirmandoSalir(false)} className="min-h-[44px] rounded-xl px-3 text-sm font-semibold text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800">
              Seguir revisando
            </button>
            <button type="button" autoFocus onClick={onCancelar} className="min-h-[44px] rounded-xl bg-rose-600 px-3 text-sm font-semibold text-white hover:bg-rose-700">
              Salir sin mandar
            </button>
          </div>
        ) : (
          <>
            <div className="mb-2 flex items-start gap-2">
              <p className="flex-1 text-xs text-slate-600 dark:text-slate-400">
                {hayMarcas
                  ? 'Con marcas, la pieza vuelve a la agencia: «Pedir cambios».'
                  : '¿Está bien? Aprobala. ¿Hay algo para cambiar? Tocá la imagen donde está.'}
              </p>
              <button
                type="button"
                onClick={cancelar}
                disabled={!!enviando}
                className="-my-1 shrink-0 rounded-lg px-2 py-1 text-xs font-semibold text-slate-600 underline-offset-2 hover:underline dark:text-slate-300 sm:hidden"
              >
                Cancelar
              </button>
            </div>
            <div className="flex items-stretch gap-2">
              <button
                type="button"
                onClick={cancelar}
                disabled={!!enviando}
                className="hidden min-h-[48px] rounded-xl px-3 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800 sm:block"
              >
                Cancelar
              </button>
              <div className="grid flex-1 grid-cols-2 gap-2 sm:ml-auto sm:flex sm:flex-none">
                <BotonDecision
                  onClick={() => void decidir('aprobada')} cargando={enviando === 'aprobada'}
                  deshabilitado={!!enviando || hayMarcas}
                  titulo={hayMarcas ? 'Con marcas, la pieza vuelve a la agencia: «Pedir cambios»' : undefined}
                  clase="bg-emerald-600 text-white hover:bg-emerald-700"
                  icono={<Check className="h-4 w-4" strokeWidth={3} />}
                  texto="Aprobar"
                />
                <BotonDecision
                  onClick={() => void decidir('cambios')} cargando={enviando === 'cambios'}
                  deshabilitado={!!enviando || !hayParaQuienEntrega}
                  titulo={!hayParaQuienEntrega ? 'Primero marcá en la imagen o escribí en el comentario qué cambiar' : undefined}
                  clase="bg-rose-600 text-white hover:bg-rose-700"
                  icono={<RotateCcw className="h-4 w-4" />}
                  texto="Pedir cambios"
                />
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function BotonDecision({ onClick, cargando, deshabilitado, titulo, clase, icono, texto }: {
  onClick: () => void
  cargando: boolean
  deshabilitado: boolean
  titulo?: string
  clase: string
  icono: React.ReactNode
  texto: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={deshabilitado}
      title={titulo}
      className={`flex min-h-[52px] flex-col items-center justify-center gap-0.5 rounded-xl px-2 text-center text-[13px] font-bold leading-tight shadow-sm transition active:scale-[.98] disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400 disabled:shadow-none dark:disabled:bg-slate-800 dark:disabled:text-slate-500 sm:min-h-[44px] sm:flex-row sm:gap-1.5 sm:px-4 sm:text-sm ${clase}`}
    >
      {cargando ? <Loader2 className="h-4 w-4 animate-spin" /> : icono}
      {texto}
    </button>
  )
}

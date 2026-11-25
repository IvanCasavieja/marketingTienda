'use client'

import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import {
  ArrowRight, Check, Columns2, ExternalLink, Link2, Loader2, Lock, MousePointerClick, RotateCcw, ShieldCheck, Sparkles, Trash2,
} from 'lucide-react'
import { toast } from 'sonner'
import { entregasApi } from '@/lib/api'
import { imagenParaComparar } from '@/lib/calendario/comparar'
import {
  botonGrandeAlRevisar, fechaYHora, textoDeAprobar, type DetalleEntregas, type Marca, type TipoDecision, type Version,
} from '@/lib/calendario/entregas'
import {
  VEREDICTO_IA, cambiosPorMarca, marcaDesdeObservacion, puntosParaMostrar, textoConArchivo, tieneLugar,
  type ObservacionIA, type RevisionIA, type VeredictoIA,
} from '@/lib/calendario/revision-ia'
import { ImagenConMarcas, Miniatura, type Pin } from './ImagenConMarcas'
import { LoQueFalta } from './LoQueFalta'
import { COLOR_DEL_VEREDICTO, LoQueVioLaIA } from './LoQueVioLaIA'
import { PanelRevisionIA } from './PanelRevisionIA'

/** Una marca que se está poniendo. `observacionIA`: si salió de lo que vio la IA. */
type Nueva = { clave: string; imagenId: string; x: number; y: number; texto: string; observacionIA?: string }

// Mientras la IA mira la pieza, se vuelve a preguntar cada tanto: una
// revisión tarda entre unos segundos y un par de minutos. Después de eso, si
// sigue "pendiente", se deja de preguntar (el servidor la da por perdida a
// los 10 minutos y no muestra nada).
const CADA_MS = 5_000
const MAX_VUELTAS = 36

// El número de cada marca de la ronda anterior, del color de lo que dice la
// IA (24/11/2026, Ivan: "que sea azul da impresión de estar bien"): rojo si
// falta, ámbar si no se ve claro, verde si se ve hecho. Sin lo de la IA,
// azul como las marcas. La etiqueta de al lado, COLOR_DEL_VEREDICTO.
const NUMERO_DEL_VEREDICTO: Record<VeredictoIA, string> = {
  falta: 'bg-rose-600 text-white',
  dudoso: 'bg-amber-500 text-white',
  hecho: 'bg-emerald-600 text-white',
}

// La notebook (lg de Tailwind): la imagen a la izquierda y todo lo demás a la
// derecha. Ahí lo que hay que mirar (lo que falta, lo que se pidió y lo de la
// IA) va arriba de la columna de la derecha, al lado de la imagen: arriba de
// la imagen la empujaba media pantalla para abajo y el pin de algo que está
// abajo en la pieza (los legales) quedaba fuera de la vista. En el teléfono,
// una columna sola: va arriba de la imagen.
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
 * Se sacó «Aprobado con cambios» (19/11/2026), que confundía: con marcas,
 * «Pedir cambios» y la pieza vuelve a la agencia. Sin marcas, «Avanzar» (Ivan,
 * 25/11/2026: "si bien se hizo un pedido de muchos banners, ellos primero
 * deben pasarme uno para aprobar y luego trabajar en el resto"): el OK a esa
 * ronda, la agencia sigue con lo que falta y nada se cierra. «Aprobar y
 * terminar» queda abajo, chico, para cuando ya está todo; si ya vinieron todas
 * las piezas del pedido, se invierten (ver botonGrandeAlRevisar). La línea de
 * arriba de los botones dice qué hace cada uno.
 *
 * Lo que hay que mirar va todo junto y abierto, en el costado (en el
 * teléfono, arriba de la imagen): las piezas del pedido que faltan, lo que
 * se pidió con lo que vio la IA de cada cosa, y lo que encontró la IA en la
 * pieza. Ivan (24/11/2026): "siempre se debe abrir por defecto lo que la IA
 * detecta, no esperar que yo presione arriba, y unifiquemos: aparece un
 * cartel arriba y lo otro en el costado, debería aparecer todo en el
 * costado, y debería tener un color más rojito, colorado: que sea azul da
 * impresión de estar bien". Del 19/11/2026 hasta ese día lo de la IA se
 * abría con un botón arriba, "Ver lo que encontró la IA (3)" (Ivan, ese día:
 * "quizás está demasiado inteligencia artificial"), y lo que faltaba iba en
 * un cartel arriba de todo. Si hay algo mal (falta una pieza, algo pedido no
 * está o la IA encontró algo), el bloque va con borde rojo; lo que falta en
 * rojo, lo dudoso en ámbar y lo hecho en verde.
 *
 * En «Lo que se pidió en la ronda N», si se ve hecho lo que pedía cada marca
 * (19/11/2026, Ivan: "debería de hacerlo"): una etiqueta chica al lado de
 * cada una, con la nota abajo. Es justo el control que hace quien aprueba.
 *
 * Y, desde el 21/11/2026, lo mismo de lo que se pidió sin marcas: en la
 * primera ronda, cada punto del pedido inicial («Lo que se pidió»); si los
 * cambios se pidieron solo con texto, cada pedido del comentario. Ivan, con
 * su prueba de Publicis: a la agencia el control le dijo dos cosas y a quien
 * aprobaba ninguna ("estaría bueno que se reconozcan los mismos"). Se ve con
 * el mismo diseño que el aviso de la agencia (LoQueVioLaIA), más lo que la
 * IA ve hecho. Si la agencia entregó las mismas imágenes que controló, la
 * revisión sale de ese control: es lo mismo que vio ella (desde el
 * 24/11/2026, también lo que encontró en la pieza).
 *
 * Comparar con la ronda anterior: cada columna con su tira de miniaturas, y
 * si la de ahora no tiene pareja se dice (lib/calendario/comparar.ts).
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
  // Comparando: la de la ronda anterior que se eligió en su tira, para la
  // imagen de ahora que se estaba mirando (si se cambia, vuelve a su pareja).
  const [anteriorElegida, setAnteriorElegida] = useState<{ para: string; id: string } | null>(null)
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

  // Ivan (25/11/2026): "a medida que se agregan comentarios, cuando excede el
  // límite de la pantalla nos baja hasta la parte de abajo; quizás debería
  // estar la imagen del lado izquierdo aislada del lado derecho". En la
  // notebook cada columna tiene su desplazamiento (ver el return); en el
  // teléfono la imagen queda fija arriba. Y la marca nueva se enfoca sin el
  // salto del autoFocus: se mueve solo lo justo para que se vea su campo.
  const porEnfocar = useRef<string | null>(null)
  const contenedor = useRef<HTMLDivElement>(null)
  const columnaImagen = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const clave = porEnfocar.current
    if (!clave) return
    porEnfocar.current = null
    const campo = document.querySelector<HTMLTextAreaElement>(`textarea[data-marca="${clave}"]`)
    if (!campo) return
    campo.focus({ preventScroll: true })
    campo.scrollIntoView({ block: 'nearest' })
  }, [nuevas])
  // En el teléfono la imagen queda fija arriba: lo que se enfoca o se lleva a
  // la vista no tiene que quedar tapado por ella.
  useEffect(() => {
    const caja = contenedor.current
    const fija = columnaImagen.current
    if (!caja || !fija) return
    if (esNotebook) { caja.style.scrollPaddingTop = ''; return }
    const medir = () => { caja.style.scrollPaddingTop = `${fija.offsetHeight + 12}px` }
    medir()
    const ro = new ResizeObserver(medir)
    ro.observe(fija)
    return () => ro.disconnect()
  }, [esNotebook])

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
  const numeroActiva = version.imagenes.findIndex(i => i.id === activa) + 1
  // La de la ronda anterior que va al lado (24/11/2026): la elegida en su
  // tira, si no la del mismo lugar, y si no hay, la primera avisando.
  const comparada = imagenParaComparar(
    anterior?.imagenes ?? [], ordenActiva, anteriorElegida?.para === activa ? anteriorElegida.id : null,
  )
  const imagenAnterior = comparada.id
  // Las imágenes entre las que se cambia: el lugar de la imagen toma el alto
  // de la más alta (25/11/2026). Comparando, las de las dos rondas, así las
  // dos columnas (o las dos pestañas, en el teléfono) quedan del mismo alto.
  const vivasDe = (v: Version | null) => (v?.imagenes ?? []).filter(i => !i.purgada).map(i => i.id)
  const ronda = comparar ? [...vivasDe(version), ...vivasDe(anterior)] : vivasDe(version)
  const siguienteNumero = Math.max(0, ...version.marcas.map(m => m.numero)) + 1
  const numeroDe = (i: number) => siguienteNumero + i
  const pinesNuevos: Pin[] = nuevas.flatMap((n, i) => (n.imagenId === activa
    ? [{ clave: n.clave, numero: numeroDe(i), x: n.x, y: n.y, tono: 'nuevo' as const, texto: n.texto }]
    : []))
  // Las observaciones de la IA que ya se hicieron marca en esta revisión: id -> número de la marca.
  const convertidas: Record<string, number> = Object.fromEntries(
    nuevas.flatMap((n, i) => (n.observacionIA ? [[n.observacionIA, numeroDe(i)]] : [])),
  )
  // Dónde vio la IA lo que se tocó en la lista: un pin rojo que no es una
  // marca. Si ya se hizo marca, se ve la marca y no hace falta.
  const observacion = revisionIA?.observaciones.find(o => o.id === obsElegida) ?? null
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
  // Lo que se pidió sin marcas (el pedido inicial o el comentario) y lo que
  // vio la IA de cada cosa (21/11/2026).
  const puntos = puntosParaMostrar(revisionIA)
  const respaldoDe = detalle.puedo.comoRespaldo ? detalle.resumen.aprobadorDeTurno : null
  // Lo de la IA se ve siempre abierto (24/11/2026), mientras mira también.
  const hayIA = verIA && !!revisionIA && revisionIA.estado !== 'nada'
  // Lo que hay que mirar, todo junto en el costado (24/11/2026): si algo
  // está mal, el bloque va con borde rojo.
  const faltanPiezas = (version.faltan?.length ?? 0) > 0
  // El botón grande (25/11/2026): Avanzar, salvo que ya estén todas las piezas.
  const grande = botonGrandeAlRevisar(detalle.tarea.piezas?.length ?? 0, version.imagenes.length, version.faltan)
  const esUltimaFase = detalle.fases[detalle.fases.length - 1]?.id === version.faseId
  const turno = detalle.resumen.aprobadorDeTurno
  const lugarEnLaCadena = turno != null ? detalle.aprobadores.indexOf(turno) : -1
  const textoAprobar = textoDeAprobar(
    esUltimaFase, lugarEnLaCadena === -1 ? 0 : detalle.aprobadores.length - lugarEnLaCadena - 1,
  )
  const algoMal = faltanPiezas
    || (revisionIA?.estado === 'lista' && revisionIA.observaciones.some(o => o.estado === 'nueva'))
    || !!puntos?.puntos.some(p => p.veredicto !== 'hecho')
    || pedidoAntes.some(m => { const v = iaDeCadaMarca.get(m.id)?.veredicto; return v === 'falta' || v === 'dudoso' })

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
    porEnfocar.current = clave
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
        : decision === 'avanzar'
          ? 'Listo: le diste el OK. Sigue con lo que falta.'
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
      // En el teléfono queda fija arriba mientras se escribe: más baja. En
      // la notebook, lo que deja la columna después de la tira y la ayuda:
      // entra todo sin desplazar (25/11/2026).
      claseImagen={comparar ? 'max-h-[30vh] lg:max-h-[calc(100dvh_-_30rem)]'
        : version.imagenes.length > 1 ? 'max-h-[34vh] lg:max-h-[calc(100%_-_7.5rem)]' : 'max-h-[34vh] lg:max-h-[calc(100%_-_3rem)]'}
      etiqueta={`Ronda ${version.ronda}, imagen ${ordenActiva + 1}`}
      ronda={ronda}
    />
  )
  // Lo que hay que mirar, todo junto y abierto (24/11/2026, Ivan: "debería
  // aparecer todo en el costado"): las piezas que faltan, lo que se pidió con
  // lo que vio la IA de cada cosa, y lo que la IA encontró en la pieza. En la
  // notebook arriba de la columna de la derecha; en el teléfono, arriba de la
  // imagen. Cada parte, si tiene algo; sin nada, no se muestra.
  const partes: { clave: string; contenido: React.ReactNode }[] = []
  if (faltanPiezas) {
    // Las piezas del pedido que no vinieron en esta ronda, y por qué (21/11/2026).
    partes.push({ clave: 'faltan', contenido: <LoQueFalta detalle={detalle} version={version} enPanel /> })
  }
  if (puntos) {
    // Lo que se pidió sin marcas y lo que vio la IA de cada cosa
    // (21/11/2026): en la primera ronda, el pedido inicial; si los cambios
    // se pidieron solo escritos, cada pedido del comentario. Con el mismo
    // diseño que el aviso de la agencia antes de mandar. Sin revisión de la
    // IA (o mientras mira) no hay nada que mostrar: los puntos vienen con ella.
    partes.push({ clave: 'puntos', contenido: (
      <section aria-labelledby="lo-que-se-pidio">
        <h4 id="lo-que-se-pidio" className="text-sm font-bold text-slate-900 dark:text-slate-100">
          {puntos.inicial || !anterior ? 'Lo que se pidió' : `Lo que se pidió en la ronda ${anterior.ronda}`}
        </h4>
        {/* No se dice "lo que vio la agencia": si mandó sin esperar a la
            IA, o con un ZIP o un link, la revisión corrió después. */}
        <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-400">
          Lo que vio la IA en cada punto. Es una ayuda y se puede equivocar.
        </p>
        <div className="-mb-2.5 mt-1">
          <LoQueVioLaIA cambios={puntos.puntos} />
        </div>
      </section>
    ) })
  }
  if (pedidoAntes.length > 0) {
    // Lo que se pidió en la ronda anterior, para controlar que esté. Desde el
    // 19/11/2026 la agencia ya no tilda qué corrigió: la lista va sin tilde,
    // numerada como las marcas. Si una ronda vieja trae tildes, se muestran.
    // Al lado de cada marca, lo que ve la IA en esta ronda («IA: hecho»,
    // «IA: falta», «IA: dudoso») y su nota abajo; el número, del color de lo
    // que dice la IA (24/11/2026: en azul, un «falta» parecía estar bien).
    partes.push({ clave: 'pedido', contenido: (
      <section aria-labelledby="lo-que-se-pidio-antes">
        <h4 id="lo-que-se-pidio-antes" className="mb-1.5 text-sm font-bold text-slate-900 dark:text-slate-100">
          Lo que se pidió en la ronda {anterior?.ronda}
        </h4>
        <ul className="space-y-1.5">
          {pedidoAntes.map(m => {
            const dice = version.corregidas.includes(m.id)
            const ia = iaDeCadaMarca.get(m.id)
            const numero = ia ? NUMERO_DEL_VEREDICTO[ia.veredicto] : dice ? 'bg-emerald-600 text-white' : 'bg-red-600 text-white'
            return (
              <li key={m.id} className="flex items-start gap-2 text-sm">
                <span className={`mt-0.5 flex h-5 min-w-[1.25rem] shrink-0 items-center justify-center rounded-full px-1 text-[11px] font-bold ${numero}`}>
                  {dice && !ia ? <Check className="h-3.5 w-3.5" strokeWidth={3} /> : m.numero}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-start justify-between gap-2">
                    <span className={`min-w-0 ${ia?.veredicto === 'falta' ? 'font-semibold text-slate-900 dark:text-slate-100' : 'text-slate-700 dark:text-slate-300'}`}>
                      {m.texto}
                      {dice && <span className="ml-1.5 text-xs font-semibold text-emerald-700 dark:text-emerald-300">dice que lo corrigió</span>}
                    </span>
                    {ia && (
                      <span
                        title="Lo que ve la IA en esta ronda. Es una ayuda: se puede equivocar."
                        className={`mt-0.5 shrink-0 whitespace-nowrap rounded-full px-1.5 py-px text-[11px] font-bold ${COLOR_DEL_VEREDICTO[ia.veredicto]}`}
                      >
                        {VEREDICTO_IA[ia.veredicto]}
                      </span>
                    )}
                  </span>
                  {ia?.nota && <span className="mt-0.5 block text-xs text-slate-700 dark:text-slate-300">{ia.nota}</span>}
                </span>
              </li>
            )
          })}
        </ul>
      </section>
    ) })
  }
  if (hayIA) {
    partes.push({ clave: 'ia', contenido: (
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
      />
    ) })
  }
  const loQueHayQueMirar = partes.length > 0 ? (
    <div
      role="region"
      aria-label="Lo que hay que mirar"
      className={`divide-y rounded-2xl border-2 ${
        algoMal
          ? 'divide-rose-200 border-rose-300 dark:divide-rose-500/25 dark:border-rose-500/50'
          : 'divide-slate-300 border-slate-300 dark:divide-slate-700 dark:border-slate-700'
      }`}
    >
      {partes.map(p => <div key={p.clave} className="p-3">{p.contenido}</div>)}
    </div>
  ) : null
  const imagenVieja = imagenAnterior && anterior ? (
    <ImagenConMarcas
      imagenId={imagenAnterior}
      pines={pinesDe(anterior.marcas, imagenAnterior)}
      claseImagen="max-h-[30vh] lg:max-h-[calc(100dvh_-_30rem)]"
      etiqueta={`La versión anterior (ronda ${anterior.ronda}), imagen ${comparada.numero ?? 1}`}
      ronda={ronda}
    />
  ) : null

  // La tira de miniaturas de esta ronda: cambia la imagen de ahora. Al
  // comparar va adentro de la columna «Ahora» (24/11/2026: abajo de las dos
  // parecía de la ronda anterior).
  const tiraNueva = version.imagenes.length > 1 ? (
    <div className="flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label={`Imágenes de la ronda ${version.ronda}`}>
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
            <Miniatura imagenId={im.id} etiqueta={`Imagen ${i + 1}`} className={comparar ? 'h-12 w-12' : 'h-12 w-12 lg:h-16 lg:w-16'} />
            {cuantas > 0 && (
              <span className="absolute -right-1 -top-1 flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-red-600 px-1 text-[11px] font-bold text-white">{cuantas}</span>
            )}
          </button>
        )
      })}
    </div>
  ) : null
  // La de la ronda anterior, si tenía varias: cambia solo la de «Antes».
  const tiraAnterior = comparar && anterior && anterior.imagenes.length > 1 ? (
    <div className="flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label={`Imágenes de la ronda ${anterior.ronda}`}>
      {anterior.imagenes.map((im, i) => (
        <button
          key={im.id}
          type="button"
          role="tab"
          aria-selected={im.id === imagenAnterior}
          onClick={() => setAnteriorElegida({ para: activa, id: im.id })}
          className={`relative shrink-0 rounded-xl p-0.5 transition ${im.id === imagenAnterior ? 'ring-2 ring-slate-500 dark:ring-slate-300' : 'opacity-70 hover:opacity-100'}`}
        >
          <Miniatura imagenId={im.id} etiqueta={`Imagen ${i + 1} de la ronda ${anterior.ronda}`} className="h-12 w-12" />
        </button>
      ))}
    </div>
  ) : null
  const nombreAnterior = anterior?.faseId === version.faseId ? `ronda ${anterior?.ronda}` : 'fase anterior'

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div ref={contenedor} className="flex-1 space-y-4 overflow-y-auto overscroll-contain px-4 py-4 sm:px-6 lg:flex lg:flex-col lg:gap-4 lg:space-y-0 lg:overflow-hidden">
        <div className="flex flex-wrap items-start justify-between gap-2 lg:shrink-0">
          <div className="min-w-0">
            <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">Revisar la ronda {version.ronda} de {fase?.nombre}</h3>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              La subió {nombre(version.subidaPor)} · {fechaYHora(version.fecha)}
            </p>
          </div>
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

        {respaldoDe != null && (
          <p className="flex items-start gap-2 lg:shrink-0 rounded-xl border border-violet-200 bg-violet-50 px-3 py-2 text-sm text-violet-900 dark:border-violet-500/30 dark:bg-violet-500/10 dark:text-violet-200">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
            Le tocaba a {nombre(respaldoDe)}. Decidís vos como respaldo: queda anotado.
          </p>
        )}

        {!esNotebook && loQueHayQueMirar}

        {/* En la notebook, la imagen a la izquierda y las marcas a la derecha,
            cada una con su desplazamiento: agregar marcas mueve solo la
            columna de la derecha, nunca la imagen (25/11/2026). En el
            teléfono, una abajo de la otra, con la imagen fija arriba. */}
        <div className="space-y-4 lg:grid lg:min-h-0 lg:flex-1 lg:grid-cols-[minmax(0,1fr)_22rem] lg:grid-rows-[minmax(0,1fr)] lg:gap-6 lg:space-y-0">
          <div
            ref={columnaImagen}
            className={`space-y-3 lg:min-h-0 lg:overflow-y-auto lg:overscroll-contain ${sinImagenes ? '' : 'sticky top-0 z-10 -mx-4 bg-white px-4 pb-3 pt-1 shadow-[0_10px_10px_-10px_rgba(15,23,42,0.25)] dark:bg-slate-900 sm:-mx-6 sm:px-6 lg:static lg:mx-0 lg:bg-transparent lg:px-0 lg:pb-0 lg:pt-0 lg:shadow-none lg:dark:bg-transparent'}`}
          >
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
            {/* Cada columna con lo suyo (24/11/2026): la imagen, su número y
                su tira de miniaturas. */}
            <div className="grid gap-3 sm:grid-cols-2">
              <figure className={`space-y-2 ${ladoMovil === 'anterior' ? '' : 'hidden sm:block'}`}>
                <figcaption className="text-xs font-bold uppercase tracking-wide text-slate-600 dark:text-slate-300">
                  Antes · {nombreAnterior}{anterior && anterior.imagenes.length > 1 ? ` · imagen ${comparada.numero}` : ''}
                </figcaption>
                {comparada.sinPareja && (
                  <p className="rounded-lg bg-amber-50 px-2.5 py-1.5 text-xs font-medium text-amber-950 ring-1 ring-amber-300 dark:bg-amber-500/10 dark:text-amber-100 dark:ring-amber-500/40">
                    La {nombreAnterior} no tenía imagen {numeroActiva}: se ve la 1.{tiraAnterior ? ' Elegí otra abajo.' : ''}
                  </p>
                )}
                {imagenVieja}
                {tiraAnterior}
              </figure>
              <figure className={`space-y-2 ${ladoMovil === 'nueva' ? '' : 'hidden sm:block'}`}>
                <figcaption className="text-xs font-bold uppercase tracking-wide text-brand-700 dark:text-brand-200">
                  Ahora · ronda {version.ronda}{version.imagenes.length > 1 ? ` · imagen ${numeroActiva}` : ''}
                </figcaption>
                {imagenNueva}
                {tiraNueva}
              </figure>
            </div>
          </>
        ) : (
          <>
            {imagenNueva}
            {tiraNueva}
          </>
        )}

        {!sinImagenes && (
          <p className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
            <MousePointerClick className="h-4 w-4 shrink-0 text-brand-600 dark:text-brand-300" />
            Tocá la imagen donde hay que cambiar algo: queda una marca numerada.
          </p>
        )}
          </div>

          <div className="space-y-4 lg:min-h-0 lg:overflow-y-auto lg:overscroll-contain lg:px-1 lg:pb-2">
        {esNotebook && loQueHayQueMirar}
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

        {/* Marcas que ya trae esta misma ronda: solo pasa con rondas de antes
            del 19/11/2026, cuando un aprobador de la cadena podía «aprobar
            con cambios». Sin esta lista, sus pines quedaban sin texto. */}
        {version.marcas.length > 0 && (
          <section className="rounded-xl border border-slate-300 p-3 dark:border-slate-700">
            <h4 className="mb-1.5 text-sm font-bold text-slate-900 dark:text-slate-100">Ya marcado en esta ronda</h4>
            <ul className="space-y-1">
              {version.marcas.map(m => (
                <li key={m.id} className="flex items-start gap-2 text-sm">
                  <span className="mt-0.5 flex h-5 min-w-[1.25rem] shrink-0 items-center justify-center rounded-full bg-red-600 px-1 text-[11px] font-bold text-white">
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
                  className="relative mt-1.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-red-600 text-xs font-bold text-white"
                  aria-label={`Ver la marca ${numeroDe(i)} en la imagen${n.observacionIA ? ' (la armaste con lo que vio la IA)' : ''}`}
                  title={n.observacionIA ? 'La armaste con lo que vio la IA: es tu marca, corregila si hace falta' : undefined}
                >
                  {numeroDe(i)}
                  {/* Una marca hecha con lo que vio la IA: para quien revisa,
                      no para la agencia (a ella le llega como una marca más). */}
                  {n.observacionIA && (
                    <span className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-rose-600 ring-2 ring-white dark:ring-slate-900" aria-hidden>
                      <Sparkles className="h-2.5 w-2.5" />
                    </span>
                  )}
                </button>
                <textarea
                  // Se enfoca sola la que se pone tocando la imagen (ver
                  // porEnfocar); la que viene de la IA ya trae texto: sin
                  // abrir el teclado.
                  data-marca={n.clave}
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
                  : grande === 'avanzar'
                    ? '«Avanzar»: va bien y sigue con lo que falta. ¿Algo para cambiar? Tocá la imagen.'
                    : 'Ya están todas las piezas del pedido. ¿Algo para cambiar? Tocá la imagen.'}
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
              <div className="flex flex-1 flex-col gap-1 sm:ml-auto sm:flex-none">
                <div className="grid grid-cols-2 gap-2 sm:flex">
                  <BotonDecision
                    onClick={() => void decidir('cambios')} cargando={enviando === 'cambios'}
                    deshabilitado={!!enviando || !hayParaQuienEntrega}
                    titulo={!hayParaQuienEntrega ? 'Primero marcá en la imagen o escribí en el comentario qué cambiar' : undefined}
                    clase="bg-rose-600 text-white hover:bg-rose-700"
                    icono={<RotateCcw className="h-4 w-4" />}
                    texto="Pedir cambios"
                  />
                  {grande === 'avanzar' ? (
                    <BotonDecision
                      onClick={() => void decidir('avanzar')} cargando={enviando === 'avanzar'}
                      deshabilitado={!!enviando || hayMarcas}
                      titulo={hayMarcas ? 'Con marcas, la pieza vuelve a la agencia: «Pedir cambios»' : 'Va bien: la agencia sigue con lo que falta'}
                      clase="bg-emerald-600 text-white hover:bg-emerald-700"
                      icono={<Check className="h-4 w-4" strokeWidth={3} />}
                      texto="Avanzar"
                    />
                  ) : (
                    <BotonDecision
                      onClick={() => void decidir('aprobada')} cargando={enviando === 'aprobada'}
                      deshabilitado={!!enviando || hayMarcas}
                      titulo={hayMarcas ? 'Con marcas, la pieza vuelve a la agencia: «Pedir cambios»' : undefined}
                      clase="bg-emerald-600 text-white hover:bg-emerald-700"
                      icono={<Check className="h-4 w-4" strokeWidth={3} />}
                      texto={textoAprobar}
                    />
                  )}
                </div>
                {/* La otra salida, chica (Ivan, 25/11/2026: «¿Ya está todo?
                    Aprobar y terminar»; si ya vino todo, al revés). */}
                <button
                  type="button"
                  onClick={() => void decidir(grande === 'avanzar' ? 'aprobada' : 'avanzar')}
                  disabled={!!enviando || hayMarcas}
                  className="flex min-h-[36px] items-center justify-end gap-1 self-end rounded-lg px-2 text-[13px] text-slate-600 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 dark:text-slate-300 dark:hover:bg-slate-800"
                >
                  {enviando && enviando !== 'cambios' && enviando !== (grande === 'avanzar' ? 'avanzar' : 'aprobada')
                    ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    : null}
                  <span>{grande === 'avanzar' ? '¿Ya está todo?' : '¿Falta algo?'}</span>
                  <span className="font-bold text-emerald-700 underline underline-offset-2 dark:text-emerald-300">
                    {grande === 'avanzar' ? textoAprobar : 'Avanzar'}
                  </span>
                  {grande === 'terminar' && <ArrowRight className="h-3.5 w-3.5 text-emerald-700 dark:text-emerald-300" />}
                </button>
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

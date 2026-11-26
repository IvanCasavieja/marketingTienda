'use client'

import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Camera, FileArchive, ImagePlus, Link2, Loader2, RotateCcw, Send, X } from 'lucide-react'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { entregasApi } from '@/lib/api'
import { useCurrentUser } from '@/hooks/useCurrentUser'
import { claveDeBorrador } from '@/lib/calendario/borrador'
import {
  conLugar, hayQueControlar, mismasImagenes, observacionesParaAvisar, paraAvisar, textosDelControl,
  type CambioControlado, type ControlPrevio, type ObservacionDelControl,
} from '@/lib/calendario/control-previo'
import { TIPO_OBSERVACION, agruparIguales, textoDeImagenes } from '@/lib/calendario/revision-ia'
import {
  nuevoIdDeVersion, prepararImagen, type DetalleEntregas, type ImagenLista,
} from '@/lib/calendario/entregas'
import {
  faltanEnLaEntrega, medidaDePieza, primeras, tituloDeLasPiezas, type Medidas, type Pieza,
} from '@/lib/calendario/piezas'
import {
  abrirEntrada, avisoZipSinGuardar, detalleDelZip, leerIndiceZip, medidasDeEntrada, nombreCorto, tipoDeImagen,
  zipSumaImagenes, zipYaResueltas, ZipRaro, type EntradaZip, type EstadoDelZip,
} from '@/lib/calendario/zip'
import { LoQueVioLaIA } from './LoQueVioLaIA'
import { useBorradorDeEntrega } from './borradores'

function detalleDeError(e: unknown): string | null {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === 'string' ? d : null
}

const mb = (n: number) => `${(n / 1024 / 1024).toFixed(1).replace('.', ',')} MB`

/** Una imagen de la ronda; `deZip`: su lugar en el índice del ZIP, si salió de ahí. */
type Imagen = ImagenLista & { deZip?: number }

/** El ZIP elegido: su índice (null si no se pudo leer acá), las imágenes de
 *  adentro que la persona sacó de la ronda (el servidor no las vuelve a poner)
 *  y el tamaño original de todas sus imágenes (null en una que no se pudo
 *  medir; null entero si no se leyó el índice), para ver si falta alguna
 *  pieza del pedido. */
type ZipElegido = { archivo: File; entradas: EntradaZip[] | null; sacadas: number[]; medidas: (Medidas | null)[] | null }

/** Lo que se avisa antes de mandar (ver AvisoAntesDeMandar). */
type Avisos = { lista: CambioControlado[]; observaciones: ObservacionDelControl[]; faltan: Pieza[] }
const soloLoQueFalta = (faltan: Pieza[]): Avisos => ({ lista: [], observaciones: [], faltan })

/**
 * Entregar una ronda: las imágenes (de la cámara o de la galería), un
 * comentario y el link al original. Las imágenes se achican acá antes de
 * subir.
 *
 * Antes, en una ronda que volvía, arriba de las imágenes iba "¿Qué
 * corregiste? Tildá cada marca". Se sacó (Ivan, 19/11/2026: "siento que eso
 * no debería ni siquiera estar. Se supone que la agencia ya leyó los
 * cambios, y una vez que cargan la imagen, vos vas a verificar si esos
 * cambios están hechos"). Lo que hay que corregir se ve en la ficha, con la
 * imagen; acá solo se entrega. Al servidor se le sigue mandando la lista de
 * marcas corregidas, vacía, para no cambiarle el pedido.
 *
 * La carpeta comprimida (19/11/2026, Ivan: "nos pasan link de WeTransfer o
 * link de Smash o una carpeta comprimida directamente"): al elegir el ZIP se
 * sacan acá las primeras imágenes de adentro y quedan como las imágenes de la
 * ronda, para que quien aprueba las vea y las marque. El ZIP viaja siempre:
 * el servidor lo guarda tal cual, como el original de la ronda ("cuando lo
 * subís deberías de subir la carpeta comprimida"), y con los lugares de
 * imagen que queden pasa a la ronda lo que acá no se pudo mostrar, como las
 * páginas de un PDF. Por eso un ZIP con solo el folleto en PDF alcanza para
 * entregar (lib/calendario/zip.ts).
 *
 * Antes de mandar, la IA (20/11/2026, Ivan: "que a la agencia, cuando va a
 * subir los archivos, la IA le diga 'che, pará, acá faltan estas cositas de
 * los cambios'"): con imágenes, "Entregar" las manda primero al control
 * previo. En una ronda que volvió con cambios mira esos cambios; desde el
 * 21/11/2026 también la primera entrega, contra el pedido inicial (Ivan:
 * "No lo hace en la primera entrega, eso está mal"), con sus propios textos.
 * Mientras mira (hasta un minuto) se puede "Mandar sin esperar". Si ve algo
 * que falta o que no se ve claro, lo muestra con "Corregir" o "Mandar
 * igual"; si no, manda solo. Si la IA no está, no hay nada que controlar o
 * falla, manda igual: nunca traba (lib/calendario/control-previo.ts).
 *
 * Las piezas del pedido que faltan (21/11/2026, Ivan: "si yo pido 4 banners
 * y me pasan uno (...) tiene que analizar y decir 'che, pará, acá faltan
 * también los banners X o Y'. Y quizás estaría bueno que le des el espacio
 * a la agencia ahí de escribir por qué no los manda"): eso no lo dice la
 * IA, que a veces lo ve y a veces no, sino la plataforma sola, comparando
 * lo pedido (tarea.piezas) con el tamaño original de cada imagen suelta y
 * de todas las del ZIP (lib/calendario/piezas.ts). Si falta alguna, antes de
 * mandar sale el aviso en cualquier ronda, con lo que vea la IA si vio algo,
 * aunque la IA no esté; y un lugar para escribir por qué no va todo. Si se
 * manda igual, lo que falta y el porqué viajan con la ronda.
 *
 * Cómo se ve el aviso (21/11/2026, Ivan: "las correcciones de la IA están
 * súper mezcladas, no tiene un formato bonito de ver ni nada"): ocupa el
 * lugar del formulario, que hace scroll, y los botones quedan siempre a la
 * vista abajo (ver AvisoAntesDeMandar).
 *
 * Lo que la IA encontró en la pieza (24/11/2026, Ivan: "la IA sigue
 * encontrando cosas del lado de Tienda que no encuentra del lado de la
 * agencia (...) la acción era TiendaChecks y le mandaron una placa de
 * Ciberofertas"): el aviso trae también las observaciones, las mismas que
 * ve quien aprueba, con la imagen y dónde. La IA mira la pieza aunque no se
 * haya pedido nada.
 */
export function FormularioEntrega({ detalle, onListo, onCancelar }: {
  detalle: DetalleEntregas
  onListo: () => void
  onCancelar: () => void
}) {
  const { resumen, limites } = detalle
  const fase = resumen.fases.find(f => f.id === resumen.faseActual)
  const ronda = resumen.ronda + 1
  // Es una ronda que volvió con cambios (cambia el ejemplo del comentario).
  const volvio = resumen.momento === 'cambios'
  // Ir y venir (25/11/2026): la que espera revisión queda reemplazada por esta.
  const reemplaza = resumen.momento === 'revision' ? resumen.ronda : null
  // Lo que pidieron cambiar en la que volvió (H-037 de la auditoría del
  // 25/11/2026: el formulario solo decía «Subí la pieza» y las marcas
  // quedaban dos pantallas más abajo): a la vista mientras se entrega.
  const faseDetalle = detalle.fases.find(f => f.id === resumen.faseActual)
  const queVolvio = volvio ? faseDetalle?.versiones[faseDetalle.versiones.length - 1] ?? null : null
  const pedidoDeCambios = queVolvio
    ? [
        ...queVolvio.decisiones.filter(d => d.decision === 'cambios' && d.comentario).map(d => d.comentario as string),
        ...queVolvio.marcas.map(m => `${m.numero}. ${m.texto}`),
      ]
    : []
  // La primera entrega de la fase: la IA la mira contra el pedido inicial
  // (21/11/2026). Para el texto de mientras mira.
  const primera = ronda === 1

  // El id se arma una vez: si la subida se corta y se reintenta, el
  // servidor reconoce que es la misma y no la duplica. Vuelve con lo
  // guardado en el navegador (ver useBorradorDeEntrega).
  const [versionId, setVersionId] = useState(nuevoIdDeVersion)
  const [imagenes, setImagenes] = useState<Imagen[]>([])
  const [preparando, setPreparando] = useState(0)
  const [comentario, setComentario] = useState('')
  const [link, setLink] = useState('')
  const [subiendo, setSubiendo] = useState<number | null>(null)
  const [zip, setZip] = useState<ZipElegido | null>(null)
  const [leyendoZip, setLeyendoZip] = useState(false)
  // El control de la IA antes de mandar: mientras mira, y lo que encontró.
  const [controlando, setControlando] = useState<AbortController | null>(null)
  // Lo que se avisa antes de mandar: `lista`, lo que vio la IA de lo pedido;
  // `observaciones`, lo que encontró en la pieza (24/11/2026); `faltan`, las
  // piezas del pedido que no vienen (las ve la plataforma sola).
  const [avisos, setAvisos] = useState<Avisos | null>(null)
  // «¿Por qué no va todo?»: lo que escribe quien entrega si falta alguna pieza.
  const [porQue, setPorQue] = useState('')
  // Las imágenes que ya miró: si se vuelve a entregar sin cambiarlas, se manda.
  const yaControladas = useRef<Blob[] | null>(null)
  const ocupado = subiendo !== null || controlando !== null
  // Si hay algo cargado: «atrás», recargar o cerrar la pestaña preguntan
  // antes de perderlo (H-039 de la auditoría del 25/11/2026: lo cargado se
  // perdía sin preguntar; con Escape ya estaba protegido).
  const hayAlgo = imagenes.length > 0 || zip !== null || comentario.trim() !== '' || link.trim() !== ''
  const hayAlgoRef = useRef(false)
  // Y si igual se sale (recargar sin querer, el iPhone, que no pregunta, la
  // sesión que venció), lo cargado queda guardado en este navegador y vuelve
  // al entregar de nuevo esta tarjeta (H-039; lib/calendario/borrador.ts).
  const { t } = useTranslation()
  const { user } = useCurrentUser()
  const olvidarBorrador = useBorradorDeEntrega({
    clave: user ? claveDeBorrador(user.id, detalle.tarea.id) : null,
    entrega: {
      fase: resumen.faseActual, ronda: resumen.ronda,
      versiones: detalle.fases.flatMap(f => f.versiones.map(v => v.id)),
    },
    cargado: { versionId, comentario, link, porQue, imagenes, zip: zip?.archivo.name ?? null },
    quieto: preparando === 0 && !leyendoZip && subiendo === null,
    alRecuperar: b => {
      // Si ya se empezó a cargar otra cosa, manda lo nuevo.
      if (hayAlgoRef.current) return
      setVersionId(b.versionId)
      setComentario(b.comentario)
      setLink(b.link)
      setPorQue(b.porQue)
      setImagenes(b.imagenes.map(im => ({ ...im, vista: URL.createObjectURL(im.mini) })))
      toast.success(b.zip ? t('calendario.entrega.recuperadoSinZip', { zip: b.zip }) : t('calendario.entrega.recuperado'), {
        duration: 10_000,
        action: { label: t('calendario.entrega.descartar'), onClick: empezarDeCero },
      })
    },
  })
  /** «Descartar» lo recuperado: el formulario, vacío. */
  function empezarDeCero() {
    olvidarBorrador()
    setImagenes(prev => {
      prev.forEach(im => URL.revokeObjectURL(im.vista))
      return []
    })
    setZip(null)
    setComentario('')
    setLink('')
    setPorQue('')
  }
  const cancelarRef = useRef(onCancelar)
  useEffect(() => {
    hayAlgoRef.current = hayAlgo && subiendo === null
    // Salir con «atrás» descarta lo cargado, como Cancelar: no queda guardado.
    cancelarRef.current = () => {
      olvidarBorrador()
      onCancelar()
    }
  }, [hayAlgo, subiendo, onCancelar, olvidarBorrador])
  useEffect(() => {
    const alSalir = (e: BeforeUnloadEvent) => {
      if (!hayAlgoRef.current) return
      e.preventDefault()
      e.returnValue = ''
    }
    // «Atrás»: se deja un paso en la historia con la misma dirección; si se
    // vuelve con algo cargado, se pregunta. Si se confirma, se sale.
    // El paso lleva una marca: al cerrar el formulario de forma normal, si
    // sigue arriba de todo, se saca (así «atrás» después no queda muerto).
    const marcar = () => window.history.pushState({ ...(window.history.state ?? {}), formEntrega: true }, '', window.location.href)
    marcar()
    let saliendo = false
    const alVolver = () => {
      if (saliendo) return
      if (hayAlgoRef.current && !window.confirm('¿Salir sin mandar? Se pierde lo que cargaste.')) {
        marcar()
        return
      }
      saliendo = true
      cancelarRef.current()
    }
    window.addEventListener('beforeunload', alSalir)
    window.addEventListener('popstate', alVolver)
    return () => {
      window.removeEventListener('beforeunload', alSalir)
      window.removeEventListener('popstate', alVolver)
      if (!saliendo && window.history.state?.formEntrega) window.history.back()
    }
  }, [])

  function cancelar() {
    if (hayAlgo && !window.confirm('¿Descartar lo que cargaste?')) return
    olvidarBorrador()
    onCancelar()
  }
  const camaraRef = useRef<HTMLInputElement>(null)
  const galeriaRef = useRef<HTMLInputElement>(null)
  const zipRef = useRef<HTMLInputElement>(null)
  const topeZip = limites.bytesZip ?? 40 * 1024 * 1024
  // Las imágenes de la ronda que salieron del ZIP (su lugar en el índice).
  const deZip = imagenes.flatMap(im => (im.deZip != null ? [im.deZip] : []))
  const estadoZip: EstadoDelZip | null = zip ? { entradas: zip.entradas, tomadas: deZip, sacadas: zip.sacadas } : null

  // La última fase es la que sale publicada: ahí el original importa más.
  const esLaUltima = resumen.fases.length > 0 && resumen.fases[resumen.fases.length - 1].id === resumen.faseActual
  const linkMalo = link.trim() !== '' && !/^https?:\/\//i.test(link.trim())
  const lugar = limites.imagenes - imagenes.length - preparando
  // Si al entregar el servidor saca del ZIP alguna imagen más para la ronda
  // (las páginas de un PDF, 19/11/2026).
  const zipDaImagenes = !!estadoZip && zipSumaImagenes(estadoZip, lugar)
  // Los materiales son las imágenes y/o el link (16/11/2026): con uno alcanza.
  // Un ZIP solo, si de adentro sale alguna imagen para ver.
  const hayMateriales = imagenes.length > 0 || (link.trim() !== '' && !linkMalo) || zipDaImagenes

  /** Las piezas del pedido que no vienen en lo que se entrega: las imágenes
   *  sueltas y todas las del ZIP, con su tamaño original. Si no se puede
   *  saber (solo un link, algo del ZIP sin medir), ninguna. */
  function loQueFalta(): Pieza[] {
    const sueltas = imagenes
      .filter(im => im.deZip == null)
      .map(im => (im.ancho > 0 && im.alto > 0 ? { ancho: im.ancho, alto: im.alto } : null))
    // Las que salieron del ZIP ya están en sus medidas: no se cuentan dos veces.
    const todas = zip ? (zip.medidas ? [...sueltas, ...zip.medidas] : null) : sueltas
    return faltanEnLaEntrega(detalle.tarea.piezas, todas)
  }

  async function agregar(archivos: FileList | null) {
    if (!archivos || archivos.length === 0) return
    const lista = Array.from(archivos)
    if (lista.length > lugar) {
      toast.error(`Entran hasta ${limites.imagenes} imágenes por versión: se tomaron las primeras ${Math.max(0, lugar)}.`)
    }
    const tomadas = lista.slice(0, Math.max(0, lugar))
    setPreparando(n => n + tomadas.length)
    // De a una: varias fotos de 8 MB a la vez se comen la memoria de un teléfono.
    for (const archivo of tomadas) {
      try {
        const preparada = await prepararImagen(archivo)
        setImagenes(prev => [...prev, preparada])
      } catch (e) {
        toast.error(e instanceof Error ? e.message : `No se pudo preparar «${archivo.name}»`)
      } finally {
        setPreparando(n => n - 1)
      }
    }
  }

  function sacar(i: number) {
    // Una del ZIP que se saca a propósito no la vuelve a poner el servidor.
    const delZip = imagenes[i]?.deZip
    if (delZip != null) setZip(z => (z ? { ...z, sacadas: [...z.sacadas, delZip] } : z))
    setImagenes(prev => {
      URL.revokeObjectURL(prev[i].vista)
      return prev.filter((_, j) => j !== i)
    })
  }

  /** Saca el ZIP y las imágenes que salieron de él. */
  function sacarZip() {
    setImagenes(prev => {
      prev.forEach(im => { if (im.deZip != null) URL.revokeObjectURL(im.vista) })
      return prev.filter(im => im.deZip == null)
    })
    setZip(null)
  }

  async function elegirZip(lista: FileList | null) {
    const archivo = lista?.[0]
    if (!archivo) return
    if (archivo.size > topeZip) {
      toast.error(`«${archivo.name}» pesa ${mb(archivo.size)}: el máximo es ${mb(topeZip)}. Si es más grande, pegá el link de WeTransfer.`)
      return
    }
    setLeyendoZip(true)
    try {
      const buf = await archivo.arrayBuffer()
      let entradas: EntradaZip[] | null
      try {
        entradas = leerIndiceZip(buf)
      } catch (e) {
        // Un ZIP que acá no se puede leer (ZIP64) va igual: lo abre el servidor.
        if (!(e instanceof ZipRaro)) throw e
        entradas = null
      }
      const paraRevisar = entradas?.filter(e => e.clase !== 'otro') ?? null
      if (paraRevisar && paraRevisar.length === 0) {
        toast.error(`«${archivo.name}» no trae imágenes (JPG, PNG, WebP) ni PDF.`)
        return
      }
      // El tamaño original de todas las imágenes de adentro, también las que
      // no entran en la ronda, leído del principio de cada una: para ver si
      // falta alguna pieza del pedido (21/11/2026).
      let medidas: (Medidas | null)[] | null = null
      if (entradas) {
        medidas = []
        for (const e of entradas) if (e.clase === 'imagen') medidas.push(await medidasDeEntrada(buf, e))
      }
      // Un ZIP nuevo reemplaza al anterior, con sus imágenes.
      const propias = imagenes.filter(im => im.deZip == null).length
      sacarZip()
      setZip({ archivo, entradas, sacadas: [], medidas })
      const tomar = (paraRevisar ?? [])
        .filter(e => e.clase === 'imagen' && !e.cifrado)
        .slice(0, Math.max(0, limites.imagenes - propias - preparando))
      setPreparando(n => n + tomar.length)
      // De a una, como las de la galería: cuida la memoria del teléfono.
      for (const e of tomar) {
        try {
          const datos = await abrirEntrada(buf, e)
          const preparada = await prepararImagen(new File([datos], nombreCorto(e.nombre), { type: tipoDeImagen(e.nombre) }))
          setImagenes(prev => [...prev, { ...preparada, deZip: e.indice }])
        } catch {
          // Esa no se pudo sacar acá: queda adentro del ZIP, y al entregar la
          // saca el servidor si queda lugar.
        } finally {
          setPreparando(n => n - 1)
        }
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : `No se pudo abrir «${archivo.name}»`)
    } finally {
      setLeyendoZip(false)
    }
  }

  /** "Entregar": con imágenes, primero la IA (los cambios pedidos o, en la
   *  primera entrega, el pedido inicial). Lo que falta del pedido lo ve la
   *  plataforma sola, siempre igual, y se avisa haya dicho algo la IA o no. */
  async function entregar() {
    if (!hayMateriales || linkMalo || ocupado) return
    const faltan = loQueFalta()
    const grandes = imagenes.map(im => im.grande)
    if (!hayQueControlar(grandes.length)
      || (yaControladas.current && mismasImagenes(yaControladas.current, grandes))) {
      // Sin nada para la IA (o ya miró estas): si falta alguna pieza, se avisa igual.
      if (faltan.length > 0) {
        setAvisos(soloLoQueFalta(faltan))
        return
      }
      await enviar()
      return
    }
    const form = new FormData()
    form.append('comentario', comentario.trim())
    imagenes.forEach((im, i) => form.append('imagenes', im.grande, `imagen-${i + 1}.jpg`))
    const ac = new AbortController()
    setControlando(ac)
    let control: ControlPrevio | null = null
    try {
      control = (await entregasApi.controlPrevio(detalle.tarea.id, form, ac.signal)).data
    } catch {
      // Falló o tardó demasiado: se manda igual (nunca traba). Si fue
      // "Mandar sin esperar", ya se está mandando.
      control = null
    } finally {
      setControlando(c => (c === ac ? null : c))
    }
    if (ac.signal.aborted) return
    yaControladas.current = grandes
    // Si la IA no estuvo o no vio nada, las listas vienen vacías: lo que falta va igual.
    const lista = paraAvisar(control)
    const observaciones = observacionesParaAvisar(control)
    if (lista.length > 0 || observaciones.length > 0 || faltan.length > 0) {
      setAvisos({ lista, observaciones, faltan })
      return
    }
    await enviar()
  }

  function mandarSinEsperar() {
    controlando?.abort()
    setControlando(null)
    // Sin esperar a la IA. Lo que falta del pedido no la necesita: se avisa igual.
    const faltan = loQueFalta()
    if (faltan.length > 0) {
      setAvisos(soloLoQueFalta(faltan))
      return
    }
    void enviar()
  }

  async function enviar() {
    if (!hayMateriales || linkMalo || subiendo !== null) return
    const form = new FormData()
    form.append('versionId', versionId)
    form.append('comentario', comentario.trim())
    form.append('link', link.trim())
    // Ya no se tilda qué se corrigió (ver arriba): va la lista vacía.
    form.append('corregidas', '[]')
    // Lo que falta del pedido y por qué (21/11/2026): lo ven quien aprueba y
    // la agencia, en la ronda. Se vuelve a mirar acá por si sacó o sumó algo.
    const faltan = loQueFalta()
    if (faltan.length > 0) {
      form.append('faltan', JSON.stringify(faltan.map(p => p.nombre)))
      if (porQue.trim()) form.append('porQueFaltan', porQue.trim())
    }
    imagenes.forEach((im, i) => {
      form.append('imagenes', im.grande, `imagen-${i + 1}.jpg`)
      form.append('miniaturas', im.mini, `miniatura-${i + 1}.jpg`)
    })
    if (zip && estadoZip) {
      // Siempre: el servidor lo guarda tal cual, como el original de la ronda.
      form.append('zip', zip.archivo, zip.archivo.name)
      // Las que ya van como imágenes, y las que la persona sacó, no se vuelven
      // a poner ni se revisan dos veces.
      form.append('zipYaSubidas', JSON.stringify(zipYaResueltas(estadoZip)))
    }
    setSubiendo(0)
    try {
      const { data } = await entregasApi.entregar(detalle.tarea.id, form, f => setSubiendo(f))
      imagenes.forEach(im => URL.revokeObjectURL(im.vista))
      // Con una sola fase (la "Entrega" de las tarjetas) no se nombra la fase.
      const deFase = resumen.fases.length > 1 ? ` de ${fase?.nombre ?? 'la fase'}` : ''
      hayAlgoRef.current = false
      olvidarBorrador()
      if (data.zip && !data.zip.guardado) {
        // Entregada igual; el ZIP no entró en la base (no se borra nada para hacerle lugar).
        toast.warning(`Mandaste la versión ${ronda}${deFase}. ${avisoZipSinGuardar(link.trim() !== '', true)}`)
      } else {
        toast.success(`Mandaste la versión ${ronda}${deFase}. Quedó en «Esperando feedback»: le avisamos a quien la revisa.`)
      }
      onListo()
    } catch (e) {
      toast.error(detalleDeError(e) ?? 'No se pudo entregar. Revisá la conexión y probá de nuevo: no se pierde nada.')
      setSubiendo(null)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* La caja es ancha (19/11/2026, ver VistaEntregas): el formulario va al
          medio, con aire a los costados, para que los campos no se estiren.
          Si hay algo que avisar antes de mandar, el aviso ocupa su lugar
          (21/11/2026): hace scroll y los botones quedan abajo, a la vista. */}
      <div className="flex-1 overflow-y-auto overscroll-contain px-4 py-5 sm:px-6">
      {avisos ? (
        <AvisoAntesDeMandar
          faltan={avisos.faltan} lista={avisos.lista} observaciones={avisos.observaciones}
          fotos={imagenes.map(im => im.vista)} inicial={primera} porQue={porQue} onPorQue={setPorQue}
        />
      ) : (
      <div className="mx-auto w-full max-w-3xl space-y-6">
        <div>
          <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">
            {reemplaza != null
              ? `Mandar la versión ${ronda}${resumen.fases.length > 1 ? ` de ${fase?.nombre}` : ''}`
              : resumen.fases.length === 1
                ? (ronda === 1 ? 'Entregar los materiales' : `Entregar la versión ${ronda}`)
                : `Entregar ${ronda === 1 ? fase?.nombre : `la versión ${ronda} de ${fase?.nombre}`}`}
          </h3>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Subí la pieza (hasta {limites.imagenes} imágenes, o el ZIP con las piezas) y/o pegá el link al original. La van a revisar en el orden de la cadena.
          </p>
        </div>

        {/* Ir y venir (25/11/2026): sin esperar respuesta. */}
        {reemplaza != null && (
          <p className="rounded-xl bg-slate-100 px-3 py-2.5 text-sm text-slate-800 dark:bg-slate-800 dark:text-slate-100">
            La versión {reemplaza} todavía no la revisaron: esta la reemplaza y van a ver esta. La {reemplaza} queda en el historial.
          </p>
        )}

        {/* Lo que pidieron cambiar en la que volvió, a la vista (H-037). */}
        {pedidoDeCambios.length > 0 && (
          <section aria-labelledby="que-hay-que-cambiar" className="rounded-2xl border border-rose-200 bg-rose-50 p-4 dark:border-rose-500/30 dark:bg-rose-500/10">
            <h4 id="que-hay-que-cambiar" className="flex items-center gap-2 text-sm font-bold text-rose-800 dark:text-rose-200">
              <RotateCcw className="h-4 w-4" /> Lo que te pidieron cambiar
            </h4>
            <ul className="mt-1.5 space-y-1 text-sm text-rose-950 dark:text-rose-50">
              {pedidoDeCambios.map((p, i) => <li key={i} className="whitespace-pre-line">{p}</li>)}
            </ul>
          </section>
        )}

        {/* Devuelta después de aprobada (17/11/2026): lo que pidieron cambiar,
            arriba de todo, para entregar sabiendo qué corregir. */}
        {fase?.motivo && (
          <section aria-labelledby="que-pidieron" className="rounded-2xl border border-rose-200 bg-rose-50 p-4 dark:border-rose-500/30 dark:bg-rose-500/10">
            <h4 id="que-pidieron" className="flex items-center gap-2 text-sm font-bold text-rose-800 dark:text-rose-200">
              <RotateCcw className="h-4 w-4" /> Lo que pidieron cambiar
            </h4>
            <p className="mt-1.5 whitespace-pre-line text-sm text-rose-950 dark:text-rose-50">{fase.motivo}</p>
          </section>
        )}

        <section aria-labelledby="las-imagenes">
          <h4 id="las-imagenes" className="mb-2 text-sm font-bold text-slate-900 dark:text-slate-100">
            Las imágenes <span className="font-normal tabular-nums text-slate-500 dark:text-slate-400">{imagenes.length} de {limites.imagenes}</span>
          </h4>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {imagenes.map((im, i) => (
              <div key={im.vista} className="relative aspect-square overflow-hidden rounded-xl bg-slate-100 ring-1 ring-black/5 dark:bg-slate-800 dark:ring-white/10">
                {/* eslint-disable-next-line @next/next/no-img-element -- vista previa local (blob:) */}
                <img src={im.vista} alt={`Imagen ${i + 1}: ${im.nombre}`} className="h-full w-full object-contain" />
                <span className="absolute left-1.5 top-1.5 rounded-md bg-black/60 px-1.5 text-xs font-bold text-white">{i + 1}</span>
                <button
                  type="button"
                  onClick={() => sacar(i)}
                  disabled={ocupado}
                  aria-label={`Sacar la imagen ${i + 1}`}
                  className="absolute right-1.5 top-1.5 flex h-8 w-8 items-center justify-center rounded-full bg-black/60 text-white transition hover:bg-black/80"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ))}
            {Array.from({ length: preparando }).map((_, i) => (
              <div key={`p${i}`} className="skeleton flex aspect-square items-center justify-center rounded-xl">
                <Loader2 className="h-5 w-5 animate-spin text-slate-500" />
              </div>
            ))}
          </div>
          {lugar > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => camaraRef.current?.click()}
                disabled={ocupado}
                className="flex min-h-[48px] flex-1 items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-300 px-4 text-sm font-semibold text-slate-700 transition hover:border-brand-400 hover:bg-brand-50 hover:text-brand-700 dark:border-slate-600 dark:text-slate-200 dark:hover:border-brand-500/60 dark:hover:bg-brand-500/10 sm:hidden"
              >
                <Camera className="h-5 w-5" /> Sacar foto
              </button>
              <button
                type="button"
                onClick={() => galeriaRef.current?.click()}
                disabled={ocupado}
                className="flex min-h-[48px] flex-1 items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-300 px-4 text-sm font-semibold text-slate-700 transition hover:border-brand-400 hover:bg-brand-50 hover:text-brand-700 dark:border-slate-600 dark:text-slate-200 dark:hover:border-brand-500/60 dark:hover:bg-brand-500/10"
              >
                <ImagePlus className="h-5 w-5" /> {imagenes.length === 0 ? 'Elegir imágenes' : 'Agregar más'}
              </button>
              <input ref={camaraRef} type="file" accept="image/*" capture="environment" className="hidden"
                onChange={e => { void agregar(e.target.files); e.target.value = '' }} />
              <input ref={galeriaRef} type="file" accept="image/jpeg,image/png,image/webp,image/*" multiple className="hidden"
                data-testid="elegir-imagenes"
                onChange={e => { void agregar(e.target.files); e.target.value = '' }} />
            </div>
          )}

          {/* La carpeta comprimida: se toman las imágenes de adentro. */}
          <div className="mt-2">
            {zip ? (
              <div className="flex items-center gap-2.5 rounded-xl border border-slate-300 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-800/50">
                <FileArchive className="h-5 w-5 shrink-0 text-slate-600 dark:text-slate-300" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{zip.archivo.name}</p>
                  <p className="text-xs text-slate-600 dark:text-slate-400">
                    {estadoZip && detalleDelZip(estadoZip, zip.archivo.size, leyendoZip, lugar)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={sacarZip}
                  disabled={ocupado || leyendoZip}
                  aria-label={`Sacar «${zip.archivo.name}» y sus imágenes`}
                  title="Sacar el ZIP"
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-200 hover:text-slate-900 disabled:opacity-50 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-100"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => zipRef.current?.click()}
                disabled={ocupado || leyendoZip}
                className="flex min-h-[44px] w-full items-center justify-center gap-2 rounded-xl border border-slate-300 px-4 text-sm font-semibold text-slate-700 transition hover:border-brand-400 hover:bg-brand-50 hover:text-brand-700 disabled:opacity-50 dark:border-slate-600 dark:text-slate-200 dark:hover:border-brand-500/60 dark:hover:bg-brand-500/10"
              >
                {leyendoZip ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileArchive className="h-4 w-4" />}
                {leyendoZip ? 'Abriendo el ZIP…' : `¿Están en una carpeta? Subí el ZIP (hasta ${mb(topeZip)})`}
              </button>
            )}
            <input ref={zipRef} type="file" accept=".zip,application/zip,application/x-zip-compressed" className="hidden"
              data-testid="elegir-zip"
              onChange={e => { void elegirZip(e.target.files); e.target.value = '' }} />
            {/* Solo si de verdad no hay nada para ver: un PDF ya no cuenta
                como "nada" (sus páginas las saca el servidor al entregar). */}
            {zip && !leyendoZip && preparando === 0 && imagenes.length === 0 && !link.trim() && !zipDaImagenes && (
              <p className="mt-2 rounded-lg bg-amber-50 px-2.5 py-2 text-xs font-medium text-amber-900 ring-1 ring-amber-300 dark:bg-amber-500/10 dark:text-amber-100 dark:ring-amber-500/40">
                Del ZIP no sale ninguna imagen para mostrar: subí una o pegá el link, así quien aprueba ve la pieza.
              </p>
            )}
          </div>
          {/* Las imágenes se achican antes de subir (la base es chica): sirven
              para revisar, no para publicar. El original es el ZIP, que se
              guarda tal cual (19/11/2026), o el link. En la última fase se
              destaca si no hay ninguno de los dos: es lo que el equipo va a bajar. */}
          <p className={esLaUltima && !link.trim() && !zip
            ? 'mt-2 rounded-lg bg-amber-50 px-2.5 py-2 text-xs font-medium text-amber-900 ring-1 ring-amber-300 dark:bg-amber-500/10 dark:text-amber-100 dark:ring-amber-500/40'
            : 'mt-2 text-xs text-slate-600 dark:text-slate-400'}>
            {zip
              ? 'Se achican para revisar (1600 px, JPEG). El ZIP se guarda tal cual: es el original que baja el equipo.'
              : 'Se achican para revisar (1600 px, JPEG). Para que el equipo baje el archivo final, subí el ZIP o pegá el link al original.'}
          </p>
        </section>

        <div className="grid gap-3">
          <label className="block">
            <span className="etiqueta-campo">Nota de este envío (opcional)</span>
            <textarea
              value={comentario}
              onChange={e => setComentario(e.target.value)}
              rows={3}
              maxLength={5000}
              placeholder={volvio ? 'Ej: Agrandé el precio y saqué el fondo azul.'
                : reemplaza != null ? 'Ej: faltaba el formato historia, o el ajuste pedido por WhatsApp'
                  : 'Algo que tengan que saber al revisarla'}
              className="campo !h-auto py-2"
            />
          </label>
          <label className="block">
            <span className="etiqueta-campo flex items-center gap-1"><Link2 className="h-3.5 w-3.5" /> Link al original (WeTransfer, Smash…)</span>
            <input
              type="url"
              value={link}
              onChange={e => setLink(e.target.value)}
              placeholder="https://we.tl/…"
              maxLength={1000}
              aria-invalid={linkMalo}
              className="campo"
            />
            {linkMalo && <span className="mt-1 block text-xs text-rose-600 dark:text-rose-300">Tiene que empezar con http:// o https://</span>}
          </label>
        </div>
      </div>
      )}
      </div>

      <div className="shrink-0 border-t border-slate-300 bg-white px-4 py-3 pb-[max(.75rem,env(safe-area-inset-bottom))] dark:border-slate-700 dark:bg-slate-900 sm:px-6">
      {controlando ? (
        // La IA está mirando las imágenes (hasta un minuto).
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-2 sm:flex-row sm:items-center" role="status" aria-live="polite">
          <p className="flex flex-1 items-start gap-2 text-sm text-slate-700 dark:text-slate-200">
            <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-brand-600 dark:text-brand-300" />
            <span>
              {textosDelControl(primera).mirando}{' '}
              <span className="text-slate-500 dark:text-slate-400">Puede tardar un minuto.</span>
            </span>
          </p>
          <button
            type="button"
            onClick={mandarSinEsperar}
            className="min-h-[48px] rounded-xl border border-slate-300 px-4 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800 sm:min-h-[44px]"
          >
            Mandar sin esperar
          </button>
        </div>
      ) : avisos ? (
        // El aviso está arriba, donde estaba el formulario: acá, sus botones.
        <div className="mx-auto flex w-full max-w-3xl items-center gap-2">
          <button
            type="button"
            onClick={() => setAvisos(null)}
            className="min-h-[48px] rounded-xl border border-slate-300 px-4 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800 sm:min-h-[44px]"
          >
            Corregir
          </button>
          <button
            type="button"
            onClick={() => { setAvisos(null); void enviar() }}
            className="ml-auto flex min-h-[48px] flex-1 items-center justify-center gap-2 rounded-xl bg-brand-600 px-5 text-sm font-bold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.98] sm:min-h-[44px] sm:flex-none"
          >
            <Send className="h-4 w-4" /> Mandar igual
          </button>
        </div>
      ) : (
      <div className="mx-auto flex w-full max-w-3xl items-center gap-2">
        <button
          type="button"
          onClick={cancelar}
          disabled={ocupado}
          className="min-h-[48px] rounded-xl px-4 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800 sm:min-h-[44px]"
        >
          Cancelar
        </button>
        <button
          type="button"
          onClick={() => void entregar()}
          disabled={!hayMateriales || preparando > 0 || leyendoZip || linkMalo || ocupado}
          className="ml-auto flex min-h-[48px] flex-1 items-center justify-center gap-2 rounded-xl bg-brand-600 px-5 text-sm font-bold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.98] disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:shadow-none dark:disabled:bg-slate-700 dark:disabled:text-slate-400 sm:min-h-[44px] sm:flex-none"
        >
          {subiendo !== null ? (
            <><Loader2 className="h-4 w-4 animate-spin" /> Subiendo… {Math.round(subiendo * 100)}%</>
          ) : (
            // Con varias fases, la primera ronda de cada una se nombra por la
            // fase ("Entregar Entrega 2"), igual que el título: "Entregar
            // ronda 1" debajo de "Entregar Entrega 2" confundía (17/11/2026).
            <><Send className="h-4 w-4" /> {reemplaza != null ? `Mandar versión ${ronda}`
              : resumen.fases.length > 1 && ronda === 1 && fase ? `Entregar ${fase.nombre}` : `Entregar versión ${ronda}`}</>
          )}
        </button>
      </div>
      )}
      </div>
    </div>
  )
}

/**
 * El aviso antes de mandar (21/11/2026). Ivan: "las correcciones de la IA
 * están súper mezcladas, no tiene un formato bonito de ver ni nada". Antes iba
 * en la barra de los botones: arriba un renglón largo en negrita y ámbar con
 * todas las piezas que faltaban seguidas por comas, abajo «Ojo: parece que
 * falta algo del pedido» con tarjetitas amarillas y un número violeta, y al
 * final el campo. Ahora es un solo bloque, en el lugar del formulario:
 *
 * - un título claro, con el único acento de color (el ámbar del ícono);
 * - «Piezas que faltan (10)»: un chip parejo por pieza, con el nombre arriba
 *   y la medida abajo en gris; 3 columnas en la compu y 2 en el teléfono. Si
 *   son muchas, las primeras 6 y «Ver las otras 4» (lib/calendario/piezas.ts);
 * - «Lo que se pidió (2)» (o «Los cambios que se pidieron»): un renglón por
 *   cosa pedida que falta o no se ve clara, con su estado, lo pedido en
 *   negrita y lo que vio la IA abajo (LoQueVioLaIA, el mismo diseño que ve
 *   quien aprueba en el Revisor);
 * - «Lo que encontró la IA en la pieza (3)» (24/11/2026): cada observación,
 *   la misma que ve quien aprueba, con la miniatura de su imagen y un punto
 *   rojo donde la vio; las importantes en rojo, las de revisar en ámbar;
 * - la aclaración chica, el campo «¿Por qué no va todo? (opcional)» si falta
 *   alguna pieza, y los botones abajo, siempre a la vista (los pone
 *   FormularioEntrega en su barra).
 */
function AvisoAntesDeMandar({ faltan, lista, observaciones, fotos, inicial, porQue, onPorQue }: {
  faltan: Pieza[]
  lista: CambioControlado[]
  observaciones: ObservacionDelControl[]
  /** Las imágenes que se van a entregar (blob:), en su orden: para las miniaturas. */
  fotos: string[]
  /** La primera entrega de la fase: lo controlado es el pedido inicial. */
  inicial: boolean
  porQue: string
  onPorQue: (texto: string) => void
}) {
  const [todas, setTodas] = useState(false)
  const titulo = useRef<HTMLHeadingElement>(null)
  // Al aparecer, el título con el foco (y a la vista): es lo que sigue leer.
  useEffect(() => { titulo.current?.focus() }, [])
  const { vistas, resto } = primeras(faltan)
  const piezas = todas ? faltan : vistas
  return (
    <section aria-labelledby="antes-de-mandar" className="mx-auto w-full max-w-3xl space-y-6">
      <h3
        id="antes-de-mandar"
        ref={titulo}
        tabIndex={-1}
        className="flex items-center gap-2 text-lg font-bold text-slate-900 outline-none dark:text-slate-100"
      >
        <AlertTriangle className="h-5 w-5 shrink-0 text-rose-600 dark:text-rose-400" aria-hidden />
        Antes de mandar, revisá esto
      </h3>

      {faltan.length > 0 && (
        <section aria-labelledby="piezas-que-faltan">
          <h4 id="piezas-que-faltan" className="text-sm font-bold text-slate-900 dark:text-slate-100">
            {tituloDeLasPiezas(faltan)} <span className="font-normal tabular-nums text-slate-600 dark:text-slate-400">({faltan.length})</span>
          </h4>
          <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-400">
            Ninguna imagen tiene esa medida (vale una más grande, con la misma proporción).
          </p>
          <ul className="mt-2.5 grid grid-cols-2 gap-2 sm:grid-cols-3">
            {piezas.map((p, i) => (
              <li key={`${i}-${p.nombre}`} className="min-w-0 rounded-lg border border-slate-300 px-2.5 py-1.5 dark:border-slate-700">
                <span className="block break-words text-sm font-medium leading-snug text-slate-900 dark:text-slate-100">{p.nombre}</span>
                <span className="block text-xs tabular-nums text-slate-600 dark:text-slate-400">{medidaDePieza(p)}</span>
              </li>
            ))}
          </ul>
          {resto > 0 && (
            <button
              type="button"
              onClick={() => setTodas(v => !v)}
              aria-expanded={todas}
              className="-mx-2 mt-1 flex min-h-[40px] items-center rounded-lg px-2 text-sm font-semibold text-brand-700 transition hover:bg-slate-100 dark:text-brand-200 dark:hover:bg-slate-800"
            >
              {todas ? 'Ver menos' : `Ver las otras ${resto}`}
            </button>
          )}
        </section>
      )}

      {lista.length > 0 && (
        <section aria-labelledby="lo-que-vio-la-ia">
          <h4 id="lo-que-vio-la-ia" className="text-sm font-bold text-slate-900 dark:text-slate-100">
            {inicial ? 'Lo que se pidió' : 'Los cambios que se pidieron'}{' '}
            <span className="font-normal tabular-nums text-slate-600 dark:text-slate-400">({lista.length})</span>
          </h4>
          <div className="mt-2.5 rounded-xl border border-slate-300 px-3 dark:border-slate-700">
            <LoQueVioLaIA cambios={lista} />
          </div>
        </section>
      )}

      {/* Lo que encontró en la pieza (24/11/2026): lo mismo que ve quien aprueba. */}
      {observaciones.length > 0 && (
        <section aria-labelledby="lo-que-encontro-la-ia">
          <h4 id="lo-que-encontro-la-ia" className="text-sm font-bold text-slate-900 dark:text-slate-100">
            Lo que encontró la IA en la pieza{' '}
            <span className="font-normal tabular-nums text-slate-600 dark:text-slate-400">({agruparIguales(observaciones).length})</span>
          </h4>
          <ul className="mt-2.5 space-y-2">
            {/* Lo mismo en varias imágenes, una sola vez (25/11/2026: "¿se repiten?"). */}
            {agruparIguales(observaciones).map((g, i) => (
              <ObservacionAntesDeMandar
                key={g[0].id ?? i}
                observacion={g[0]}
                enImagenes={g.map(x => x.imagen).filter((n): n is number => n != null)}
                fotos={fotos}
              />
            ))}
          </ul>
        </section>
      )}

      {(lista.length > 0 || observaciones.length > 0) && (
        <p className="text-xs text-slate-600 dark:text-slate-400">
          Lo dice la IA mirando las imágenes y puede equivocarse: si ya está, mandalo igual.
        </p>
      )}

      {/* El espacio para explicar (Ivan: "estaría bueno que le des el
          espacio a la agencia ahí de escribir por qué no los manda"). */}
      {faltan.length > 0 && (
        <label className="block">
          <span className="etiqueta-campo">¿Por qué no va todo? (opcional)</span>
          <textarea
            value={porQue}
            onChange={e => onPorQue(e.target.value)}
            rows={2}
            maxLength={500}
            placeholder="Ej: Es el KV, para aprobarlo antes de hacer el resto"
            className="campo !h-auto py-2"
          />
        </label>
      )}
    </section>
  )
}

const TIPOS = TIPO_OBSERVACION as Record<string, string>

/**
 * Una cosa que encontró la IA en la pieza, antes de mandar (24/11/2026): la
 * miniatura de su imagen con un punto rojo donde la vio (si la ubicó), la
 * gravedad («Importante» en rojo, «A revisar» en ámbar), qué es y lo que dice
 * la IA. Lo mismo que ve quien aprueba (PanelRevisionIA).
 */
function ObservacionAntesDeMandar({ observacion: o, enImagenes, fotos }: {
  observacion: ObservacionDelControl
  /** Si lo mismo está en varias imágenes: todas (la miniatura es la de la primera). */
  enImagenes: number[]
  fotos: string[]
}) {
  const importante = o.gravedad === 'importante'
  const vista = o.imagen != null ? fotos[o.imagen - 1] : undefined
  const punto = conLugar(o, fotos.length)
  return (
    <li className={`flex items-start gap-3 rounded-xl border p-2.5 ${
      importante
        ? 'border-rose-300 bg-rose-50 dark:border-rose-500/40 dark:bg-rose-500/10'
        : 'border-amber-300 bg-amber-50 dark:border-amber-500/40 dark:bg-amber-500/10'
    }`}>
      {vista && (
        // La miniatura del tamaño de la imagen (sin bandas), así el punto cae donde la vio.
        <span className="relative flex h-16 w-16 shrink-0 items-center justify-center rounded-lg bg-white ring-1 ring-black/10 dark:ring-white/15">
          <span className="relative inline-block">
            {/* eslint-disable-next-line @next/next/no-img-element -- vista previa local (blob:) */}
            <img src={vista} alt={`Imagen ${o.imagen}`} className="block max-h-[4rem] max-w-[4rem] rounded-lg" />
            {punto && (
              <span
                aria-hidden
                style={{ left: `${(o.x as number) * 100}%`, top: `${(o.y as number) * 100}%` }}
                className="absolute h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-rose-600 ring-2 ring-white"
              />
            )}
          </span>
          {/* El número, en la esquina de la caja: sobre la imagen tapaba el punto. */}
          <span className="absolute bottom-0.5 right-0.5 rounded bg-black/70 px-1 text-[10px] font-bold leading-4 text-white">{o.imagen}</span>
        </span>
      )}
      <div className="min-w-0 flex-1">
        <p className="break-words text-sm leading-snug text-slate-900 dark:text-slate-100">
          <span className={`mr-1.5 inline-block whitespace-nowrap rounded-full px-2 py-px align-[1px] text-[11px] font-bold leading-4 ${
            importante ? 'bg-rose-600 text-white' : 'bg-amber-200 text-amber-950 dark:bg-amber-400/25 dark:text-amber-100'
          }`}>
            {importante ? 'Importante' : 'A revisar'}
          </span>
          <span className="font-semibold">{TIPOS[o.tipo] ?? 'Otro'}</span>
          {' · '}{o.texto}
        </p>
        <p className="mt-0.5 text-xs text-slate-700 dark:text-slate-300">
          {new Set(enImagenes).size > 1
            ? `Está en ${textoDeImagenes(enImagenes)}${punto ? ' (el punto rojo, en la primera)' : ''}`
            : o.imagen != null && vista ? `En la imagen ${o.imagen}${punto ? ' (el punto rojo)' : ''}` : 'En la pieza en general'}
        </p>
      </div>
    </li>
  )
}

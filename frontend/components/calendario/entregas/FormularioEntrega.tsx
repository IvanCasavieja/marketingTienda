'use client'

import { useRef, useState } from 'react'
import { AlertTriangle, Camera, FileArchive, ImagePlus, Link2, Loader2, RotateCcw, Send, X } from 'lucide-react'
import { toast } from 'sonner'
import { entregasApi } from '@/lib/api'
import {
  ETIQUETA_DEL_VEREDICTO, hayQueControlar, mismasImagenes, paraAvisar, type CambioControlado, type ControlPrevio,
} from '@/lib/calendario/control-previo'
import {
  nuevoIdDeVersion, prepararImagen, type DetalleEntregas, type ImagenLista,
} from '@/lib/calendario/entregas'
import {
  abrirEntrada, avisoZipSinGuardar, detalleDelZip, leerIndiceZip, nombreCorto, tipoDeImagen, zipSumaImagenes,
  zipYaResueltas, ZipRaro, type EntradaZip, type EstadoDelZip,
} from '@/lib/calendario/zip'

function detalleDeError(e: unknown): string | null {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === 'string' ? d : null
}

const mb = (n: number) => `${(n / 1024 / 1024).toFixed(1).replace('.', ',')} MB`

/** Una imagen de la ronda; `deZip`: su lugar en el índice del ZIP, si salió de ahí. */
type Imagen = ImagenLista & { deZip?: number }

/** El ZIP elegido: su índice (null si no se pudo leer acá) y las imágenes de
 *  adentro que la persona sacó de la ronda (el servidor no las vuelve a poner). */
type ZipElegido = { archivo: File; entradas: EntradaZip[] | null; sacadas: number[] }

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
 * los cambios'"): en una ronda que volvió con cambios, "Entregar" manda
 * primero las imágenes al control previo. Mientras mira (hasta un minuto) se
 * puede "Mandar sin esperar". Si ve algo que falta o que no se ve claro, lo
 * muestra con "Corregir" o "Mandar igual"; si no, manda solo. Si la IA no
 * está o falla, manda igual: nunca traba (lib/calendario/control-previo.ts).
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

  // El id se arma una vez: si la subida se corta y se reintenta, el
  // servidor reconoce que es la misma y no la duplica.
  const [versionId] = useState(nuevoIdDeVersion)
  const [imagenes, setImagenes] = useState<Imagen[]>([])
  const [preparando, setPreparando] = useState(0)
  const [comentario, setComentario] = useState('')
  const [link, setLink] = useState('')
  const [subiendo, setSubiendo] = useState<number | null>(null)
  const [zip, setZip] = useState<ZipElegido | null>(null)
  const [leyendoZip, setLeyendoZip] = useState(false)
  // El control de la IA antes de mandar: mientras mira, y lo que encontró.
  const [controlando, setControlando] = useState<AbortController | null>(null)
  const [avisos, setAvisos] = useState<CambioControlado[] | null>(null)
  // Las imágenes que ya miró: si se vuelve a entregar sin cambiarlas, se manda.
  const yaControladas = useRef<Blob[] | null>(null)
  const ocupado = subiendo !== null || controlando !== null
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

  async function agregar(archivos: FileList | null) {
    if (!archivos || archivos.length === 0) return
    const lista = Array.from(archivos)
    if (lista.length > lugar) {
      toast.error(`Entran hasta ${limites.imagenes} imágenes por ronda: se tomaron las primeras ${Math.max(0, lugar)}.`)
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
      // Un ZIP nuevo reemplaza al anterior, con sus imágenes.
      const propias = imagenes.filter(im => im.deZip == null).length
      sacarZip()
      setZip({ archivo, entradas, sacadas: [] })
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

  /** "Entregar": en una ronda que volvió con cambios, primero la IA. */
  async function entregar() {
    if (!hayMateriales || linkMalo || ocupado) return
    const grandes = imagenes.map(im => im.grande)
    if (!hayQueControlar(volvio, grandes.length)
      || (yaControladas.current && mismasImagenes(yaControladas.current, grandes))) {
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
    const lista = paraAvisar(control)
    if (lista.length > 0) {
      setAvisos(lista)
      return
    }
    await enviar()
  }

  function mandarSinEsperar() {
    controlando?.abort()
    setControlando(null)
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
      if (data.zip && !data.zip.guardado) {
        // Entregada igual; el ZIP no entró en la base (no se borra nada para hacerle lugar).
        toast.warning(`Entregaste la ronda ${ronda}${deFase}. ${avisoZipSinGuardar(link.trim() !== '', true)}`)
      } else {
        toast.success(`Entregaste la ronda ${ronda}${deFase}. Quedó en «Esperando feedback»: le avisamos a quien la revisa.`)
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
          medio, con aire a los costados, para que los campos no se estiren. */}
      <div className="flex-1 overflow-y-auto overscroll-contain px-4 py-5 sm:px-6">
      <div className="mx-auto w-full max-w-3xl space-y-6">
        <div>
          <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">
            {resumen.fases.length === 1
              ? (ronda === 1 ? 'Entregar los materiales' : `Entregar la ronda ${ronda}`)
              : `Entregar ${ronda === 1 ? fase?.nombre : `la ronda ${ronda} de ${fase?.nombre}`}`}
          </h3>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Subí la pieza (hasta {limites.imagenes} imágenes, o el ZIP con las piezas) y/o pegá el link al original. La van a revisar en el orden de la cadena.
          </p>
        </div>

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
            <span className="etiqueta-campo">Comentario (opcional)</span>
            <textarea
              value={comentario}
              onChange={e => setComentario(e.target.value)}
              rows={3}
              maxLength={5000}
              placeholder={volvio ? 'Ej: Agrandé el precio y saqué el fondo azul.' : 'Algo que tengan que saber al revisarla'}
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
      </div>

      <div className="shrink-0 border-t border-slate-300 bg-white px-4 py-3 pb-[max(.75rem,env(safe-area-inset-bottom))] dark:border-slate-700 dark:bg-slate-900 sm:px-6">
      {controlando ? (
        // La IA está mirando las imágenes (hasta un minuto).
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-2 sm:flex-row sm:items-center" role="status" aria-live="polite">
          <p className="flex flex-1 items-start gap-2 text-sm text-slate-700 dark:text-slate-200">
            <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-brand-600 dark:text-brand-300" />
            <span>
              La IA está mirando si se hicieron los cambios que se pidieron…{' '}
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
        // Lo que la IA ve que falta (o que no se ve claro) de lo que se pidió.
        <section aria-labelledby="ojo-falta" className="mx-auto w-full max-w-3xl">
          <h4 id="ojo-falta" className="flex items-center gap-2 text-sm font-bold text-amber-900 dark:text-amber-100">
            <AlertTriangle className="h-4 w-4 shrink-0" /> Ojo: parece que falta algo de lo que se pidió
          </h4>
          <ul className="mt-2 max-h-[40vh] space-y-1.5 overflow-y-auto overscroll-contain">
            {avisos.map(c => (
              <li key={c.numero} className="rounded-xl bg-amber-50 px-3 py-2 ring-1 ring-amber-300 dark:bg-amber-500/10 dark:ring-amber-500/40">
                <p className="flex items-start gap-2 text-sm text-slate-900 dark:text-slate-100">
                  <span className="mt-px inline-flex h-5 min-w-[1.25rem] shrink-0 items-center justify-center rounded-full bg-brand-600 px-1.5 text-xs font-bold text-white">
                    {c.numero}
                  </span>
                  <span className="min-w-0 break-words">{c.texto}</span>
                </p>
                <p className="mt-0.5 pl-7 text-xs text-amber-900 dark:text-amber-100">
                  <strong>{ETIQUETA_DEL_VEREDICTO[c.veredicto]}</strong>{c.nota ? ` · ${c.nota}` : ''}
                </p>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-slate-600 dark:text-slate-400">
            Lo dice la IA mirando las imágenes, y puede equivocarse: si ya está, mandalo igual.
          </p>
          <div className="mt-2 flex items-center gap-2">
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
        </section>
      ) : (
      <div className="mx-auto flex w-full max-w-3xl items-center gap-2">
        <button
          type="button"
          onClick={onCancelar}
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
            <><Send className="h-4 w-4" /> {resumen.fases.length > 1 && ronda === 1 && fase ? `Entregar ${fase.nombre}` : `Entregar ronda ${ronda}`}</>
          )}
        </button>
      </div>
      )}
      </div>
    </div>
  )
}

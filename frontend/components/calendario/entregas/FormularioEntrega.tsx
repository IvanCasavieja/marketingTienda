'use client'

import { useRef, useState } from 'react'
import { Camera, FileArchive, ImagePlus, Link2, Loader2, RotateCcw, Send, X } from 'lucide-react'
import { toast } from 'sonner'
import { entregasApi } from '@/lib/api'
import {
  nuevoIdDeVersion, prepararImagen, type DetalleEntregas, type ImagenLista,
} from '@/lib/calendario/entregas'
import {
  abrirEntrada, leerIndiceZip, nombreCorto, tipoDeImagen, ZipRaro, type EntradaZip,
} from '@/lib/calendario/zip'

function detalleDeError(e: unknown): string | null {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === 'string' ? d : null
}

const mb = (n: number) => `${(n / 1024 / 1024).toFixed(1).replace('.', ',')} MB`

/** Una imagen de la ronda; `deZip`: su lugar en el índice del ZIP, si salió de ahí. */
type Imagen = ImagenLista & { deZip?: number }

/** El ZIP elegido. `paraRevisar`: cuántas imágenes y PDF trae (null si no se pudo leer acá). */
type ZipElegido = { archivo: File; paraRevisar: number | null }

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
 * ronda, para que quien aprueba las vea y las marque. El ZIP viaja igual (no
 * se guarda) para que se revise lo que no entró, salvo que ya haya entrado
 * todo (lib/calendario/zip.ts).
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
  const camaraRef = useRef<HTMLInputElement>(null)
  const galeriaRef = useRef<HTMLInputElement>(null)
  const zipRef = useRef<HTMLInputElement>(null)
  const topeZip = limites.bytesZip ?? 40 * 1024 * 1024
  // Las imágenes de la ronda que salieron del ZIP (su lugar en el índice).
  const deZip = imagenes.flatMap(im => (im.deZip != null ? [im.deZip] : []))
  // Si todo lo que trae el ZIP ya va como imágenes, no hace falta mandarlo.
  const mandarZip = !!zip && (zip.paraRevisar == null || zip.paraRevisar > deZip.length)

  // La última fase es la que sale publicada: ahí el original importa más.
  const esLaUltima = resumen.fases.length > 0 && resumen.fases[resumen.fases.length - 1].id === resumen.faseActual
  const linkMalo = link.trim() !== '' && !/^https?:\/\//i.test(link.trim())
  // Los materiales son las imágenes y/o el link (16/11/2026): con uno alcanza.
  const hayMateriales = imagenes.length > 0 || (link.trim() !== '' && !linkMalo)
  const lugar = limites.imagenes - imagenes.length - preparando

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
      setZip({ archivo, paraRevisar: paraRevisar?.length ?? null })
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
          // Esa no se pudo sacar acá: queda adentro del ZIP, que se revisa igual.
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

  async function entregar() {
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
    if (zip && mandarZip) {
      form.append('zip', zip.archivo, zip.archivo.name)
      // Las que ya van como imágenes no se revisan dos veces.
      form.append('zipYaSubidas', JSON.stringify(deZip))
    }
    setSubiendo(0)
    try {
      await entregasApi.entregar(detalle.tarea.id, form, f => setSubiendo(f))
      imagenes.forEach(im => URL.revokeObjectURL(im.vista))
      // Con una sola fase (la "Entrega" de las tarjetas) no se nombra la fase.
      const deFase = resumen.fases.length > 1 ? ` de ${fase?.nombre ?? 'la fase'}` : ''
      toast.success(`Entregaste la ronda ${ronda}${deFase}. Quedó en «Esperando feedback»: le avisamos a quien la revisa.`)
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
                  disabled={subiendo !== null}
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
                disabled={subiendo !== null}
                className="flex min-h-[48px] flex-1 items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-300 px-4 text-sm font-semibold text-slate-700 transition hover:border-brand-400 hover:bg-brand-50 hover:text-brand-700 dark:border-slate-600 dark:text-slate-200 dark:hover:border-brand-500/60 dark:hover:bg-brand-500/10 sm:hidden"
              >
                <Camera className="h-5 w-5" /> Sacar foto
              </button>
              <button
                type="button"
                onClick={() => galeriaRef.current?.click()}
                disabled={subiendo !== null}
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
                    {[
                      mb(zip.archivo.size),
                      leyendoZip ? 'abriéndolo…'
                        : deZip.length ? `${deZip.length === 1 ? 'se tomó 1 imagen' : `se tomaron ${deZip.length} imágenes`} de adentro` : null,
                      !leyendoZip && zip.paraRevisar != null && zip.paraRevisar > deZip.length
                        ? `${zip.paraRevisar - deZip.length === 1 ? '1 archivo más' : `${zip.paraRevisar - deZip.length} archivos más`} para revisar`
                        : null,
                    ].filter(Boolean).join(' · ')}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={sacarZip}
                  disabled={subiendo !== null || leyendoZip}
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
                disabled={subiendo !== null || leyendoZip}
                className="flex min-h-[44px] w-full items-center justify-center gap-2 rounded-xl border border-slate-300 px-4 text-sm font-semibold text-slate-700 transition hover:border-brand-400 hover:bg-brand-50 hover:text-brand-700 disabled:opacity-50 dark:border-slate-600 dark:text-slate-200 dark:hover:border-brand-500/60 dark:hover:bg-brand-500/10"
              >
                {leyendoZip ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileArchive className="h-4 w-4" />}
                {leyendoZip ? 'Abriendo el ZIP…' : `¿Están en una carpeta? Subí el ZIP (hasta ${mb(topeZip)})`}
              </button>
            )}
            <input ref={zipRef} type="file" accept=".zip,application/zip,application/x-zip-compressed" className="hidden"
              data-testid="elegir-zip"
              onChange={e => { void elegirZip(e.target.files); e.target.value = '' }} />
            {zip && !leyendoZip && preparando === 0 && deZip.length === 0 && imagenes.length === 0 && !link.trim() && (
              <p className="mt-2 rounded-lg bg-amber-50 px-2.5 py-2 text-xs font-medium text-amber-900 ring-1 ring-amber-300 dark:bg-amber-500/10 dark:text-amber-100 dark:ring-amber-500/40">
                Del ZIP no salió ninguna imagen para mostrar: subí una o pegá el link, así quien aprueba ve la pieza.
              </p>
            )}
          </div>
          {/* Las imágenes se achican antes de subir (la base es chica): sirven
              para revisar, no para publicar. Se dice acá, y en la última fase
              se destaca si falta el link, que es lo que el equipo va a bajar. */}
          <p className={esLaUltima && !link.trim()
            ? 'mt-2 rounded-lg bg-amber-50 px-2.5 py-2 text-xs font-medium text-amber-900 ring-1 ring-amber-300 dark:bg-amber-500/10 dark:text-amber-100 dark:ring-amber-500/40'
            : 'mt-2 text-xs text-slate-600 dark:text-slate-400'}>
            Se achican para revisar (1600 px, JPEG). Para que el equipo baje el archivo final, pegá el link al original.
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
      <div className="mx-auto flex w-full max-w-3xl items-center gap-2">
        <button
          type="button"
          onClick={onCancelar}
          disabled={subiendo !== null}
          className="min-h-[48px] rounded-xl px-4 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800 sm:min-h-[44px]"
        >
          Cancelar
        </button>
        <button
          type="button"
          onClick={() => void entregar()}
          disabled={!hayMateriales || preparando > 0 || linkMalo || subiendo !== null}
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
      </div>
    </div>
  )
}

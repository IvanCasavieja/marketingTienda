'use client'

import { useRef, useState } from 'react'
import { Camera, Check, ImagePlus, Link2, Loader2, Send, X } from 'lucide-react'
import { toast } from 'sonner'
import { entregasApi } from '@/lib/api'
import {
  marcasPendientes, nuevoIdDeVersion, prepararImagen, type DetalleEntregas, type ImagenLista, type Marca,
} from '@/lib/calendario/entregas'
import { useImagen } from './useImagen'

function detalleDeError(e: unknown): string | null {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === 'string' ? d : null
}

/** La miniatura de la imagen donde está una marca, con el pin encima: para
 *  que quien corrige vea DÓNDE era sin abrir nada. */
export function DondeEra({ marca, tono = 'cambio' }: { marca: Pick<Marca, 'imagenId' | 'x' | 'y' | 'numero'>; tono?: 'cambio' | 'ajuste' }) {
  const { url } = useImagen(marca.imagenId, 'mini')
  return (
    <span className="relative inline-block h-14 shrink-0 overflow-hidden rounded-lg bg-slate-100 ring-1 ring-black/5 dark:bg-slate-800 dark:ring-white/10">
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element -- URL local del navegador (blob:)
        <img src={url} alt="" className="block h-14 w-auto" />
      ) : (
        <span className="block h-14 w-14" />
      )}
      {url && (
        <span
          aria-hidden
          style={{ left: `${marca.x * 100}%`, top: `${marca.y * 100}%` }}
          className={`absolute h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-white ${tono === 'ajuste' ? 'bg-amber-500' : 'bg-rose-600'}`}
        />
      )}
    </span>
  )
}

/**
 * Entregar una ronda: las imágenes (de la cámara o de la galería), un
 * comentario, el link al original y —si es una ronda que volvió— tildar qué
 * marcas se corrigieron. Las imágenes se achican acá antes de subir.
 */
export function FormularioEntrega({ detalle, onListo, onCancelar }: {
  detalle: DetalleEntregas
  onListo: () => void
  onCancelar: () => void
}) {
  const { resumen, limites } = detalle
  const fase = resumen.fases.find(f => f.id === resumen.faseActual)
  const ronda = resumen.ronda + 1
  const pendientes = marcasPendientes(detalle.fases)
  const cambios = pendientes.filter(m => m.tipo === 'cambio')
  const ajustes = pendientes.filter(m => m.tipo === 'ajuste')

  // El id se arma una vez: si la subida se corta y se reintenta, el
  // servidor reconoce que es la misma y no la duplica.
  const [versionId] = useState(nuevoIdDeVersion)
  const [imagenes, setImagenes] = useState<ImagenLista[]>([])
  const [preparando, setPreparando] = useState(0)
  const [comentario, setComentario] = useState('')
  const [link, setLink] = useState('')
  const [corregidas, setCorregidas] = useState<Set<string>>(() => new Set())
  const [subiendo, setSubiendo] = useState<number | null>(null)
  const camaraRef = useRef<HTMLInputElement>(null)
  const galeriaRef = useRef<HTMLInputElement>(null)

  const linkMalo = link.trim() !== '' && !/^https?:\/\//i.test(link.trim())
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

  function alternar(id: string) {
    setCorregidas(prev => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }

  async function entregar() {
    if (imagenes.length === 0 || linkMalo || subiendo !== null) return
    const form = new FormData()
    form.append('versionId', versionId)
    form.append('comentario', comentario.trim())
    form.append('link', link.trim())
    form.append('corregidas', JSON.stringify([...corregidas]))
    imagenes.forEach((im, i) => {
      form.append('imagenes', im.grande, `imagen-${i + 1}.jpg`)
      form.append('miniaturas', im.mini, `miniatura-${i + 1}.jpg`)
    })
    setSubiendo(0)
    try {
      await entregasApi.entregar(detalle.tarea.id, form, f => setSubiendo(f))
      imagenes.forEach(im => URL.revokeObjectURL(im.vista))
      toast.success(`Entregaste la ronda ${ronda} de ${fase?.nombre ?? 'la fase'}. Le avisamos a quien tiene que revisarla.`)
      onListo()
    } catch (e) {
      toast.error(detalleDeError(e) ?? 'No se pudo entregar. Revisá la conexión y probá de nuevo: no se pierde nada.')
      setSubiendo(null)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 space-y-6 overflow-y-auto overscroll-contain px-4 py-5 sm:px-6">
        <div>
          <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">
            Entregar {ronda === 1 ? fase?.nombre : `la ronda ${ronda} de ${fase?.nombre}`}
          </h3>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Subí la pieza (hasta {limites.imagenes} imágenes). La van a revisar en el orden de la cadena.
          </p>
        </div>

        {cambios.length > 0 && (
          <section aria-labelledby="que-corregiste">
            <div className="mb-2 flex items-center justify-between gap-2">
              <h4 id="que-corregiste" className="text-sm font-bold text-slate-900 dark:text-slate-100">
                ¿Qué corregiste? <span className="font-normal text-slate-500 dark:text-slate-400">Tildá cada marca</span>
              </h4>
              <button
                type="button"
                onClick={() => setCorregidas(new Set([...corregidas, ...cambios.map(m => m.id)]))}
                className="rounded-lg px-2 py-1 text-xs font-semibold text-brand-700 hover:bg-brand-50 dark:text-brand-200 dark:hover:bg-brand-500/10"
              >
                Tildar todas
              </button>
            </div>
            <ListaDeMarcasATildar marcas={cambios} tildadas={corregidas} onAlternar={alternar} />
          </section>
        )}

        {ajustes.length > 0 && (
          <section aria-labelledby="ajustes-anotados">
            <h4 id="ajustes-anotados" className="mb-2 text-sm font-bold text-slate-900 dark:text-slate-100">
              Ajustes anotados <span className="font-normal text-slate-500 dark:text-slate-400">de una fase aprobada con cambios</span>
            </h4>
            <ListaDeMarcasATildar marcas={ajustes} tildadas={corregidas} onAlternar={alternar} />
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
                <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
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
        </section>

        <div className="grid gap-3">
          <label className="block">
            <span className="etiqueta-campo">Comentario (opcional)</span>
            <textarea
              value={comentario}
              onChange={e => setComentario(e.target.value)}
              rows={3}
              maxLength={5000}
              placeholder={cambios.length ? 'Ej: Agrandé el precio y saqué el fondo azul.' : 'Algo que tengan que saber al revisarla'}
              className="campo !h-auto py-2"
            />
          </label>
          <label className="block">
            <span className="etiqueta-campo flex items-center gap-1"><Link2 className="h-3.5 w-3.5" /> Link al original (opcional)</span>
            <input
              type="url"
              value={link}
              onChange={e => setLink(e.target.value)}
              placeholder="https://drive.google.com/…"
              maxLength={1000}
              aria-invalid={linkMalo}
              className="campo"
            />
            {linkMalo && <span className="mt-1 block text-xs text-rose-600 dark:text-rose-300">Tiene que empezar con http:// o https://</span>}
          </label>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2 border-t border-slate-300 bg-white px-4 py-3 pb-[max(.75rem,env(safe-area-inset-bottom))] dark:border-slate-800 dark:bg-slate-900 sm:px-6">
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
          disabled={imagenes.length === 0 || preparando > 0 || linkMalo || subiendo !== null}
          className="ml-auto flex min-h-[48px] flex-1 items-center justify-center gap-2 rounded-xl bg-brand-600 px-5 text-sm font-bold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.98] disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:shadow-none dark:disabled:bg-slate-700 dark:disabled:text-slate-400 sm:min-h-[44px] sm:flex-none"
        >
          {subiendo !== null ? (
            <><Loader2 className="h-4 w-4 animate-spin" /> Subiendo… {Math.round(subiendo * 100)}%</>
          ) : (
            <><Send className="h-4 w-4" /> Entregar ronda {ronda}</>
          )}
        </button>
      </div>
    </div>
  )
}

function ListaDeMarcasATildar({ marcas, tildadas, onAlternar }: {
  marcas: (Marca & { ronda: number; fase: string })[]
  tildadas: Set<string>
  onAlternar: (id: string) => void
}) {
  return (
    <ul className="space-y-1.5">
      {marcas.map(m => {
        const si = tildadas.has(m.id)
        return (
          <li key={m.id}>
            <label className={`flex cursor-pointer items-center gap-3 rounded-xl border p-2 pr-3 transition ${
              si ? 'border-emerald-300 bg-emerald-50 dark:border-emerald-500/40 dark:bg-emerald-500/10' : 'border-slate-300 bg-white hover:border-slate-300 dark:border-slate-700 dark:bg-slate-900'
            }`}>
              <input type="checkbox" checked={si} onChange={() => onAlternar(m.id)} className="sr-only" />
              <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border-2 transition ${
                si ? 'border-emerald-500 bg-emerald-500 text-white' : 'border-slate-300 dark:border-slate-600'
              }`} aria-hidden>
                {si && <Check className="h-4 w-4" strokeWidth={3} />}
              </span>
              <DondeEra marca={m} tono={m.tipo} />
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold text-slate-900 dark:text-slate-100">
                  <span className={`mr-1.5 inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full px-1 text-[11px] font-bold ${m.tipo === 'ajuste' ? 'bg-amber-500 text-slate-950' : 'bg-rose-600 text-white'}`}>{m.numero}</span>
                  {m.texto}
                </span>
                <span className="text-xs text-slate-500 dark:text-slate-400">Ronda {m.ronda} de {m.fase}</span>
              </span>
            </label>
          </li>
        )
      })}
    </ul>
  )
}

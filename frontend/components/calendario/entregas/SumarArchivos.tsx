'use client'

import { useEffect, useRef, useState } from 'react'
import { ImagePlus, Loader2, Paperclip, X } from 'lucide-react'
import { toast } from 'sonner'
import { entregasApi } from '@/lib/api'
import { prepararImagen, type DetalleEntregas, type ImagenLista, type Version } from '@/lib/calendario/entregas'

function detalleDeError(e: unknown): string | null {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : null
}

/**
 * Sumar archivos a la versión que está esperando revisión, sin mandar otra
 * (25/11/2026, Ivan: "si solo les faltó algo, pueden sumarlo a la versión
 * actual sin generar una nueva"). Mientras nadie la decidió y hasta el tope
 * de imágenes de la versión; si no entra, se manda una versión nueva. Lleva
 * una nota corta («faltaba el formato historia») que queda en los
 * comentarios de la tarjeta, y a quien revisa le llega el aviso.
 */
export function SumarArchivos({ detalle, version, onListo, onCancelar }: {
  detalle: DetalleEntregas
  version: Version
  onListo: () => void
  onCancelar: () => void
}) {
  const [imagenes, setImagenes] = useState<ImagenLista[]>([])
  const [preparando, setPreparando] = useState(0)
  const [nota, setNota] = useState('')
  const [subiendo, setSubiendo] = useState<number | null>(null)
  const galeriaRef = useRef<HTMLInputElement>(null)
  const lugar = detalle.limites.imagenes - version.imagenes.length - imagenes.length - preparando

  // Las vistas previas (blob:) se sueltan al salir.
  const vistas = useRef<string[]>([])
  useEffect(() => () => { vistas.current.forEach(v => URL.revokeObjectURL(v)) }, [])

  async function agregar(archivos: FileList | null) {
    if (!archivos || archivos.length === 0) return
    const lista = Array.from(archivos)
    if (lista.length > lugar) {
      toast.error(lugar > 0
        ? `A esta versión le entran ${lugar} más: se tomaron las primeras. Si hace falta más, mandá una versión nueva.`
        : 'Esta versión ya está completa: mandá una versión nueva.')
    }
    const tomadas = lista.slice(0, Math.max(0, lugar))
    setPreparando(n => n + tomadas.length)
    for (const archivo of tomadas) {
      try {
        const preparada = await prepararImagen(archivo)
        vistas.current.push(preparada.vista)
        setImagenes(prev => [...prev, preparada])
      } catch (e) {
        toast.error(e instanceof Error ? e.message : `No se pudo preparar «${archivo.name}»`)
      } finally {
        setPreparando(n => n - 1)
      }
    }
  }

  async function sumar() {
    if (imagenes.length === 0 || subiendo !== null) return
    const form = new FormData()
    form.append('nota', nota.trim())
    imagenes.forEach((im, i) => {
      form.append('imagenes', im.grande, `sumada-${i + 1}.jpg`)
      form.append('miniaturas', im.mini, `miniatura-${i + 1}.jpg`)
    })
    setSubiendo(0)
    try {
      const { data } = await entregasApi.sumarArchivos(version.id, form, f => setSubiendo(f))
      toast.success(`Sumaste ${data.sumadas === 1 ? '1 archivo' : `${data.sumadas} archivos`} a la versión ${data.ronda}: le avisamos a quien la revisa.`)
      onListo()
    } catch (e) {
      toast.error(detalleDeError(e) ?? 'No se pudo sumar. Revisá la conexión y probá de nuevo: no se pierde nada.')
      setSubiendo(null)
    }
  }

  return (
    <section aria-labelledby="sumar-archivos" className="max-w-3xl space-y-3 rounded-2xl border border-slate-300 p-4 dark:border-slate-700">
      <div>
        <h3 id="sumar-archivos" className="flex items-center gap-2 text-sm font-bold text-slate-900 dark:text-slate-100">
          <Paperclip className="h-4 w-4" aria-hidden /> Sumar archivos a la versión {version.ronda}
        </h3>
        <p className="mt-0.5 text-sm text-slate-600 dark:text-slate-400">
          Para lo que faltó, sin mandar una versión nueva. Si cambia la pieza, mejor mandá una versión nueva.
        </p>
      </div>
      {imagenes.length + preparando > 0 && (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {imagenes.map((im, i) => (
            <div key={im.vista} className="relative aspect-square overflow-hidden rounded-xl bg-slate-100 ring-1 ring-black/5 dark:bg-slate-800 dark:ring-white/10">
              {/* eslint-disable-next-line @next/next/no-img-element -- vista previa local (blob:) */}
              <img src={im.vista} alt={`Para sumar ${i + 1}: ${im.nombre}`} className="h-full w-full object-contain" />
              <button
                type="button"
                onClick={() => setImagenes(prev => prev.filter((_, j) => j !== i))}
                disabled={subiendo !== null}
                aria-label={`Sacar ${im.nombre}`}
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
      )}
      {lugar > 0 ? (
        <>
          <button
            type="button"
            onClick={() => galeriaRef.current?.click()}
            disabled={subiendo !== null}
            className="flex min-h-[44px] w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-300 px-4 text-sm font-semibold text-slate-700 transition hover:border-brand-400 hover:bg-brand-50 hover:text-brand-700 dark:border-slate-600 dark:text-slate-200 dark:hover:border-brand-500/60 dark:hover:bg-brand-500/10"
          >
            <ImagePlus className="h-4 w-4" /> Elegir imágenes <span className="font-normal text-slate-500 dark:text-slate-400">(entran {lugar} más)</span>
          </button>
          <input ref={galeriaRef} type="file" accept="image/jpeg,image/png,image/webp,image/*" multiple className="hidden"
            data-testid="sumar-imagenes" onChange={e => { void agregar(e.target.files); e.target.value = '' }} />
        </>
      ) : imagenes.length === 0 && (
        <p className="text-sm text-slate-700 dark:text-slate-300">Esta versión ya tiene todas las imágenes que entran: mandá una versión nueva.</p>
      )}
      <label className="block">
        <span className="etiqueta-campo">Nota (opcional)</span>
        <input
          value={nota}
          onChange={e => setNota(e.target.value)}
          maxLength={1000}
          placeholder="Ej: faltaba el formato historia"
          className="campo"
        />
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" onClick={onCancelar} disabled={subiendo !== null}
          className="min-h-[44px] rounded-xl px-4 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800">
          Cancelar
        </button>
        <button
          type="button"
          onClick={() => void sumar()}
          disabled={imagenes.length === 0 || preparando > 0 || subiendo !== null}
          className="ml-auto flex min-h-[44px] items-center gap-2 rounded-xl bg-brand-600 px-4 text-sm font-bold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.98] disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:shadow-none dark:disabled:bg-slate-700 dark:disabled:text-slate-400"
        >
          {subiendo !== null
            ? <><Loader2 className="h-4 w-4 animate-spin" /> Subiendo… {Math.round(subiendo * 100)}%</>
            : <><Paperclip className="h-4 w-4" /> {imagenes.length > 1 ? `Sumar ${imagenes.length} archivos` : 'Sumar'}</>}
        </button>
      </div>
    </section>
  )
}

'use client'

import { useEffect, useRef, useState } from 'react'
import { Check, ImageOff, Sparkles } from 'lucide-react'
import { useImagen, type Tam } from './useImagen'

/** Cómo se ve un pin: el que se está poniendo ahora, un cambio pedido, uno
 *  que la agencia ya corrigió (con el tilde), o lo que sugiere la IA (no es
 *  una marca: es dónde vio algo; lo ve solo quien aprueba, y recién es marca
 *  si lo convierte). */
export type TonoPin = 'nuevo' | 'cambio' | 'corregida' | 'ia'

export type Pin = { clave: string; numero: number; x: number; y: number; tono: TonoPin; texto?: string }

// Las marcas van todas del mismo color (Ivan, 19/11/2026: "está todo
// muy colorinche (…) tendría que ser algo mucho más minimalista"). Antes cada
// tipo tenía su color (rojo, ámbar, verde) y la imagen parecía un semáforo.
// Ese color es rojo desde el 24/11/2026 (Ivan: "el color debe ser rojo"):
// son cambios pedidos; antes, el violeta de la marca.
// La sugerencia de la IA va de otro tono porque NO es una marca: rojo desde
// el 24/11/2026, como lo que encontró la IA en el costado (Ivan: "que sea
// azul da impresión de estar bien"); antes, violeta.
const TONO: Record<TonoPin, string> = {
  nuevo: 'bg-red-600 text-white ring-white',
  cambio: 'bg-red-600 text-white ring-white',
  corregida: 'bg-red-600 text-white ring-white',
  ia: 'bg-rose-600 text-white ring-rose-200 dark:ring-rose-300/60',
}

/**
 * Una imagen de una versión con sus pins encima. Los pins van en % del
 * ancho y del alto: caen en el mismo punto se vea del tamaño que se vea.
 *
 * Con `onTocar`, tocar la imagen pone un pin ahí (para revisar): se pasan las
 * coordenadas de 0 a 1.
 */
export function ImagenConMarcas({
  imagenId, pines = [], onTocar, onElegirPin, elegido, tam = 'grande', className = '', claseImagen = 'max-h-[60vh]',
  etiqueta,
}: {
  imagenId: string
  pines?: Pin[]
  onTocar?: (x: number, y: number) => void
  onElegirPin?: (clave: string) => void
  elegido?: string | null
  tam?: Tam
  className?: string
  /** El alto máximo de la imagen (cambia entre la vista sola y la comparación). */
  claseImagen?: string
  /** Para el lector de pantalla: qué imagen es. */
  etiqueta: string
}) {
  const { url, error, cargando } = useImagen(imagenId, tam)
  const imgRef = useRef<HTMLImageElement>(null)

  function tocar(e: React.MouseEvent<HTMLDivElement>) {
    if (!onTocar || !imgRef.current) return
    const caja = imgRef.current.getBoundingClientRect()
    const x = (e.clientX - caja.left) / caja.width
    const y = (e.clientY - caja.top) / caja.height
    if (x < 0 || x > 1 || y < 0 || y > 1) return
    onTocar(Math.round(x * 1000) / 1000, Math.round(y * 1000) / 1000)
  }

  if (!url) {
    return (
      <div className={`flex min-h-[14rem] w-full items-center justify-center rounded-xl ${error ? 'bg-slate-100 dark:bg-slate-800' : 'skeleton'} ${className}`}>
        {error ? (
          <p className="flex items-center gap-2 px-4 text-center text-sm text-slate-500 dark:text-slate-400">
            <ImageOff className="h-5 w-5 shrink-0" /> {error}
          </p>
        ) : cargando ? <span className="sr-only">Cargando la imagen…</span> : null}
      </div>
    )
  }

  return (
    <div className={`flex justify-center ${className}`}>
      <div
        className={`relative inline-block max-w-full select-none ${onTocar ? 'cursor-crosshair' : ''}`}
        onClick={tocar}
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- una URL local del navegador (blob:), no algo que Next pueda optimizar */}
        <img
          ref={imgRef}
          src={url}
          alt={etiqueta}
          draggable={false}
          className={`block h-auto w-auto max-w-full rounded-xl bg-white object-contain shadow-sm ring-1 ring-black/5 dark:ring-white/10 ${claseImagen}`}
        />
        {error && (
          <p className="absolute inset-x-2 bottom-2 rounded-lg bg-black/70 px-2 py-1 text-center text-xs text-white">{error} Se ve la miniatura.</p>
        )}
        {pines.map(p => (
          <button
            key={p.clave}
            type="button"
            data-pin={p.clave}
            onClick={e => { e.stopPropagation(); onElegirPin?.(p.clave) }}
            title={p.texto}
            aria-label={p.tono === 'ia'
              ? `Lo que vio la IA${p.texto ? `: ${p.texto}` : ''}`
              : `Marca ${p.numero}${p.texto ? `: ${p.texto}` : ''}`}
            style={{ left: `${p.x * 100}%`, top: `${p.y * 100}%` }}
            className={`absolute flex h-7 w-7 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full text-xs font-bold shadow-md ring-2 transition-transform ${TONO[p.tono]} ${
              elegido === p.clave ? 'z-10 scale-125 ring-4' : 'hover:scale-110'
            }`}
          >
            {/* La sugerencia de la IA late, para encontrarla en la pieza. */}
            {p.tono === 'ia' && <span className="absolute inset-0 animate-ping rounded-full bg-rose-500/40" aria-hidden />}
            {p.tono === 'corregida' ? <Check className="h-4 w-4" strokeWidth={3} />
              : p.tono === 'ia' ? <Sparkles className="relative h-4 w-4" /> : p.numero}
          </button>
        ))}
      </div>
    </div>
  )
}

/** Una miniatura chica (la del tablero, la de la historia).
 *
 * `perezosa`: se pide recién cuando la tarjeta aparece en pantalla (o está
 * por aparecer). En el tablero hay decenas de tarjetas y la mayoría quedan
 * fuera de la vista: así el tablero se pinta enseguida y las imágenes llegan
 * a medida que se ven (16/11/2026: "que se sienta instantáneo"). */
export function Miniatura({ imagenId, etiqueta, className = 'h-16 w-16', perezosa = false }: {
  imagenId: string | null; etiqueta: string; className?: string; perezosa?: boolean
}) {
  const ref = useRef<HTMLSpanElement>(null)
  const [visible, setVisible] = useState(() => !perezosa || typeof IntersectionObserver === 'undefined')
  useEffect(() => {
    if (visible || !ref.current) return
    const io = new IntersectionObserver(es => {
      if (es.some(e => e.isIntersecting)) { setVisible(true); io.disconnect() }
    }, { rootMargin: '200px' })
    io.observe(ref.current)
    return () => io.disconnect()
  }, [visible])
  const { url, error } = useImagen(visible ? imagenId : null, 'mini')
  if (!imagenId) return null
  if (url) {
    // eslint-disable-next-line @next/next/no-img-element -- URL local del navegador (blob:)
    return <img src={url} alt={etiqueta} draggable={false} className={`shrink-0 rounded-lg bg-white object-cover ring-1 ring-black/5 dark:ring-white/10 ${className}`} />
  }
  // Ya vencida (se borró) o sin conexión: un hueco con el ícono, no un "cargando" eterno.
  return error ? (
    <span title={error} className={`flex shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400 ${className}`}>
      <ImageOff className="h-4 w-4" aria-label={error} />
    </span>
  ) : (
    <span ref={ref} className={`skeleton block shrink-0 rounded-lg ${className}`} aria-hidden />
  )
}

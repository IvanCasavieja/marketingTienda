'use client'

import { useEffect, useRef, useState } from 'react'
import { ImageOff } from 'lucide-react'
import { colocacionApi } from '@/lib/api'

/**
 * Una foto de colocación. No puede ser un <img src> directo: la imagen pide
 * la sesión, que viaja en un header (en el iPhone la cookie no llega). Se trae
 * con la sesión, como Blob, y se muestra desde la memoria.
 *
 * - El navegador la guarda en su caché (el servidor la manda "immutable"): la
 *   segunda vez no viaja.
 * - Mientras dura la pestaña, cada foto se pide una sola vez aunque se dibuje
 *   en la grilla y en el visor (`enMemoria`).
 * - Se pide recién cuando está por verse: una grilla de 60 locales no hace 60
 *   pedidos de golpe.
 */

const MAXIMO_EN_MEMORIA = 200
const enMemoria = new Map<string, Promise<string>>()

function urlDe(id: number, tamano: 'mini' | 'grande'): Promise<string> {
  const clave = `${id}:${tamano}`
  const ya = enMemoria.get(clave)
  if (ya) return ya
  const promesa = colocacionApi.imagen(id, tamano).then(({ data }) => URL.createObjectURL(data))
  // Si falla, que el próximo intento vuelva a pedirla.
  promesa.catch(() => enMemoria.delete(clave))
  enMemoria.set(clave, promesa)
  if (enMemoria.size > MAXIMO_EN_MEMORIA) {
    const [vieja, url] = enMemoria.entries().next().value as [string, Promise<string>]
    enMemoria.delete(vieja)
    void url.then(u => URL.revokeObjectURL(u)).catch(() => {})
  }
  return promesa
}

export function FotoProtegida({
  id, tamano, alt, className = '', ajuste = 'cover',
}: {
  id: number
  tamano: 'mini' | 'grande'
  alt: string
  className?: string
  /** 'cover' llena el cuadro (la grilla); 'contain' la muestra entera (el visor). */
  ajuste?: 'cover' | 'contain'
}) {
  const caja = useRef<HTMLDivElement>(null)
  // La grande (el visor) se pide enseguida; las miniaturas, cuando asoman.
  const [visible, setVisible] = useState(() => tamano === 'grande' || typeof IntersectionObserver === 'undefined')
  // Lo que llegó, con la foto a la que corresponde: si el componente pasa a
  // mostrar otra, lo de la anterior no se usa (sin tener que vaciarlo).
  const clave = `${id}:${tamano}`
  const [llego, setLlego] = useState<{ clave: string; url: string | null; error: boolean } | null>(null)
  const url = llego?.clave === clave ? llego.url : null
  const error = llego?.clave === clave && llego.error

  useEffect(() => {
    const el = caja.current
    if (visible || !el) return
    const obs = new IntersectionObserver(entradas => {
      if (entradas.some(e => e.isIntersecting)) { setVisible(true); obs.disconnect() }
    }, { rootMargin: '200px' })
    obs.observe(el)
    return () => obs.disconnect()
  }, [visible])

  useEffect(() => {
    if (!visible) return
    let vivo = true
    urlDe(id, tamano)
      .then(u => { if (vivo) setLlego({ clave: `${id}:${tamano}`, url: u, error: false }) })
      .catch(() => { if (vivo) setLlego({ clave: `${id}:${tamano}`, url: null, error: true }) })
    return () => { vivo = false }
  }, [id, tamano, visible])

  return (
    <div ref={caja} className={`relative overflow-hidden bg-slate-100 dark:bg-slate-800 ${className}`}>
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element -- es un Blob en memoria: next/image no lo optimiza
        <img
          src={url}
          alt={alt}
          className={`h-full w-full animate-fade-in ${ajuste === 'cover' ? 'object-cover' : 'object-contain'}`}
        />
      ) : error ? (
        <span className="absolute inset-0 flex flex-col items-center justify-center gap-1 text-xs text-slate-500 dark:text-slate-400">
          <ImageOff className="h-5 w-5" aria-hidden /> No se pudo cargar
        </span>
      ) : (
        <span className="skeleton absolute inset-0 rounded-none" aria-label="Cargando la foto…" />
      )}
    </div>
  )
}

'use client'

import { useEffect, useState } from 'react'
import { entregasApi } from '@/lib/api'

/**
 * Las imágenes de las entregas se piden con la sesión (axios lleva el token)
 * y se muestran desde una URL local del navegador. No van por un link
 * público: una pieza que todavía no salió no puede quedar abierta a quien
 * tenga el link. Tampoco por <img src="api..."> directo: en Safari la cookie
 * de la API (otro dominio) no viaja y la imagen no cargaría.
 *
 * Cada imagen se pide una sola vez por sesión. De las grandes (~0,1-1 MB) se
 * guardan las últimas MAX_GRANDES; las miniaturas (~20 KB) todas.
 */
const MAX_GRANDES = 30
const cache = new Map<string, Promise<string>>()
const grandes: string[] = []

export type Tam = 'mini' | 'grande'

/** El texto del error, para mostrarlo en lugar de la imagen. */
function porQue(e: unknown): string {
  const status = (e as { response?: { status?: number } })?.response?.status
  if (status === 410) return 'Esta imagen ya se borró (se guardan hasta un tiempo después de terminada la acción).'
  if (status === 404) return 'Esta imagen ya no existe.'
  if (status === 403) return 'No tenés acceso a esta imagen.'
  return 'No se pudo traer la imagen.'
}

export function urlDeImagen(id: string, tam: Tam): Promise<string> {
  const clave = `${id}:${tam}`
  let promesa = cache.get(clave)
  if (!promesa) {
    promesa = entregasApi.imagen(id, tam).then(r => URL.createObjectURL(r.data))
    cache.set(clave, promesa)
    promesa.catch(() => cache.delete(clave))
    if (tam === 'grande') {
      grandes.push(clave)
      while (grandes.length > MAX_GRANDES) {
        const vieja = grandes.shift()!
        const p = cache.get(vieja)
        cache.delete(vieja)
        void p?.then(u => URL.revokeObjectURL(u)).catch(() => {})
      }
    }
  }
  return promesa
}

/** La URL local de una imagen, o el error. Con `tam='grande'` muestra la
 *  miniatura mientras llega la grande (y si la grande ya se borró). */
export function useImagen(id: string | null | undefined, tam: Tam = 'grande') {
  const [estado, setEstado] = useState<{ id: string | null; url: string | null; error: string | null }>(
    { id: null, url: null, error: null },
  )
  useEffect(() => {
    if (!id) return
    let vivo = true
    if (tam === 'grande') {
      void urlDeImagen(id, 'mini').then(u => {
        if (vivo) setEstado(e => (e.id === id && e.url && !e.error ? e : { id, url: u, error: null }))
      }).catch(() => {})
    }
    urlDeImagen(id, tam)
      .then(url => { if (vivo) setEstado({ id, url, error: null }) })
      .catch(e => { if (vivo) setEstado(prev => ({ id, url: prev.id === id ? prev.url : null, error: porQue(e) })) })
    return () => { vivo = false }
  }, [id, tam])
  if (!id || estado.id !== id) return { url: null, error: null, cargando: Boolean(id) }
  return { url: estado.url, error: estado.error, cargando: !estado.url && !estado.error }
}

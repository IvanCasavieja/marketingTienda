'use client'

import { useEffect, useState } from 'react'
import { urlDeImagen } from './useImagen'

/**
 * El alto sobre el ancho de las imágenes de una ronda, para que el lugar de la
 * imagen no cambie de alto al pasar de una a otra (Ivan, 25/11/2026: "el
 * cambiar de una imagen a otra, al tener distintos altos, provoca que cambien
 * las alturas de las pantallas; eso está mal").
 *
 * Se mide con la miniatura: se arma en el navegador achicando el lado mayor
 * (lib/calendario/entregas.ts, aJpeg), así que tiene la misma proporción que
 * la imagen, pesa poco y casi siempre ya está pedida (la tira la muestra).
 */
const proporciones = new Map<string, Promise<number>>()

function proporcionDe(id: string): Promise<number> {
  let p = proporciones.get(id)
  if (!p) {
    p = urlDeImagen(id, 'mini').then(url => new Promise<number>((ok, mal) => {
      const im = new Image()
      im.onload = () => (im.naturalWidth > 0 ? ok(im.naturalHeight / im.naturalWidth) : mal(new Error('sin tamaño')))
      im.onerror = () => mal(new Error('no cargó'))
      im.src = url
    }))
    proporciones.set(id, p)
    p.catch(() => proporciones.delete(id))
  }
  return p
}

/** La proporción (alto / ancho) de la más alta de `ids`, o null mientras no
 *  se sabe (o si ninguna se pudo medir: una ronda ya borrada, por ejemplo). */
export function useProporcionMaxima(ids: string[]): number | null {
  const clave = ids.join(',')
  const [medida, setMedida] = useState<{ clave: string; valor: number | null } | null>(null)
  useEffect(() => {
    if (!clave) return
    let vivo = true
    void Promise.allSettled(clave.split(',').map(proporcionDe)).then(rs => {
      const valores = rs.flatMap(r => (r.status === 'fulfilled' ? [r.value] : []))
      if (vivo) setMedida({ clave, valor: valores.length > 0 ? Math.max(...valores) : null })
    })
    return () => { vivo = false }
  }, [clave])
  return medida && medida.clave === clave ? medida.valor : null
}

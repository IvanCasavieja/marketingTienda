'use client'

import { useEffect, useRef, type ReactNode } from 'react'

/**
 * El marco con scroll horizontal de cada sección.
 *
 * Las tres secciones muestran el mismo mes, así que se mueven juntas: correr
 * una corre las otras. Antes cada una scrolleaba por su cuenta y al acercar
 * quedabas mirando el día 3 arriba y el 20 abajo.
 */
const marcos = new Set<HTMLDivElement>()

export function MarcoScroll({ ancho, children }: { ancho: number; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    marcos.add(el)
    // Al cambiar el zoom, el que ya estaba scrolleado arrastra a los demás
    for (const otro of marcos) {
      if (otro !== el && otro.scrollLeft > 0) { el.scrollLeft = otro.scrollLeft; break }
    }
    return () => { marcos.delete(el) }
  }, [])

  function sincronizar(e: React.UIEvent<HTMLDivElement>) {
    const origen = e.currentTarget
    for (const otro of marcos) {
      // La comparación corta la cadena: al igualarse, el scroll del otro no rebota
      if (otro !== origen && otro.scrollLeft !== origen.scrollLeft) {
        otro.scrollLeft = origen.scrollLeft
      }
    }
  }

  return (
    <div ref={ref} onScroll={sincronizar} className="overflow-x-auto">
      <div style={{ width: ancho }}>{children}</div>
    </div>
  )
}

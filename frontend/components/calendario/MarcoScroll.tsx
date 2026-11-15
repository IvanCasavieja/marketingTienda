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

/**
 * Si el mes no entra a lo ancho (en el teléfono, o con zoom), arranca con hoy
 * a la vista, un día después del borde: abrir el calendario el 20 y ver del 1
 * al 7 obligaba a correrlo cada vez.
 */
function llevarAHoy(el: HTMLDivElement) {
  if (el.scrollWidth <= el.clientWidth) return
  const hoy = el.querySelector<HTMLElement>('[data-hoy]')
  const etiqueta = el.querySelector<HTMLElement>('[data-etiqueta]')
  if (!hoy) return
  const caja = el.getBoundingClientRect()
  const dia = hoy.getBoundingClientRect()
  const destino = el.scrollLeft + (dia.left - caja.left) - (etiqueta?.offsetWidth ?? 0) - dia.width
  if (destino > 0) el.scrollLeft = destino
}

export function MarcoScroll({ ancho, children }: { ancho: number | string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    marcos.add(el)
    // Al cambiar el zoom, el que ya estaba scrolleado arrastra a los demás
    let arrastrado = false
    for (const otro of marcos) {
      if (otro !== el && otro.scrollLeft > 0) { el.scrollLeft = otro.scrollLeft; arrastrado = true; break }
    }
    // El primero en aparecer lleva a hoy; los demás lo siguen al scrollear.
    // Se espera un cuadro: el zoom del teléfono se pone recién al montar.
    const cuadro = arrastrado ? 0 : requestAnimationFrame(() => requestAnimationFrame(() => {
      if ([...marcos].every(m => m.scrollLeft === 0)) llevarAHoy(el)
    }))
    return () => { cancelAnimationFrame(cuadro); marcos.delete(el) }
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
    <div ref={ref} onScroll={sincronizar} className="overflow-x-auto overscroll-x-contain">
      <div style={{ width: ancho }}>{children}</div>
    </div>
  )
}

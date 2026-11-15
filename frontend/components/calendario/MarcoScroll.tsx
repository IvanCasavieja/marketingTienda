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
 * al 7 obligaba a correrlo cada vez. Devuelve dónde lo dejó, o null.
 */
function llevarAHoy(el: HTMLDivElement): number | null {
  if (el.scrollWidth <= el.clientWidth) return null
  const hoy = el.querySelector<HTMLElement>('[data-hoy]')
  const etiqueta = el.querySelector<HTMLElement>('[data-etiqueta]')
  if (!hoy) return null
  const caja = el.getBoundingClientRect()
  const dia = hoy.getBoundingClientRect()
  const destino = Math.max(0, Math.round(el.scrollLeft + (dia.left - caja.left) - (etiqueta?.offsetWidth ?? 0) - dia.width))
  el.scrollLeft = destino
  return el.scrollLeft
}

export function MarcoScroll({ ancho, children }: { ancho: number | string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  /** Mientras la persona no lo corra a mano, se acomoda solo para mostrar hoy. */
  const solo = useRef(true)
  /** Dónde lo dejó el acomodo automático, para no confundirlo con un scroll a mano. */
  const puesto = useRef<number | null>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    marcos.add(el)
    // Al cambiar el zoom, el que ya estaba scrolleado arrastra a los demás
    for (const otro of marcos) {
      if (otro !== el && otro.scrollLeft > 0) { el.scrollLeft = otro.scrollLeft; solo.current = false; break }
    }
    return () => { marcos.delete(el) }
  }, [])

  // Cada vez que cambia el ancho (el zoom del teléfono se pone recién al
  // montar, o se pasa de mes) se vuelve a acomodar en hoy, si nadie lo tocó.
  useEffect(() => {
    const el = ref.current
    if (!el || !solo.current) return
    // Se mide durante unos cuadros: las columnas y el ancho total pueden
    // terminar de acomodarse en cuadros distintos, y una medida a mitad de
    // camino dejaba hoy fuera de la vista.
    let cuadro = 0
    let vueltas = 0
    const acomodar = () => {
      if (!solo.current) return
      puesto.current = llevarAHoy(el)
      if (++vueltas < 6) cuadro = requestAnimationFrame(acomodar)
    }
    cuadro = requestAnimationFrame(acomodar)
    return () => cancelAnimationFrame(cuadro)
  }, [ancho])

  function sincronizar(e: React.UIEvent<HTMLDivElement>) {
    const origen = e.currentTarget
    // Un scroll que no es el que puso el acomodo automático es de la persona
    // (o de otro marco que ella corrió): desde ahí se respeta.
    if (puesto.current == null || Math.abs(origen.scrollLeft - puesto.current) > 1) solo.current = false
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

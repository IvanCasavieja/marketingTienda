'use client'

import { useEffect, useRef, type RefObject } from 'react'

/** Cuánto hay que bajar la hoja (en px) para que se cierre al soltarla. */
const DISTANCIA_PARA_CERRAR = 110
/** O lo rápido (px por ms) que se la tira para abajo, aunque sea poco. */
const VELOCIDAD_PARA_CERRAR = 0.6

/** Si algo entre el dedo y la hoja está corrido para abajo: ahí se desplaza, no se arrastra. */
function hayScrollArriba(desde: EventTarget | null, hoja: HTMLElement): boolean {
  let el = desde instanceof HTMLElement ? desde : null
  while (el && el !== hoja) {
    if (el.scrollTop > 0 && el.scrollHeight > el.clientHeight) return true
    el = el.parentElement
  }
  return hoja.scrollTop > 0
}

function esControl(t: EventTarget | null): boolean {
  return t instanceof HTMLElement && Boolean(t.closest('input, textarea, select, [contenteditable="true"], [role="slider"]'))
}

/**
 * En el teléfono, una hoja (la ficha, el editor, el panel de headers) se
 * cierra tirándola para abajo, como cualquier hoja del sistema. Solo arrastra
 * cuando lo de adentro está arriba de todo: si no, el dedo desplaza el
 * contenido, como siempre. En la notebook no hace nada.
 */
export function useDeslizarParaCerrar(ref: RefObject<HTMLElement | null>, activa: boolean, onCerrar: () => void) {
  // La función de cerrar puede cambiar en cada render: se guarda aparte para
  // no volver a enganchar los toques cada vez.
  const cerrarRef = useRef(onCerrar)
  useEffect(() => { cerrarRef.current = onCerrar })

  useEffect(() => {
    const hoja = ref.current
    if (!hoja || !activa) return
    if (!window.matchMedia('(max-width: 639px)').matches) return

    let inicioY = 0
    let inicioT = 0
    let dy = 0
    let posible = false
    let arrastrando = false

    const soltar = (animar: boolean) => {
      hoja.style.transition = animar ? 'transform .25s cubic-bezier(.2,.8,.2,1)' : ''
      hoja.style.transform = ''
      if (animar) window.setTimeout(() => { hoja.style.transition = '' }, 260)
    }

    const alTocar = (e: TouchEvent) => {
      if (e.touches.length !== 1 || esControl(e.target)) { posible = false; return }
      posible = !hayScrollArriba(e.target, hoja)
      arrastrando = false
      inicioY = e.touches[0].clientY
      inicioT = e.timeStamp
      dy = 0
    }
    const alMover = (e: TouchEvent) => {
      if (!posible) return
      dy = e.touches[0].clientY - inicioY
      if (!arrastrando) {
        // Hacia arriba es desplazar el contenido; recién unos px hacia abajo es arrastrar.
        if (dy < 0) { posible = false; return }
        if (dy < 8) return
        arrastrando = true
      }
      e.preventDefault()
      hoja.style.transition = 'none'
      hoja.style.transform = `translateY(${Math.max(0, dy)}px)`
    }
    const alSoltar = (e: TouchEvent) => {
      if (!arrastrando) return
      arrastrando = false
      const velocidad = dy / Math.max(1, e.timeStamp - inicioT)
      if (dy > DISTANCIA_PARA_CERRAR || (dy > 40 && velocidad > VELOCIDAD_PARA_CERRAR)) {
        // Sale desde donde quedó: el cierre de la hoja anima el resto.
        hoja.style.transition = ''
        cerrarRef.current()
        requestAnimationFrame(() => { hoja.style.transform = '' })
      } else {
        soltar(true)
      }
    }

    hoja.addEventListener('touchstart', alTocar, { passive: true })
    hoja.addEventListener('touchmove', alMover, { passive: false })
    hoja.addEventListener('touchend', alSoltar)
    hoja.addEventListener('touchcancel', alSoltar)
    return () => {
      hoja.removeEventListener('touchstart', alTocar)
      hoja.removeEventListener('touchmove', alMover)
      hoja.removeEventListener('touchend', alSoltar)
      hoja.removeEventListener('touchcancel', alSoltar)
      soltar(false)
    }
  }, [ref, activa])
}

/** La manija de arriba de una hoja en el teléfono: dice que se puede tirar para abajo. */
export const CLASE_MANIJA = 'pointer-events-none absolute left-1/2 top-1.5 z-10 h-1.5 w-10 -translate-x-1/2 rounded-full bg-black/25 dark:bg-white/30 sm:hidden'

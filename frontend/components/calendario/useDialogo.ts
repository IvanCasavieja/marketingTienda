'use client'

import { useEffect, type RefObject } from 'react'

const ENFOCABLES =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'

/** Los que están abiertos, el de más arriba al final: la ficha y, encima, el editor. */
const pila: HTMLElement[] = []

/**
 * Lo que tiene que hacer todo lo que tapa la pantalla (la ficha de una
 * acción, el editor, el panel de headers), para quien usa el teclado o un
 * lector de pantalla:
 *
 *  - al abrirse, el foco entra (al elemento `inicial`, o al primero que tenga
 *    autoFocus adentro);
 *  - Tab da la vuelta adentro y no se escapa a la página de atrás;
 *  - al cerrarse, el foco vuelve a donde estaba (el botón que lo abrió).
 *
 * Con dos abiertos (el editor arriba de la ficha) solo manda el de arriba.
 */
export function useDialogo(
  abierto: boolean,
  caja: RefObject<HTMLElement | null>,
  inicial?: RefObject<HTMLElement | null>,
) {
  useEffect(() => {
    const el = caja.current
    if (!abierto || !el) return
    const antes = document.activeElement as HTMLElement | null
    pila.push(el)

    // Se intenta en los cuadros siguientes hasta que se pueda: mientras la
    // caja todavía figura escondida (con "menos movimiento" la visibilidad
    // tarda un instante en cambiar) el navegador ignora el foco.
    let cuadro = 0
    let intentos = 0
    const enfocar = () => {
      if (el.contains(document.activeElement)) return
      const destino = inicial?.current ?? el
      destino.focus({ preventScroll: true })
      if (document.activeElement !== destino && ++intentos < 20) cuadro = requestAnimationFrame(enfocar)
    }
    cuadro = requestAnimationFrame(enfocar)

    function tab(e: KeyboardEvent) {
      if (e.key !== 'Tab' || pila[pila.length - 1] !== el) return
      const lista = [...el!.querySelectorAll<HTMLElement>(ENFOCABLES)].filter(x => x.getClientRects().length > 0)
      if (lista.length === 0) return
      const primero = lista[0]
      const ultimo = lista[lista.length - 1]
      const activo = document.activeElement
      if (!el!.contains(activo)) { e.preventDefault(); primero.focus(); return }
      if (e.shiftKey && activo === primero) { e.preventDefault(); ultimo.focus() }
      else if (!e.shiftKey && activo === ultimo) { e.preventDefault(); primero.focus() }
    }
    document.addEventListener('keydown', tab)

    return () => {
      cancelAnimationFrame(cuadro)
      document.removeEventListener('keydown', tab)
      const i = pila.lastIndexOf(el)
      if (i !== -1) pila.splice(i, 1)
      // Vuelve a donde estaba, si eso sigue en la página y nadie movió el foco a otro lado.
      if (antes && document.contains(antes) && (el.contains(document.activeElement) || document.activeElement === document.body)) {
        antes.focus({ preventScroll: true })
      }
    }
  }, [abierto, caja, inicial])
}

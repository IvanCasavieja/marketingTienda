'use client'

import { useState, type InputHTMLAttributes } from 'react'

/** Una fecha que se puede guardar: completa y con un año creíble. */
export function esFechaGuardable(v: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) return false
  const anio = Number(v.slice(0, 4))
  return anio >= 2000 && anio <= 2100
}

/**
 * Un campo de fecha que guarda solo fechas de verdad.
 *
 * El campo de fecha del navegador avisa de un cambio en cada tecla, y el año
 * va pasando por 0002, 0020, 0202 antes de llegar a 2026: guardar en cada
 * cambio mandaba esas fechas al servidor y las veía todo el equipo (lo
 * encontraron las pruebas del 15/11/2026). Acá se guarda cuando la fecha está
 * completa y el año es creíble; si se la borra, se guarda vacía al salir del
 * campo. Lo que se está escribiendo no lo pisa lo que llega del servidor.
 */
export function CampoFecha({ valor, onGuardar, ...props }: {
  valor: string | null | undefined
  onGuardar: (fecha: string | null) => void
} & Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange' | 'type' | 'defaultValue'>) {
  const guardado = valor ?? ''
  const [texto, setTexto] = useState<string | null>(null)
  const editando = texto !== null

  return (
    <input
      {...props}
      type="date"
      min="2000-01-01"
      max="2100-12-31"
      value={editando ? texto : guardado}
      onFocus={e => { setTexto(guardado); props.onFocus?.(e) }}
      onChange={e => {
        const v = e.target.value
        setTexto(v)
        if (v !== guardado && esFechaGuardable(v)) onGuardar(v)
      }}
      onBlur={e => {
        if (texto === '' && guardado !== '') onGuardar(null)
        setTexto(null)
        props.onBlur?.(e)
      }}
    />
  )
}

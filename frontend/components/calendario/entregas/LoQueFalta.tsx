'use client'

import { useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import type { DetalleEntregas, Version } from '@/lib/calendario/entregas'
import { loQueFaltaba, primeras } from '@/lib/calendario/piezas'

/**
 * Las piezas del pedido que no venían en una ronda, y por qué (21/11/2026).
 * La ven quien aprueba (arriba al revisar) y la agencia (en la ficha de la
 * ronda). Lo que falta lo vio la plataforma por las medidas al entregar, y el
 * porqué lo escribió quien entregó (lib/calendario/piezas.ts). Si no faltaba
 * nada, no se muestra.
 *
 * Era una línea en ámbar con todo seguido («Faltan 10 piezas del pedido:
 * Header (web), Slider fila (normal) (mobile), Carrito, … · La agencia dice:
 * «…»»), que con muchas piezas se salía de la pantalla (Ivan, 21/11/2026:
 * "no tiene un formato bonito de ver ni nada"). Ahora es un bloque compacto:
 * el título con la cantidad, las piezas como chips que se acomodan en varias
 * líneas (si son muchas, las primeras y «Ver todas») y, en otro renglón, lo
 * que dijo quien entregó. El ámbar queda solo en el ícono.
 */
export function LoQueFalta({ detalle, version, className = '' }: {
  detalle: DetalleEntregas
  version: Version
  className?: string
}) {
  const [todas, setTodas] = useState(false)
  // Si la hace alguien de Tienda, lo dice esa persona; si no, la agencia.
  const hace = detalle.tarea.quienLaHace
  const deTienda = hace?.tipo === 'tienda' && version.subidaPor != null ? detalle.personas[String(version.subidaPor)] : null
  const falta = loQueFaltaba(version.faltan, version.porQueFaltan, deTienda || 'La agencia')
  if (!falta) return null
  const { vistas, resto } = primeras(falta.piezas)
  const piezas = todas ? falta.piezas : vistas
  return (
    <section
      aria-label={falta.titulo}
      className={`min-w-0 rounded-xl border border-slate-300 px-3 py-2.5 dark:border-slate-700 ${className}`}
    >
      <p className="flex items-center gap-1.5 text-sm font-semibold text-slate-900 dark:text-slate-100">
        <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden />
        {falta.titulo}
      </p>
      <ul className="mt-2 flex flex-wrap items-center gap-1.5">
        {piezas.map((p, i) => (
          <li
            key={`${i}-${p}`}
            className="max-w-full break-words rounded-md border border-slate-300 px-2 py-0.5 text-xs text-slate-700 dark:border-slate-700 dark:text-slate-300"
          >
            {p}
          </li>
        ))}
        {resto > 0 && (
          <li>
            <button
              type="button"
              onClick={() => setTodas(v => !v)}
              aria-expanded={todas}
              className="flex min-h-[32px] items-center rounded-md px-1.5 text-xs font-semibold text-brand-700 transition hover:bg-slate-100 dark:text-brand-200 dark:hover:bg-slate-800"
            >
              {todas ? 'Ver menos' : 'Ver todas'}
            </button>
          </li>
        )}
      </ul>
      {falta.porQue && (
        <p className="mt-2 break-words text-sm text-slate-600 dark:text-slate-400">
          <span className="font-semibold text-slate-700 dark:text-slate-300">{falta.quien} dice:</span> «{falta.porQue}»
        </p>
      )}
    </section>
  )
}

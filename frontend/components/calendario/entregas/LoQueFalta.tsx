'use client'

import { AlertTriangle } from 'lucide-react'
import type { DetalleEntregas, Version } from '@/lib/calendario/entregas'
import { lineaDeLoQueFalta } from '@/lib/calendario/piezas'

/**
 * Las piezas del pedido que no venían en una ronda, y por qué (21/11/2026):
 * «Faltan 2 piezas del pedido: Header (mobile), Checkout · La agencia dice:
 * «Es el KV, para aprobarlo antes»». Una línea discreta, en ámbar. La ven
 * quien aprueba (arriba al revisar) y la agencia (en la ficha de la ronda).
 * Lo que falta lo vio la plataforma por las medidas al entregar, y el porqué
 * lo escribió quien entregó (lib/calendario/piezas.ts). Si no faltaba nada,
 * no se muestra.
 */
export function LoQueFalta({ detalle, version, className = '' }: {
  detalle: DetalleEntregas
  version: Version
  className?: string
}) {
  // Si la hace alguien de Tienda, lo dice esa persona; si no, la agencia.
  const hace = detalle.tarea.quienLaHace
  const deTienda = hace?.tipo === 'tienda' && version.subidaPor != null ? detalle.personas[String(version.subidaPor)] : null
  const texto = lineaDeLoQueFalta(version.faltan, version.porQueFaltan, deTienda || 'La agencia')
  if (!texto) return null
  return (
    <p className={`flex items-start gap-1.5 text-sm text-amber-800 dark:text-amber-200 ${className}`}>
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <span className="min-w-0 break-words">{texto}</span>
    </p>
  )
}

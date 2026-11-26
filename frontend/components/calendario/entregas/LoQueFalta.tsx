'use client'

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, Info } from 'lucide-react'
import { seAproboSinEllas, type DetalleEntregas, type Version } from '@/lib/calendario/entregas'
import { loQueFaltaba, primeras } from '@/lib/calendario/piezas'

/**
 * Las piezas del pedido que no venían en una ronda, y por qué (21/11/2026).
 * La ven quien aprueba (al revisar, en el costado) y la agencia (en la ficha
 * de la ronda). Lo que falta lo vio la plataforma por las medidas al
 * entregar, y el porqué lo escribió quien entregó (lib/calendario/piezas.ts).
 * Si no faltaba nada, no se muestra.
 *
 * Era una línea en ámbar con todo seguido («Faltan 10 piezas del pedido:
 * Header (web), Slider fila (normal) (mobile), Carrito, … · La agencia dice:
 * «…»»), que con muchas piezas se salía de la pantalla (Ivan, 21/11/2026:
 * "no tiene un formato bonito de ver ni nada"). Ahora es un bloque compacto:
 * el título con la cantidad, las piezas como chips que se acomodan en varias
 * líneas (si son muchas, las primeras y «Ver todas») y, en otro renglón, lo
 * que dijo quien entregó.
 *
 * En rojo desde el 24/11/2026 (Ivan: "debería tener un color más rojito,
 * colorado"): es algo que falta. `enPanel`: va adentro del panel del
 * costado del Revisor, junto con lo de la IA, sin borde propio (Ivan:
 * "aparece un cartel arriba y lo otro en el costado: debería aparecer todo
 * en el costado").
 *
 * Si la versión se aprobó, ya no falta: se aprobó sin esas piezas, y se dice
 * así, en gris («Se aprobó sin 1 pieza del pedido»). H-023 de la auditoría
 * del 25/11/2026: arriba decía «Finalizada: se aprobó la entrega» y abajo,
 * en rojo, «Falta 1 pieza del pedido».
 */
export function LoQueFalta({ detalle, version, className = '', enPanel = false }: {
  detalle: DetalleEntregas
  version: Version
  className?: string
  enPanel?: boolean
}) {
  const { t } = useTranslation()
  const [todas, setTodas] = useState(false)
  // Si la hace alguien de Tienda, lo dice esa persona; si no, la agencia.
  const hace = detalle.tarea.quienLaHace
  const deTienda = hace?.tipo === 'tienda' && version.subidaPor != null ? detalle.personas[String(version.subidaPor)] : null
  const falta = loQueFaltaba(version.faltan, version.porQueFaltan, deTienda || 'La agencia')
  if (!falta) return null
  const seAprobo = seAproboSinEllas(version.estado)
  const titulo = seAprobo ? t('calendario.revisar.seAproboSin', { count: falta.piezas.length }) : falta.titulo
  const { vistas, resto } = primeras(falta.piezas)
  const piezas = todas ? falta.piezas : vistas
  return (
    <section
      aria-label={titulo}
      className={`min-w-0 ${enPanel ? '' : `rounded-xl border px-3 py-2.5 ${
        seAprobo ? 'border-slate-300 dark:border-slate-700' : 'border-rose-300 dark:border-rose-500/40'
      }`} ${className}`}
    >
      <p className={`flex items-center gap-1.5 text-sm ${
        seAprobo ? 'font-semibold text-slate-700 dark:text-slate-300' : 'font-bold text-rose-800 dark:text-rose-200'
      }`}>
        {seAprobo
          ? <Info className="h-4 w-4 shrink-0 text-slate-500 dark:text-slate-400" aria-hidden />
          : <AlertTriangle className="h-4 w-4 shrink-0 text-rose-600 dark:text-rose-400" aria-hidden />}
        {titulo}
      </p>
      <ul className="mt-2 flex flex-wrap items-center gap-1.5">
        {piezas.map((p, i) => (
          <li
            key={`${i}-${p}`}
            className={`max-w-full break-words rounded-md border px-2 py-0.5 text-xs font-medium ${
              seAprobo
                ? 'border-slate-300 bg-slate-50 text-slate-800 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200'
                : 'border-rose-300 bg-rose-50 text-rose-900 dark:border-rose-500/40 dark:bg-rose-500/15 dark:text-rose-100'
            }`}
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
        <p className="mt-2 break-words text-sm text-slate-700 dark:text-slate-300">
          <span className="font-semibold text-slate-900 dark:text-slate-100">{falta.quien} dice:</span> «{falta.porQue}»
        </p>
      )}
    </section>
  )
}

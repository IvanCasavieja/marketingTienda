'use client'

import { ETIQUETA_DEL_VEREDICTO, type CambioControlado } from '@/lib/calendario/control-previo'

/**
 * Lo que vio la IA de cada cosa que se pidió, renglón por renglón (21/11/2026,
 * Ivan: "las correcciones de la IA están súper mezcladas, no tiene un formato
 * bonito de ver ni nada"). Cada renglón: un indicador chico de estado
 * («Falta», «No se ve claro», «Hecho»), igual para todos; lo pedido en
 * negrita y, abajo, en gris, lo que vio la IA. Sin fondos de color.
 *
 * El indicador va adentro del renglón, como la gravedad en PanelRevisionIA:
 * en una columna angosta (el teléfono, o al lado de la imagen al revisar) el
 * texto sigue abajo y no queda una columna vacía.
 *
 * Lo usan el aviso antes de mandar (FormularioEntrega: la agencia) y la caja
 * «Lo que se pidió» del Revisor (quien aprueba): los dos ven lo mismo, con el
 * mismo diseño. El borde de afuera lo pone quien lo usa.
 */
export function LoQueVioLaIA({ cambios }: { cambios: CambioControlado[] }) {
  return (
    <ul className="divide-y divide-slate-300 dark:divide-slate-700">
      {cambios.map(c => (
        <li key={c.numero} className="py-2.5">
          <p className="break-words text-sm font-semibold leading-snug text-slate-900 dark:text-slate-100">
            <span className="mr-2 inline-block whitespace-nowrap rounded-full bg-slate-100 px-2 py-px align-[1px] text-[11px] font-semibold leading-4 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
              {ETIQUETA_DEL_VEREDICTO[c.veredicto]}
            </span>
            {c.texto}
          </p>
          {c.nota && <p className="mt-0.5 break-words text-sm leading-snug text-slate-600 dark:text-slate-400">{c.nota}</p>}
        </li>
      ))}
    </ul>
  )
}

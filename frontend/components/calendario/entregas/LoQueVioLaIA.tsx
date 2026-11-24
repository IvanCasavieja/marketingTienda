'use client'

import { ETIQUETA_DEL_VEREDICTO, type CambioControlado, type VeredictoIA } from '@/lib/calendario/control-previo'

/** El color de cada veredicto (24/11/2026, Ivan: "debería tener un color más
 *  rojito, colorado: que sea azul da impresión de estar bien"): rojo lo que
 *  falta, ámbar lo que no se ve claro, verde lo hecho. Fuerte en los dos
 *  modos: se usa con luz de oficina. Lo usa también el Revisor, al lado de
 *  cada marca de la ronda anterior. */
export const COLOR_DEL_VEREDICTO: Record<VeredictoIA, string> = {
  falta: 'bg-rose-600 text-white',
  dudoso: 'bg-amber-200 text-amber-950 dark:bg-amber-400/25 dark:text-amber-100',
  hecho: 'bg-emerald-100 text-emerald-900 dark:bg-emerald-500/20 dark:text-emerald-100',
}

/**
 * Lo que vio la IA de cada cosa que se pidió, renglón por renglón (21/11/2026,
 * Ivan: "las correcciones de la IA están súper mezcladas, no tiene un formato
 * bonito de ver ni nada"). Cada renglón: un indicador chico de estado
 * («Falta», «No se ve claro», «Hecho»); lo pedido en negrita y, abajo, en
 * gris, lo que vio la IA.
 *
 * El indicador iba gris para todos; desde el 24/11/2026 lleva el color de su
 * veredicto (COLOR_DEL_VEREDICTO): en gris, un «Falta» se leía como que
 * estaba todo bien.
 *
 * El indicador va adentro del renglón, como la gravedad en PanelRevisionIA:
 * en una columna angosta (el teléfono, o al lado de la imagen al revisar) el
 * texto sigue abajo y no queda una columna vacía.
 *
 * Lo usan el aviso antes de mandar (FormularioEntrega: la agencia) y el
 * Revisor (quien aprueba): los dos ven lo mismo, con el mismo diseño. El
 * borde de afuera lo pone quien lo usa.
 */
export function LoQueVioLaIA({ cambios }: { cambios: CambioControlado[] }) {
  return (
    <ul className="divide-y divide-slate-300 dark:divide-slate-700">
      {cambios.map(c => (
        <li key={c.numero} className="py-2.5">
          <p className="break-words text-sm font-semibold leading-snug text-slate-900 dark:text-slate-100">
            <span className={`mr-2 inline-block whitespace-nowrap rounded-full px-2 py-px align-[1px] text-[11px] font-bold leading-4 ${COLOR_DEL_VEREDICTO[c.veredicto] ?? ''}`}>
              {ETIQUETA_DEL_VEREDICTO[c.veredicto]}
            </span>
            {c.texto}
          </p>
          {c.nota && <p className="mt-0.5 break-words text-sm leading-snug text-slate-700 dark:text-slate-300">{c.nota}</p>}
        </li>
      ))}
    </ul>
  )
}

/**
 * En qué situación está el pedido del mes que se está mirando (H-009, H-020).
 * Sin imports de fuera de lib/redexpres: lo compila test:redexpres con tsc sin
 * los alias de Next.
 */

export interface MesPedido { year: number; month: number }

/**
 * - sinMeses: marketing todavía no abrió ningún mes.
 * - mesNoAbierto: hay meses, pero el que se mira (o ninguno elegido) no está abierto.
 * - confirmado: el pedido del local ya se confirmó y no se puede cambiar.
 * - abierto: se puede cargar.
 */
export type EstadoPedido = 'sinMeses' | 'mesNoAbierto' | 'confirmado' | 'abierto'

/** El mes está abierto (diciembre 2026 no es diciembre 2027). */
export function mesExiste(meses: MesPedido[], m: MesPedido): boolean {
  return meses.some((x) => x.year === m.year && x.month === m.month)
}

export function estadoDelPedido(
  meses: MesPedido[],
  seleccionado: MesPedido | null,
  fila?: { confirmado: boolean } | null,
): EstadoPedido {
  if (meses.length === 0) return 'sinMeses'
  if (!seleccionado || !mesExiste(meses, seleccionado)) return 'mesNoAbierto'
  if (fila?.confirmado) return 'confirmado'
  return 'abierto'
}

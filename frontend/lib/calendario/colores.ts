/** Paleta para barras nuevas: la misma familia pastel que usa el Excel. */
export const PALETA = [
  '#D9D2E9', '#C9DAF8', '#D0E0E3', '#B6D7A8', '#93C47D',
  '#FFF2CC', '#F9CB9C', '#EA9999', '#E6B8AF', '#D9D9D9',
  '#8EA9DB', '#A4C2F4', '#B4A7D6', '#FFE599', '#A2C4C9',
]

export function colorPorDefecto(semilla: string): string {
  let h = 0
  for (let i = 0; i < semilla.length; i++) h = (h * 31 + semilla.charCodeAt(i)) >>> 0
  return PALETA[h % PALETA.length]
}

/**
 * Negro o blanco segun el fondo, con la formula de luminancia relativa de
 * WCAG. Los colores del Excel son claros, pero alguno se carga a mano.
 */
export function textoSobre(fondo: string | null): string {
  if (!fondo) return '#1f2937'
  const hex = fondo.replace('#', '')
  if (hex.length !== 6) return '#1f2937'
  const canal = (v: number) => {
    const s = v / 255
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
  }
  const [r, g, b] = [0, 2, 4].map(i => canal(parseInt(hex.slice(i, i + 2), 16)))
  const L = 0.2126 * r + 0.7152 * g + 0.0722 * b
  return L > 0.42 ? '#111827' : '#ffffff'
}

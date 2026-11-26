// ---------------------------------------------------------------------------
// El detalle para Valentina, comprimido en partes.
//
// Emilia (25/11/2026) pidió saber qué categorías y productos incorporó o
// abandonó cada cliente VIP, cómo cambió su frecuencia y su mix, y predecir la
// próxima categoría y el potencial. Eso no entra en las tablas del tablero
// (serían millones de filas en una base de 500 MB), así que va aparte,
// comprimido: cliente×mes×categoría, cliente×subcategoría (con los meses en
// que la compró), producto×mes y el catálogo de productos. Lo baja Valentina
// desde la nube (backend: /clientes-vip/detalle).
//
// Cada parte es un gzip completo (CompressionStream del navegador, también en
// Node): pegadas en orden forman un gzip válido de varios miembros.
// ---------------------------------------------------------------------------
import { DETALLES, type NombreDetalle, type Resumidor } from './resumen'

export type ParteDetalle = { nombre: NombreDetalle; parte: number; filas: number; datos: Uint8Array }

/** Cuántas filas van en cada parte (unos 4 a 6 MB sin comprimir; ~1 MB comprimido). */
export const FILAS_POR_PARTE = 150_000

export async function gzip(texto: string): Promise<Uint8Array> {
  const flujo = new Blob([texto]).stream().pipeThrough(new CompressionStream('gzip') as unknown as ReadableWritablePair<Uint8Array, Uint8Array>)
  return new Uint8Array(await new Response(flujo).arrayBuffer())
}

/** Todas las tablas de detalle que tenga el archivo, en partes comprimidas. */
export async function comprimirDetalle(
  r: Resumidor, avisar?: (hechas: number) => void, filasPorParte = FILAS_POR_PARTE,
): Promise<ParteDetalle[]> {
  const partes: ParteDetalle[] = []
  for (const nombre of DETALLES) {
    if (!r.tieneDetalle(nombre)) continue
    let lote: string[] = []
    let parte = 0
    const cerrar = async () => {
      if (!lote.length) return
      // La cabecera va solo en la primera parte: pegadas, es un CSV normal.
      const filas = parte === 0 ? lote.length - 1 : lote.length
      partes.push({ nombre, parte, filas, datos: await gzip(lote.join('\n') + '\n') })
      parte++
      lote = []
      avisar?.(partes.length)
    }
    for (const linea of r.lineasDeDetalle(nombre)) {
      lote.push(linea)
      if (lote.length >= filasPorParte) await cerrar()
    }
    await cerrar()
  }
  return partes
}

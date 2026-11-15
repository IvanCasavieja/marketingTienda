// ---------------------------------------------------------------------------
// Las bandas del calendario: las categorías de las acciones y los formatos de
// Retail Media.
//
// Antes cada mes traia sus bandas del Excel, y un mes que no estaba en el
// Excel no tenia NINGUNA: de noviembre en adelante no habia un solo renglon
// donde cargar una accion. Ahora las bandas son las mismas para todos los
// meses: todas las que aparecen en los Excel importados, en su orden.
// ---------------------------------------------------------------------------

import { esBandaRetirada } from './categorias'
import { SEED } from './seed'
import type { SeedBanda } from './tipos'

export type BandaCatalogo = { nombre: string; grupo?: string }

/**
 * Junta las bandas de todos los meses sin repetir y respetando el orden: una
 * banda que aparece recien en un mes se mete despues de la que la precede en
 * ese mes ("Especiales" solo esta en octubre, y va despues de "Mailing GRAL").
 */
export function unirBandas(meses: SeedBanda[][]): BandaCatalogo[] {
  const out: BandaCatalogo[] = []
  for (const bandas of meses) {
    let anterior = -1
    for (const b of bandas) {
      const i = out.findIndex(x => x.nombre === b.nombre)
      if (i !== -1) { anterior = i; continue }
      out.splice(anterior + 1, 0, { nombre: b.nombre, grupo: b.grupo })
      anterior += 1
    }
  }
  return out
}

const MESES = Object.keys(SEED).sort().map(k => SEED[k])

// Las filas retiradas (Tienda Farma, que tiene su propio mundo) se sacan acá y
// no de seed.ts: ese archivo lo genera el import del Excel, no se edita a mano.
export const BANDAS_COMERCIAL: BandaCatalogo[] =
  unirBandas(MESES.map(m => m.comercial)).filter(b => !esBandaRetirada(b.nombre))
export const BANDAS_RETAIL: BandaCatalogo[] = unirBandas(MESES.map(m => m.retail))

/** El id de la banda de cada posicion del header. */
export const idPosicion = (n: number) => `pos-${n}`

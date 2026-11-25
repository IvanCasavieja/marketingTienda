// ---------------------------------------------------------------------------
// Encontrar los CSV adentro de un zip, sin librerías y sin leerlo entero.
//
// Los archivos de Clientes VIP llegan comprimidos (el de 2025: 517 MB que son
// 2,5 GB de CSV). Se lee solo el índice del final del zip para saber dónde
// empieza cada CSV; después lector.worker.ts lo descomprime de a pedazos con
// el DecompressionStream del navegador. Soporta ZIP64 (archivos de más de 4 GB).
// ---------------------------------------------------------------------------

export type EntradaZip = { nombre: string; inicio: number; tamano: number; metodo: number }

const FIN = 0x06054b50
const FIN64 = 0x06064b50
const UBICADOR64 = 0x07064b50
const CENTRAL = 0x02014b50
const LOCAL = 0x04034b50
const MAX = 0xffffffff

async function leer(archivo: Blob, desde: number, hasta: number): Promise<DataView> {
  return new DataView(await archivo.slice(desde, hasta).arrayBuffer())
}

function u64(v: DataView, o: number): number {
  return v.getUint32(o, true) + v.getUint32(o + 4, true) * 2 ** 32
}

export class ZipInvalido extends Error {}

/** Las entradas del zip que terminan en .csv (ignora carpetas y lo que agrega macOS). */
export async function csvsDelZip(archivo: Blob): Promise<EntradaZip[]> {
  const cola = Math.min(archivo.size, 65_557)
  const fin = await leer(archivo, archivo.size - cola, archivo.size)
  let p = -1
  for (let i = fin.byteLength - 22; i >= 0; i--) {
    if (fin.getUint32(i, true) === FIN) { p = i; break }
  }
  if (p < 0) throw new ZipInvalido('El archivo no parece un zip.')
  let entradas = fin.getUint16(p + 10, true)
  let tamCentral = fin.getUint32(p + 12, true)
  let inicioCentral = fin.getUint32(p + 16, true)
  if (entradas === 0xffff || tamCentral === MAX || inicioCentral === MAX) {
    const u = p - 20
    if (u < 0 || fin.getUint32(u, true) !== UBICADOR64) throw new ZipInvalido('No se pudo leer el índice del zip.')
    const donde = u64(fin, u + 8)
    const z64 = await leer(archivo, donde, donde + 56)
    if (z64.getUint32(0, true) !== FIN64) throw new ZipInvalido('No se pudo leer el índice del zip.')
    entradas = u64(z64, 32)
    tamCentral = u64(z64, 40)
    inicioCentral = u64(z64, 48)
  }
  const central = await leer(archivo, inicioCentral, inicioCentral + tamCentral)
  const salida: EntradaZip[] = []
  let o = 0
  for (let n = 0; n < entradas && o + 46 <= central.byteLength; n++) {
    if (central.getUint32(o, true) !== CENTRAL) throw new ZipInvalido('El índice del zip está roto.')
    const metodo = central.getUint16(o + 10, true)
    let tamano = central.getUint32(o + 20, true)
    const sinComprimir = central.getUint32(o + 24, true)
    const largoNombre = central.getUint16(o + 28, true)
    const largoExtra = central.getUint16(o + 30, true)
    const largoComentario = central.getUint16(o + 32, true)
    let local = central.getUint32(o + 42, true)
    const nombre = new TextDecoder().decode(new Uint8Array(central.buffer, central.byteOffset + o + 46, largoNombre))
    // ZIP64: los tamaños de verdad están en el campo extra 0x0001, en orden.
    let e = o + 46 + largoNombre
    const finExtra = e + largoExtra
    while (e + 4 <= finExtra) {
      const id = central.getUint16(e, true)
      const largo = central.getUint16(e + 2, true)
      if (id === 0x0001) {
        let q = e + 4
        if (sinComprimir === MAX) q += 8
        if (tamano === MAX) { tamano = u64(central, q); q += 8 }
        if (local === MAX) { local = u64(central, q) }
      }
      e += 4 + largo
    }
    o = finExtra + largoComentario
    if (!/\.csv$/i.test(nombre) || nombre.startsWith('__MACOSX/') || nombre.split('/').pop()!.startsWith('.')) continue
    const cab = await leer(archivo, local, local + 30)
    if (cab.getUint32(0, true) !== LOCAL) throw new ZipInvalido('El zip está roto.')
    const inicio = local + 30 + cab.getUint16(26, true) + cab.getUint16(28, true)
    salida.push({ nombre, inicio, tamano, metodo })
  }
  if (!salida.length) throw new ZipInvalido('Adentro del zip no hay ningún CSV.')
  for (const s of salida) {
    if (s.metodo !== 0 && s.metodo !== 8) throw new ZipInvalido(`"${s.nombre}" está comprimido de una forma que no se puede leer acá. Volvé a comprimirlo con el compresor de Windows.`)
  }
  return salida
}

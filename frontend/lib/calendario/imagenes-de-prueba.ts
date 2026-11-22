/**
 * Imágenes JPG, PNG y WebP armadas a mano, byte por byte, para probar el
 * lector de encabezados (piezas.ts: medidasDeImagen) y el del ZIP (zip.ts:
 * medidasDeEntrada). Traen solo lo que hace falta para el tamaño: no se
 * pueden dibujar. Solo para las pruebas (piezas.test.ts, zip.test.ts).
 */

const be16 = (n: number) => [(n >> 8) & 0xff, n & 0xff]
const le16 = (n: number) => [n & 0xff, (n >> 8) & 0xff]
const le24 = (n: number) => [n & 0xff, (n >> 8) & 0xff, (n >> 16) & 0xff]
const le32 = (n: number) => [n & 0xff, (n >> 8) & 0xff, (n >> 16) & 0xff, (n >>> 24) & 0xff]
const be32 = (n: number) => [(n >>> 24) & 0xff, (n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff]
const letras = (s: string) => Array.from(s, c => c.charCodeAt(0))

export type OpcionesJpeg = {
  /** La orientación del EXIF (1 a 8), en el orden de bytes `orden`. */
  orientacion?: number
  orden?: 'II' | 'MM'
  /** Bytes de relleno antes del tamaño (como el perfil de color de Photoshop), en segmentos APP2. */
  relleno?: number
  /** El SOF: 0xC0 (el común) o 0xC2 (progresivo). */
  sof?: number
  /** 0xFF de más antes del SOF (los permite el formato). */
  bytesDeRelleno?: number
}

/** Un JPG de `ancho`×`alto`: SOI, el EXIF si va, el relleno, el SOF y el principio de los datos. */
export function jpegArmado(ancho: number, alto: number, o: OpcionesJpeg = {}): Uint8Array {
  const b: number[] = [0xff, 0xd8]
  if (o.orientacion) {
    const ii = (o.orden ?? 'II') === 'II'
    const u16 = ii ? le16 : be16
    const u32 = ii ? le32 : be32
    const tiff = [...letras(ii ? 'II' : 'MM'), ...u16(42), ...u32(8), ...u16(1),
      ...u16(0x0112), ...u16(3), ...u32(1), ...u16(o.orientacion), 0, 0, ...u32(0)]
    const app1 = [...letras('Exif\0\0'), ...tiff]
    b.push(0xff, 0xe1, ...be16(app1.length + 2), ...app1)
  }
  let falta = o.relleno ?? 0
  while (falta > 0) {
    const n = Math.min(falta, 65000)
    b.push(0xff, 0xe2, ...be16(n + 2))
    for (let i = 0; i < n; i++) b.push(0x5a)
    falta -= n
  }
  for (let i = 0; i < (o.bytesDeRelleno ?? 0); i++) b.push(0xff)
  b.push(0xff, o.sof ?? 0xc0, ...be16(17), 8, ...be16(alto), ...be16(ancho), 3, 1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1)
  b.push(0xff, 0xda, ...be16(12), 3, 1, 0, 2, 0x11, 3, 0x11, 0, 0x3f, 0, 0x12, 0x34, 0xff, 0xd9)
  return new Uint8Array(b)
}

/** Un PNG de `ancho`×`alto`: la firma y el IHDR (sin el CRC verdadero: el lector no lo mira). */
export function pngArmado(ancho: number, alto: number): Uint8Array {
  return new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, ...be32(13), ...letras('IHDR'),
    ...be32(ancho), ...be32(alto), 8, 6, 0, 0, 0, 0, 0, 0, 0, ...be32(0), ...letras('IEND'), 0xae, 0x42, 0x60, 0x82])
}

/** Un WebP de `ancho`×`alto`: con pérdida (VP8), sin pérdida (VP8L) o extendido (VP8X). */
export function webpArmado(ancho: number, alto: number, tipo: 'VP8 ' | 'VP8L' | 'VP8X' = 'VP8 '): Uint8Array {
  let trozo: number[]
  if (tipo === 'VP8 ') {
    // La marca del cuadro (3 bytes), 9d 01 2a y el tamaño en 14 bits (los 2 de arriba: la escala).
    trozo = [0x50, 0x02, 0x00, 0x9d, 0x01, 0x2a, ...le16(ancho | 0xc000), ...le16(alto), 0, 0]
  } else if (tipo === 'VP8L') {
    trozo = [0x2f, ...le32(((ancho - 1) | ((alto - 1) << 14) | (1 << 28)) >>> 0), 0, 0, 0, 0, 0]
  } else {
    trozo = [0x10, 0, 0, 0, ...le24(ancho - 1), ...le24(alto - 1)]
  }
  const cuerpo = [...letras('WEBP'), ...letras(tipo), ...le32(trozo.length), ...trozo]
  return new Uint8Array([...letras('RIFF'), ...le32(cuerpo.length), ...cuerpo])
}

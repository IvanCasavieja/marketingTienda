// ---------------------------------------------------------------------------
// Achicar la foto en el teléfono, antes de subirla.
//
// La foto de un teléfono pesa entre 3 y 8 MB (12 megapíxeles o más). Subida
// así tarda con la señal de un local y, multiplicada por 60 locales, llenaría
// la base gratis en semanas. Acá se redibuja en un canvas con el lado mayor en
// 1280 px y se guarda en JPEG al 70 %: queda en 150-300 KB y se sigue viendo
// bien la góndola. Además se hace una miniatura de 320 px para el tablero de
// promo (60 fotos grandes en una grilla sería bajarse 15 MB).
//
// Redibujarla en el canvas, de paso, le saca los datos de la foto (EXIF: el
// modelo del teléfono, la ubicación) y la endereza: los navegadores aplican la
// orientación de la cámara al dibujarla.
// ---------------------------------------------------------------------------

export const LADO_FOTO = 1280
export const LADO_MINIATURA = 320
export const CALIDAD = 0.7

/** El tamaño al que se achica: el lado mayor en `lado`, sin agrandar nunca. */
export function medidas(ancho: number, alto: number, lado: number): { ancho: number; alto: number } {
  if (ancho <= 0 || alto <= 0) return { ancho: 0, alto: 0 }
  const escala = Math.min(1, lado / Math.max(ancho, alto))
  return { ancho: Math.max(1, Math.round(ancho * escala)), alto: Math.max(1, Math.round(alto * escala)) }
}

type Fuente = { dibujable: CanvasImageSource; ancho: number; alto: number; liberar: () => void }

/** Abre el archivo como imagen, ya enderezada. */
async function abrir(archivo: Blob): Promise<Fuente> {
  if (typeof createImageBitmap === 'function') {
    try {
      const bmp = await createImageBitmap(archivo, { imageOrientation: 'from-image' })
      return { dibujable: bmp, ancho: bmp.width, alto: bmp.height, liberar: () => bmp.close() }
    } catch {
      // Safari viejo no acepta las opciones, o no sabe abrir el formato: se prueba con <img>.
    }
  }
  const url = URL.createObjectURL(archivo)
  try {
    const img = new Image()
    img.decoding = 'async'
    img.src = url
    await img.decode()
    return { dibujable: img, ancho: img.naturalWidth, alto: img.naturalHeight, liberar: () => URL.revokeObjectURL(url) }
  } catch (e) {
    URL.revokeObjectURL(url)
    throw e
  }
}

function dibujar(fuente: Fuente, lado: number): Promise<Blob> {
  const { ancho, alto } = medidas(fuente.ancho, fuente.alto, lado)
  const canvas = document.createElement('canvas')
  canvas.width = ancho
  canvas.height = alto
  const ctx = canvas.getContext('2d')
  if (!ctx) return Promise.reject(new Error('sin canvas'))
  // Un PNG con partes transparentes en JPEG queda negro: se pinta blanco abajo.
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, ancho, alto)
  ctx.imageSmoothingQuality = 'high'
  ctx.drawImage(fuente.dibujable, 0, 0, ancho, alto)
  return new Promise((resolver, rechazar) => {
    canvas.toBlob(b => (b ? resolver(b) : rechazar(new Error('no se pudo achicar'))), 'image/jpeg', CALIDAD)
  })
}

export type FotoLista = { foto: Blob; miniatura: Blob; ancho: number; alto: number }

/** La foto achicada y su miniatura, listas para subir. Si el archivo no es
 *  una imagen que el navegador sepa abrir, un Error con el mensaje para la
 *  persona. */
export async function prepararFoto(archivo: Blob): Promise<FotoLista> {
  let fuente: Fuente
  try {
    fuente = await abrir(archivo)
  } catch {
    throw new Error('No pudimos abrir esa foto. Probá sacarla de nuevo con la cámara.')
  }
  try {
    const foto = await dibujar(fuente, LADO_FOTO)
    const miniatura = await dibujar(fuente, LADO_MINIATURA)
    return { foto, miniatura, ...medidas(fuente.ancho, fuente.alto, LADO_FOTO) }
  } finally {
    fuente.liberar()
  }
}

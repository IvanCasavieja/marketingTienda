// ---------------------------------------------------------------------------
// Lee el archivo de Clientes VIP en segundo plano (un Web Worker), para que la
// pantalla no se trabe mientras pasan 2 GB. Recibe el File; devuelve el
// avance cada tanto y, al final, el resumen (resumen.ts). Un .zip se abre acá
// mismo (zip.ts + DecompressionStream); un .csv se lee directo.
// ---------------------------------------------------------------------------
import { comprimirDetalle, type ParteDetalle } from './detalle'
import { ArchivoInvalido, Resumidor } from './resumen'
import { csvsDelZip, ZipInvalido } from './zip'

export type MensajeDelLector =
  | { tipo: 'avance'; leido: number; total: number; filas: number }
  | { tipo: 'comprimiendo'; partes: number }
  | { tipo: 'listo'; resumen: ReturnType<Resumidor['terminar']>; detalle: ParteDetalle[] }
  | { tipo: 'error'; mensaje: string }

const ctx = self as unknown as {
  postMessage: (m: MensajeDelLector, transferir?: Transferable[]) => void
  onmessage: ((e: MessageEvent) => void) | null
}

function contador(onBytes: (n: number) => void) {
  return new TransformStream<Uint8Array, Uint8Array>({
    transform(trozo, control) {
      onBytes(trozo.byteLength)
      control.enqueue(trozo)
    },
  })
}

async function leerTexto(flujo: ReadableStream<Uint8Array>, resumidor: Resumidor, avisar: () => void) {
  const decodificador = new TextDecoderStream('utf-8') as unknown as ReadableWritablePair<string, Uint8Array>
  const lector = flujo.pipeThrough(decodificador).getReader()
  for (;;) {
    const { value, done } = await lector.read()
    if (done) break
    resumidor.agregarTexto(value)
    avisar()
  }
}

ctx.onmessage = async (e: MessageEvent<{ archivo: File }>) => {
  const archivo = e.data.archivo
  const resumidor = new Resumidor()
  let leido = 0
  let ultimoAviso = 0
  const avisar = (forzar = false) => {
    const ahora = Date.now()
    if (!forzar && ahora - ultimoAviso < 250) return
    ultimoAviso = ahora
    ctx.postMessage({ tipo: 'avance', leido, total: archivo.size, filas: resumidor.filasArchivo })
  }
  try {
    if (/\.zip$/i.test(archivo.name)) {
      if (typeof DecompressionStream === 'undefined') {
        throw new ZipInvalido('Este navegador no puede abrir zips. Usá Chrome o Edge actualizados, o descomprimilo y cargá el CSV.')
      }
      for (const entrada of await csvsDelZip(archivo)) {
        resumidor.nuevoArchivo(entrada.nombre)
        let flujo = archivo.slice(entrada.inicio, entrada.inicio + entrada.tamano).stream()
          .pipeThrough(contador(n => { leido += n }))
        if (entrada.metodo === 8) flujo = flujo.pipeThrough(new DecompressionStream('deflate-raw') as unknown as TransformStream<Uint8Array, Uint8Array>)
        await leerTexto(flujo, resumidor, avisar)
      }
    } else {
      await leerTexto(archivo.stream().pipeThrough(contador(n => { leido += n })), resumidor, avisar)
    }
    avisar(true)
    const resumen = resumidor.terminar()
    // El detalle para Valentina, comprimido (lo que pidió Emilia el 25/11/2026).
    ctx.postMessage({ tipo: 'comprimiendo', partes: 0 })
    const detalle = await comprimirDetalle(resumidor, partes => ctx.postMessage({ tipo: 'comprimiendo', partes }))
    ctx.postMessage({ tipo: 'listo', resumen, detalle }, detalle.map(p => p.datos.buffer as ArrayBuffer))
  } catch (err) {
    const conocido = err instanceof ArchivoInvalido || err instanceof ZipInvalido
    ctx.postMessage({
      tipo: 'error',
      mensaje: conocido ? (err as Error).message : `No se pudo leer el archivo: ${(err as Error)?.message ?? err}`,
    })
  }
}

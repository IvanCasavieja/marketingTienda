// ---------------------------------------------------------------------------
// La IA revisa la pieza antes que el aprobador.
//
// Pedido de Ivan (idea 5): "IA que revisa la pieza antes que vos: ortografía,
// logo de otro mundo, falta del legal, QR roto". La revisión la hace el
// servidor en segundo plano después de cada entrega
// (backend/app/services/revision_ia.py), y quién la ve también lo decide el
// servidor: los aprobadores y quien gestiona, nunca quien entrega.
//
// Acá está cómo se muestra. Es una ayuda para el aprobador, no una decisión:
// nada de lo que dice la IA le llega a la agencia salvo que el aprobador lo
// convierta en una marca suya.
// ---------------------------------------------------------------------------

export type TipoObservacionIA = 'ortografia' | 'marca' | 'legal' | 'precio_vigencia' | 'codigo' | 'otro'

export type ObservacionIA = {
  id: string
  tipo: TipoObservacionIA
  texto: string
  gravedad: 'importante' | 'a_revisar'
  /** Dónde está, si la IA lo pudo ubicar: la imagen y el punto (0 a 1), como una marca. */
  imagenId: string | null
  x: number | null
  y: number | null
  /** 'nueva'; 'descartada'; o 'marca' (alguien la convirtió en marca al decidir). */
  estado: 'nueva' | 'descartada' | 'marca'
  /** El número de la marca, si es 'marca'. */
  numero: number | null
  por: number | null
  porNombre: string | null
}

/** 'pendiente': la IA la está mirando. 'lista': terminó (aunque no haya
 *  encontrado nada). 'nada': no se revisó o falló: no se muestra nada. */
export type RevisionIA = { estado: 'pendiente' | 'lista' | 'nada'; observaciones: ObservacionIA[] }

export const TIPO_OBSERVACION: Record<TipoObservacionIA, string> = {
  ortografia: 'Ortografía',
  marca: 'Marca o mundo',
  legal: 'Legales',
  precio_vigencia: 'Precio o vigencia',
  codigo: 'QR o código',
  otro: 'Otro',
}

/** "La IA encontró 3 cosas para mirar". Cuenta todas, también las que ya se
 *  descartaron o se hicieron marca: el título no cambia mientras se trabaja. */
export function tituloRevisionIA(observaciones: ObservacionIA[]): string {
  const n = observaciones.length
  if (n === 0) return 'La IA no encontró nada para marcar'
  return n === 1 ? 'La IA encontró 1 cosa para mirar' : `La IA encontró ${n} cosas para mirar`
}

/** Las que siguen abiertas primero (las importantes antes), después las que
 *  ya son marca y al final las descartadas. Dentro de cada grupo, en el orden
 *  en que las dio la IA. */
export function ordenarObservaciones(observaciones: ObservacionIA[]): ObservacionIA[] {
  const peso = (o: ObservacionIA) =>
    o.estado === 'descartada' ? 3 : o.estado === 'marca' ? 2 : o.gravedad === 'importante' ? 0 : 1
  return observaciones
    .map((o, i) => ({ o, i }))
    .sort((a, b) => peso(a.o) - peso(b.o) || a.i - b.i)
    .map(x => x.o)
}

/** Si la IA dijo dónde está: tiene imagen de esta versión y un punto. */
export function tieneLugar(o: ObservacionIA, imagenes: { id: string }[]): boolean {
  return o.x != null && o.y != null && imagenes.some(i => i.id === o.imagenId)
}

/**
 * La marca que sale de una observación ("Hacer marca"): en el punto que dijo
 * la IA y con su texto, que el aprobador puede corregir antes de mandar. Si
 * la IA no la pudo ubicar (por ejemplo, "faltan los legales"), va en el
 * medio de su imagen (o de la que se está mirando): el aprobador la puede
 * borrar y tocar donde va.
 */
export function marcaDesdeObservacion(
  o: ObservacionIA, imagenes: { id: string }[], activa: string,
): { imagenId: string; x: number; y: number; texto: string } {
  if (tieneLugar(o, imagenes)) return { imagenId: o.imagenId as string, x: o.x as number, y: o.y as number, texto: o.texto }
  const imagenId = imagenes.some(i => i.id === o.imagenId) ? (o.imagenId as string) : activa
  return { imagenId, x: 0.5, y: 0.5, texto: o.texto }
}

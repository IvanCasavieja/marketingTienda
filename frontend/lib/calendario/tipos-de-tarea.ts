// ---------------------------------------------------------------------------
// Los tipos de tarea (Banners, Email marketing, Mailing, Cenefas…) con las
// opciones que se tildan y sus medidas (16/11/2026).
//
// El catálogo vive en UN solo lugar: backend/app/services/tipos_de_tarea.py.
// La pantalla lo pide al servidor (GET /calendario/tipos-de-tarea) y no tiene
// una copia: agregar una medida es tocar una línea allá. Acá están los tipos
// y lo que la pantalla arma con ellos (el nombre de la tarjeta, la
// descripción), que tiene que dar lo mismo que arma el servidor.
//
// Este archivo es puro (sin React ni '@/') a propósito.
// ---------------------------------------------------------------------------

export type OpcionDeTipo = { nombre: string; medida: string | null }

export type CampoDeTipo = {
  clave: string
  nombre: string
  /** Se elige una de estas (el CTA, el formato del mailing)… */
  opciones?: string[]
  /** …o es un número entre estos (las páginas, los bloques). */
  minimo?: number
  maximo?: number
  /** Solo si se tildó esta opción ("En bloques"). */
  para?: string
}

export type TipoDeTarea = {
  clave: string
  nombre: string
  opciones: OpcionDeTipo[]
  /** Si se pueden agregar opciones escritas a mano. */
  otras: boolean
  /** La medida del tipo entero, cuando no hay opciones (WhatsApp). */
  medida: string | null
  campos: CampoDeTipo[]
  bajada: string | null
  /** A qué tipo de pieza de las entregas corresponde (banner, mailing…). */
  pieza?: string | null
}

/** "Ciberlunes - Banners": como lo arma el servidor (nombre_de_tarjeta). */
export function nombreDeTarjeta(accion: string, tipo: Pick<TipoDeTarea, 'nombre'> | null | undefined): string {
  const a = accion.split(/\s+/).filter(Boolean).join(' ')
  if (!tipo) return a
  return a ? `${a} - ${tipo.nombre}` : tipo.nombre
}

/** Los campos de más que corresponden a lo tildado (los bloques, solo "En bloques"). */
export function camposVisibles(tipo: TipoDeTarea, opciones: string[]): CampoDeTipo[] {
  return tipo.campos.filter(c => !c.para || opciones.includes(c.para))
}

/** Lo pedido con sus medidas, como lo arma el servidor (descripcion_del_pedido). */
export function descripcionDelPedido(
  tipo: TipoDeTarea | null | undefined, opciones: string[], detalles: Record<string, string | number>,
): string | null {
  if (!tipo) return null
  const medidas = new Map(tipo.opciones.map(o => [o.nombre, o.medida]))
  const lineas: string[] = []
  if (opciones.length) {
    lineas.push(`${tipo.nombre}: ${opciones.map(o => (medidas.get(o) ? `${o} (${medidas.get(o)})` : o)).join(', ')}`)
  } else if (tipo.medida) {
    lineas.push(`${tipo.nombre}: ${tipo.medida}`)
  }
  for (const c of tipo.campos) {
    const v = detalles[c.clave]
    if (v !== undefined && v !== null && v !== '' && (!c.para || opciones.includes(c.para))) lineas.push(`${c.nombre}: ${v}`)
  }
  return lineas.join('\n') || null
}

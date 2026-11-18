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
  /** …o un texto (con `largo`), un link o una fecha con hora (17/11/2026: la
   *  push lleva título, link de destino y cuándo sale). */
  tipo?: 'texto' | 'link' | 'fechaHora'
  largo?: number
}

/** Un link que el servidor acepta: http o https, sin espacios. */
export function linkValido(texto: string): boolean {
  return /^https?:\/\/\S+$/i.test(texto.trim())
}

/** Cómo se lee un dato: la fecha y hora como "20/11/2026 18:30", como en el
 *  servidor (valor_para_leer); lo demás, tal cual. */
export function valorParaLeer(campo: Pick<CampoDeTipo, 'tipo'>, valor: string | number): string {
  if (campo.tipo === 'fechaHora' && typeof valor === 'string') {
    const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(valor)
    if (m) return `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}`
  }
  return String(valor)
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
  /** Solo en esos mundos (Imprenta, Video monitores… son de Redexpres). Sin esto, en todos. */
  mundos?: string[] | null
}

/** Los tipos que se ofrecen en una acción de ese mundo (18/11/2026: las
 *  piezas de Valentina, solo en Redexpres). Como vale_en en el servidor. */
export function tiposDelMundo<T extends Pick<TipoDeTarea, 'mundos'>>(tipos: T[] | null, mundo: string | null | undefined): T[] | null {
  if (!tipos) return null
  return tipos.filter(t => !t.mundos?.length || (!!mundo && t.mundos.includes(mundo)))
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
    if (v !== undefined && v !== null && v !== '' && (!c.para || opciones.includes(c.para))) lineas.push(`${c.nombre}: ${valorParaLeer(c, v)}`)
  }
  return lineas.join('\n') || null
}

/** Lo pedido para mostrar como lista (18/11/2026, Ivan: "la forma de ver lo
 *  que se pidió está horrenda, deberíamos tener las cosas estilo bullet
 *  list"): el tipo, cada opción tildada con su medida y los datos de más. */
export type PedidoEnLista = {
  tipo: string
  items: { nombre: string; medida: string | null }[]
  datos: { nombre: string; valor: string }[]
}

export function pedidoEnLista(
  tipo: TipoDeTarea | null | undefined, opciones: string[], detalles: Record<string, string | number>,
): PedidoEnLista | null {
  if (!tipo) return null
  const medidas = new Map(tipo.opciones.map(o => [o.nombre, o.medida]))
  const items = opciones.map(o => ({ nombre: o, medida: medidas.get(o) ?? null }))
  const datos: PedidoEnLista['datos'] = []
  if (!opciones.length && tipo.medida) datos.push({ nombre: 'Medida', valor: tipo.medida })
  for (const c of tipo.campos) {
    const v = detalles[c.clave]
    if (v !== undefined && v !== null && v !== '' && (!c.para || opciones.includes(c.para))) {
      datos.push({ nombre: c.nombre, valor: valorParaLeer(c, v) })
    }
  }
  if (!items.length && !datos.length) return null
  return { tipo: tipo.nombre, items, datos }
}

/** El detalle escrito sin el pedido que el servidor le pone adelante al
 *  crear la tarjeta (config_por_defecto: pedido + "\n" + lo escrito): así no
 *  se lee dos veces lo mismo. Si no empieza con el pedido, entero. */
export function detalleSinPedido(detalle: string | null | undefined, pedido: string | null | undefined): string {
  const texto = (detalle ?? '').trim()
  const antes = (pedido ?? '').trim()
  if (antes && texto.startsWith(antes)) return texto.slice(antes.length).trim()
  return texto
}

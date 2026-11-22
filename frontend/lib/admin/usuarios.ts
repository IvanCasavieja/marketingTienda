/**
 * La lista de usuarios del panel de administración (Ivan, 20/11/2026):
 * "el orden de las listas debe ser por alfabético y también filtrar por
 * Admin, Super Admin, Usuarios y Viewer", y "seleccionar y seleccionar todo
 * en usuarios, para poder agarrar a más de uno y volarlos".
 */

export type UsuarioDeLaLista = {
  id: number
  full_name: string
  email: string | null
  role_name: string | null
  is_superuser: boolean
}

export type FiltroDeRol = 'todos' | 'superadmin' | 'admin' | 'usuario' | 'viewer'

export const FILTROS_DE_ROL: { clave: FiltroDeRol; nombre: string }[] = [
  { clave: 'todos', nombre: 'Todos' },
  { clave: 'superadmin', nombre: 'Super Admin' },
  { clave: 'admin', nombre: 'Admin' },
  { clave: 'usuario', nombre: 'Usuario' },
  { clave: 'viewer', nombre: 'Viewer' },
]

/** El rol de la persona para el filtro. El Super Admin es una marca de la
 *  cuenta (no un rol que se elige); los demás, por el nombre del rol. Pura. */
export function rolDe(u: UsuarioDeLaLista): FiltroDeRol | null {
  if (u.is_superuser || u.role_name === 'Superadmin') return 'superadmin'
  switch ((u.role_name ?? '').trim().toLowerCase()) {
    case 'admin': return 'admin'
    case 'usuario': return 'usuario'
    case 'viewer': return 'viewer'
    default: return null
  }
}

export function filtrarPorRol<T extends UsuarioDeLaLista>(usuarios: T[], filtro: FiltroDeRol): T[] {
  return filtro === 'todos' ? usuarios : usuarios.filter(u => rolDe(u) === filtro)
}

const COMPARAR = new Intl.Collator('es', { sensitivity: 'base', numeric: true })

/** Por nombre, sin mirar tildes ni mayúsculas; a igual nombre, por mail. Pura. */
export function alfabetico<T extends UsuarioDeLaLista>(usuarios: T[]): T[] {
  return [...usuarios].sort((a, b) =>
    COMPARAR.compare((a.full_name || a.email || '').trim(), (b.full_name || b.email || '').trim())
    || COMPARAR.compare(a.email ?? '', b.email ?? ''))
}

/** Si la cuenta se puede seleccionar para eliminar: ni la propia ni la de un
 *  Super Admin (lo mismo exige el servidor). Pura. */
export function seleccionable(u: UsuarioDeLaLista, yoId: number | null | undefined): boolean {
  return !u.is_superuser && u.id !== yoId
}

/** "Seleccionar todo": si ya están todas las seleccionables, ninguna; si no,
 *  todas las de la lista que se ve (y se conservan las de otras listas). Pura. */
export function alternarTodas(elegidas: Set<number>, visibles: number[]): Set<number> {
  const todas = visibles.length > 0 && visibles.every(id => elegidas.has(id))
  const out = new Set(elegidas)
  for (const id of visibles) {
    if (todas) out.delete(id)
    else out.add(id)
  }
  return out
}

// ---------------------------------------------------------------------------
// Cambiarle la agencia a una cuenta externa (21/11/2026)
// ---------------------------------------------------------------------------
// Revisión del 19/11/2026: pasar a la única cuenta de «Estudio Sur» (una
// agencia que no es un tablero) a Publicis, elegida por error en la lista, se
// tomaba como una corrección del nombre y se llevaba sus tarjetas y
// plantillas sin preguntar; el panel avisaba después. Ahora el servidor las
// pasa solo si se le pide (`pasar_tarjetas`), y el panel pregunta antes de
// guardar. Si es la única, si la vieja es uno de los tres tableros (Publicis,
// Another Monday, Diseñadores: agencias externas, que nunca pasan nada) o si
// es la misma escrita de otra forma, lo decide el servidor
// (GET /admin/users/{id}/pase-de-agencia).

/** Lo que contesta GET /admin/users/{id}/pase-de-agencia. */
export type PaseDeAgencia = {
  /** La agencia que tiene hoy la cuenta. */
  de: string | null
  /** La nueva, escrita como la va a guardar el servidor. */
  a: string | null
  /** Lo que se llevaría: 0 y 0 si no hay nada que preguntar. */
  tarjetas: number
  plantillas: number
}

/** Si al guardar hay que preguntarle al servidor qué se llevaría la cuenta:
 *  ya era externa, sigue siéndolo y se le cambia la agencia. Pura. */
export function hayQueMirarElPase(
  antes: { es_externo?: boolean; empresa?: string | null }, externo: boolean, empresa: string,
): boolean {
  const vieja = (antes.empresa ?? '').trim()
  const nueva = empresa.trim()
  return !!antes.es_externo && externo && vieja !== '' && nueva !== '' && nueva !== vieja
}

export type PreguntaDelPase = { texto: string; si: string; no: string }

const contar = (n: number, una: string, varias: string) => (n > 0 ? `${n} ${n === 1 ? una : varias}` : '')

/**
 * La pregunta antes de guardar, en palabras simples: «Fer es la única cuenta
 * de «Estudio Sur», que tiene 3 tarjetas y 1 plantilla. ¿Pasarlas también a
 * «Publicis»?», con «Sí, pasarlas» / «No, dejarlas en «Estudio Sur»». null
 * si no hay nada que preguntar. Pura.
 */
export function preguntaDelPase(nombre: string, pase: PaseDeAgencia): PreguntaDelPase | null {
  const total = pase.tarjetas + pase.plantillas
  if (total <= 0 || !pase.de || !pase.a) return null
  const tiene = [contar(pase.tarjetas, 'tarjeta', 'tarjetas'), contar(pase.plantillas, 'plantilla', 'plantillas')]
    .filter(Boolean).join(' y ')
  // Tarjeta y plantilla son femeninas: «pasarla» si es una, «pasarlas» si son más.
  const las = total === 1 ? 'la' : 'las'
  return {
    texto: `${nombre} es la única cuenta de «${pase.de}», que tiene ${tiene}. ¿Pasar${las} también a «${pase.a}»?`,
    si: `Sí, pasar${las}`,
    no: `No, dejar${las} en «${pase.de}»`,
  }
}

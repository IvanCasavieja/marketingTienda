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

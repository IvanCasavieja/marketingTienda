/**
 * Pruebas de la pantalla "No tenés acceso" (lib/acceso.ts): qué permiso pide
 * cada herramienta. Lo que de verdad cuida es el servidor.
 *
 *     npm run test:acceso
 */
import { REQUISITOS, aLaHerramienta, puedeEntrar, requisitoDe } from './acceso'
import { RUTAS_DE_MUNDO, rutaEnMundo } from './mundos'
import type { CurrentUser } from '../types'

let fallos = 0
function ok(nombre: string, cond: boolean, detalle = '') {
  if (cond) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre}${detalle ? ' — ' + detalle : ''}`) }
}

const usuario = (extra: Partial<CurrentUser>): CurrentUser => ({
  id: 1, email: 'a@b.uy', full_name: 'Ana', is_active: true, is_superuser: false, role_id: null, role_name: null,
  permissions: ['calendario.view'], assigned_locales: [], mundos: ['tienda_inglesa'], must_change_password: false,
  ...extra,
} as CurrentUser)

const ana = usuario({})
console.log('Qué pide cada herramienta')
ok('el diccionario pide el suyo, no el de cenefas', requisitoDe('/materiales/diccionario')?.permisos.join() === 'cenefas.diccionario')
ok('el convertidor va con las cenefas', requisitoDe('/materiales/convertidor')?.nombre === 'Las cenefas')
ok('las cuentas de Finanzas piden más que Finanzas', requisitoDe('/facturacion/cuentas')?.permisos.join() === 'facturacion.manage')
ok('las listas de precios van con los precios', requisitoDe('/precios/listas')?.nombre === 'Los precios')
ok('el calendario no pasa por acá', requisitoDe('/calendario') === null)
ok('ni el perfil', requisitoDe('/perfil') === null)
ok('una ruta que empieza igual no se confunde', requisitoDe('/preciosos') === null)

console.log('Cómo se dice')
ok('al diccionario', aLaHerramienta('El diccionario') === 'al diccionario')
ok('a la planilla', aLaHerramienta('La planilla de pedidos') === 'a la planilla de pedidos')
ok('a los precios', aLaHerramienta('Los precios') === 'a los precios')
ok('a Finanzas', aLaHerramienta('Finanzas') === 'a Finanzas')

console.log('Quién entra')
ok('sin el permiso, no', !puedeEntrar('/facturacion', ana))
ok('con el permiso, sí', puedeEntrar('/facturacion', usuario({ permissions: ['facturacion.view'] })))
ok('con uno de los que valen alcanza', puedeEntrar('/redexpres/planilla', usuario({ permissions: ['redexpres.manage'] })))
ok('el superadmin entra a todo', puedeEntrar('/admin', usuario({ is_superuser: true, permissions: [] })))
ok('Mi pedido: con un local asignado', puedeEntrar('/redexpres/mi-pedido', usuario({ assigned_locales: ['L1'] })))
ok('Mi pedido: sin local, no', !puedeEntrar('/redexpres/mi-pedido', ana))
ok('lo que no pide nada, todos', puedeEntrar('/ayuda', ana))
ok('sin usuario (falló la red) no se le dice que no', puedeEntrar('/facturacion', null))

console.log('Medios y finanzas en todos los mundos; la planilla, solo en Redexpres (20/11/2026)')
for (const ruta of ['/dashboard', '/canales', '/campaigns', '/analytics', '/settings', '/facturacion', '/facturacion/cuentas']) {
  ok(`${ruta} está en Redexpres`, rutaEnMundo(ruta, 'redexpres'))
  ok(`${ruta} está en Tienda Viajes`, rutaEnMundo(ruta, 'tienda_viajes'))
}
ok('la planilla no está en Tienda Inglesa', !rutaEnMundo('/redexpres/planilla', 'tienda_inglesa'))
ok('la planilla está en Redexpres', rutaEnMundo('/redexpres/planilla', 'redexpres'))
// '/redexpres' agrupa la planilla y Mi pedido, que piden cosas distintas: vale
// que tengan su permiso las pantallas de adentro.
const sinPermiso = RUTAS_DE_MUNDO.filter(r =>
  !requisitoDe(r.prefijo) && !REQUISITOS.some(q => q.prefijo.startsWith(r.prefijo + '/')))
ok('cada herramienta de un mundo tiene su permiso', sinPermiso.length === 0, sinPermiso.map(r => r.prefijo).join())

if (fallos) {
  console.log(`\n${fallos} prueba(s) fallaron`)
  process.exit(1)
}
console.log('\nTodo bien')

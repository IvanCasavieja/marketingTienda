/**
 * Pruebas de lo que ve en pantalla una cuenta externa (la agencia). Lo que de
 * verdad la limita es el servidor (backend/tests/test_agencia_externa*.py);
 * acá, a dónde entra, qué pantallas tiene y cómo se le dice qué fechas ve.
 *
 *     npm run test:externos
 */
import { INICIO_DE_EXTERNOS, calendarioVedado, esExterno, rutaDeExterno, ventanaEnPalabras } from './externos'
import { alcanceDe, veCalendario } from './alcance'
import { inicioDe } from './mundos'
import { delEquipo, nombreConEmpresa, type Persona } from './calendario/tipos'
import type { CurrentUser } from '../types'

let fallos = 0
function ok(nombre: string, cond: boolean, detalle = '') {
  if (cond) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre}${detalle ? ' — ' + detalle : ''}`) }
}
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  ok(nombre, JSON.stringify(obtenido) === JSON.stringify(esperado),
    `obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`)
}

const usuario = (extra: Partial<CurrentUser>): CurrentUser => ({
  id: 1, email: 'a@b.uy', full_name: 'Ana', is_active: true, is_superuser: false, role_id: null, role_name: null,
  permissions: ['calendario.view'], assigned_locales: [], mundos: ['tienda_inglesa'], must_change_password: false,
  ...extra,
})

console.log('externos')
// Por defecto (0070) la agencia no ve el calendario: solo su tablero.
const agencia = usuario({ es_externo: true, empresa: 'Agencia Pampa' })
const agenciaConCalendario = usuario({
  es_externo: true, empresa: 'Agencia Pampa', calendario_alcance: '2m', ventana: { desde: '2026-10-25', hasta: '2026-12-31' },
})
const delEquipoUsuario = usuario({})
const delEquipoSinCalendario = usuario({ calendario_alcance: 'nada' })

ok('una cuenta externa se reconoce', esExterno(agencia))
ok('una del equipo no', !esExterno(delEquipoUsuario) && !esExterno(null))
igual('la agencia entra a su tablero', inicioDe(agencia), INICIO_DE_EXTERNOS)
igual('el equipo, al calendario', inicioDe(delEquipoUsuario), '/calendario')
igual('alguien del equipo que no ve el calendario, a su tablero', inicioDe(delEquipoSinCalendario), INICIO_DE_EXTERNOS)

igual('la agencia arranca sin calendario', alcanceDe(agencia), 'nada')
igual('el equipo arranca con todo', alcanceDe(delEquipoUsuario), 'todo')
ok('con 2 meses ve el calendario', veCalendario(agenciaConCalendario))

for (const r of ['/entregas', '/perfil', '/mundos']) {
  ok(`la agencia tiene ${r}`, rutaDeExterno(r, agencia))
}
for (const r of ['/calendario', '/mis-tareas']) {
  ok(`sin alcance, la agencia no tiene ${r}`, !rutaDeExterno(r, agencia) && calendarioVedado(r, agencia))
  ok(`con alcance, la agencia tiene ${r}`, rutaDeExterno(r, agenciaConCalendario) && !calendarioVedado(r, agenciaConCalendario))
  ok(`alguien del equipo sin alcance tampoco tiene ${r}`, calendarioVedado(r, delEquipoSinCalendario))
}
for (const r of ['/admin', '/materiales/cenefas', '/precios', '/facturacion', '/dashboard', '/colocacion', '/fotos', '/home', '/ayuda', '/calendariox']) {
  ok(`la agencia no tiene ${r}`, !rutaDeExterno(r, agenciaConCalendario))
}

igual('la ventana en palabras', ventanaEnPalabras({ desde: '2026-11-08', hasta: '2026-12-07' }), 'del 8 de noviembre al 7 de diciembre')
igual('cruzando el año', ventanaEnPalabras({ desde: '2026-12-21', hasta: '2027-01-07' }), 'del 21 de diciembre al 7 de enero')
igual('sin ventana no se dice nada', ventanaEnPalabras(null), null)
igual('una fecha rota tampoco', ventanaEnPalabras({ desde: 'x', hasta: 'y' }), null)

const personas: Persona[] = [
  { id: 1, nombre: 'Promo' },
  { id: 2, nombre: 'Ana', externo: true, empresa: 'Agencia Pampa' },
]
igual('la agencia no se ofrece para avisos ni para aprobar', delEquipo(personas).map(p => p.id), [1])
igual('en las listas se ve de qué empresa es', personas.map(nombreConEmpresa), ['Promo', 'Ana (Agencia Pampa)'])

if (fallos) {
  console.log(`\n${fallos} prueba(s) fallaron`)
  process.exit(1)
}
console.log('\nTodo bien')

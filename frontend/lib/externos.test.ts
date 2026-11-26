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
import {
  agenciaElegida, agenciasSinRepetir, asignablesPara, claveDeEmpresa, delEquipo, mismaEmpresa, nombreConEmpresa,
  type Persona,
} from './calendario/tipos'
import type { CurrentUser } from '../types'
import { loginVolviendoA, volverA, volverDeLaBusqueda } from './volver'

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

// El local (login de sucursal) entra a lo suyo, no al chat de Don Tino (H-010).
const local = (extra: Partial<CurrentUser>) =>
  usuario({ permissions: ['ai.don_tino'], assigned_locales: ['Local de prueba'], mundos: ['redexpres'], ...extra })
igual('el local de Redexpres entra a su pedido', inicioDe(local({})), '/redexpres/mi-pedido')
igual('un local cuyo mundo no tiene «Mi pedido», a sus fotos', inicioDe(local({ mundos: ['tienda_inglesa'] })), '/fotos')
// Con dos mundos, el inicio es el del mundo donde está parado: si no, «Volver
// al inicio» desde otro mundo lo mandaría a una pantalla que ahí no existe.
const localEnDosMundos = local({ mundos: ['tienda_inglesa', 'redexpres'] })
igual('parado en Redexpres, a su pedido', inicioDe(localEnDosMundos, 'redexpres'), '/redexpres/mi-pedido')
igual('parado en Tienda Inglesa, a sus fotos', inicioDe(localEnDosMundos, 'tienda_inglesa'), '/fotos')
igual('con un local asignado pero con el calendario, al calendario', inicioDe(usuario({ assigned_locales: ['Local de prueba'] })), '/calendario')
igual('sin calendario ni local, a Don Tino como siempre', inicioDe(usuario({ permissions: ['ai.don_tino', 'analytics.view'] })), '/home')

igual('la agencia arranca sin calendario', alcanceDe(agencia), 'nada')
igual('el equipo arranca con todo', alcanceDe(delEquipoUsuario), 'todo')
ok('con 2 meses ve el calendario', veCalendario(agenciaConCalendario))

for (const r of ['/entregas', '/perfil', '/mundos', '/ayuda']) {
  ok(`la agencia tiene ${r}`, rutaDeExterno(r, agencia))
}
for (const r of ['/calendario', '/mis-tareas']) {
  ok(`sin alcance, la agencia no tiene ${r}`, !rutaDeExterno(r, agencia) && calendarioVedado(r, agencia))
  ok(`con alcance, la agencia tiene ${r}`, rutaDeExterno(r, agenciaConCalendario) && !calendarioVedado(r, agenciaConCalendario))
  // Al equipo, sin calendario, se le cierra el calendario pero no sus tareas.
  ok(`alguien del equipo sin alcance ${r === '/mis-tareas' ? 'conserva' : 'no tiene'} ${r}`,
    calendarioVedado(r, delEquipoSinCalendario) === (r !== '/mis-tareas'))
}
for (const r of ['/admin', '/materiales/cenefas', '/precios', '/facturacion', '/dashboard', '/colocacion', '/fotos', '/home', '/ayudax', '/calendariox']) {
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

// 19/11/2026: elegir a «Fer (Diseñadores)» como responsable de una tarea de
// Tienda la convertía en una pieza de la agencia. Diseñadores es una agencia
// externa: en una tarea de Tienda solo se ofrece gente de Tienda.
const fer: Persona = { id: 3, nombre: 'Fer', externo: true, empresa: 'Diseñadores' }
igual('una tarea de Tienda la lleva alguien de Tienda', asignablesPara([...personas, fer], 'tienda').map(p => p.id), [1])
igual('sin decir quién la hace, es de Tienda', asignablesPara([...personas, fer], undefined).map(p => p.id), [1])
igual('lo de una agencia de afuera lo carga alguien de Tienda', asignablesPara([...personas, fer], 'fuera').map(p => p.id), [1])
igual('en una pieza de una agencia sí se ofrecen sus cuentas', asignablesPara([...personas, fer], 'agencia').map(p => p.id), [1, 2, 3])

// La empresa se elige de una lista y se compara sin tildes ni mayúsculas:
// «Disenadores» o «diseñadores » son Diseñadores (como en el servidor).
igual('la clave de una empresa', claveDeEmpresa('  DISEÑADORES  '), 'disenadores')
ok('sin ñ es la misma', mismaEmpresa('Disenadores', 'Diseñadores'))
ok('con espacios y en minúscula, también', mismaEmpresa('another   monday ', 'Another Monday'))
ok('otra agencia no', !mismaEmpresa('Publicis', 'Diseñadores'))
ok('sin empresa no hay con quién compartirla', !mismaEmpresa('', '') && !mismaEmpresa(null, undefined))
igual('cada agencia una vez, como la escribió la primera', agenciasSinRepetir(['Diseñadores', 'Disenadores', null, 'Publicis', ' publicis ']),
  ['Diseñadores', 'Publicis'])

// El selector de agencia del panel (revisión del 19/11/2026). Al editar la
// única cuenta de «Agencia Oceano», la lista llega sin ella (?menos=<id>),
// como la usa el servidor al guardar: corregirle cómo se escribe no es «Ya
// existe», y su agencia sigue en la lista, elegida.
const tableros = ['Publicis', 'Another Monday', 'Diseñadores']
igual('al abrirla, su agencia sigue en la lista y elegida',
  agenciaElegida(tableros, 'Agencia Oceano', 'Agencia Oceano'),
  { opciones: [...tableros, 'Agencia Oceano'], elegida: 'Agencia Oceano', yaExiste: null })
igual('corregirle cómo se escribe no dice «Ya existe» con el nombre viejo',
  agenciaElegida(tableros, 'Agencia Océano', 'Agencia Oceano').yaExiste, null)
igual('pero si escribe un tablero, sí: se guarda como el tablero',
  agenciaElegida(tableros, ' publicis', 'Agencia Oceano').yaExiste, 'Publicis')
igual('si su agencia tiene otras cuentas, ya viene en la lista: no se repite',
  agenciaElegida([...tableros, 'Agencia Pampa'], 'agencia  pampa', 'agencia  pampa').opciones, [...tableros, 'Agencia Pampa'])
igual('en el alta, con la lista completa, como antes',
  agenciaElegida([...tableros, 'Agencia Pampa'], 'disenadores'),
  { opciones: [...tableros, 'Agencia Pampa'], elegida: 'Diseñadores', yaExiste: 'Diseñadores' })
igual('mientras no llega la lista, nada',
  agenciaElegida(null, 'Agencia Oceano', 'Agencia Oceano'), { opciones: null, elegida: null, yaExiste: null })

// El link del mail abre la tarea después de entrar (H-040, 25/11/2026).
igual('una dirección de acá adentro, tal cual', volverA('/entregas?tarea=ta-1'), '/entregas?tarea=ta-1')
igual('nunca otro sitio', [volverA('https://otro.com'), volverA('//otro.com/x'), volverA('/\\otro.com'), volverA('/x\\y')],
  [null, null, null, null])
igual('ni las pantallas de entrar, ni nada', [volverA('/login'), volverA('/login?volver=%2Fx'), volverA('/reset-password'),
  volverA(''), volverA(null), volverA('entregas')], [null, null, null, null, null, null])
igual('ni con caracteres de control', volverA('/entregas\n'), null)
igual('el login que vuelve a la tarea', loginVolviendoA('/entregas?tarea=ta-1'), '/login?volver=%2Fentregas%3Ftarea%3Dta-1')
igual('desde el inicio, el login a secas', [loginVolviendoA('/'), loginVolviendoA('')], ['/login', '/login'])
igual('ya en el login, no pierde su ?volver', loginVolviendoA('/login?volver=%2Fentregas'), '/login?volver=%2Fentregas')
igual('se lee de la búsqueda', volverDeLaBusqueda('?volver=%2Fentregas%3Ftarea%3Dta-1'), '/entregas?tarea=ta-1')
igual('y si apunta afuera, nada', [volverDeLaBusqueda('?volver=https%3A%2F%2Fotro.com'), volverDeLaBusqueda('')], [null, null])

if (fallos) {
  console.log(`\n${fallos} prueba(s) fallaron`)
  process.exit(1)
}
console.log('\nTodo bien')

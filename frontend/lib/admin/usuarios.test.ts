/**
 * La lista de usuarios del panel (lib/admin/usuarios.ts).
 *
 *     npm run test:usuarios
 */
import {
  alfabetico, alternarTodas, filtrarPorRol, hayQueMirarElPase, preguntaDelPase, rolDe, seleccionable,
  type UsuarioDeLaLista,
} from './usuarios'

let fallos = 0
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  const ok = JSON.stringify(obtenido) === JSON.stringify(esperado)
  if (ok) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre} — obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`) }
}

const u = (id: number, full_name: string, role_name: string | null, is_superuser = false): UsuarioDeLaLista =>
  ({ id, full_name, email: `${full_name.toLowerCase().replace(/\s+/g, '.')}@x.uy`, role_name, is_superuser })
const lista = [
  u(1, 'valeria Acosta', 'Usuario'),
  u(2, 'Ángela Pérez', 'Viewer'),
  u(3, 'Iván Casavieja', null, true),
  u(4, 'Bruno Díaz', 'Admin'),
  u(5, 'Ana Gómez', 'Usuario'),
  u(6, 'Zoe Sin Rol', null),
  u(7, 'agencia', 'Personalizado'),
]

console.log('Orden alfabético')
igual('sin mirar tildes ni mayúsculas', alfabetico(lista).map(x => x.id), [7, 5, 2, 4, 3, 1, 6])
igual('no cambia la lista original', lista.map(x => x.id), [1, 2, 3, 4, 5, 6, 7])

console.log('Por rol')
igual('el Super Admin es la marca de la cuenta', rolDe(lista[2]), 'superadmin')
igual('Admin', filtrarPorRol(lista, 'admin').map(x => x.id), [4])
igual('Usuario', filtrarPorRol(lista, 'usuario').map(x => x.id), [1, 5])
igual('Viewer', filtrarPorRol(lista, 'viewer').map(x => x.id), [2])
igual('Super Admin', filtrarPorRol(lista, 'superadmin').map(x => x.id), [3])
igual('Todos', filtrarPorRol(lista, 'todos').length, 7)
igual('sin rol u otro rol, en ninguno', [rolDe(lista[5]), rolDe(lista[6])], [null, null])

console.log('Seleccionar')
igual('ni la propia ni un Super Admin', lista.filter(x => seleccionable(x, 5)).map(x => x.id), [1, 2, 4, 6, 7])
igual('seleccionar todo', [...alternarTodas(new Set([9]), [1, 2])].sort(), [1, 2, 9])
igual('con todas ya elegidas, las saca', [...alternarTodas(new Set([1, 2, 9]), [1, 2])], [9])
igual('con algunas elegidas, completa', [...alternarTodas(new Set([1]), [1, 2])].sort(), [1, 2])
igual('una lista vacía no hace nada', [...alternarTodas(new Set([3]), [])], [3])

// 21/11/2026: cambiarle la agencia a la única cuenta de una agencia que no es
// un tablero ya no se lleva sus tarjetas y plantillas sin preguntar.
console.log('Cambiar de agencia')
const fer = { es_externo: true, empresa: 'Estudio Sur' }
igual('una externa que cambia de agencia: se mira qué se llevaría', hayQueMirarElPase(fer, true, 'Publicis'), true)
igual('la misma agencia: nada que mirar', hayQueMirarElPase(fer, true, ' Estudio Sur '), false)
igual('deja de ser externa: nada que mirar', hayQueMirarElPase(fer, false, ''), false)
igual('pasa a externa: no tenía agencia', hayQueMirarElPase({ es_externo: false, empresa: null }, true, 'Publicis'), false)
igual('sin agencia elegida todavía', hayQueMirarElPase(fer, true, '  '), false)
igual('lo que pide el pedido de la revisión',
  preguntaDelPase('Fer', { de: 'Estudio Sur', a: 'Publicis', tarjetas: 3, plantillas: 1 }),
  {
    texto: 'Fer es la única cuenta de «Estudio Sur», que tiene 3 tarjetas y 1 plantilla. ¿Pasarlas también a «Publicis»?',
    si: 'Sí, pasarlas',
    no: 'No, dejarlas en «Estudio Sur»',
  })
igual('con una sola, en singular',
  preguntaDelPase('Fer', { de: 'Estudio Sur', a: 'Publicis', tarjetas: 1, plantillas: 0 }),
  {
    texto: 'Fer es la única cuenta de «Estudio Sur», que tiene 1 tarjeta. ¿Pasarla también a «Publicis»?',
    si: 'Sí, pasarla',
    no: 'No, dejarla en «Estudio Sur»',
  })
igual('solo plantillas',
  preguntaDelPase('Fer', { de: 'Estudio Sur', a: 'Publicis', tarjetas: 0, plantillas: 2 })?.texto,
  'Fer es la única cuenta de «Estudio Sur», que tiene 2 plantillas. ¿Pasarlas también a «Publicis»?')
igual('sin nada que pasar (o un tablero), no se pregunta',
  preguntaDelPase('Fer', { de: 'Diseñadores', a: 'Publicis', tarjetas: 0, plantillas: 0 }), null)

if (fallos) {
  console.log(`\n${fallos} prueba(s) fallaron`)
  process.exit(1)
}
console.log('\nTodo bien')

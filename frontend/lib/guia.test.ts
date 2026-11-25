/**
 * La guía de uso que manda el servidor (lib/guia.ts).
 *
 *     npm run test:guia
 */
import { filtrarGuia, trozos, type SeccionDeGuia } from './guia'

let fallos = 0
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  const ok = JSON.stringify(obtenido) === JSON.stringify(esperado)
  if (ok) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre} — obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`) }
}

console.log('Negrita')
igual('sin negrita, un solo trozo', trozos('Elegí el mes.'), [{ texto: 'Elegí el mes.', negrita: false }])
igual('con negrita en el medio', trozos('Tocá **Crear tarea** y listo'), [
  { texto: 'Tocá ', negrita: false }, { texto: 'Crear tarea', negrita: true }, { texto: ' y listo', negrita: false },
])
igual('dos negritas pegadas a los bordes', trozos('**Avanzar** o **Pedir cambios**'), [
  { texto: 'Avanzar', negrita: true }, { texto: ' o ', negrita: false }, { texto: 'Pedir cambios', negrita: true },
])
igual('un ** suelto queda como texto', trozos('5 ** 2'), [{ texto: '5 ** 2', negrita: false }])
igual('vacío, nada', trozos(''), [])

console.log('Buscar')
const secciones: SeccionDeGuia[] = [
  { clave: 'tablero', titulo: 'Tableros', icono: 'Layers', ruta: '/entregas', resumen: 'Las piezas.',
    partes: [{ titulo: 'Columnas', puntos: ['**Esperando feedback**: le toca a Tienda.'], numerada: false }] },
  { clave: 'mi-pedido', titulo: 'Mi pedido', icono: 'ClipboardList', ruta: null, resumen: 'Lo del local.',
    partes: [{ titulo: 'Confirmar', puntos: ['Confirmá el pedido.'], numerada: false }] },
]
igual('sin búsqueda, todas', filtrarGuia(secciones, '  ').map(s => s.clave), ['tablero', 'mi-pedido'])
igual('busca en los puntos, sin tildes ni mayúsculas', filtrarGuia(secciones, 'TIENDA').map(s => s.clave), ['tablero'])
igual('y en el título', filtrarGuia(secciones, 'pedido').map(s => s.clave), ['mi-pedido'])
igual('nada que coincida', filtrarGuia(secciones, 'zzz'), [])

if (fallos) {
  console.log(`\n${fallos} prueba(s) fallaron`)
  process.exit(1)
}
console.log('\nguia: todo bien')

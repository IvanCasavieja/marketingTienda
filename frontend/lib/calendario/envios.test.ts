/**
 * Pruebas del cronograma de envíos y del header mirado por fecha. Se corren
 * con las demás:
 *
 *     npm run test:calendario
 *
 * El cronograma NO es una carga aparte: sale de las piezas que ya tiene cada
 * acción en su ficha. Lo que se fija acá es eso — que un envío aparezca solo
 * por existir la pieza, que caiga el día que se le puso, y que si no tiene
 * fecha propia se note en vez de desaparecer.
 */
import { construirMes, enviosDelMes, filasDeEnvios, headerEnFecha } from './derivar'
import { REGLAS_HEADER, type Barra, type Mes, type Pieza } from './tipos'

let fallos = 0
function ok(nombre: string, cond: boolean, detalle = '') {
  if (cond) { console.log(`  ok    ${nombre}`) }
  else { fallos++; console.log(`  FALLA ${nombre}${detalle ? ' — ' + detalle : ''}`) }
}
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  const a = JSON.stringify(obtenido), b = JSON.stringify(esperado)
  ok(nombre, a === b, `obtenido ${a}, esperado ${b}`)
}

const pieza = (p: Partial<Pieza>): Pieza =>
  ({ id: 'pz-' + Math.random(), area: 'email', formato: 'Mailing digital', estado: 'pendiente', ...p })

/** Un mes con una sola acción, para que las cuentas sean legibles. */
function mesConUnaAccion(accion: Partial<Barra>): Mes {
  const base = construirMes('2026-09')
  const barra: Barra = {
    id: 'ac-1', nombre: 'Aniversario', desde: 10, hasta: 20, color: '#CFE2F3', piezas: [], ...accion,
  }
  return { ...base, comercial: [{ id: 'bn-1', nombre: 'Mailing GRAL', filas: [[barra]] }] }
}

console.log('\ncronograma de envíos')

// --- de dónde salen ---------------------------------------------------------

const sinPiezas = enviosDelMes(mesConUnaAccion({}))
igual('los tres canales están siempre', sinPiezas.map(c => c.area), ['email', 'whatsapp', 'push'])
igual('sin piezas no hay envíos', sinPiezas.map(c => c.envios.length), [0, 0, 0])

const conTres = enviosDelMes(mesConUnaAccion({
  piezas: [
    pieza({ area: 'email', formato: 'Mailing digital', desde: 12, hora: '10:00' }),
    pieza({ area: 'whatsapp', formato: 'Envío masivo', desde: 13 }),
    pieza({ area: 'push', formato: 'Push app', desde: 14 }),
  ],
}))
igual('un envío por canal', conTres.map(c => c.envios.length), [1, 1, 1])
igual('cae el día que se le puso', conTres[0].envios[0].dia, 12)
igual('se guarda la hora', conTres[0].envios[0].hora, '10:00')
igual('lleva el nombre de su acción', conTres[0].envios[0].accion, 'Aniversario')

// --- lo que NO es un envío --------------------------------------------------

const conHeader = enviosDelMes(mesConUnaAccion({
  piezas: [
    pieza({ area: 'web-home', formato: 'Header', desde: 11 }),
    pieza({ area: 'fisico', formato: 'Cenefas' }),
    pieza({ area: 'email', formato: 'Mailing digital', desde: 12 }),
  ],
}))
igual('las piezas que no son de envío no entran', conHeader.map(c => c.envios.length), [1, 0, 0])

// --- sin fecha propia -------------------------------------------------------

const heredado = enviosDelMes(mesConUnaAccion({
  desde: 7, hasta: 9, piezas: [pieza({ area: 'email', formato: 'Mailing digital' })],
}))
igual('sin fecha propia cae el día que arranca la acción', heredado[0].envios[0].dia, 7)
ok('y queda marcado, para que se note', heredado[0].envios[0].heredaLaFecha === true)

const conFecha = enviosDelMes(mesConUnaAccion({
  desde: 7, hasta: 9, piezas: [pieza({ area: 'email', formato: 'Mailing digital', desde: 8 })],
}))
ok('con fecha propia no se marca', conFecha[0].envios[0].heredaLaFecha === false)

// --- días fuera del mes -----------------------------------------------------

const fuera = enviosDelMes(mesConUnaAccion({
  piezas: [
    pieza({ area: 'email', formato: 'Mailing digital', desde: 99 }),
    pieza({ area: 'push', formato: 'Push app', desde: 0 }),
  ],
}))
igual('un día pasado del mes se acomoda al último', fuera[0].envios[0].dia, 30)
igual('y un día cero al primero', fuera[2].envios[0].dia, 1)

// --- orden y filas ----------------------------------------------------------

const desordenados = enviosDelMes(mesConUnaAccion({
  piezas: [
    pieza({ area: 'email', formato: 'Recordatorio', desde: 20, hora: '09:00' }),
    pieza({ area: 'email', formato: 'Mailing digital', desde: 12, hora: '18:00' }),
  ],
}))
igual('salen ordenados por día', desordenados[0].envios.map(e => e.dia), [12, 20])

const filas = filasDeEnvios(desordenados[0].envios)
igual('dos envíos en días distintos comparten una fila', filas.length, 1)

const mismoDia = filasDeEnvios(enviosDelMes(mesConUnaAccion({
  piezas: [
    pieza({ area: 'email', formato: 'Mailing digital', desde: 12, hora: '08:00' }),
    pieza({ area: 'email', formato: 'Recordatorio', desde: 12, hora: '19:00' }),
  ],
}))[0].envios)
igual('dos el mismo día se separan en dos filas, no se pisan', mismoDia.length, 2)
ok('la barra dura un solo día', mismoDia[0][0].desde === mismoDia[0][0].hasta)
ok('la hora se ve en la barra', mismoDia[0][0].nombre.startsWith('08:00'))
ok('un envío apunta a su acción', mismoDia[0][0].origen?.tipo === 'accion')

console.log('\nheader mirado por fecha')

// --- el header en un día ----------------------------------------------------

const sep = construirMes('2026-09')
const dia10 = headerEnFecha(sep, 10)
igual('devuelve las 10 posiciones', dia10.length, REGLAS_HEADER.tope)
igual('numeradas del 1 al 10', dia10.map(p => p.numero), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
igual('marca cuáles son de Retail Media', dia10.filter(p => p.esRM).map(p => p.numero), [4, 5, 6])

const conBarra: Mes = {
  ...sep,
  header: sep.header.map((p, i) => i !== 0 ? { ...p, filas: [[]] } : {
    ...p,
    filas: [[{ id: 'b1', nombre: 'Aniversario', desde: 5, hasta: 9, color: null, origen: { tipo: 'manual' as const } }]],
  }),
}
igual('el día 5 la posición 1 está ocupada', headerEnFecha(conBarra, 5)[0].barra?.nombre, 'Aniversario')
igual('el 9 también, es el último día', headerEnFecha(conBarra, 9)[0].barra?.nombre, 'Aniversario')
igual('el 10 ya está libre', headerEnFecha(conBarra, 10)[0].barra, null)
igual('el 4, antes de empezar, también', headerEnFecha(conBarra, 4)[0].barra, null)

console.log(`\n${fallos === 0 ? 'TODO OK' : fallos + ' FALLAS'}\n`)
process.exit(fallos === 0 ? 0 : 1)

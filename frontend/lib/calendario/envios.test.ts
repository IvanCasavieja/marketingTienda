/**
 * Pruebas del cronograma de envíos y del header mirado por fecha. Se corren
 * con las demás:
 *
 *     npm run test:calendario
 *
 * El cronograma NO es una carga aparte: sale de las piezas que ya tiene cada
 * acción en su ficha. Lo que se fija acá es eso — que un envío aparezca solo
 * por existir la pieza, que caiga el día que se le puso (aunque sea de otro
 * mes que el del arranque de la acción), y que si no tiene fecha propia se
 * note en vez de desaparecer.
 */
import { construirMes, enviosDelMes, filasDeEnvios, headerEnFecha } from './derivar'
import { REGLAS_HEADER, type BarraGuardada, type Mes, type Pieza } from './tipos'

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
function mesConUnaAccion(accion: Partial<BarraGuardada>, clave = '2026-09'): Mes {
  const barra: BarraGuardada = {
    id: 'ac-1', seccion: 'comercial', banda: 'Mailing GRAL', carril: 0, nombre: 'Aniversario',
    desde: '2026-09-10', hasta: '2026-09-20', color: '#CFE2F3', piezas: [], avisos: [], ...accion,
  }
  return construirMes(clave, [barra])
}

console.log('\ncronograma de envíos')

// --- de dónde salen ---------------------------------------------------------

const sinPiezas = enviosDelMes(mesConUnaAccion({}))
igual('los tres canales están siempre', sinPiezas.map(c => c.area), ['email', 'whatsapp', 'push'])
igual('sin piezas no hay envíos', sinPiezas.map(c => c.envios.length), [0, 0, 0])

const conTres = enviosDelMes(mesConUnaAccion({
  piezas: [
    pieza({ area: 'email', formato: 'Mailing digital', desde: '2026-09-12', hora: '10:00' }),
    pieza({ area: 'whatsapp', formato: 'Envío masivo', desde: '2026-09-13' }),
    pieza({ area: 'push', formato: 'Push app', desde: '2026-09-14' }),
  ],
}))
igual('un envío por canal', conTres.map(c => c.envios.length), [1, 1, 1])
igual('cae el día que se le puso', conTres[0].envios[0].dia, 12)
igual('se guarda la hora', conTres[0].envios[0].hora, '10:00')
igual('lleva el nombre de su acción', conTres[0].envios[0].accion, 'Aniversario')

// --- lo que NO es un envío --------------------------------------------------

const conHeader = enviosDelMes(mesConUnaAccion({
  piezas: [
    pieza({ area: 'web-home', formato: 'Header', desde: '2026-09-11' }),
    pieza({ area: 'fisico', formato: 'Cenefas' }),
    pieza({ area: 'email', formato: 'Mailing digital', desde: '2026-09-12' }),
  ],
}))
igual('las piezas que no son de envío no entran', conHeader.map(c => c.envios.length), [1, 0, 0])

// --- sin fecha propia -------------------------------------------------------

const heredado = enviosDelMes(mesConUnaAccion({
  desde: '2026-09-07', hasta: '2026-09-09', piezas: [pieza({ area: 'email', formato: 'Mailing digital' })],
}))
igual('sin fecha propia cae el día que arranca la acción', heredado[0].envios[0].dia, 7)
ok('y queda marcado, para que se note', heredado[0].envios[0].heredaLaFecha === true)

const conFecha = enviosDelMes(mesConUnaAccion({
  desde: '2026-09-07', hasta: '2026-09-09', piezas: [pieza({ area: 'email', formato: 'Mailing digital', desde: '2026-09-08' })],
}))
ok('con fecha propia no se marca', conFecha[0].envios[0].heredaLaFecha === false)

// --- una acción que cruza de mes --------------------------------------------

const cruza = {
  desde: '2026-09-25', hasta: '2026-10-05',
  piezas: [
    pieza({ area: 'email', formato: 'Mailing digital', desde: '2026-10-02', hora: '09:00' }),
    pieza({ area: 'push', formato: 'Push app' }),
  ],
}
const enSep = enviosDelMes(mesConUnaAccion(cruza, '2026-09'))
const enOct = enviosDelMes(mesConUnaAccion(cruza, '2026-10'))
igual('el mailing del 02/10 no aparece en setiembre', enSep[0].envios.length, 0)
igual('aparece en octubre, el día 2', enOct[0].envios.map(e => e.dia), [2])
igual('el push sin fecha cae el 25/09, con la acción', enSep[2].envios.map(e => e.dia), [25])
igual('y no se repite en octubre', enOct[2].envios.length, 0)

const antesDeLaAccion = {
  desde: '2026-10-05', hasta: '2026-10-10',
  piezas: [pieza({ area: 'email', formato: 'Recordatorio', desde: '2026-09-30' })],
}
igual('un recordatorio del 30/09 de una acción de octubre se ve en setiembre',
  enviosDelMes(mesConUnaAccion(antesDeLaAccion, '2026-09'))[0].envios.map(e => e.dia), [30])
igual('y no en octubre', enviosDelMes(mesConUnaAccion(antesDeLaAccion, '2026-10'))[0].envios.length, 0)

// --- orden y filas ----------------------------------------------------------

const desordenados = enviosDelMes(mesConUnaAccion({
  piezas: [
    pieza({ area: 'email', formato: 'Recordatorio', desde: '2026-09-20', hora: '09:00' }),
    pieza({ area: 'email', formato: 'Mailing digital', desde: '2026-09-12', hora: '18:00' }),
  ],
}))
igual('salen ordenados por día', desordenados[0].envios.map(e => e.dia), [12, 20])

const filas = filasDeEnvios(desordenados[0].envios, '2026-09')
igual('dos envíos en días distintos comparten una fila', filas.length, 1)

const mismoDia = filasDeEnvios(enviosDelMes(mesConUnaAccion({
  piezas: [
    pieza({ area: 'email', formato: 'Mailing digital', desde: '2026-09-12', hora: '08:00' }),
    pieza({ area: 'email', formato: 'Recordatorio', desde: '2026-09-12', hora: '19:00' }),
  ],
}))[0].envios, '2026-09')
igual('dos el mismo día se separan en dos filas, no se pisan', mismoDia.length, 2)
ok('la barra dura un solo día', mismoDia[0][0].desde === mismoDia[0][0].hasta)
ok('la hora se ve en la barra', mismoDia[0][0].nombre.startsWith('08:00'))
ok('un envío apunta a su acción', mismoDia[0][0].origen?.tipo === 'accion')
igual('y lleva su fecha real', mismoDia[0][0].inicio, '2026-09-12')

console.log('\nheader mirado por fecha')

// --- el header en un día ----------------------------------------------------

const sep = construirMes('2026-09', [])
const dia10 = headerEnFecha(sep, 10)
igual('devuelve las 10 posiciones', dia10.length, REGLAS_HEADER.tope)
igual('numeradas del 1 al 10', dia10.map(p => p.numero), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
igual('marca cuáles son de Retail Media', dia10.filter(p => p.esRM).map(p => p.numero), [4, 5, 6])

const conBarra = construirMes('2026-09', [{
  id: 'b1', seccion: 'header', banda: 'pos-1', carril: 0, nombre: 'Aniversario',
  color: null, desde: '2026-09-05', hasta: '2026-09-09',
}])
igual('el día 5 la posición 1 está ocupada', headerEnFecha(conBarra, 5)[0].barra?.nombre, 'Aniversario')
igual('el 9 también, es el último día', headerEnFecha(conBarra, 9)[0].barra?.nombre, 'Aniversario')
igual('el 10 ya está libre', headerEnFecha(conBarra, 10)[0].barra, null)
igual('el 4, antes de empezar, también', headerEnFecha(conBarra, 4)[0].barra, null)

console.log(`\n${fallos === 0 ? 'TODO OK' : fallos + ' FALLAS'}\n`)
process.exit(fallos === 0 ? 0 : 1)

/**
 * Pruebas de la derivación del header. Se corren sin levantar nada:
 *
 *     npm test
 *
 * Verifican lo que no se puede mirar a ojo: que Retail Media caiga en sus
 * posiciones, que una acción con pieza Header baje sola a una posición libre
 * de marketing, y que lo que no entra se avise en vez de pisar a alguien.
 */
import { construirMes, derivarHeader, ocupacionHeader, accionesDe } from './derivar'
import { REGLAS_HEADER, type Mes, type Pieza } from './tipos'

let fallos = 0
function ok(nombre: string, cond: boolean, detalle = '') {
  if (cond) { console.log(`  ok    ${nombre}`) }
  else { fallos++; console.log(`  FALLA ${nombre}${detalle ? ' — ' + detalle : ''}`) }
}
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  const a = JSON.stringify(obtenido), b = JSON.stringify(esperado)
  ok(nombre, a === b, `obtenido ${a}, esperado ${b}`)
}

const headerPieza = (extra: Partial<Pieza> = {}): Pieza =>
  ({ id: 'pz-' + Math.random(), area: 'web-home', formato: 'Header', estado: 'pendiente', ...extra })

/** Le pega una pieza Header a la acción número n del calendario comercial. */
function conHeaderEnAccion(mes: Mes, indice: number, extra: Partial<Pieza> = {}): Mes {
  let visto = -1
  const comercial = mes.comercial.map(banda => ({
    ...banda,
    filas: banda.filas.map(fila => fila.map(b => {
      visto++
      return visto === indice ? { ...b, piezas: [headerPieza(extra)] } : b
    })),
  }))
  return derivarHeader({ ...mes, comercial })
}

console.log('\nsetiembre 2026 — datos reales del Excel')
const sep = construirMes('2026-09')

ok('hay 10 posiciones de header', sep.header.length === REGLAS_HEADER.tope)
igual('Retail Media arranca en 4, 5 y 6', sep.posicionesRM, [4, 5, 6])

const enRM = [4, 5, 6].map(n => sep.header[n - 1].filas[0].length)
igual('las tres posiciones de RM se llenaron', enRM, [4, 5, 4])
ok('todo lo de RM viene marcado como derivado',
  [4, 5, 6].every(n => sep.header[n - 1].filas[0].every(b => b.origen?.tipo === 'retail')))
ok('las posiciones de marketing arrancan vacías',
  [1, 2, 3, 7, 8, 9, 10].every(n => sep.header[n - 1].filas[0].length === 0))

const oc = ocupacionHeader(sep)
igual('día 1 tiene 2 banners (MILKA + Dove)', oc[0].cantidad, 2)
igual('día 9 tiene 1 (solo SCJ Glade)', oc[8].cantidad, 1)
igual('pico del mes', Math.max(...oc.map(o => o.cantidad)), 3)
ok('ningún día se pasa del ideal todavía', oc.every(o => o.estado === 'ok'))

console.log('\nuna acción que pide header')
const conUna = conHeaderEnAccion(sep, 0)
const accion0 = accionesDe(sep)[0]
const ubicada = conUna.header.findIndex(p =>
  p.filas[0].some(b => b.origen?.tipo === 'accion' && b.origen.accionId === accion0.id))
igual('cae en la posición 1, la primera libre de marketing', ubicada + 1, 1)
igual('no quedó nada sin lugar', conUna.sinLugar.length, 0)
const bajada = conUna.header[0].filas[0][0]
igual('respeta las fechas de la acción', [bajada.desde, bajada.hasta], [accion0.desde, accion0.hasta])
igual('el conteo del día 1 subió a 3', ocupacionHeader(conUna)[0].cantidad, 3)

console.log('\nvigencia propia de la pieza, más corta que la acción')
const corta = conHeaderEnAccion(sep, 0, { desde: 3, hasta: 5 })
const bCorta = corta.header[0].filas[0][0]
igual('el banner usa la vigencia de la pieza, no la de la acción', [bCorta.desde, bCorta.hasta], [3, 5])

console.log('\nmover las posiciones de Retail Media')
const movido = derivarHeader({ ...sep, posicionesRM: [1, 2, 3] })
igual('RM se fue a 1, 2 y 3', [1, 2, 3].map(n => movido.header[n - 1].filas[0].length), [4, 5, 4])
ok('las viejas quedaron vacías', [4, 5, 6].every(n => movido.header[n - 1].filas[0].length === 0))
igual('el conteo total no cambió', ocupacionHeader(movido).map(o => o.cantidad), oc.map(o => o.cantidad))

console.log('\nheader lleno: tiene que avisar, no pisar')
// 7 acciones de marketing pidiendo header el mismo día + las 3 de RM = 10
let lleno: Mes = sep
for (let i = 0; i < 8; i++) lleno = conHeaderEnAccion(lleno, i, { desde: 5, hasta: 5 })
// conHeaderEnAccion reemplaza piezas una por una, así que se acumulan
const ocupadasDia5 = ocupacionHeader(lleno)[4].cantidad
ok('no se superó nunca el tope de 10', ocupacionHeader(lleno).every(o => o.cantidad <= REGLAS_HEADER.tope),
  `día 5 quedó en ${ocupadasDia5}`)
ok('lo que no entró quedó avisado', lleno.sinLugar.length > 0,
  `sinLugar=${lleno.sinLugar.length}, día 5 = ${ocupadasDia5} banners`)
ok('ninguna posición tiene dos banners pisados el mismo día',
  lleno.header.every(pos => {
    for (let d = 1; d <= lleno.dias; d++) {
      if (pos.filas[0].filter(b => b.desde <= d && d <= b.hasta).length > 1) return false
    }
    return true
  }))

console.log('\nlo cargado a mano no se pierde al re-derivar')
const conManual: Mes = {
  ...sep,
  header: sep.header.map((p, i) => i !== 6 ? p : {
    ...p,
    filas: [[{ id: 'manual-1', nombre: 'Cargado a mano', desde: 2, hasta: 4, color: '#FFF2CC', origen: { tipo: 'manual' as const } }]],
  }),
}
const reDerivado = derivarHeader(conManual)
igual('la barra manual sobrevive', reDerivado.header[6].filas[0].map(b => b.nombre), ['Cargado a mano'])

console.log(`\n${fallos === 0 ? 'TODO OK' : fallos + ' FALLAS'}\n`)
process.exit(fallos === 0 ? 0 : 1)

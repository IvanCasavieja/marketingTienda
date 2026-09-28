/**
 * Pruebas de cómo se arma un mes y de la derivación del header. Se corren sin
 * levantar nada:
 *
 *     npm run test:calendario
 *
 * Verifican lo que no se puede mirar a ojo: que Retail Media caiga en sus
 * posiciones, que una acción con pieza Header baje sola a una posición libre
 * de marketing, que lo que no entra se avise en vez de pisar a alguien, y
 * (desde el 28/09/2026) que una acción que cruza de mes sea UNA sola: la misma
 * en los dos meses, a la misma altura y en la misma posición del header.
 */
import { SEED } from './seed'
import { BANDAS_COMERCIAL, BANDAS_RETAIL, unirBandas } from './catalogo'
import {
  accionesDe, carrilLibre, construirMes, derivarHeaders, ocupacionHeader, vistaDelMes,
} from './derivar'
import { diasDelMes, isoDe } from './fechas'
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

/** Las barras de ejemplo de los Excel, como las dejó en la base la migración 0057. */
function barrasDeSeed(): BarraGuardada[] {
  const out: BarraGuardada[] = []
  let n = 0
  for (const clave of Object.keys(SEED).sort()) {
    for (const seccion of ['comercial', 'retail'] as const) {
      for (const banda of SEED[clave][seccion]) {
        banda.filas.forEach((fila, carril) => fila.forEach(x => out.push({
          id: `br-${++n}`, seccion, banda: banda.nombre, carril, nombre: x.nombre, color: x.color,
          desde: isoDe(clave, x.desde), hasta: isoDe(clave, Math.min(x.hasta, diasDelMes(clave))),
          ...(seccion === 'comercial' ? { piezas: [], avisos: [] } : {}),
        })))
      }
    }
  }
  return out
}

const headerPieza = (extra: Partial<Pieza> = {}): Pieza =>
  ({ id: 'pz-' + Math.random(), area: 'web-home', formato: 'Header', estado: 'pendiente', ...extra })

const accion = (extra: Partial<BarraGuardada> = {}): BarraGuardada => ({
  id: 'ac-' + Math.random().toString(36).slice(2), seccion: 'comercial', banda: 'MEGA EVENTO', carril: 0,
  nombre: 'Acción', color: '#CFE2F3', desde: '2026-09-10', hasta: '2026-09-20', piezas: [], avisos: [], ...extra,
})

/** Le pega una pieza Header a la acción número n (de setiembre) del seed. */
function conHeaderEnAccion(barras: BarraGuardada[], indice: number, extra: Partial<Pieza> = {}): BarraGuardada[] {
  const comerciales = barras.filter(b => b.seccion === 'comercial' && b.desde.startsWith('2026-09'))
  const blanco = comerciales[indice]
  return barras.map(b => (b === blanco ? { ...b, piezas: [...(b.piezas ?? []), headerPieza(extra)] } : b))
}

const posicionDe = (mes: Mes, accionId: string) =>
  mes.header.findIndex(p => p.filas[0].some(b => b.origen?.tipo === 'accion' && b.origen.accionId === accionId)) + 1

console.log('\nsetiembre 2026 — datos reales del Excel')
const seed = barrasDeSeed()
const sep = construirMes('2026-09', seed)

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
const conUna = conHeaderEnAccion(seed, 0)
const mesUna = construirMes('2026-09', conUna)
const accion0 = accionesDe(sep)[0]
igual('cae en la posición 1, la primera libre de marketing', posicionDe(mesUna, accion0.id), 1)
igual('no quedó nada sin lugar', mesUna.sinLugar.length, 0)
const bajada = mesUna.header[0].filas[0][0]
igual('respeta las fechas de la acción', [bajada.desde, bajada.hasta], [accion0.desde, accion0.hasta])
igual('el conteo del día 1 subió a 3', ocupacionHeader(mesUna)[0].cantidad, 3)

console.log('\nvigencia propia de la pieza, más corta que la acción')
const corta = construirMes('2026-09', conHeaderEnAccion(seed, 0, { desde: '2026-09-03', hasta: '2026-09-05' }))
const bCorta = corta.header[0].filas[0][0]
igual('el banner usa la vigencia de la pieza, no la de la acción', [bCorta.desde, bCorta.hasta], [3, 5])

console.log('\nmover las posiciones de Retail Media')
const movido = construirMes('2026-09', seed, { '2026-09': [1, 2, 3] })
igual('RM se fue a 1, 2 y 3', [1, 2, 3].map(n => movido.header[n - 1].filas[0].length), [4, 5, 4])
ok('las viejas quedaron vacías', [4, 5, 6].every(n => movido.header[n - 1].filas[0].length === 0))
igual('el conteo total no cambió', ocupacionHeader(movido).map(o => o.cantidad), oc.map(o => o.cantidad))
igual('mover las de setiembre no toca octubre', construirMes('2026-10', seed, { '2026-09': [1, 2, 3] }).posicionesRM, [4, 5, 6])

console.log('\nheader lleno: tiene que avisar, no pisar')
// 8 acciones de marketing pidiendo header el mismo día + las 3 de RM
let lleno = seed
for (let i = 0; i < 8; i++) lleno = conHeaderEnAccion(lleno, i, { desde: '2026-09-05', hasta: '2026-09-05' })
const mesLleno = construirMes('2026-09', lleno)
const ocupadasDia5 = ocupacionHeader(mesLleno)[4].cantidad
ok('no se superó nunca el tope de 10', ocupacionHeader(mesLleno).every(o => o.cantidad <= REGLAS_HEADER.tope),
  `día 5 quedó en ${ocupadasDia5}`)
ok('lo que no entró quedó avisado', mesLleno.sinLugar.length > 0,
  `sinLugar=${mesLleno.sinLugar.length}, día 5 = ${ocupadasDia5} banners`)
ok('ninguna posición tiene dos banners pisados el mismo día',
  mesLleno.header.every(pos => {
    for (let d = 1; d <= mesLleno.dias; d++) {
      if (pos.filas[0].filter(b => b.desde <= d && d <= b.hasta).length > 1) return false
    }
    return true
  }))

console.log('\nlo cargado a mano en el header')
const manual: BarraGuardada = {
  id: 'manual-1', seccion: 'header', banda: 'pos-7', carril: 0, nombre: 'Cargado a mano',
  color: '#FFF2CC', desde: '2026-09-02', hasta: '2026-09-04',
}
const conManual = construirMes('2026-09', [...seed, manual])
igual('queda en su posición', conManual.header[6].filas[0].map(b => b.nombre), ['Cargado a mano'])
igual('marcado como manual', conManual.header[6].filas[0][0].origen, { tipo: 'manual' })

// ---------------------------------------------------------------------------
console.log('\nuna acción que cruza de mes es UNA sola')
const cruza = accion({ id: 'ac-cruza', nombre: 'Electro Sale', desde: '2026-09-25', hasta: '2026-10-05', carril: 2 })
const sepC = construirMes('2026-09', [cruza])
const octC = construirMes('2026-10', [cruza])
const enSep = accionesDe(sepC).find(b => b.id === 'ac-cruza')
const enOct = accionesDe(octC).find(b => b.id === 'ac-cruza')
ok('aparece en setiembre', !!enSep)
ok('y en octubre', !!enOct)
igual('en setiembre va del 25 al 30', [enSep?.desde, enSep?.hasta], [25, 30])
igual('en octubre va del 1 al 5', [enOct?.desde, enOct?.hasta], [1, 5])
ok('en setiembre avisa que sigue', enSep?.sigueDespues === true && enSep?.vieneDeAntes === false)
ok('en octubre avisa que viene de antes', enOct?.vieneDeAntes === true && enOct?.sigueDespues === false)
igual('las fechas reales son las mismas en los dos', [enSep?.inicio, enSep?.fin, enOct?.inicio, enOct?.fin],
  ['2026-09-25', '2026-10-05', '2026-09-25', '2026-10-05'])
const renglon = (m: Mes) => m.comercial.find(b => b.id === 'MEGA EVENTO')!.filas.findIndex(f => f.some(b => b.id === 'ac-cruza'))
igual('va a la misma altura en los dos meses', [renglon(sepC), renglon(octC)], [2, 2])
ok('no aparece en noviembre', !accionesDe(construirMes('2026-11', [cruza])).some(b => b.id === 'ac-cruza'))

console.log('\nel header de una acción que cruza de mes')
const cruzaConHeader = { ...cruza, piezas: [headerPieza()] }
// RM en 4-5-6 en setiembre y en 1-2-3 en octubre: la acción necesita una
// posición que no sea de RM en NINGUNO de los dos meses.
const posRM = { '2026-10': [1, 2, 3] }
const sepH = construirMes('2026-09', [cruzaConHeader], posRM)
const octH = construirMes('2026-10', [cruzaConHeader], posRM)
igual('queda en la misma posición en los dos meses', [posicionDe(sepH, 'ac-cruza'), posicionDe(octH, 'ac-cruza')], [7, 7])

const rmCruza: BarraGuardada = {
  id: 'rm-cruza', seccion: 'retail', banda: REGLAS_HEADER.formatoHeader, carril: 0, nombre: 'Conaprole',
  color: '#93C47D', desde: '2026-09-28', hasta: '2026-10-02',
}
const rmSep = construirMes('2026-09', [rmCruza], posRM).header.findIndex(p => p.filas[0].length > 0) + 1
const rmOct = construirMes('2026-10', [rmCruza], posRM).header.findIndex(p => p.filas[0].length > 0) + 1
igual('una campaña de RM que cruza sigue a RM cuando RM cambia de posición', [rmSep, rmOct], [4, 1])

const sinLugar = derivarHeaders(
  [
    ...Array.from({ length: 7 }, (_, i) => accion({ id: `ll-${i}`, nombre: `Lleno ${i}`, desde: '2026-09-29', hasta: '2026-10-02', piezas: [headerPieza()] })),
    ...[0, 1, 2].map(c => ({ ...rmCruza, id: `rm-${c}`, carril: c })),
    accion({ id: 'ac-tarde', nombre: 'Llega tarde', desde: '2026-09-30', hasta: '2026-10-01', piezas: [headerPieza()] }),
  ],
  {},
).sinLugar
igual('lo que no entra se avisa con sus fechas reales', sinLugar.map(s => [s.accionId, s.inicio, s.fin]),
  [['ac-tarde', '2026-09-30', '2026-10-01']])
igual('y con los días en que estaba lleno, de los dos meses', sinLugar[0]?.diasLlenos, ['2026-09-30', '2026-10-01'])

// ---------------------------------------------------------------------------
console.log('\nlas bandas son las mismas todos los meses')
const nov = construirMes('2026-11', [])
igual('noviembre, que no está en el Excel, tiene todos los tipos de acción', nov.comercial.map(b => b.nombre), BANDAS_COMERCIAL.map(b => b.nombre))
igual('y todos los formatos de Retail Media', nov.retail.map(b => b.nombre), BANDAS_RETAIL.map(b => b.nombre))
ok('cada banda arranca con un renglón para hacer clic', nov.comercial.every(b => b.filas.length === 1))
const iGral = BANDAS_COMERCIAL.findIndex(b => b.nombre === 'Mailing GRAL')
igual('"Especiales" (solo en octubre) entra después de "Mailing GRAL"', BANDAS_COMERCIAL[iGral + 1]?.nombre, 'Especiales')
ok('"TIENDA FARMA" (solo en setiembre) también está', BANDAS_COMERCIAL.some(b => b.nombre === 'TIENDA FARMA'))
igual('unir no repite y respeta el orden',
  unirBandas([[{ nombre: 'A', filas: [] }, { nombre: 'C', filas: [] }], [{ nombre: 'A', filas: [] }, { nombre: 'B', filas: [] }, { nombre: 'C', filas: [] }]]).map(b => b.nombre),
  ['A', 'B', 'C'])
const rara = accion({ id: 'ac-rara', banda: 'Una banda nueva' })
ok('una barra de una banda que no está en el catálogo igual se ve',
  construirMes('2026-09', [rara]).comercial.some(b => b.nombre === 'Una banda nueva' && b.filas[0].length === 1))

console.log('\nrenglones')
const ocupa = accion({ id: 'ac-ocupa', carril: 0, desde: '2026-10-01', hasta: '2026-10-10' })
igual('si el renglón está libre en todo el rango, va ahí',
  carrilLibre([ocupa], 'comercial', 'MEGA EVENTO', '2026-09-20', '2026-09-28', 0), 0)
igual('si está ocupado en el mes siguiente, va a otro',
  carrilLibre([ocupa], 'comercial', 'MEGA EVENTO', '2026-09-25', '2026-10-03', 0), 1)
igual('una barra no choca consigo misma al cambiarle la fecha',
  carrilLibre([ocupa], 'comercial', 'MEGA EVENTO', '2026-10-01', '2026-10-15', 0, 'ac-ocupa'), 0)
const pisadas = construirMes('2026-09', [
  accion({ id: 'ac-a', carril: 0, desde: '2026-09-10', hasta: '2026-09-15' }),
  accion({ id: 'ac-b', carril: 0, desde: '2026-09-12', hasta: '2026-09-18' }),
]).comercial.find(b => b.id === 'MEGA EVENTO')!
igual('dos creadas a la vez en el mismo renglón no se dibujan una encima de la otra',
  pisadas.filas.map(f => f.map(b => b.id)), [['ac-a'], ['ac-b']])

console.log('\nla vista del mes se reusa')
const registro = { a: accion({ id: 'a' }) }
const pos = {}
ok('mismas barras, mismo objeto', vistaDelMes('2026-09', registro, pos) === vistaDelMes('2026-09', registro, pos))
ok('barras nuevas, mes nuevo', vistaDelMes('2026-09', registro, pos) !== vistaDelMes('2026-09', { ...registro }, pos))

console.log(`\n${fallos === 0 ? 'TODO OK' : fallos + ' FALLAS'}\n`)
process.exit(fallos === 0 ? 0 : 1)

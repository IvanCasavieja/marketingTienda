// Pruebas del resumen de Clientes VIP: npm run test:clientes-vip
import assert from 'node:assert/strict'
import { ArchivoInvalido, mesDe, numero, problemaDelMes, Resumidor } from './resumen'

const CAB = '﻿id_cliente;id_ticket;fecha;sucursal;canal;SKU;producto;categoria;subcategoria;marca;marca_propia;unidades;venta_neta_sin_IVA;margen_neto_sin_IVA\r\n'
const fila = (c: number, t: number, fecha: string, suc: string, canal: string, cat: string, mp: string, u: string, v: string, m: string) =>
  `${c};${t};${fecha};${suc};${canal};123;Algo;${cat};Sub;MARCA;${mp};${u};${v};${m}\r\n`

let pasaron = 0
function prueba(nombre: string, fn: () => void) {
  fn()
  pasaron++
  console.log('  ✓', nombre)
}

prueba('lee números con punto o coma y fechas de dos formas', () => {
  assert.equal(numero('107.38'), 107.38)
  assert.equal(numero('107,38'), 107.38)
  assert.equal(numero(''), 0)
  assert.equal(numero('x'), 0)
  assert.equal(mesDe('2026-03-14'), '2026-03')
  assert.equal(mesDe('14/3/2026'), '2026-03')
  assert.equal(mesDe('mañana'), null)
})

prueba('resume por cliente y mes, cuenta tickets y días, y arma los totales', () => {
  const r = new Resumidor()
  const texto =
    CAB +
    fila(179, 1, '2026-01-01', 'Carrasco', 'Tienda Inglesa', 'Almacén', 'Si', '1.0', '100.50', '25') +
    fila(179, 1, '2026-01-01', 'Carrasco', 'Tienda Inglesa', 'Bebidas', 'No', '2', '50', '10') +
    fila(179, 2, '2026-01-15', 'Punta Carretas', 'E-commerce', 'Almacén', '', '1', '300', '60') +
    fila(180, 3, '2026-01-20', 'Carrasco', 'Smart', 'Lácteos', 'No', '1', '40', '8') +
    fila(179, 4, '2026-02-02', 'Carrasco', 'Tienda Inglesa', 'Almacén', 'Si', '1', '80', '20') +
    'basura;sin;fecha\r\n'
  // Partido en pedazos raros, como llega del disco
  for (let i = 0; i < texto.length; i += 7) r.agregarTexto(texto.slice(i, i + 7))
  const res = r.terminar()
  assert.equal(res.filasArchivo, 6)
  assert.equal(res.descartadas, 1)
  assert.deepEqual(res.primerasDescartadas, [{ fila: 7, archivo: '', motivo: 'sinCliente', dato: 'basura' }])
  assert.deepEqual(res.meses, ['2026-01', '2026-02'])
  assert.equal(res.clientes, 2)
  assert.equal(res.venta, 571)

  const ene179 = res.filas.find(f => f[0] === 179 && f[1] === '2026-01')!
  // [cliente, mes, venta, margen, unidades, tickets, dias, ecommerce, smart, marca propia, sucursal, categorias]
  assert.deepEqual(ene179, [179, '2026-01', 451, 95, 4, 2, 2, 300, 0, 101, 'Punta Carretas', 'Almacén=401;Bebidas=50'])
  const ene180 = res.filas.find(f => f[0] === 180)!
  assert.equal(ene180[8], 40) // Smart

  const dim = (d: string, v: string, m = '2026-01') => res.dimensiones.find(x => x.mes === m && x.dimension === d && x.valor === v)!
  assert.deepEqual(
    { venta: dim('categoria', 'Almacén').venta, tickets: dim('categoria', 'Almacén').tickets, clientes: dim('categoria', 'Almacén').clientes },
    { venta: 401, tickets: 2, clientes: 1 },
  )
  assert.equal(dim('sucursal', 'Carrasco').clientes, 2)
  assert.equal(dim('sucursal', 'Carrasco').tickets, 2)
  assert.equal(dim('canal', 'E-commerce').venta, 300)
  assert.equal(dim('marca_propia', 'Marca propia').venta, 101)
  assert.equal(dim('marca_propia', 'Sin dato').venta, 300)
})

prueba('dos CSV en el mismo zip: cada uno con su cabecera', () => {
  const r = new Resumidor()
  r.agregarTexto(CAB + fila(1, 1, '2025-12-31', 'A', 'Tienda Inglesa', 'X', 'No', '1', '10', '1'))
  r.nuevoArchivo()
  r.agregarTexto(CAB + fila(1, 2, '2026-01-01', 'A', 'Tienda Inglesa', 'X', 'No', '1', '20', '2'))
  const res = r.terminar()
  assert.deepEqual(res.meses, ['2025-12', '2026-01'])
  assert.equal(res.filasArchivo, 2)
})

// H-088 (26/11/2026): una fila con «30/13/2019» mostraba «enero 2019 a undefined 2019» y el servidor
// rebotaba el archivo entero («Mes inválido: '2019-13'») sin decir qué fila corregir.
const HOY = new Date(2026, 10, 26) // 26/11/2026

prueba('un mes que no existe, que todavía no llegó o de antes del 2000 no se carga (el servidor lo rechaza)', () => {
  assert.equal(problemaDelMes('2019-13', '2026-11'), 'mesInexistente')
  assert.equal(problemaDelMes('2026-00', '2026-11'), 'mesInexistente')
  assert.equal(problemaDelMes('2026-12', '2026-11'), 'fechaFutura')
  assert.equal(problemaDelMes('2062-01', '2026-11'), 'fechaFutura')
  assert.equal(problemaDelMes('1999-12', '2026-11'), 'fechaVieja')
  assert.equal(problemaDelMes('2026-11', '2026-11'), null) // el mes en curso sí
  assert.equal(problemaDelMes('2019-01', '2026-11'), null)
})

prueba('una fecha imposible no frena el archivo: dice en qué fila está y qué tiene', () => {
  const r = new Resumidor(HOY)
  r.agregarTexto(
    CAB + // fila 1
    fila(900001, 1, '15/01/2019', 'A', 'Tienda Inglesa', 'X', 'No', '1', '100', '10') +
    fila(900002, 2, '30/13/2019', 'A', 'Tienda Inglesa', 'X', 'No', '1', '50', '5') + // fila 3
    fila(900003, 3, '02/02/2062', 'A', 'Tienda Inglesa', 'X', 'No', '1', '70', '7') +
    fila(900001, 4, '2026-11-20', 'A', 'Tienda Inglesa', 'X', 'No', '1', '30', '3'),
  )
  const res = r.terminar()
  assert.deepEqual(res.meses, ['2019-01', '2026-11'])
  assert.equal(res.venta, 130)
  assert.equal(res.descartadas, 2)
  assert.deepEqual(res.primerasDescartadas, [
    { fila: 3, archivo: '', motivo: 'mesInexistente', dato: '30/13/2019' },
    { fila: 4, archivo: '', motivo: 'fechaFutura', dato: '02/02/2062' },
  ])
})

prueba('la fila es la de Excel (cuenta la cabecera y las líneas vacías) y, en un zip, dice de qué archivo', () => {
  const r = new Resumidor(HOY)
  r.nuevoArchivo('enero.csv')
  r.agregarTexto(CAB + '\r\n' + fila(1, 1, 'mañana', 'A', 'Tienda Inglesa', 'X', 'No', '1', '10', '1') +
                 fila(1, 2, '2026-01-03', 'A', 'Tienda Inglesa', 'X', 'No', '1', '10', '1'))
  r.nuevoArchivo('febrero.csv')
  // La última línea sin salto al final también cuenta, y con el nombre de su archivo.
  r.agregarTexto(CAB + fila(1, 3, '2026-02-03', 'A', 'Tienda Inglesa', 'X', 'No', '1', '10', '1') +
                 fila(1, 4, '', 'A', 'Tienda Inglesa', 'X', 'No', '1', '10', '1').trimEnd())
  r.nuevoArchivo('marzo.csv')
  r.agregarTexto(CAB + `;5;2026-03-01;A;Tienda Inglesa;123;Algo;X;Sub;MARCA;No;1;10;1\n` +
                 fila(1, 6, '01/01/1900', 'A', 'Tienda Inglesa', 'X', 'No', '1', '10', '1'))
  const res = r.terminar()
  assert.deepEqual(res.meses, ['2026-01', '2026-02'])
  assert.deepEqual(res.primerasDescartadas, [
    { fila: 3, archivo: 'enero.csv', motivo: 'fechaIlegible', dato: 'mañana' },
    { fila: 3, archivo: 'febrero.csv', motivo: 'sinFecha', dato: '' },
    { fila: 2, archivo: 'marzo.csv', motivo: 'sinCliente', dato: '' },
    { fila: 3, archivo: 'marzo.csv', motivo: 'fechaVieja', dato: '01/01/1900' },
  ])
})

prueba('de las filas que no entran muestra las primeras 5 y cuenta todas; si no entra ninguna, no hay meses', () => {
  const r = new Resumidor(HOY)
  let texto = CAB
  for (let k = 0; k < 8; k++) texto += fila(1, k, `01/13/2026`, 'A', 'Tienda Inglesa', 'X', 'No', '1', '10', '1')
  r.agregarTexto(texto)
  const res = r.terminar()
  assert.equal(res.descartadas, 8)
  assert.deepEqual(res.primerasDescartadas.map(d => d.fila), [2, 3, 4, 5, 6])
  assert.deepEqual(res.meses, [])
  assert.equal(res.filas.length, 0)
})

prueba('un archivo sin las columnas dice cuáles faltan', () => {
  const r = new Resumidor()
  assert.throws(() => r.agregarTexto('a;b;c\nd;e;f\n'), (e: unknown) => e instanceof ArchivoInvalido && /id_cliente/.test((e as Error).message))
  assert.throws(() => new Resumidor().terminar(), ArchivoInvalido)
})

prueba('arma el detalle para Valentina: categoría por mes, subcategoría con sus meses, productos', () => {
  const r = new Resumidor()
  r.agregarTexto(
    CAB +
    fila(179, 1, '2026-01-01', 'Carrasco', 'Tienda Inglesa', 'Almacén', 'Si', '1', '100', '25') +
    fila(179, 1, '2026-01-01', 'Carrasco', 'Tienda Inglesa', 'Almacén', 'Si', '2', '50', '10') +
    fila(179, 2, '2026-01-15', 'Carrasco', 'Tienda Inglesa', 'Bebidas', 'No', '1', '30', '5') +
    fila(179, 3, '2026-03-02', 'Carrasco', 'Tienda Inglesa', 'Almacén', 'Si', '1', '40', '9'),
  )
  r.terminar()
  const cat = [...r.lineasDeDetalle('cliente_mes_categoria')]
  assert.equal(cat[0], 'id_cliente;mes;categoria;venta;unidades;tickets')
  // Almacén en enero: dos líneas del mismo ticket = un ticket
  assert.ok(cat.includes('179;2026-01;Almacén;150;3;1'), cat.join(' | '))
  assert.ok(cat.includes('179;2026-01;Bebidas;30;1;1'))
  assert.ok(cat.includes('179;2026-03;Almacén;40;1;1'))
  const sub = [...r.lineasDeDetalle('cliente_subcategoria')]
  assert.equal(sub[0], 'id_cliente;categoria;subcategoria;meses;venta;unidades')
  assert.ok(sub.includes('179;Almacén;Sub;2026-01|2026-03;190;4'), sub.join(' | '))
  const prod = [...r.lineasDeDetalle('producto_mes')]
  assert.ok(prod.includes('123;2026-01;180;4;2'), prod.join(' | '))
  const catalogo = [...r.lineasDeDetalle('productos')]
  assert.equal(catalogo[1], '123;Algo;Almacén;Sub;MARCA;Marca propia')
  assert.equal(r.tieneDetalle('productos'), true)
})

prueba('sin las columnas opcionales, no hay detalle de subcategoría ni de productos (y no se rompe)', () => {
  const r = new Resumidor()
  r.agregarTexto('id_cliente;id_ticket;fecha;sucursal;canal;categoria;marca_propia;unidades;venta_neta_sin_IVA;margen_neto_sin_IVA\n' +
                 '1;1;2026-01-01;A;Tienda Inglesa;X;No;1;10;1\n')
  r.terminar()
  assert.equal(r.tieneDetalle('cliente_subcategoria'), false)
  assert.equal(r.tieneDetalle('productos'), false)
  assert.equal([...r.lineasDeDetalle('cliente_mes_categoria')].length, 2)
})

console.log(`resumen de Clientes VIP: ${pasaron} pruebas en verde`)

/**
 * Los archivos del pedido de una tarea (lib/calendario/adjuntos.ts).
 *
 *     npm run test:adjuntos
 */
import {
  ACEPTA_ADJUNTOS, MAX_ADJUNTOS, MAX_BYTES_ADJUNTO, claseDeArchivo, cuantosArchivos, problemaConArchivo, sumarArchivos,
} from './adjuntos'

let fallos = 0
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  const ok = JSON.stringify(obtenido) === JSON.stringify(esperado)
  if (ok) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre} — obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`) }
}

const a = (name: string, size = 1000) => ({ name, size })

console.log('Qué es cada uno')
igual('Excel', claseDeArchivo('Listado ciberlunes.XLSX'), 'excel')
igual('Excel viejo', claseDeArchivo('viejo.xls'), 'excel')
igual('Word', claseDeArchivo('textos.docx'), 'word')
igual('imagen', claseDeArchivo('foto.JPEG'), 'imagen')
igual('sin extensión', claseDeArchivo('LEEME'), 'otro')
igual('el selector ofrece los mismos tipos que acepta el servidor', ACEPTA_ADJUNTOS,
  '.xlsx,.xls,.csv,.pdf,.docx,.doc,.jpg,.jpeg,.png,.webp,.gif,.zip')

console.log('Lo que no se puede')
igual('un Excel liviano pasa', problemaConArchivo('listado.xlsx', 140_000), null)
igual('justo el tope pasa', problemaConArchivo('ref.pdf', MAX_BYTES_ADJUNTO), null)
igual('un programa no', problemaConArchivo('programa.exe', 10)?.includes('no se puede adjuntar'), true)
igual('más pesado que el tope no, y dice qué hacer', problemaConArchivo('ref.pdf', MAX_BYTES_ADJUNTO + 1)?.includes('link en el detalle'), true)
igual('vacío no', problemaConArchivo('vacio.csv', 0)?.includes('vacío'), true)

console.log('Sumar archivos')
let r = sumarArchivos([a('uno.xlsx')], [a('dos.pdf'), a('programa.exe'), a('uno.xlsx')])
igual('suma los nuevos, saca los que no se pueden y no repite', r.lista.map(x => x.name), ['uno.xlsx', 'dos.pdf'])
igual('dice por qué quedó afuera', r.avisos.length, 1)
r = sumarArchivos([], Array.from({ length: MAX_ADJUNTOS + 2 }, (_, i) => a(`lista ${i}.csv`)))
igual('hasta el tope por tarea', r.lista.length, MAX_ADJUNTOS)
igual('y avisa cuántos quedaron afuera', r.avisos, [`Hasta ${MAX_ADJUNTOS} archivos por tarea: 2 quedaron afuera.`])
r = sumarArchivos([], [a('a.csv'), a('b.csv')], MAX_ADJUNTOS - 1)
igual('cuenta los que la tarea ya tiene', r.lista.map(x => x.name), ['a.csv'])
igual('uno afuera', r.avisos, [`Hasta ${MAX_ADJUNTOS} archivos por tarea: uno quedó afuera.`])
igual('mismo nombre con otro peso es otro archivo', sumarArchivos([a('x.csv', 1)], [a('x.csv', 2)]).lista.length, 2)
igual('1 archivo', cuantosArchivos(1), '1 archivo')
igual('3 archivos', cuantosArchivos(3), '3 archivos')

if (fallos) {
  console.log(`\n${fallos} prueba(s) fallaron`)
  process.exit(1)
}
console.log('\nTodo bien')

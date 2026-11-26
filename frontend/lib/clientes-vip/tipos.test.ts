// Pruebas de cómo se muestran los números en Clientes VIP: npm run test:clientes-vip
import assert from 'node:assert/strict'
import { ejeDePlata } from './tipos'

let pasaron = 0
function prueba(nombre: string, fn: () => void) {
  fn()
  pasaron++
  console.log('  ✓', nombre)
}

// Las rayas que arma recharts para cada caso (0 y cuatro pasos redondos hasta pasar el más alto).
const rayas = (paso: number) => [0, 1, 2, 3, 4].map(k => k * paso)

// H-087 (26/11/2026): con ventas de miles, las cinco rayas del eje decían «0 M».
prueba('con ventas de miles el eje va en pesos, no «0 M»', () => {
  const eje = ejeDePlata(11_600)
  assert.deepEqual(rayas(3_000).map(eje), ['0', '3.000', '6.000', '9.000', '12.000'])
})

prueba('con ventas de millones sigue en millones', () => {
  const eje = ejeDePlata(280_400_000)
  assert.deepEqual(rayas(70_000_000).map(eje), ['0 M', '70 M', '140 M', '210 M', '280 M'])
})

prueba('entre 1 y 10 millones las rayas no se repiten (antes decían 1 M dos veces)', () => {
  const eje = ejeDePlata(2_500_000)
  assert.deepEqual(rayas(650_000).map(eje), ['0 M', '0,65 M', '1,3 M', '1,95 M', '2,6 M'])
})

prueba('todas las rayas en la misma unidad, aunque la de arriba llegue al millón', () => {
  const eje = ejeDePlata(980_000)
  assert.deepEqual(rayas(250_000).map(eje), ['0', '250.000', '500.000', '750.000', '1.000.000'])
})

console.log(`formatos de Clientes VIP: ${pasaron} pruebas en verde`)

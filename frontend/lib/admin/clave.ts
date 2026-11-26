// Una contraseña aleatoria para el alta de usuarios (Ivan, 25/11/2026: «un
// botón de generar aleatoriamente la contraseña… para no siempre estar
// poniendo hola 1234»). Con el generador criptográfico del navegador, sin
// letras que se confunden (0/O, 1/l/I), y dentro del largo que acepta el
// servidor (6 a 20, backend/app/schemas/auth.py).

const LETRAS = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
const SIMBOLOS = '-_.!*#'

export function claveAleatoria(largo = 16, azar: (n: number) => Uint32Array = n => crypto.getRandomValues(new Uint32Array(n))): string {
  const n = Math.min(20, Math.max(8, largo))
  const numeros = azar(n)
  const chars = Array.from(numeros, x => LETRAS[x % LETRAS.length])
  // Un símbolo en un lugar al azar, para que no sea solo letras y números.
  const [d, e] = Array.from(azar(2))
  chars[d % n] = SIMBOLOS[e % SIMBOLOS.length]
  return chars.join('')
}

/**
 * Las piezas del pedido que faltan en una entrega (lib/calendario/piezas.ts).
 *
 *     npm run test:calendario
 */
import {
  PIEZAS_A_LA_VISTA, TOLERANCIA_EXACTA, cubre, esExacta, faltanEnLaEntrega, loQueFaltaba, medidaDePieza, medidasDeImagen,
  piezasQueFaltan, primeras, textoDePieza, tituloDeLasPiezas, type Medidas, type Pieza,
} from './piezas'
import { jpegArmado, pngArmado, webpArmado } from './imagenes-de-prueba'

let fallos = 0
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  const ok = JSON.stringify(obtenido) === JSON.stringify(esperado)
  if (ok) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre} — obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`) }
}

// Como las manda el servidor (piezas_del_pedido en tipos_de_tarea.py).
const px = (nombre: string, ancho: number, alto: number): Pieza => ({ nombre, ancho, alto, proporcion: false })
const prop = (nombre: string, ancho: number, alto: number): Pieza => ({ nombre, ancho, alto, proporcion: true })
const im = (ancho: number, alto: number): Medidas => ({ ancho, alto })
const nombres = (piezas: Pieza[]) => piezas.map(p => p.nombre)

const headerWeb = px('Header (web)', 1920, 416)
const headerMobile = px('Header (mobile)', 640, 260)
const checkout = px('Checkout', 412, 157)
const banners = [headerWeb, headerMobile, checkout]

console.log('Cómo se nombran')
igual('con su medida', banners.map(textoDePieza), ['Header (web) 1920×416', 'Header (mobile) 640×260', 'Checkout 412×157'])
igual('las de proporción, solo el nombre', textoDePieza(prop('Redes 4:5', 4, 5)), 'Redes 4:5')

console.log('\nLas medidas exactas')
igual('todo lo pedido, a la medida: no falta nada', piezasQueFaltan(banners, [im(1920, 416), im(640, 260), im(412, 157)]), [])
igual('en cualquier orden', piezasQueFaltan(banners, [im(412, 157), im(1920, 416), im(640, 260)]), [])
// El pedido de Ivan: "si yo pido 4 banners y me pasan uno (...) acá faltan también los banners X o Y".
igual('pasan solo el header web: faltan el mobile y el checkout',
  nombres(piezasQueFaltan(banners, [im(1920, 416)])), ['Header (mobile)', 'Checkout'])
igual('sin imágenes, falta todo', nombres(piezasQueFaltan(banners, [])), ['Header (web)', 'Header (mobile)', 'Checkout'])
igual('sin piezas pedidas, nada', piezasQueFaltan([], [im(100, 100)]), [])
igual('una imagen que no es de nada no cubre nada', nombres(piezasQueFaltan([checkout], [im(1080, 1080)])), ['Checkout'])

console.log('\nMás grande vale, más chica no')
igual('@2x vale', piezasQueFaltan([headerWeb], [im(3840, 832)]), [])
igual('@1,5x vale', piezasQueFaltan([headerMobile], [im(960, 390)]), [])
igual('achicada (1600×347, la misma proporción) no vale', nombres(piezasQueFaltan([headerWeb], [im(1600, 347)])), ['Header (web)'])
igual('un píxel menos de alto no vale', nombres(piezasQueFaltan([checkout], [im(412, 156)])), ['Checkout'])
igual('la proporción con ±2 % y no más chica: vale', cubre(im(1920, 424), headerWeb), true)
igual('...con 3 % de diferencia ya es otra pieza', cubre(im(1920, 430), headerWeb), false)
igual('...con 2 % pero más chica de alto: no', cubre(im(1920, 408), headerWeb), false)
igual('de costado no es la misma', cubre(im(416, 1920), headerWeb), false)
igual('sin medida (0×0) no cubre nada', cubre(im(0, 0), checkout), false)

console.log('\nLas de proporción (redes)')
const redes45 = prop('Redes 4:5', 4, 5)
const redes916 = prop('Redes 9:16', 9, 16)
igual('4:5 de cualquier tamaño vale', [im(1080, 1350), im(400, 500), im(4000, 5000)].map(i => cubre(i, redes45)), [true, true, true])
igual('1:1 no es 4:5', cubre(im(1080, 1080), redes45), false)
igual('9:16 no es 16:9', [cubre(im(1080, 1920), redes916), cubre(im(1920, 1080), redes916)], [true, false])
igual('el pedido de redes, con una sola', nombres(piezasQueFaltan([prop('Redes 1:1', 1, 1), redes45, redes916], [im(1080, 1350)])),
  ['Redes 1:1', 'Redes 9:16'])
igual('WhatsApp (1080×1350) también es px: una de 4:5 más chica no vale',
  nombres(piezasQueFaltan([px('Envío WhatsApp', 1080, 1350)], [im(800, 1000)])), ['Envío WhatsApp'])

console.log('\nCada imagen, una pieza')
const receta = px('Foto receta', 1200, 900)
const producto = px('Foto producto', 1200, 900)
igual('dos piezas iguales y una imagen: falta la segunda', nombres(piezasQueFaltan([receta, producto], [im(1200, 900)])), ['Foto producto'])
igual('...con dos imágenes, ninguna', piezasQueFaltan([receta, producto], [im(1200, 900), im(2400, 1800)]), [])
// Óctuples (140×140) y Quíntuples (230×230) son cuadradas: la grande sirve
// para las dos, la chica solo para Óctuples. Se reparten bien aunque la
// grande venga primero.
const octuples = px('Óctuples', 140, 140)
const quintuples = px('Quíntuples', 230, 230)
igual('la grande se deja para la que la chica no alcanza', piezasQueFaltan([octuples, quintuples], [im(300, 300), im(140, 140)]), [])
igual('...en cualquier orden', piezasQueFaltan([quintuples, octuples], [im(140, 140), im(300, 300)]), [])
igual('dos chicas no cubren la grande', nombres(piezasQueFaltan([octuples, quintuples], [im(140, 140), im(150, 150)])), ['Quíntuples'])
// Carrito (368×140) y Checkout (412×157) tienen casi la misma proporción: una de 412×157 sirve para las dos, pero una sola vez.
const carrito = px('Carrito', 368, 140)
// Hasta el 21/11/2026 se la quedaba la de más arriba (el Carrito) y faltaba el Checkout: ver «La medida exacta», abajo.
igual('una que sirve para dos: se la queda la que mide exacto, y falta el Carrito',
  nombres(piezasQueFaltan([carrito, checkout], [im(412, 157)])), ['Carrito'])
igual('...con las dos medidas, ninguna', piezasQueFaltan([carrito, checkout], [im(412, 157), im(368, 140)]), [])
igual('el mobile repetido (Header y Slider, los dos 640×260): dos imágenes',
  nombres(piezasQueFaltan([headerMobile, px('Slider fila (normal) (mobile)', 640, 260)], [im(640, 260)])), ['Slider fila (normal) (mobile)'])

console.log('\nLa medida exacta (21/11/2026)')
// En la prueba de la entrega de Publicis, el checkout de 412×157 se lo
// quedaba el Carrito (más arriba en el pedido) y el aviso decía que faltaba
// el Checkout. Ahora: primero cubrir la mayor cantidad de piezas; entre los
// repartos que cubren las mismas, el de más piezas con su medida exacta
// (±2 px); y si empatan, la de más arriba.
igual('exacta: la misma medida, o hasta 2 px de diferencia de cada lado', [
  esExacta(im(412, 157), checkout), esExacta(im(414, 159), checkout), esExacta(im(410, 155), checkout),
  esExacta(im(415, 157), checkout), esExacta(im(412, 160), checkout), esExacta(im(824, 314), checkout),
], [true, true, true, false, false, false])
igual('la tolerancia es de 2 px', TOLERANCIA_EXACTA, 2)
igual('las de proporción nunca son exactas (no tienen medida)', esExacta(im(4, 5), redes45), false)
igual('el checkout de la prueba, con el pedido al revés: igual falta el Carrito',
  nombres(piezasQueFaltan([checkout, carrito], [im(412, 157)])), ['Carrito'])
igual('a 2 px sigue siendo del Checkout (414×159)', nombres(piezasQueFaltan([carrito, checkout], [im(414, 159)])), ['Carrito'])
igual('a 3 px ya no es exacta de ninguna (415×158): se la queda la de más arriba',
  nombres(piezasQueFaltan([carrito, checkout], [im(415, 158)])), ['Checkout'])
igual('@2x no es exacta de ninguna (824×314): se la queda la de más arriba',
  nombres(piezasQueFaltan([carrito, checkout], [im(824, 314)])), ['Checkout'])
igual('una cuadrada de 230×230 es de Quíntuples aunque Óctuples esté más arriba: falta Óctuples',
  nombres(piezasQueFaltan([octuples, quintuples], [im(230, 230)])), ['Óctuples'])
igual('...con la de 300×300 (exacta de ninguna), la de más arriba: falta Quíntuples',
  nombres(piezasQueFaltan([octuples, quintuples], [im(300, 300)])), ['Quíntuples'])
igual('exacta y @2x: cada una a la suya', piezasQueFaltan([carrito, checkout], [im(824, 314), im(368, 140)]), [])
// Cubrir más piezas va antes que la medida exacta: la de 1030×400 cubre el
// Checkout (1,9 % de diferencia de proporción) pero no el Carrito (2,04 %).
igual('1030×400 sirve para el Checkout y no para el Carrito', [cubre(im(1030, 400), checkout), cubre(im(1030, 400), carrito)],
  [true, false])
igual('cubrir más va primero: el 412×157 exacto se lo deja al Carrito para cubrir los dos',
  piezasQueFaltan([checkout, carrito], [im(412, 157), im(1030, 400)]), [])
// Los mobile de Dobles (315×405), Triples (206×265) y Cuádruples (155×200)
// tienen casi la misma proporción: una más grande sirve para las más chicas.
const doblesMobile = px('Dobles (mobile)', 315, 405)
const triplesMobile = px('Triples (mobile)', 206, 265)
const cuadruplesMobile = px('Cuádruples (mobile)', 155, 200)
igual('los mobile: cada una a la que mide exacto, y falta la que no vino',
  nombres(piezasQueFaltan([doblesMobile, triplesMobile, cuadruplesMobile], [im(206, 265), im(315, 405)])), ['Cuádruples (mobile)'])
igual('...con la de Cuádruples exacta y una grande de más (@2x de Triples), se cubren las tres',
  piezasQueFaltan([doblesMobile, triplesMobile, cuadruplesMobile], [im(412, 530), im(315, 405), im(155, 200)]), [])
igual('...y si la única que viene es la de Cuádruples, solo Cuádruples',
  nombres(piezasQueFaltan([doblesMobile, triplesMobile, cuadruplesMobile], [im(155, 200)])), ['Dobles (mobile)', 'Triples (mobile)'])
// La entrega de la prueba: doce medidas pedidas, el header web y el checkout.
const pedidoDeLaPrueba = [
  headerWeb, headerMobile, px('Slider fila (normal) (web)', 1200, 179), px('Slider fila (normal) (mobile)', 640, 260), carrito,
  checkout, px('Menú principal', 625, 450), px('Dobles (web)', 590, 240), px('Dobles (mobile)', 315, 405), quintuples,
  px('Séxtuples', 190, 182), octuples,
]
igual('la entrega de la prueba: faltan diez, el Carrito y no el Checkout',
  nombres(piezasQueFaltan(pedidoDeLaPrueba, [im(1920, 416), im(412, 157)])), [
    'Header (mobile)', 'Slider fila (normal) (web)', 'Slider fila (normal) (mobile)', 'Carrito', 'Menú principal',
    'Dobles (web)', 'Dobles (mobile)', 'Quíntuples', 'Séxtuples', 'Óctuples',
  ])
const conElCarrito = nombres(piezasQueFaltan(pedidoDeLaPrueba, [im(1920, 416), im(412, 157), im(368, 140)]))
igual('...y si viene también el carrito, faltan nueve (ni el Carrito ni el Checkout)',
  [conElCarrito.length, conElCarrito.filter(n => /Carrito|Checkout/.test(n))], [9, []])

console.log('\nLa entrega: las sueltas y las del ZIP')
// Las sueltas, con su tamaño de antes de achicar; las del ZIP, todas (también
// las que no entran en las 4 de la ronda), leídas del encabezado.
const delZip = [im(1920, 416), im(640, 260), im(412, 157), im(1200, 900), im(1200, 900)]
igual('el ZIP con todo', faltanEnLaEntrega([...banners, receta, producto], delZip), [])
igual('el ZIP con el KV solo', nombres(faltanEnLaEntrega([...banners, receta], [im(3840, 832)])),
  ['Header (mobile)', 'Checkout', 'Foto receta'])
igual('alguna del ZIP sin medir (con contraseña, dañada): no se dice nada', faltanEnLaEntrega(banners, [im(1920, 416), null]), [])
igual('un ZIP que acá no se lee: no se dice nada', faltanEnLaEntrega(banners, null), [])
igual('sin imágenes (solo el link o un PDF): no se dice nada', faltanEnLaEntrega(banners, []), [])
igual('un servidor de antes (sin piezas): nada', [faltanEnLaEntrega(undefined, [im(1, 1)]), faltanEnLaEntrega(null, [im(1, 1)])], [[], []])

console.log('\nLo que se dice (los chips, 21/11/2026)')
// Ivan: "las correcciones de la IA están súper mezcladas". Antes iba todo en
// un renglón, seguido por comas; ahora cada pieza es un chip.
igual('el subtítulo del aviso (la cantidad va aparte, en gris)',
  [tituloDeLasPiezas([headerMobile, checkout]), tituloDeLasPiezas([checkout])], ['Piezas que faltan', 'Pieza que falta'])
igual('la medida, abajo del nombre', [medidaDePieza(headerWeb), medidaDePieza(checkout)], ['1920×416', '412×157'])
igual('las de proporción: la proporción ya está en el nombre', medidaDePieza(prop('Redes 4:5', 4, 5)), 'cualquier tamaño')
// El pedido de la captura de Ivan: diez piezas que faltan.
const diez = ['Header (web)', 'Slider fila (normal) (mobile)', 'Carrito', 'Checkout', 'Menú principal', 'Dobles (web)',
  'Dobles (mobile)', 'Quíntuples', 'Séxtuples', 'Óctuples']
igual('se ven 6', PIEZAS_A_LA_VISTA, 6)
igual('con 10, las primeras 6 y «Ver las otras 4»', primeras(diez), { vistas: diez.slice(0, 6), resto: 4 })
igual('con 8, las primeras 6 y «Ver las otras 2»', primeras(diez.slice(0, 8)).resto, 2)
igual('con 7, las 7: un botón para una sola ocupa lo mismo que mostrarla', primeras(diez.slice(0, 7)),
  { vistas: diez.slice(0, 7), resto: 0 })
igual('con 6 o menos, todas', [primeras(diez.slice(0, 6)).resto, primeras(diez.slice(0, 1)).resto, primeras([]).resto], [0, 0, 0])
igual('con otro tope', primeras(diez, 3), { vistas: diez.slice(0, 3), resto: 7 })
const lista = ['Header (web)']
primeras(lista).vistas.push('otra')
igual('no toca la lista de entrada', lista, ['Header (web)'])
igual('lo que faltaba en la ronda, con lo que dice la agencia aparte',
  loQueFaltaba(['Header (mobile)', 'Checkout'], '  Es el KV, para aprobarlo antes '),
  { titulo: 'Faltan 2 piezas del pedido', piezas: ['Header (mobile)', 'Checkout'], quien: 'La agencia',
    porQue: 'Es el KV, para aprobarlo antes' })
igual('de una y sin porqué', loQueFaltaba(['Checkout'], '  '),
  { titulo: 'Falta 1 pieza del pedido', piezas: ['Checkout'], quien: 'La agencia', porQue: null })
igual('si la hizo alguien de Tienda, lo dice esa persona', loQueFaltaba(['Checkout'], 'Mañana', 'Lucía')?.quien, 'Lucía')
igual('no faltaba nada (o es de antes): nada', [loQueFaltaba([], 'x'), loQueFaltaba(undefined, null)], [null, null])

console.log('\nEl tamaño, del encabezado')
igual('JPG', medidasDeImagen(jpegArmado(1920, 416)), { ancho: 1920, alto: 416 })
igual('JPG progresivo', medidasDeImagen(jpegArmado(640, 260, { sof: 0xc2 })), { ancho: 640, alto: 260 })
igual('JPG con 0xFF de relleno', medidasDeImagen(jpegArmado(412, 157, { bytesDeRelleno: 3 })), { ancho: 412, alto: 157 })
igual('JPG con 200 KB antes del tamaño (perfil de color)', medidasDeImagen(jpegArmado(1200, 900, { relleno: 200_000 })),
  { ancho: 1200, alto: 900 })
igual('JPG de costado (EXIF 6, Intel): como lo muestra el navegador',
  medidasDeImagen(jpegArmado(1350, 1080, { orientacion: 6 })), { ancho: 1080, alto: 1350 })
igual('JPG de costado (EXIF 8, Motorola)', medidasDeImagen(jpegArmado(1350, 1080, { orientacion: 8, orden: 'MM' })),
  { ancho: 1080, alto: 1350 })
igual('JPG derecho (EXIF 1) o dado vuelta (EXIF 3): igual',
  [medidasDeImagen(jpegArmado(1350, 1080, { orientacion: 1 })), medidasDeImagen(jpegArmado(1350, 1080, { orientacion: 3, orden: 'MM' }))],
  [{ ancho: 1350, alto: 1080 }, { ancho: 1350, alto: 1080 }])
const cortado = jpegArmado(1200, 900, { relleno: 200_000 }).subarray(0, 100_000)
igual('JPG cortado antes del tamaño: hay que leer más', medidasDeImagen(cortado), 'faltan-bytes')
igual('JPG sin tamaño antes de los datos: no se entiende',
  medidasDeImagen(new Uint8Array([0xff, 0xd8, 0xff, 0xda, 0, 4, 0, 0, 0xff, 0xd9])), null)
igual('PNG', medidasDeImagen(pngArmado(1080, 1350)), { ancho: 1080, alto: 1350 })
igual('PNG de 20000 px de ancho', medidasDeImagen(pngArmado(20_000, 400)), { ancho: 20_000, alto: 400 })
igual('PNG cortado: hay que leer más', medidasDeImagen(pngArmado(10, 10).subarray(0, 20)), 'faltan-bytes')
igual('WebP con pérdida', medidasDeImagen(webpArmado(1080, 1920)), { ancho: 1080, alto: 1920 })
igual('WebP sin pérdida', medidasDeImagen(webpArmado(412, 157, 'VP8L')), { ancho: 412, alto: 157 })
igual('WebP extendido (transparencia)', medidasDeImagen(webpArmado(3840, 832, 'VP8X')), { ancho: 3840, alto: 832 })
igual('WebP cortado: hay que leer más', medidasDeImagen(webpArmado(10, 10).subarray(0, 16)), 'faltan-bytes')
igual('un PDF no es una imagen', medidasDeImagen(new TextEncoder().encode('%PDF-1.7\n%âãÏÓ\n1 0 obj')), null)
igual('un RIFF que no es WebP (un WAV)', medidasDeImagen(new Uint8Array([...new TextEncoder().encode('RIFF\0\0\0\0WAVEfmt '), ...new Uint8Array(20)])), null)
igual('nada todavía: hay que leer más', medidasDeImagen(new Uint8Array([0xff])), 'faltan-bytes')

if (fallos) {
  console.log(`\n${fallos} prueba(s) fallaron`)
  process.exit(1)
}
console.log('\nTodo bien')

# Por qué algo «parece hecho con IA» y cómo darle identidad propia

Ivan, 25/11/2026: «Hoy se ve muy "hecho con IA". Hay que trabajarlo para que
tenga una identidad más propia.» El pedido de la auditoría fue «más tranqui,
más chill, más minimal».

## El diagnóstico: no es una cosa, es la suma de valores por defecto

Las interfaces hechas rápido (por una IA o con apuro) se parecen entre sí
porque arrancan de los mismos valores por defecto y copian la estética de las
páginas de venta de software: degradés, brillos, tarjetas flotantes, íconos
con fondo de color, un emoji por título. Cada señal sola es menor; juntas
gritan «plantilla». Y debajo de todas hay lo mismo: **decoración que no
informa y falta de decisiones** (todo pide la misma atención porque nadie
decidió qué es lo importante).

| Señal | Por qué delata | En Core Tienda (informe del 25/11) | Qué hacer |
|---|---|---|---|
| Color de fábrica | El índigo de Tailwind es el acento de muchísimas plantillas y ejemplos: se reconoce de lejos y no dice nada de Tienda Inglesa | `brand` = índigo `#4f46e5`, 1.252 usos | El azul de Tienda Inglesa `#0047BA`, cambiado en el token |
| Degradés | Adornan sin decir nada | `.btn-primary` en degradé; cuadraditos de ícono con degradé | Color liso |
| Brillos y resplandores | Sombras de color, halos, desenfoque detrás | Resplandor violeta en el login e índigo en Mundos; `shadow-glow`; `backdrop-blur` en ventanas | Sin sombras de color; velo gris liso |
| Destellos para «IA» | El destello se volvió el ícono genérico de «esto lo hace la IA» | 26 usos de destellos | Decir qué hace, con palabras: «Revisar con IA» |
| Emojis | Tono de chat y de marketing en una herramienta | La manito que saluda, la estrella de «Mega evento», el confeti al finalizar | Sin emojis; el logro se dice con palabras («Finalizado») |
| Mascotas dibujadas | Personajes sin función que ocupan lugar y tapan botones | Cinco: Don Tino robot, Tinín, CatTi, DogTi, Doña Tina (99 usos); el robot tapa «Más» (H-025) | Sin dibujo, con su nombre e identidad (decisión de Ivan): una función, no un muñeco |
| Tarjeta dentro de tarjeta | Caja sobre caja: ruido y menos lugar | Cenefas: tarjeta flotante con tres tarjetas adentro; Convertidor: caja dentro de caja | Un solo nivel; separar con aire y una línea fina |
| Sombra en todo | Todo flota, nada se apoya | `shadow-card` en cada `.card`; `shadow-xl` suelto | Lo apoyado, con borde; sombra solo lo que flota |
| Bordes muy redondeados | Estética de app de consumo | `rounded-2xl` (16 px) en cajas, `rounded-xl` en controles | 6 px controles y tarjetas, 8 px ventanas |
| Pastillas para todo | Cada dato en un chip de color | 18 pastillas arcoíris de cadenas en Precios; «SUPER ADMIN» rosa de 9 px | Texto gris; el color, solo para estados |
| Cuadradito de ícono junto a cada título | Relleno de plantilla | Mis tareas, Tablero, Finanzas, Convertidor | El título solo |
| MAYÚSCULAS ESPACIADAS | Etiqueta «de diseño» que se lee peor | «HERRAMIENTAS», «MUNDO», «CATEGORÍA» (108 usos) | Minúscula, 12 px, gris |
| Textos que explican de más | La herramienta se vende a quien ya la usa | «Motor v2 — componentes inteligentes», «Powered by Claude Sonnet 5», «en tiempo real», «Marketing Intelligence Platform», «tokens» bajo cada respuesta | Título de 1 a 3 palabras; subtítulo de una línea o nada |
| Composición de página de venta | Portada centrada y tarjetas que venden adentro de la herramienta | Login de folleto con cuatro tarjetas sobre IA; Precios como buscador de portada con «134+ sucursales» | Una columna; título a la izquierda; herramienta, no folleto |
| Movimiento de adorno | Latidos, rebotes, el puntito verde «en línea» | 153 usos | 150 ms al abrir y cerrar, nada más |
| Arcoíris | Un color fuerte por columna, categoría o acción | Tablero con columnas pastel; calendario de Redexpres en amarillo flúo (H-068) | El mismo gris para todas, puntito de estado; el color de las acciones, duda abierta con Ivan |

**Ojo con el costo:** los desenfoques (`backdrop-filter`) y las animaciones
permanentes también pesan en un celular modesto. Sacarlos suele hacer la
plataforma más tranquila **y** más rápida.

## La identidad: de dónde sale

Identidad propia no es sumar adornos «distintos»: es tomar decisiones que
solo tienen sentido para Tienda Inglesa y sostenerlas en todas partes.

1. **La marca de verdad:** la margarita de 7 pétalos en el menú, el login y
   la carga (hoy solo está en la pestaña del navegador y adentro hay tres
   marcas distintas, H-059); el azul `#0047BA` como único acento; el rojo de
   la «i» solo en el logo.
2. **El contenido de verdad:** las piezas de las agencias, las acciones del
   mes, los locales. Una pieza que se ve grande y nítida dice más de Tienda
   Inglesa que cualquier ilustración. Es la deferencia de Apple: la interfaz
   se corre y el contenido manda.
3. **La voz:** castellano rioplatense con «vos», las palabras de promo y
   marca, frases cortas (`escritura.md`). Ninguna plantilla habla así.
4. **La coherencia:** el mismo botón, encabezado, campo y cartel en todas las
   pantallas. La coherencia se percibe como calidad; la mezcla, como algo
   armado de a pedazos.
5. **La contención:** decir que no a lo que no informa. Dieter Rams lo
   resumió en «menos, pero mejor», y uno de sus diez principios dice que el
   buen diseño es el que tiene la menor cantidad de diseño posible.
6. **El oficio en los detalles:** cifras tabulares, alineaciones exactas,
   textos que no se cortan, vacíos que ayudan, foco visible. Eso no viene en
   ninguna plantilla: es la señal de que alguien cuidó.

**Modelos dentro de casa** (la auditoría los marcó como «ya tranquilos»):
Mi pedido, Fotos, Colocación, la Planilla de pedidos, Listas de monitoreo y la
ficha de una entrega. Antes de inventar, mirá cómo resolvieron lo mismo.

## Cuidado con pasarse

- **Minimal no es todo gris.** Un «Falta» en gris se leía como que estaba
  todo bien y se le devolvió el color (24/11/2026). El color de estado es
  información, no decoración.
- **Minimal no es esconder.** Si sacás textos, que no se pierda lo que la
  persona necesita para decidir: dónde está, qué falta, qué hace ahora.
- **Minimal no es chico ni pálido.** Más aire alrededor, no letra más chica
  ni contraste más bajo: el gris clarito «elegante» es un error de
  accesibilidad (`accesibilidad.md`).
- **Sacar el dibujo no es sacar la función ni el nombre.** Don Tino sigue
  presente y siendo Don Tino (Ivan, 25/11/2026), igual que los demás
  asistentes.
- **Lo que la gente ya aprendió se cambia preguntando.** El color de las
  acciones del calendario es una duda abierta con Ivan, no un gusto tuyo.

## Prueba rápida «¿parece IA?»

Sobre una captura, contá: degradés, sombras de color o brillos, emojis,
destellos, mascotas dibujadas, tarjetas dentro de tarjetas, pastillas de color
que no son estados, mayúsculas espaciadas, cuadraditos de ícono junto a los
títulos, párrafos que explican la pantalla, acentos de color distintos del
azul de la marca. La meta es **cero** en todo. Anotá el conteo antes y después:
es un número que Ivan entiende de un vistazo.

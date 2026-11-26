# Celular primero, responsive y modo oscuro

## Celular primero, como método

- Diseñá primero a 390 px de ancho: obliga a decidir qué es lo importante; en
  la notebook se agrega, no al revés (Luke Wroblewski, *Mobile First*).
- Quién está en el celular: el local (siempre), la agencia (a veces; desde el
  celular hoy no ve lo que volvió con cambios, H-038), el equipo «entre dos
  reuniones» e Ivan.
- **La primera pantalla (390×664)** muestra el título en una línea, lo
  principal y su acción. Si el título ocupa 8 renglones y no se ve ninguna
  tarjeta (tablero, H-052), sobra encabezado.
- **El pulgar:** lo frecuente, abajo y hacia el centro; lo destructivo, lejos
  de donde se toca sin querer. Steven Hoober, que observó cómo se agarra el
  teléfono, encontró que la gente cambia de agarre todo el tiempo y que el
  centro de la pantalla se toca con más precisión que los bordes: no hay una
  «zona segura» fija. Lo que sí es seguro: con una mano, las esquinas de
  arriba quedan lejos del pulgar.
- **No existe el hover:** lo que en la notebook aparece al pasar el mouse, en
  el celular está siempre a la vista o en «⋯».
- **El teclado tapa:** el campo enfocado tiene que quedar visible; usá `dvh`
  en lugar de `vh` y que nada fijo abajo tape el campo (el local de Redexpres
  escribe su pedido con el teclado abierto).
- **iPhone:** la barra de abajo respeta `env(safe-area-inset-bottom)`; los
  campos van a 16 px o Safari agranda la página; probá en Safari de verdad
  (es una regla de `CONTEXTO.md`).
- **Hojas desde abajo** para fichas y filtros, con X y deslizar para cerrar
  (ya existe `useDeslizarParaCerrar`).
- **Nada flotante encima de la barra de abajo:** el robot de Don Tino tapaba
  «Más», la puerta al resto del menú (H-025).

## Responsive

- Los cortes de Tailwind: `sm` 640, `md` 768, `lg` 1024, `xl` 1280. En Core
  Tienda el que cambia la estructura es 768: debajo hay barra de abajo y menú
  en hoja.
- La notebook de referencia es 1366×768: lo importante entra sin bajar.
  Probá también un monitor grande: formularios y textos con ancho máximo para
  que no se estiren de punta a punta.
- El corte va donde el diseño se rompe, no donde termina un aparato.
- Tablas: en el celular, tarjetas con los 2 o 3 datos clave; la tabla con
  scroll de costado y primera columna fija solo si hay que comparar columnas.
- Calendario: en el celular, abrir en Lista (que se lee) y no en el mes, que
  muestra una semana y la columna de categorías ocupa la mitad (H-051).
- Imágenes con su proporción reservada, para que nada salte al cargar.

## Modo oscuro bien hecho

- **No es invertir colores.** Es otra paleta con los mismos significados: cada
  token semántico tiene su valor oscuro (la tabla del `SKILL.md`).
- **Gris muy oscuro, no negro puro.** Material 2 recomendaba `#121212`; el
  informe propone `#111113` de fondo y `#1A1A1D` de superficie. Blanco puro
  sobre negro puro (21:1) encandila, y a mucha gente (sobre todo con
  astigmatismo) el texto le parece «correrse».
- **La altura se muestra aclarando:** lo que está más arriba es un poco más
  claro, porque las sombras en oscuro casi no se ven (Material usa superficies
  más claras; Apple habla de fondos «base» y «elevados»).
- **Texto sin blanco puro:** principal `#F4F4F5` (15,8:1), secundario
  `#A1A1AA` (6,8:1).
- **Los colores saturados vibran sobre oscuro:** van versiones más claras y
  menos saturadas. El azul de la marca `#0047BA` sobre `#111113` da 2,34:1, ni
  siquiera llega a 3:1: por eso en oscuro el botón es `#2563EB` (texto blanco
  5,2:1) y el link `#7AA2F7` (6,9:1).
- **Bordes e íconos que desaparecen:** revisalos uno por uno. El borde de
  campo oscuro `#71717A` da 3,6:1 sobre la superficie.
- **Ninguna caja blanca:** el cuadro «+» de Conexiones queda blanco en oscuro
  (H-033); también ilustraciones, íconos con relleno blanco, cocardas sin
  versión oscura (`entrada-admin-diseno.md`, §4.2).
- **El logo no se recolorea por tu cuenta.** El azul de la margarita pierde
  contraste sobre fondo oscuro; si no se lee bien, es una duda para Ivan (no
  se propone otro logo).
- **Las piezas de las agencias se muestran tal cual:** son su trabajo; lo que
  cambia es el marco alrededor.
- **`color-scheme: dark`** (ya está) para que los controles del navegador
  sigan el tema.
- **Sin destello claro al abrir:** el tema se aplica antes de pintar la
  página (hoy se sospecha ese destello, `entrada-admin-diseno.md`, §2.8).
- **Se prueba con cada cambio de color**, en los dos modos. El oscuro no se
  «arregla después».

**Errores típicos:** invertir con un filtro; usar el mismo azul de marca en
los dos modos; sombras negras sobre fondo negro como única separación; probar
el oscuro solo en el núcleo y olvidarse de las pantallas viejas (Olvidé mi
contraseña, «Algo salió mal»).

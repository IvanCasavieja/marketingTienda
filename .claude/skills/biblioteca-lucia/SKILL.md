---
name: biblioteca-lucia
description: Biblioteca profesional de Lucía, diseñadora de producto del Escuadrón Lechuza (principios visuales, sistemas de diseño de referencia, usabilidad, WCAG 2.2 AA, celular y modo oscuro, cómo sacarle a Core Tienda la «cara de hecho con IA», escritura de interfaz, revisar y defender un diseño); usala antes de revisar capturas, al diseñar o corregir una pantalla, al armar un antes/después y cada vez que haya que aceptar, discutir o mejorar un pedido de diseño.
---

# Biblioteca de Lucía

Lo que sabe una diseñadora de producto de primer nivel, destilado de los
métodos y estándares **públicos** más reconocidos (Nielsen Norman Group, W3C,
Material Design de Google, Human Interface Guidelines de Apple, Fluent 2 de
Microsoft, Carbon de IBM, Atlassian, GOV.UK) y vuelto práctico para Core
Tienda. No reemplaza tu vara (`.claude/skills/recorrido-humano/criterios.md`)
ni el mapa del sistema visual (`docs/equipo-nocturno/plataforma/entrada-admin-diseno.md`,
§4): los explica, los profundiza y te da con qué argumentar.

**Regla de honestidad.** Acá no hay datos ni citas inventadas: los contrastes
están calculados con la fórmula de WCAG y las frases de Ivan, copiadas de
comentarios del código, mensajes de commit y el cuaderno, con su fecha. Lo
marcado *verificá en la web* puede haber cambiado. Vos tampoco inventes: si no
mediste, no pongas número.

## Qué abrir según lo que estás haciendo

| Estás… | Abrí |
|---|---|
| Revisando las capturas del recorrido (Trabajo 1) | `referencias/revisar-y-defender.md` (lista de control) y `referencias/sin-cara-de-ia.md` |
| Decidiendo jerarquía, espacios, letra, color, densidad | `referencias/fundamentos-visuales.md` |
| Creando o unificando un componente, los tokens o los estados | `referencias/sistemas-de-diseno.md` |
| Con formularios, navegación, tablas, filtros, borrar, avisos, esperas | `referencias/usabilidad.md` |
| Midiendo contraste, foco, tamaños, lector de pantalla, movimiento | `referencias/accesibilidad.md` |
| En el celular, el responsive o el modo oscuro | `referencias/celular-y-oscuro.md` |
| Escribiendo botones, errores, vacíos, avisos | `referencias/escritura.md` |
| Armando un antes/después o discutiendo un pedido | `referencias/revisar-y-defender.md` |

## La dirección ya decidida

Ivan pidió el 25/11/2026 una plataforma «más tranqui, más chill, más minimal»
y, al leer la auditoría: «Hoy se ve muy "hecho con IA". Hay que trabajarlo
para que tenga una identidad más propia.» Aprobó la dirección del informe
(`cuaderno/auditoria-2026-11-25/INFORME.md`, §3, rama
`equipo-nocturno/cuaderno`) con un cambio: los asistentes **mantienen su
nombre y su identidad** aunque dejen de verse como robots. Las 12 reglas:

1. **Paleta:** un azul (`#0047BA`), un rojo de interfaz (`#C81E2B`), verde y
   ámbar solo para estados, grises neutros. El rojo del logo (`#F6323E`), solo
   en el logo. El color de cada mundo, un puntito al lado del nombre.
2. **Letra:** Inter, cargada una vez. 22 / 16 / 14 / 12 px (16 en campos del
   celular). Pesos 400 y 600. Nada debajo de 12 px. Sin MAYÚSCULAS ESPACIADAS.
3. **Espacio:** 4 · 8 · 12 · 16 · 24 · 32. Margen de página: 32 px en la
   notebook, 16 en el celular. Nunca una tarjeta dentro de otra.
4. **Radios:** 6 px en botones, campos y tarjetas; 8 px en ventanas. Redondo
   del todo, solo el número de avisos.
5. **Sombras:** lo apoyado lleva borde, no sombra; sombra solo lo que flota.
   Sin sombras de color ni desenfoque detrás de las ventanas: velo gris liso.
6. **Botones:** uno principal por pantalla, azul liso, 40 px de alto (44 en el
   celular). Secundario blanco con borde. Borrar, en rojo.
7. **Íconos:** de línea, 16–18 px, del color del texto, sin cuadradito de
   color detrás. Sin destellos.
8. **El color se gana:** azul = «tocá acá / estás acá»; rojo = vencido, error,
   cambios pedidos; verde = aprobado; ámbar = esperando. Lo demás, gris. Un
   estado es puntito + palabra, no un fondo pastel.
9. **Textos:** título de 1 a 3 palabras; subtítulo de una línea o nada. Sin
   marketing adentro de la herramienta, sin emojis.
10. **Asistentes y logo:** sin dibujos de mascotas en la interfaz de trabajo,
    pero cada asistente conserva nombre e identidad. Don Tino sigue como la
    burbuja de abajo a la derecha que pidió Ivan: un solo ayudante por
    pantalla y sin tapar nada. Logo: la margarita de 7 pétalos en el menú, el
    login y la pantalla de carga.
11. **Movimiento:** 150 ms al abrir y cerrar. Nada de latidos, rebotes ni
    brillos. Se respeta «reducir movimiento».
12. **Celular y oscuro, con la misma regla:** lo principal a mano del pulgar,
    nada flotante encima de la barra de abajo, 44 px para tocar; en oscuro,
    los mismos tokens con su valor oscuro y ninguna caja blanca.

**Paleta propuesta** (informe §3.1; nombres de token sugeridos; contraste
calculado contra la superficie de cada modo):

| Token | Claro | Oscuro | Para qué |
|---|---|---|---|
| `fondo` | `#FAFAFA` | `#111113` | la página |
| `superficie` | `#FFFFFF` | `#1A1A1D` | tarjetas, menú, ventanas |
| `borde` | `#E4E4E7` | `#2E2E33` | cajas y separadores (decorativo) |
| `borde-control` | `#8A8A93` (3,4:1) | `#71717A` (3,6:1) | campos y botones secundarios |
| `texto` | `#18181B` (17,7:1) | `#F4F4F5` (15,8:1) | texto principal |
| `texto-2` | `#52525B` (7,7:1) | `#A1A1AA` (6,8:1) | texto secundario |
| `marca` | `#0047BA` (8,0:1); al pasar el mouse, `#003A99` | botón `#2563EB` (texto blanco 5,2:1), link `#7AA2F7` (6,9:1) | botón principal, link, activo, foco |
| `marca-suave` | `#E8EEF9` | `#1E2A44` | ítem elegido |
| `peligro` | `#C81E2B` (5,7:1) | `#FF6B73` (6,3:1) | error, vencido, borrar, cambios pedidos |
| `exito` | `#15803D` (5,0:1) | `#4ADE80` (10:1) | aprobado |
| `atencion` | `#B45309` (5,0:1) | `#FBBF24` (10,4:1) | esperando |

**Pendiente de Ivan** (no lo decidas vos; antes, mirá `cuaderno/DECISIONES.md`):
si la gente reconoce las acciones del calendario por el color de fondo
(propuesta: barra blanca con una rayita de color, o barra llena con 8 tonos
apagados) y si el azul nuevo va de una vez en toda la plataforma.

## Números de bolsillo

| Qué | Número | De dónde sale |
|---|---|---|
| Contraste de texto | 4,5:1; texto grande (24 px, o 18,66 px en negrita) 3:1 | WCAG 1.4.3 |
| Contraste de bordes de controles, íconos que informan y foco | 3:1 | WCAG 1.4.11 |
| Letra | mínimo 12 px; 14 para leer de corrido; 16 en campos del celular | Core Tienda; Safari agranda la página si el campo tiene menos de 16 |
| Objetivo táctil | 44 px en el celular; el piso de WCAG es 24 px | Core Tienda; Apple 44 pt; Material 48 dp; WCAG 2.5.8 |
| Alto de control | 40 px en la notebook, 44 en el celular | núcleo y regla 6 |
| Largo de línea para leer | 45 a 75 caracteres | Robert Bringhurst |
| Respuesta | 0,1 s se siente instantáneo · 1 s no corta el hilo · 10 s se pierde la atención | Robert B. Miller (1968), Jakob Nielsen (1993) |
| Espera en Core Tienda | más de 3 s necesita indicación; más de 6 s es hallazgo | `criterios.md`, punto 13 |
| Vistas de prueba | 1366×768 y 390×664, en claro y en oscuro | `criterios.md` y la auditoría |

## Cómo trabajás con esta biblioteca

**Trabajo 1, la revisión visual** (`.claude/agents/lucia-diseno.md`): releé
las 12 reglas y pasá cada pantalla por la lista de control de
`referencias/revisar-y-defender.md`. Para el inventario de patrones, poné lado
a lado todas las variantes de un mismo patrón (encabezados, botones
principales, vacíos, carteles): es el *inventario de interfaz* de Brad Frost,
y lo dispar salta solo. La «cara de IA» suele ser **desprolijo**; pasa a
**traba** cuando además tapa, confunde o no se lee (el robot que tapaba «Más»
en el celular, H-025).

**Trabajo 2, la parte visual de una mejora:**

1. La necesidad primero: quién, qué tarea, cuán seguido (`CONTEXTO.md`).
2. Lo que ya existe: `frontend/components/`, `frontend/tailwind.config.ts`,
   `frontend/app/globals.css`, la pantalla hermana del núcleo. Si hay dos
   estilos, unificá hacia el nuevo.
3. Los estados antes que el caso feliz: vacío, cargando, error, sin permiso,
   mucho contenido, nombre larguísimo.
4. Las cuatro vistas, el teclado y el contraste medido.
5. El antes/después de `referencias/revisar-y-defender.md`.
6. Que no quede más lento: nada de fuentes nuevas, desenfoques, animaciones
   permanentes ni imágenes pesadas. Si tocás algo que carga, medí antes y después.

**Ante un pedido de diseño:** separá la necesidad de la solución pedida,
buscá precedentes de Ivan y, si la solución empeora la experiencia, decilo
con argumentos y una alternativa («Criterio propio», en
`referencias/revisar-y-defender.md`). La decisión final es de Ivan. Las
reglas comunes del Escuadrón (evidencia antes que autoridad, ni esponja ni
terca, hechos separados de opiniones) están en `docs/equipo-nocturno/CRITERIO.md`:
esta biblioteca las aplica al diseño.

## Lo que no se negocia mientras diseñás

- La margarita completa de 7 pétalos; nunca la de 5; no se propone otro logo.
- Contraste alto en claro y oscuro; notebook y celular, iPhone/Safari incluido.
- Las agencias (Publicis, Another Monday, «Diseñadores», que es una agencia
  externa) ven solo su tablero.
- Las imágenes de las entregas no se borran nunca: ningún diseño lo ofrece.
- Nada que exija pagar (planes, fuentes, servicios). Y si algo es feo pero
  cambiarlo rompe lo que la gente ya aprendió, va como duda para Ivan.

## Fuentes (todas públicas)

W3C: WCAG 2.2 (`w3.org/TR/WCAG22`), *Understanding WCAG 2.2*, *Using ARIA* ·
Nielsen Norman Group (`nngroup.com`) · Material Design 3 (`m3.material.io`) ·
Apple Human Interface Guidelines (`developer.apple.com/design`) · Fluent 2
(`fluent2.microsoft.design`), Microsoft Writing Style Guide, Microsoft
Inclusive Design · Carbon (`carbondesignsystem.com`), IBM Equal Access ·
Atlassian Design System (`atlassian.design`) · GOV.UK Design System
(`design-system.service.gov.uk`). Libros: Don Norman, *The Design of Everyday
Things*; Steve Krug, *Don't Make Me Think*; Wathan y Schoger, *Refactoring
UI*; Jon Yablonski, *Laws of UX*; Luke Wroblewski, *Web Form Design* y *Mobile
First*; Robert Bringhurst, *The Elements of Typographic Style*; Edward Tufte,
*The Visual Display of Quantitative Information*; Brad Frost, *Atomic Design*;
Torrey Podmajersky, *Strategic Writing for UX*.

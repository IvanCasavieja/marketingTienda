# Fundamentos visuales

Seis herramientas que se usan juntas: jerarquía, agrupamiento, espaciado,
tipografía, color y densidad. Cuando una pantalla «se ve rara» y no sabés por
qué, casi siempre falla una de estas seis.

## 1. Jerarquía visual

Es el orden en que el ojo recorre la pantalla. La deciden los contrastes entre
elementos: posición, peso, color, tamaño y aire. Si todo resalta, nada resalta.

**Método:**
1. Escribí la pregunta que la pantalla contesta: «¿qué me toca hoy?» (Mis
   tareas), «¿qué me pidieron y para cuándo?» (la tarjeta de la agencia).
2. Ordená los elementos en tres niveles: lo que contesta la pregunta, lo que
   sirve para actuar, lo accesorio.
3. Dale un recurso a cada nivel, en este orden: **posición** (arriba a la
   izquierda se ve primero), **peso** (600 contra 400), **color del texto**
   (principal contra secundario) y recién al final **tamaño**. El azul se
   guarda para «tocá acá».
4. Antes de agrandar lo importante, achicá lo accesorio: *Refactoring UI*
   (Wathan y Schoger) lo llama «enfatizar desenfatizando».

**Pruebas:** desenfocá la captura (lo que sigue viéndose es lo que manda; si
es un adorno, está mal) y pasala a grises (si la jerarquía se pierde,
dependía del color). El «patrón en F» de NN/g describe cómo se escanea un
texto **sin** estructura: no es una meta, es el aviso de poner lo importante
al principio de cada título y renglón.

**En Core Tienda:** el calendario tiene «Conectar mi calendario» y «Nueva
acción» con el mismo botón lleno (H-029): la principal es «Nueva acción», la
otra pasa a secundaria. En Mis tareas, «1 vencida · 2 esta semana» en una
línea, con «vencida» en rojo, dice más que dos pastillas de color.

**Errores típicos:** jerarquía solo por tamaño; tres colores de botón en la
misma barra (Revisar, informe §3.2); un ícono con degradé que le gana al
título; todo en negrita.

## 2. Agrupar sin cajas (Gestalt)

Los principios de la psicología de la Gestalt (Wertheimer, Köhler, Koffka)
explican qué ve el ojo como «un grupo». Usalos del más barato al más caro:

| Principio | Qué dice | Cómo se usa acá |
|---|---|---|
| Proximidad | lo cercano se lee junto | El más barato. Adentro de un grupo, menos espacio que entre grupos: etiqueta y campo a 8 px, campos del mismo grupo a 16, secciones a 32 |
| Semejanza | lo que se ve igual se entiende igual | Un mismo botón principal en todas partes; dos estilos (degradé y liso, H-017) parecen dos cosas distintas |
| Alineación y continuidad | lo alineado se lee relacionado | Un borde izquierdo común ordena sin líneas ni cajas |
| Región común | un borde o fondo agrupa | El más caro: suma ruido. Solo si la proximidad no alcanza. Caja dentro de caja = ruido sobre ruido |
| Figura y fondo | lo de adelante se separa del fondo | Una ventana se separa con un velo gris liso, sin desenfoque |
| Aislamiento (efecto Von Restorff) | lo distinto se ve primero y se recuerda | Para **una** cosa por pantalla (el botón principal, lo vencido). Cinco cosas distintas = ninguna |

**En Core Tienda:** el tablero con una columna de cada color pastel rompe la
semejanza (todas son lo mismo: estados) y gasta la atención; van todas en el
mismo gris, con un puntito de estado. En la ficha de una acción, las tareas
como tarjetas celestes con borde índigo pasan a filas separadas por una línea.

## 3. Espaciado y ritmo (escala de 4 y 8)

- Base de 4 px, pocos valores y siempre los mismos: 4 · 8 · 12 · 16 · 24 · 32
  (48 y 64 para separar bloques grandes). Material trabaja sobre una grilla de
  8 dp, y Carbon y Atlassian definen el espacio en tokens con pasos de 4 y 8:
  lo que importa es la escala, no el número mágico.
- En Tailwind, 1 = 4 px: la escala es `1, 2, 3, 4, 6, 8` (y `12`, `16`).
  Desconfiá de `2.5`, `3.5`, `5`, `7` y de los corchetes (`p-[13px]`).
- Ritmo: la misma relación, la misma distancia. Título de pantalla → 24 →
  contenido; título de sección → 12 → lo suyo; entre secciones, 32.
- El relleno de un componente es menor o igual que el espacio que lo separa
  de sus vecinos.
- Empezá con más aire y sacá (*Refactoring UI*: «empezá con demasiado espacio
  en blanco»). Ivan, 19/11/2026: «el espacio libre da tranquilidad».
- Pero en una herramienta el aire tiene costo: en 1366×768 lo importante entra
  sin bajar (criterio 10). Aire entre grupos, no adentro de las filas de datos.

**Errores típicos:** 12, 14, 18 y 22 px en la misma pantalla; la misma
distancia entre todo (nada se agrupa); tarjetas enormes con poco adentro
(Finanzas); texto que toca el borde (Materiales, H-002).

## 4. Tipografía para pantallas

- **Una familia:** Inter, hecha para pantalla y con cifras tabulares, cargada
  una vez (hoy entra dos: `next/font` y un `@import` en `globals.css`).
- **Escala corta:** 22 título · 16 sección · 14 texto · 12 etiquetas (16 en
  campos del celular). Material 3 define 15 estilos para cubrir cualquier app;
  una herramienta como esta se arregla con cuatro. El 22 no existe en Tailwind
  por defecto: va como token en la configuración, no como `text-[22px]`.
- **Dos pesos**, 400 y 600, y **nada debajo de 12 px** (la auditoría contó
  419 usos de 9 a 11 px).
- **Interlineado** cerca de 1,5 en texto de corrido, 1,2–1,3 en títulos; que
  aguante si la persona agranda el espaciado (WCAG 1.4.12).
- **Largo de línea:** 45 a 75 caracteres para leer (Bringhurst); ayudas y
  formularios con ancho máximo (`max-w-prose`).
- **Sin mayúsculas espaciadas** en etiquetas y estados («HERRAMIENTAS»,
  «SUPER ADMIN»: 108 usos): se leen peor y gritan. Las siglas, sí (ZIP, IVA).
- **Mayúscula solo al principio** («Nueva acción», no «Nueva Acción»), como
  recomiendan Material y la guía de estilo de Microsoft.
- **Números** con `tabular-nums` en tablas, precios y contadores; en columnas,
  a la derecha.
- **Cortar con «…» solo lo accesorio.** Lo que identifica (mundo, agencia,
  responsable) va entero o en dos renglones (H-004, H-022).

**Errores típicos:** 13, 14 y 15 px que no se distinguen; gris clarito «por
elegancia»; títulos en mayúscula cortados (calendario de Redexpres, H-068).

## 5. Color con criterio

- **Un acento.** El azul de Tienda Inglesa (`#0047BA`, 8,0:1 sobre blanco)
  quiere decir «tocá acá / estás acá». Si aparece en algo que no se toca,
  pierde valor.
- **Grises neutros para todo lo demás.** Los «slate» de Tailwind tiran a azul
  y compiten con el azul de la marca; la dirección es pasar a neutros.
- **Estados con significado fijo:** rojo = vencido, error, borrar, cambios
  pedidos; verde = aprobado; ámbar = esperando. Ivan lo confirmó con un caso:
  lo que falta en una entrega no podía ir en azul porque «que sea azul da
  impresión de estar bien» (24/11/2026).
- **Color de datos** (mundos, acciones, categorías): un puntito o una rayita,
  no un fondo (el amarillo flúo de Redexpres, H-068).
- **El color se gana:** si la respuesta a «¿qué significa?» es «para que se
  vea lindo», va en gris. Y **nunca solo el color** (WCAG 1.4.1): puntito +
  palabra, rojo + «Vencida».
- **Medí, no estimes:** `slate-400` sobre blanco da 2,56:1 (no pasa),
  `slate-500` 4,76:1 (justo), `#52525B` 7,7:1 (cómodo). El rojo del logo da
  3,86:1: sirve para el logo, no para texto chico; por eso el rojo de interfaz
  es `#C81E2B` (5,7:1).

**Errores típicos:** el índigo de fábrica; un color por categoría (las 18
pastillas de cadenas en Precios); fondos pastel por estado; colores de Meta o
Google como adorno fuera de sus gráficos; rojo para algo que no es un problema
(una falsa alarma enseña a ignorar el rojo).

## 6. Densidad en una herramienta de trabajo

- Core Tienda se usa todos los días: la densidad justa es «todo lo necesario
  para decidir sin bajar, y nada más».
- Carbon (IBM) distingue estilos **productivos** (interfaz de trabajo) y
  **expresivos** (marketing, editorial). Core Tienda es productiva casi
  entera: el login no es un folleto.
- Se decide por pantalla: calendario y tablas, densos (filas de 40 px); fichas
  y formularios, con aire; al revisar una pieza, la imagen grande y aire
  alrededor (Ivan, 19/11/2026).
- **Divulgación progresiva** (NN/g): lo que se usa poco, plegado, como las
  versiones viejas «en versión minimalista, cerraditas» que pidió Ivan
  (19/11/2026).
- **Tableros de datos** (Clientes VIP, Medios): Edward Tufte pide sacar la
  tinta que no es dato (fondos, cuadrículas fuertes, 3D, íconos en los
  indicadores). Un número, su etiqueta gris y su comparación alcanzan. Para
  los gráficos, usá el skill `dataviz` si está disponible.
- **Cómo se mide:** en 1366×768 lo principal entra sin bajar; en 390×664 lo
  principal y su botón entran en la primera pantalla.

**Errores típicos:** un párrafo de tres renglones sobre cómo arrastrar arriba
del tablero; el tablero en el celular con el título en 8 renglones y ninguna
tarjeta a la vista (H-052).

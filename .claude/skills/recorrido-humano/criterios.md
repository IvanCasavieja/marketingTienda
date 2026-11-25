# Cómo mira una persona: criterios para juzgar una pantalla de Core Tienda

## El principio

**Usá el código para moverte y la captura para juzgar.**

Vos podés leer IDs, clases, `aria-label` y el HTML entero. Una persona no:
ve forma, color, tamaño, posición y palabras, en una notebook con luz de
oficina o en el celular entre dos cosas. Por eso:

- Todo juicio sale de **mirar la captura** (`ver`), no del código.
- Si para encontrar algo necesitaste `elementos`, `texto` o leer el código,
  una persona probablemente no lo encuentra: **eso ya es un hallazgo**.
- Si `click "Texto"` no encuentra lo que buscabas por lo que dice, y la
  persona tendría que adivinar un ícono, también.
- Lo que miden los chequeos automáticos (contraste, letra chica, desborde) es
  una pista. Confirmalo en la captura antes de anotarlo.

## La prueba de los 5 segundos (en cada pantalla)

Mirá la captura como si fuera la primera vez y contestá:

1. ¿Dónde estoy? (título, menú marcado, mundo)
2. ¿Qué es lo más importante acá?
3. ¿Qué puedo hacer?
4. ¿Qué hago ahora? (¿hay UNA acción principal clara?)

Si alguna no tiene respuesta clara en 5 segundos, anotalo.

## Para quién se mira

| Persona | Dónde y cómo | Qué quiere | Qué la frustra |
|---|---|---|---|
| **Analista de promo y marca** (el equipo de Tienda) | Notebook de 14" (1366×768), luz de oficina, ojos cansados, muchas acciones a la vez, apurada. No es técnica. | Cargar acciones, pedir piezas a la agencia, revisar entregas, saber qué le toca hoy. | Buscar cosas, pasos de más, no saber si algo se guardó, textos chicos o grises. |
| **Diseñador/a de una agencia externa** (Publicis, Another Monday, «Diseñadores») | Notebook o celular. Entra a entregar, no a pasear. | Saber qué le pidieron, para cuándo y con qué medidas; entregar rápido; saber qué le corrigieron. | Pedidos ambiguos, no saber si la entrega llegó, ver cosas que no le tocan. |
| **Encargado/a de un local de Redexpres** | Celular, en el local, con poco tiempo. | Cargar el pedido del mes y la foto de colocación. | Letra chica, campos que no se ven con el teclado abierto, perder lo escrito. |
| **Jefatura (Ivan)** | Notebook y celular. | Ver el panorama, aprobar, administrar usuarios y permisos. | Lo que se ve poco profesional, lo que traba al equipo. |

## Lo que se mira en cada pantalla (14 puntos)

1. **Orientación.** Título claro, el menú marca dónde estás, el mundo se ve
   entero (no «Tienda In…»).
2. **Jerarquía.** Lo importante se ve primero (tamaño, peso, color,
   posición). Hay **una** acción principal destacada; no compiten tres
   botones de color.
3. **Lectura.** Textos completos (lo importante no se corta con «…»), letra
   de 12 px como mínimo (14 para leer de corrido), contraste de 4,5:1 como
   mínimo. La gente trabaja con luz de oficina y ojos cansados: el gris
   clarito sobre blanco no se lee.
4. **Palabras.** Castellano rioplatense, con las palabras de la gente
   (acción, tarea, pieza, entrega, ronda, tablero, local). Nada de jerga ni
   inglés suelto («jobs», «upload», «status», «Retail Media» si nadie lo dice
   así). Lo mismo se llama igual en todas las pantallas.
5. **Qué se puede tocar.** Lo que se toca parece tocable. Íconos solos
   únicamente si se entienden sin explicación (✕ cerrar, 🔍 buscar). En el
   celular, 44 px para el dedo.
6. **Respuesta.** Cada acción dice qué pasó (aviso, cambio visible). Lo que
   tarda muestra que está trabajando. Un doble clic no manda dos veces.
7. **Estados.** Vacío (explica qué va ahí y ofrece la primera acción),
   cargando, error (qué pasó y qué hacer, en criollo, sin códigos), sin
   permiso, sin conexión.
8. **Errores evitables.** Lo que borra pide confirmación o se puede
   deshacer. La validación aparece al lado del campo. Nunca se pierde lo
   escrito.
9. **Consistencia.** Mismos componentes, colores y posiciones que las
   pantallas hermanas. El botón principal se ve igual en todos lados.
10. **Densidad.** Ni apretado ni espacio muerto. En 1366×768 lo importante
    entra sin bajar. Las tablas se leen.
11. **Celular.** Nada se sale de costado, lo principal se alcanza con el
    pulgar, el teclado no tapa el campo, las hojas y modales se cierran.
12. **Modo oscuro.** El mismo contraste, nada que desaparezca (bordes,
    íconos, separadores), los logos y las imágenes se leen.
13. **Velocidad que se siente.** Menos de 1 s es instantáneo. Más de 3 s
    necesita indicación. Más de 6 s es un hallazgo.
14. **El flujo.** Después de hacer algo, ¿la pantalla lleva a lo siguiente
    lógico? ¿Cuántos pasos lleva la tarea? ¿Hay que ir y volver entre
    pantallas? ¿Lo que hace uno (el equipo) le llega bien al otro (la
    agencia)?

## Gravedad

| | Qué es | Ejemplos |
|---|---|---|
| 🔴 **Bloquea** | La persona no puede hacer su tarea, pierde datos o ve algo que no debería. | Error al guardar, la agencia entra a precios, el pedido se guarda mal. |
| 🟠 **Traba** | Puede, pero duda, se equivoca fácil o hace pasos de más. | Botón principal escondido, sin aviso de que se guardó, cinco clics para algo diario. |
| 🟡 **Desprolijo** | Se nota poco profesional. | Textos cortados, contraste justo, desalineados, el mismo botón con dos estilos. |
| ⚪ **Detalle** | Pulido. | Un ícono que podría ser más claro. |

**Para elegir qué hacer:** gravedad × cuánta gente lo sufre × cuán seguido
÷ esfuerzo. Un 🟠 que el equipo sufre todos los días le gana a un 🔴 en una
pantalla que no usa nadie.

## Cómo se anota un hallazgo

Cada hallazgo es algo que una persona notaría, contado como lo contaría ella,
con la prueba:

```
### <Título corto en criollo: lo que le pasa a la persona>
- Gravedad: 🔴 / 🟠 / 🟡 / ⚪   ·   Quién: <persona>   ·   Dónde: <pantalla `ruta`>, <vista: notebook/celular, claro/oscuro>
- Qué ve una persona: <lo que se ve en la captura, sin código>
- Por qué importa: <qué le cuesta: tiempo, errores, confianza>
- Cómo repetirlo: <pasos con la cuenta y los datos>
- Evidencia: <captura(s)>; <medida automática si la hay>
- Idea de arreglo: <una línea; opcional>
```

No vale: «el botón no tiene aria-label» a secas. Sí vale: «hay un ícono de
engranaje sin texto arriba a la derecha; no se sabe qué hace hasta tocarlo
(y los lectores de pantalla tampoco lo nombran)».

## Antes y después

Toda mejora que cambia una pantalla lleva captura **antes** y **después**,
en las mismas vistas (notebook claro y celular claro como mínimo; oscuro si
tocó colores). Sin eso no se puede juzgar.

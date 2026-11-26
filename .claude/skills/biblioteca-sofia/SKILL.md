---
name: biblioteca-sofia
description: La biblioteca profesional de Sofía, la analista del Escuadrón Lechuza — los métodos públicos más reconocidos de descubrimiento continuo, investigación de usuarios, priorización, métricas, Forward Deployed Engineering y producto B2B, convertidos en pasos para Core Tienda. Usala antes del recorrido (qué mirar y cómo), al anotar y consolidar hallazgos, al elegir la propuesta de la noche, al cuestionar un pedido y cuando los datos dicen algo distinto de lo decidido.
---

# Biblioteca de Sofía

Ivan pidió que cada integrante del Escuadrón Lechuza sea un profesional de
primer nivel. Los cursos privados no se copian, pero sus métodos están en
libros, papers y guías públicas (Google, Meta, IBM, Amazon, Toyota, Palantir,
Anthropic, Intercom, Basecamp). Acá están destilados y bajados a Core Tienda:
qué es cada método, de quién es, cómo se usa acá y en qué trampa se cae.
Cada uno cita a su autor (y obra y año, cuando los hay); no hay cifras ni
citas inventadas, y lo que es inferencia de Sofía o ejemplo armado, lo dice.

Este archivo es la hoja de bolsillo; las referencias tienen el detalle, y se
vuelve a ellas en el momento que las pide (tabla de abajo). No reemplaza a tu
archivo de agente, a los skills del recorrido y del cuaderno ni a
`docs/equipo-nocturno/CRITERIO.md`: los formatos (hallazgo, RECORRIDO,
PROPUESTA) siguen siendo esos; esto es el oficio para llenarlos bien.

## La vara en nueve frases

1. **Ir a ver:** la pantalla manda; el código y el mapa son sospechas
   (Toyota: *genchi genbutsu*, «andá y mirá con tus ojos»).
2. **Problema antes que solución:** una idea sin persona ni momento es una
   ocurrencia (Torres, Christensen).
3. **Lo que la gente hace pesa más que lo que dice**, y lo que pasó, más que
   lo que «pasaría» (Fitzpatrick).
4. **Cada afirmación con su etiqueta:** hecho, inferencia u opinión.
5. **Resultado, no producción:** un resultado es un cambio en lo que hace una
   persona (Josh Seiden, *Outcomes Over Output*, 2019), no un PR. Una noche
   sin cambios con un buen recorrido no es un fracaso.
6. **Elegir es renunciar:** una cosa terminada por noche y un «no» con
   motivo para todo lo demás.
7. **Medir lo justo:** primero lo que ya existe; flujos, nunca personas.
8. **Lo general antes que lo particular:** nada de casos especiales.
9. **Respeto con columna vertebral:** lo que decide Ivan se respeta y se
   estudia; si los datos dicen otra cosa, se dice una vez, con datos y con
   una salida compatible con su motivo.

## Qué abrir y cuándo

| Momento | La pregunta | Métodos | Dónde |
|---|---|---|---|
| Antes del recorrido | ¿Qué quiero aprender hoy? | Árbol de oportunidades, JTBD, mapa del trabajo | [descubrimiento.md](referencias/descubrimiento.md) §1-2 |
| Durante el recorrido | ¿Cómo observo sin engañarme? | Observación contextual, análisis de tareas, brechas de Norman | [descubrimiento.md](referencias/descubrimiento.md) §4, [investigacion.md](referencias/investigacion.md) §2-3 |
| Consignas de Martina | ¿Cómo no le doy pistas? | Mom Test, tareas de usabilidad | [descubrimiento.md](referencias/descubrimiento.md) §3, [investigacion.md](referencias/investigacion.md) §1 |
| Anotar y consolidar | ¿Está bien escrito? ¿Es síntoma o causa? ¿Cuánto le creo? | Formato del hallazgo, triangulación, 5 porqués, Ishikawa | [investigacion.md](referencias/investigacion.md) §4-7 |
| Elegir | ¿Qué conviene esta noche? | Fórmula de la casa, RICE, costo de demora, Kano, apetito | [priorizacion.md](referencias/priorizacion.md) |
| Proponer | ¿Cómo sabremos que funcionó? | HEART, North Star, criterios de éxito | [metricas.md](referencias/metricas.md) |
| Bajar a tierra | ¿Qué versión entra terminada? | FDE, SPIDR, prototipos sin código | [fde-y-b2b.md](referencias/fde-y-b2b.md) §1-2 |
| Agencias y locales | ¿Funciona entre empresas? | Grudin, mínimo privilegio, adopción | [fde-y-b2b.md](referencias/fde-y-b2b.md) §3-6 |
| Un pedido o una decisión | ¿Qué problema resuelve? ¿Lo planteo? | Criterio propio | [criterio-propio.md](referencias/criterio-propio.md) |

## La noche con método

### 1. Antes de recorrer: hipótesis, no paseo (5 min)

- Leé el cuaderno como un árbol de oportunidades: arriba, la vara de
  CONTEXTO.md; abajo, los hallazgos agrupados por lo que le pasa a la gente.
- Para la zona del día escribí **de una a tres hipótesis** que la pantalla
  pueda confirmar o tirar (de los «puntos a mirar» del mapa, el cuaderno y
  los pedidos). Ej.: «al local se le pierde el campo de cantidad cuando abre
  el teclado». Decidí antes qué tendrías que ver para darla por falsa: si
  nada te haría cambiar de idea, no es una hipótesis.

### 2. Recorrer como aprendiz

- Sos la persona: su dispositivo, su luz, su apuro, su objetivo (tareas.md)
  y datos realistas (un mes con varias acciones, no una sola).
- En cada paso importante anotá **intentaba**, **esperaba** y **pasó**: diez
  segundos que después son el hallazgo.
- Clasificá la traba (Norman): no supe **qué hacer** o no supe **qué pasó**.
  Contá pasos, decisiones, idas y vueltas, esperas de más de 3 s y dudas de
  «¿se guardó?».
- Cada vez que una cuenta hace algo, mirá qué le llegó a la otra: los
  traspasos entre equipo, agencia y local son donde más se pierde.

### 3. Consignas para Martina

- Persona + situación + objetivo + cuándo está logrado, en sus palabras;
  nunca el camino. Si sospechás un problema de palabras, no uses la del
  botón: «mandales la versión corregida», no «Entregar ronda 2».
- Una consigna pone a prueba una hipótesis del paso 1; la otra va adonde
  una persona nueva podría trabarse y nadie miró todavía.

### 4. Anotar y consolidar

- «Qué ve una persona» arranca por lo que intentaba («Intentando entregar la
  corrección, …»), con verbos que se ven en la captura y no con juicios
  («es confuso»). La causa sospechada va en **Idea de arreglo** («Causa: …;
  arreglo: …»).
- Lo que vieron dos fuentes independientes (vos y Martina, dos cuentas, un
  pedido real) vale más que lo visto una vez. Si Martina se trabó donde vos
  pasaste de largo, gana Martina: vos ya conocés demasiado la plataforma.
- Agrupá por flujo y por causa: ahí aparecen los paquetes.

### 5. Elegir en cinco minutos

1. **Filtro duro:** «Ya decidido: NO proponer», Descartados, ramas o PR
   abiertos y lo que no se puede probar acá.
2. **Puntaje** de los diez primeros: gravedad × gente × frecuencia ×
   confianza ÷ esfuerzo (escalas en priorizacion.md).
3. **Ajustes:** fecha fija cerca, básico roto, paquete del mismo flujo,
   pedido de Ivan (va primero).
4. **Apetito:** ¿qué versión entra terminada en una noche? Si ninguna,
   recortá o pasá a la siguiente.
5. **Una propuesta y dos reservas**, con el porqué en números.

### 6. Proponer

- **Necesidad:** quién, en qué momento, qué le pasa y qué le cuesta, con la
  captura.
- **Cómo se va a notar:** el comportamiento que cambia («la agencia entrega
  la corrección sin preguntar qué le marcaron»), no el código, y cómo se
  comprueba esta noche (antes/después, menos pasos, Martina la logra).
- **Pre-mortem de un minuto** (Gary Klein): si Tomás la frenara, Ivan dijera
  que no o nadie la notara, ¿por qué sería? Arreglalo antes o elegí otra.

## Antes de decir que sí

1. ¿Qué problema resuelve, contado como lo contaría la persona?
2. ¿Para quién? ¿Cuánta gente y cada cuánto?
3. ¿Cómo lo resuelve hoy? (Si nadie lo sufre ni lo esquiva, ojo.)
4. ¿Qué evidencia hay: lo vi, me lo contaron o lo supongo?
5. ¿Cómo sabremos que funcionó?
6. ¿Qué dejamos de hacer por hacer esto?
7. ¿Choca con algo decidido o con las reglas que no se discuten?

**Señales de alarma:** «estaría bueno que…» sin un caso concreto; una
solución disfrazada de problema («falta un botón de X»); una propuesta sin
persona, pantalla o captura; contar el éxito en PR (la trampa de
construir); creer que el hallazgo de recién es el más grave (sesgo de
disponibilidad); elegir lo fácil de construir en vez de lo que importa
(buscar las llaves bajo el farol porque ahí hay luz); un arreglo para una
sola persona o agencia; reabrir lo decidido sin datos nuevos.

# Investigación de usuarios: observar bien, anotar bien, no engañarse

## 1. Pruebas de usabilidad

**Qué es.** Una persona hace una tarea realista mientras piensa en voz alta,
y se mira dónde se traba. El protocolo de pensar en voz alta lo llevó al
diseño de interfaces Clayton Lewis, en IBM (1982). Jakob Nielsen mostró que
rinden más muchas rondas chicas: con unas cinco personas por ronda aparece
la mayoría de los problemas (Nielsen y Landauer, 1993; «Why You Only Need to
Test with 5 Users», 2000), siempre que personas y tareas se parezcan a las
reales. Steve Krug (*Rocket Surgery Made Easy*, 2009) propone pruebas
caseras, cortas y frecuentes.

**En Core Tienda**, la prueba a ciegas de Martina es una prueba de
usabilidad con una participante simulada y dos tareas por noche.
- **Buena tarea:** persona + situación + objetivo + cuándo está logrado; sin
  camino y, si se prueban palabras, sin las palabras de la pantalla.
- **Qué se mide:** resultado (logrado, con dificultad, abandonado), pasos,
  dónde se trabó y sus frases textuales («busco algo que diga Entregar y no
  lo veo»), que son la mejor evidencia de la noche.
- **Muchas noches son muchas rondas:** lo que se repite es un patrón; lo que
  pasó una vez, un caso.
- **Límites (decilos siempre):** Martina no tiene la historia de la persona,
  no se cansa, no tiene atajos ni un jefe esperando. Encuentra problemas de
  descubrimiento, lectura y respuesta de la pantalla, no de motivación ni de
  contexto. «Martina lo logró» prueba que una persona nueva puede, no que a
  la gente le sirva.

## 2. Análisis de tareas

**Qué es.** El análisis jerárquico de tareas (HTA; John Annett y Keith
Duncan, 1967) parte un objetivo en subtareas y operaciones, con un plan de
orden y condiciones. GOMS y su modelo de pulsaciones (KLM; Stuart Card,
Thomas Moran y Allen Newell, *The Psychology of Human-Computer Interaction*,
1983) estiman cuánto tarda una tarea sumando teclear, apuntar y pensar.

**En Core Tienda** no hace falta cronometrar. Por tarea contá **pasos**
(clics y escritura), **decisiones** (elegir entre opciones cuesta más que un
clic), **idas y vueltas** entre pantallas, **esperas** (más de 3 s piden
aviso; más de 6 s son hallazgo, criterios.md punto 13) y **memoria** (tener
que acordarse de algo de otra pantalla: mejor reconocer que recordar).

Ejemplo de HTA, «pedir banners para una acción» (analista; sale del ciclo de
tareas.md y del mapa):

```
0. Pedir banners para la acción «Ciberlunes»
   1. Encontrar la acción en el calendario y abrir su ficha
   2. Pestaña Tareas → «Crear tarea»
   3. Completar: qué se pide (Banners + opciones) → quién la hace →
      detalle, adjunto, responsable de Tienda, fecha
   4. Confirmar que nació la tarjeta y que la agencia la ve
   Plan: 1 → 2 → 3 → 4. Si la acción no existe, crearla antes de 1.
```

Contar lo mismo antes y después de una mejora da el antes/después en números
(«de 14 pasos y 4 decisiones a 9 y 2», por poner un ejemplo).

## 3. Diagnóstico: ¿dónde se rompió? (Norman y Nielsen)

En *The Design of Everyday Things* (1988; revisado en 2013), Don Norman
separa la **brecha de ejecución** (no sé cómo hacer lo que quiero) de la
**brecha de evaluación** (no sé qué pasó ni en qué estado está). Clasificá
cada traba **antes** de imaginar el arreglo:

| La persona… | El problema es de… | El arreglo va por… |
|---|---|---|
| No lo encontró | Descubrimiento | Ubicación, jerarquía, una acción principal |
| No entendió qué hace | Señales y palabras | Texto visible, palabras de la gente |
| Lo hizo mal | Restricciones | Prevenir, confirmar, poder deshacer |
| No supo si funcionó | Respuesta | Aviso, cambio visible, estado |
| No entendió cómo funciona | Modelo conceptual | Explicar el concepto (qué es una ronda, quién aprueba) |

No se arregla con un cartel un problema de modelo, ni con un rediseño lo que
era una palabra. Las diez heurísticas de Jakob Nielsen (1994; la evaluación
heurística es de Nielsen y Rolf Molich, 1990) son el vocabulario del oficio y
los 14 puntos de criterios.md las cubren: nombrarlas en la «Idea de arreglo»
(«visibilidad del estado») ayuda a ver el patrón detrás del caso.

## 4. Gravedad sin contar dos veces

Nielsen califica la gravedad por frecuencia, impacto y persistencia (si se
supera una vez o molesta siempre). En la casa, **la frecuencia y la cantidad
de gente ya están en la fórmula de prioridad**: la gravedad es el impacto
(🔴 no puede, pierde datos o ve lo que no debe; 🟠 duda o hace pasos de más;
🟡 se nota poco profesional; ⚪ pulido), ajustado por persistencia. Si metés
la frecuencia en la gravedad, la contás dos veces.

## 5. Triangulación: cuánto creerle a un hallazgo

Norman Denzin (*The Research Act*, 1970) propuso cruzar datos, investigadores
y métodos para que una conclusión no dependa de una sola mirada. La noche ya
trae los tres: métodos (barrido, tarea real, prueba a ciegas), investigadoras
(Sofía, Martina, Lucía) y datos (tres cuentas, cuatro vistas, pedidos
reales). **Escalera de evidencia**, de más fuerte a más débil:

1. Una persona real lo contó o lo pidió, y se reproduce en la pantalla.
2. Lo vieron dos fuentes independientes (vos y Martina; dos cuentas o vistas).
3. Lo viste vos en la captura, con pasos que lo repiten.
4. Una alerta del barrido todavía sin mirar en la captura.
5. Una sospecha del mapa o del código.

Solo 1 a 3 entran al cuaderno (nada sin prueba); 4 y 5 son pistas. Si chocan
una alerta y la captura, gana la captura; si Martina se trabó y vos no, gana
Martina para «persona nueva». Un pedido real se vuelve hallazgo cuando lo
reproducís: la evidencia es el pedido (quién, fecha, frase textual) más la
captura de cómo está hoy esa pantalla.

## 6. Cómo se escribe un hallazgo

La investigación «atómica» (Tomer Sharon, ex Google, y Daniel Pidcock)
separa lo que se hizo, lo que se **encontró**, lo que se **interpreta** y lo
que se **recomienda**: mezclarlos es la forma más común de colar una opinión
como hecho. Las cinco piezas, en el formato del cuaderno:

| Pieza | Campo del cuaderno | Cómo se escribe |
|---|---|---|
| Quién | Quién · Dónde | Persona, pantalla con ruta y vista |
| Qué intentaba | Arranque de «Qué ve una persona» | «Intentando entregar la corrección, …» |
| Qué pasó | «Qué ve una persona» | Lo que muestra la captura, con verbos observables |
| Evidencia | Evidencia · Cómo repetirlo | Captura marcada, pasos, cuenta, datos, frase de Martina |
| Impacto | Por qué importa · Gravedad | En la moneda de la persona: tiempo, errores, confianza, idas y vueltas con la otra empresa |

Un hallazgo = un problema de una persona en un lugar; el título es lo que le
pasa a ella, no lo que le falta al código. Nada de «es confuso» ni «no es
intuitivo»: es una conclusión; mostrá el hecho que te llevó a ella.

Mal: «Campanita con bug · 🔴 · todos · el catch de Campanita.tsx deja la lista
vacía» (habla de código, no dice a quién le pasa ni qué intentaba, y la
gravedad está inflada). Bien, armado con una **sospecha** del mapa
(`calendario-tareas-entregas.md`, Campanita; no es hallazgo hasta verlo):

```
### H-0xx · Si los avisos no cargan, la campanita dice que no hay ninguno
- **Gravedad:** 🟠 Traba · **Quién:** agencia (también el equipo) · **Dónde:** campanita, notebook claro
- **Qué ve una persona:** intentando ver si le pidieron cambios, abre la campanita y lee «Todavía no tenés notificaciones», aunque tiene un aviso sin leer: la lista no cargó.
- **Por qué importa:** un error se ve como «no hay nada»: la agencia no corrige, el equipo espera y nadie se entera de la falla.
- **Cómo repetirlo:** cuenta de agencia con un aviso sin leer; frenar el servidor; abrir la campanita.
- **Evidencia:** captura marcada + `errores` del navegador con el pedido fallido.
- **Idea de arreglo:** Causa: el error de carga se muestra como lista vacía. Arreglo: un estado de error propio («No pudimos traer tus avisos. Reintentar»).
- **Visto:** <fecha>
```

## 7. Síntoma o causa raíz

**Los 5 porqués** vienen de Sakichi Toyoda, y Taiichi Ohno los volvió
práctica en Toyota (*Toyota Production System*, 1978): preguntar «¿por
qué?» hasta una causa sobre la que se puede actuar. Arrancá del hecho, no de
una solución; que cada respuesta se pueda comprobar (captura, mapa o
código); se vale abrir ramas; pará cuando llegues a algo que el código puede
cambiar; y nunca termines en «la persona se equivocó»: si es fácil
equivocarse, la causa es de diseño (Norman).

Ejemplo de método con un caso que el mapa ya documenta (si es prioridad lo
decide la fórmula: hace falta alguien que lo sufra):

```
Síntoma: el equipo no encuentra a una agencia nueva en «¿Quién la hace?».
¿Por qué? La lista ofrece solo tres tableros (Publicis, Another Monday, «Diseñadores»).
¿Por qué? Esos tableros están fijos en el código (backend/app/core/tableros.py).
Causa accionable: sumar una agencia pide tocar código, aunque su cuenta externa ya exista.
Arreglo del síntoma: agregar esa agencia a mano a la lista.
Arreglo de la causa: que la lista salga de las empresas de las cuentas externas
(las plantillas ya lo hacen así).
```

**El diagrama de Ishikawa** (Kaoru Ishikawa, la «espina de pescado») ordena
las causas posibles por categorías. Para Core Tienda:

| Categoría | Preguntas |
|---|---|
| Pantalla | ¿Jerarquía, texto, contraste, ubicación? |
| Flujo | ¿Pasos de más, orden, idas y vueltas, traspaso entre cuentas? |
| Permisos y alcance | ¿Rol, permisos, mundo, alcance, cuenta externa? |
| Datos y estados | ¿Vacío, cargando, error, datos que no llegan? |
| Avisos | ¿Campanita, mail, aviso en pantalla: le llega al otro? |
| Entorno | ¿Celular, Safari, red, servidor dormido, IA simulada en pruebas? |
| Reglas y decisiones | ¿Lo decidido por Ivan, los límites gratis (500 MB, mails)? |
| Personas y hábitos | ¿Lo que traen de antes, lo que nadie les explicó? |

Usalo cuando un problema tiene varias causas posibles o para armar un
paquete: los hallazgos son las espinas; la categoría con más espinas es
donde probablemente está la causa, y un arreglo ahí resuelve varios juntos.

# Priorizar con criterio y decir que no

Priorizar es decidir qué **no** se hace. Cada noche entra una sola cosa
terminada; todo lo demás espera, con su motivo escrito.

## 1. La fórmula de la casa, con escalas

criterios.md y el cuaderno ordenan por **gravedad × cuánta gente × cuán
seguido ÷ esfuerzo**. Para que dos noches distintas ordenen igual, usá estas
escalas y sumá la **confianza**, que viene de RICE (§2):

| Factor | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| Gravedad | ⚪ Detalle | 🟡 Desprolijo | 🟠 Traba | 🔴 Bloquea |
| Gente | Una persona o un rol chico (jefatura, admin) | Un grupo: un equipo, una agencia, la gente de Redexpres | Muchos o entre empresas: todo promo y marca, todas las agencias, todos los locales | — |
| Frecuencia | Mensual o menos | Semanal, o en cada pedido | Todos los días, o cada vez que entra | — |
| Esfuerzo | Chico: textos, un estado, una pantalla | Mediano: varias pantallas del mismo flujo, o pantalla + servidor | Grande: no entra terminado en una noche (se recorta o no va) | — |

**Confianza:** 1 si lo vieron dos fuentes o es un pedido real que se
reproduce; 0,8 si lo viste vos con pasos; 0,5 si pasó una vez y no se
repitió.

**Prioridad = Gravedad × Gente × Frecuencia × Confianza ÷ Esfuerzo**

Con la misma confianza y el mismo esfuerzo se cumple lo que pide
criterios.md: un 🟠 que todo el equipo sufre a diario (3 × 3 × 3 = 27) le
gana a un 🔴 en una pantalla que casi nadie usa (4 × 1 × 1 = 4). Son números
para **ordenar y explicar**, no mediciones: si el orden te parece absurdo,
revisá el puntaje; si el puntaje está bien, revisá tu intuición.

**Ajustes antes de elegir:**
- **Fecha fija cerca** (§3): si el problema pega en algo con fecha (la
  ventana del pedido del mes de los locales, un mega evento del
  calendario), sube mientras falte poco.
- **Básico roto** (§4): perder lo escrito, ver lo que no corresponde o no
  poder entregar va primero aunque empate.
- **Paquete:** los hallazgos del mismo flujo que se arreglan juntos suman
  sus puntajes y se dividen por el esfuerzo del paquete.
- **Pedido de Ivan:** va primero (README). Igual se puntúa, para poder decir
  qué desplaza.

## 2. RICE, ICE y la confianza que da la evidencia

Intercom (Sean McBride) difundió **RICE**: alcance (gente o eventos por
período) × impacto (3 masivo, 2 alto, 1 medio, 0,5 bajo, 0,25 mínimo) ×
confianza (100 %, 80 % o 50 %) ÷ esfuerzo (en persona-mes). La fórmula de la
casa es RICE adaptado (alcance = gente × frecuencia; impacto = gravedad):
usá el idioma de RICE cuando se lo expliques a alguien de afuera.

**ICE** (Sean Ellis) puntúa impacto, confianza y facilidad de 1 a 10 y los
combina (según la versión, en promedio o multiplicados). Es rápido para
ideas sin datos y fácil de inflar: la confianza puesta a ojo favorece a las
ideas propias. Por eso **Itamar Gilad** (ex Google, *Evidence-Guided*)
propone que la confianza la dé el **tipo de evidencia** y no el entusiasmo:
la convicción propia vale poco; la opinión de otros, algo más; los datos
anecdóticos, más; la evidencia de usuarios y los resultados de pruebas,
mucho más. Es la escalera de investigacion.md, §5: puntuá con ella.

## 3. Costo de demora

Don Reinertsen (*The Principles of Product Development Flow*, 2009) sostiene
que, si se va a cuantificar una sola cosa, sea el **costo de demora**:
cuánto se pierde por cada semana que algo no está. De ahí salen WSJF (costo
de demora ÷ tamaño, como lo usa SAFe) y CD3 (costo de demora dividido
duración, difundido por Joshua Arnold): lo que cuesta poco y pierde valor
rápido va primero. Las clases de servicio de Kanban (David J. Anderson,
*Kanban*, 2010) dan cuatro perfiles de urgencia:

| Perfil | Cómo pierde valor | En Core Tienda |
|---|---|---|
| Urgente | Cuesta desde ya | Algo que hoy impide entregar o deja ver lo que no corresponde |
| Fecha fija | Vale mucho hasta una fecha y después nada | Pedir y entregar piezas antes de un mega evento; la ventana del pedido del mes de los locales |
| Estándar | Cuesta parejo cada día | Una traba diaria en Mis tareas o en el tablero |
| Intangible | Barato hoy, caro mañana | Las pantallas viejas que se ven poco profesionales («pareja en todas partes») |

Mirá el calendario comercial antes de elegir: la misma traba en el pedido de
piezas no cuesta lo mismo una semana tranquila que antes de un evento grande.

## 4. Kano

Noriaki Kano (1984) clasifica las características por cómo mueven la
satisfacción: **básicas** (si faltan, enojan; si están, nadie lo nota), **de
desempeño** (cuanto más, mejor), **atractivas** (sorprenden, y con el tiempo
se vuelven básicas), **indiferentes** y **contraproducentes**.
- Básicas en Core Tienda: nada se pierde, cada uno ve solo lo suyo, cada
  acción avisa qué pasó, todo se lee bien (casi todas las reglas que no se
  discuten son básicas).
- De desempeño: menos pasos, más rapidez, saber en 10 segundos qué toca.
- Atractivas: el control previo de la IA antes de entregar, comparar rondas.
- Indiferentes: lo que nadie pidió ni sufre (CONTEXTO.md las descarta).
- Regla: nada atractivo mientras haya un básico roto en el mismo flujo.

## 5. Apetito antes que estimación (Shape Up)

En *Shape Up* (Basecamp, 2019), Ryan Singer da vuelta la pregunta: **tiempo
fijo, alcance variable**. Primero se decide cuánto vale el problema (el
apetito) y después se le da forma a una solución que entre, marcando los
agujeros donde uno se puede perder y lo que queda afuera a propósito. Acá el
apetito ya está fijo (una noche, unos 45 minutos de construcción): la
pregunta no es «¿cuánto tarda?» sino «¿qué versión entra terminada y se
nota?». El «Tamaño» de la propuesta va con lo que queda **afuera** escrito,
para que Tomás no tenga que descubrirlo.

## 6. Decir que no, y por qué

Steve Jobs lo planteó en la conferencia de desarrolladores de Apple de 1997:
enfocarse es decirle que no a muchas buenas ideas. Melissa Perri (*Escaping
the Build Trap*, 2018) llama «la trampa de construir» a medir el éxito por
lo que se entrega y no por lo que cambia. En Facebook colgaban carteles con
«Done is better than perfect»; acá es «mejor mediano y terminado que grande
y a medias» (README). Y Anthropic, en «Building effective agents» (2024),
recomienda empezar por la solución más simple y sumar complejidad solo
cuando mejora el resultado.

**Motivos válidos para un no:** choca con «Ya decidido: NO proponer» o con
una regla que no se discute; no hay una persona concreta que lo sufra; la
evidencia es floja (escalones 4 o 5); no entra terminado en una noche ni
tiene una versión chica que se note; hay algo con más puntaje; no se puede
probar en el entorno de pruebas; arregla el síntoma y deja la causa (va a
volver con otra forma); es un caso especial para una persona o una agencia.

**Cómo se dice:**

```
Esto no es prioridad esta noche porque <motivo, con el dato>.
Lo que sí hacemos: <lo elegido y por qué le gana>.
Para que sea prioridad haría falta: <evidencia o condición>.
Queda en <Abiertos | Descartados> con esta nota.
```

«No ahora» y «no» son distintos. Lo primero queda en Abiertos con su puntaje
y su nota. Lo segundo (Ivan dijo que no, o choca con lo decidido) va a
Descartados con el motivo y no se vuelve a proponer.

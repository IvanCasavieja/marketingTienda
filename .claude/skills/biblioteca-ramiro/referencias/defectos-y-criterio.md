# Defectos que se arreglan rápido, decidir y aprender

## Un ROTO que se arregla en una vuelta

Cem Kaner lo plantea en *Testing Computer Software* y en su curso *Bug
Advocacy*: el mejor tester no es el que más defectos encuentra, sino el que
logra que más se arreglen. Un reporte es un argumento con evidencia. La
receta del curso, RIMGEA: **replicá** (y decí cuántas
veces de cuántas), **aislá** (el mínimo de pasos y datos), **maximizá** (la
peor consecuencia del mismo defecto: ¿solo se ve mal o además guarda mal?),
**generalizá** (¿pasa en otras pantallas, cuentas, vistas?), **externalizá**
(lo que le pasa a la persona, no al código) **y decilo** claro y sin juicio.

El bloque es el de `ramiro-tester.md`, con cuatro líneas más que ahorran
una vuelta. El ejemplo es inventado, para mostrar el formato:

```
ROTO: La agencia B abre la tarjeta de la agencia A pegando su link
Dónde: /entregas?tarea=ta-… · GET /api/v1/calendario/tareas/{id}/entregas
Cuenta y vista: agencia B (creada en /admin), notebook
Pasos: 1. Equipo pide «QA 0213 Ciberlunes - Banners» a «Agencia de prueba».
       2. Como agencia B, abrir /entregas?tarea=<id de esa tarjeta>.
Esperado: «no la encontramos» (404) y nada de la tarjeta   Obtenido: 200, con el pedido y las imágenes
Evidencia: $S/romper/idor-1.png; curl con el token de B → 200 (salida sin el token)
Gravedad: 🔴   Para esta noche: bloquea VERDE   Frecuencia: 3 de 3
Pista (inferencia, no confirmada): el endpoint nuevo no pasa por el filtro de empresa
Para verificar el arreglo: repetir el paso 2 y la misma llamada con el token de B → 404
```

- **El título:** qué falla, dónde y en qué condición. Nunca «error en
  entregas», ni a quién culpar, ni la solución.
- **Hechos, inferencias y opiniones, separados** (`CRITERIO.md`): lo visto,
  en Obtenido y Evidencia; lo supuesto, en Pista y marcado así.
- **La evidencia:** la captura con su ruta, la salida recortada, el pedido
  (método, ruta, código), sin tokens ni contraseñas. Un defecto por bloque;
  cinco síntomas con una causa, un bloque que los nombra.
- Lo que ISTQB pide en un reporte de defecto (identificador, título, fecha y
  autor, objeto y entorno, pasos, esperado y obtenido, evidencia, severidad,
  prioridad, estado) queda cubierto; el H-0xx lo pone el cuaderno.

## Gravedad y prioridad no son lo mismo

**Gravedad:** cuánto daño le hace a la persona o a los datos (🔴 🟠 🟡 ⚪
de `criterios.md`). **Prioridad:** cuándo se arregla; para Ramiro, **esta
noche** (bloquea VERDE) o **al cuaderno**.

| | Esta noche | Al cuaderno |
|---|---|---|
| **Gravedad alta** | La rama deja que la agencia B vea una tarjeta de A: ROJO, vuelve a Bruno | H-001 (borrar una acción borra las imágenes entregadas), si la rama no lo tocó: ya estaba; cuaderno y «Además encontramos» |
| **Gravedad baja** | Un error de tipeo en el botón nuevo: cuesta un minuto e Ivan lo va a ver en el antes/después | Un ícono corrido un píxel en una pantalla que casi nadie usa |

**ROJO es por lo que trae o rompe la rama**, no por lo que ya estaba. La
fórmula de `criterios.md` (gravedad × gente × frecuencia ÷ esfuerzo) es para
elegir qué hacer del cuaderno, no para decidir VERDE o ROJO.

## Criterio propio

Lo general está en `docs/equipo-nocturno/CRITERIO.md`: evidencia antes que
autoridad, ni esponja ni terco, las decisiones son de las personas. Para un
QA quiere decir:

- **«Lo probé», «ya está arreglado»:** repetí los pasos exactos del ROTO y
  los de al lado, y mirá que el arreglo esté **en la rama**
  (`git log --oneline origin/main..HEAD`, `git diff origin/main...HEAD -- <archivo>`).
  Bruno y Lucía también son agentes y pueden contar de buena fe algo que no
  pasó: cuentan la salida del comando y la captura, no el relato.
- **«Es así por diseño»:** buscá la fuente (CONTEXTO, el mapa, una decisión
  de Ivan con fecha, un commit). Si existe, retirá el ROTO; si no, es una
  discrepancia: a Tomás, con la evidencia, sin pelear ni ceder en silencio.
- **«Eso no lo toqué»:** lo dicen el barrido y la suite, no la intención. Un
  componente compartido cambia pantallas que nadie abrió.
- **Tus conclusiones también:** la alerta del barrido es una pista, la
  sospecha del mapa es una sospecha, tu primera explicación es una
  hipótesis. Con evidencia mejor, cambiás de idea y decís por qué.
- **Una norma informa; una decisión de Ivan manda:** ASVS pide contraseñas
  de 12 caracteres; Ivan decidió de 6 a 20 el 19/11. Se prueba lo decidido y
  no se reabre lo que CONTEXTO da por decidido.
- **Decir «no está listo», con apuro también.** El README da hasta 3
  vueltas; si no queda verde, es una noche sin cambios bien contada, que no
  es un fracaso. Un PR que rompe la confianza de Ivan, sí. Se dice con el
  hecho, la evidencia, el impacto en la persona y cómo se va a verificar:
  «No está listo: la agencia B abre la tarjeta de la agencia A (captura y
  curl con 200). Es una fuga a una cuenta externa. Lo verifico repitiendo la
  llamada con el token de B: tiene que dar 404.»
- Lo que no pudiste probar se dice; nunca se omite para que quede VERDE. Y
  VERDE o ROJO es tu veredicto técnico: publicar lo decide Ivan.

## Aprender de lo que se escapó, sin tragarse todo

**Sin culpables** (el libro de SRE de Google): la pregunta es qué agujero
de la red lo dejó pasar, no quién. **La regla de Beyoncé** (*Software
Engineering at Google*: «si te gustaba, le hubieras puesto una prueba»):
todo defecto arreglado deja su prueba de regresión, en el nivel más bajo que
lo agarra. **Clasificar** con la Orthogonal Defect Classification de IBM
(Ram Chillarege), por tipo (función, interfaz, chequeo, asignación, sincronización, algoritmo,
armado, documentación) y por disparador, muestra dónde se amontonan. Y antes
de cada noche, `cuaderno/APRENDIDO.md`.

| Qué pasó (fecha, commit) | Por dónde se escapó | El hábito que lo agarra |
|---|---|---|
| 15/11, `737fcfe`: con el servidor caído, tildar una tarea se veía guardado y al volver la conexión se destildaba | Nadie probaba sin red | Cortar red o servidor a mitad de una acción |
| 15/11, `73fd15b`: la fecha se guardaba con el año a medio escribir; desde otra pestaña se veían tareas vencidas hace 1.800 años | Sin límites en fechas; nadie miraba desde otra pestaña | Años 1, 2000 y 2100, y mirar lo guardado desde otra cuenta |
| Hasta el 16/11 (`ci.yml`): sin base, las pruebas de quién ve qué se salteaban y el CI quedaba verde | Salteada contada como pasada | Contar las salteadas y por qué |
| Julio a 15/11, `c5b1ff6`: el límite general de pedidos, apagado desde una actualización de FastAPI | Nadie probaba que la protección saltara | Después de actualizar dependencias, provocar el 429 |
| Hasta el 15/11, `c5b1ff6`: en Safari del iPhone la sesión se cortaba a los 30 minutos | Todo en Chromium y en sesiones cortas | WebKit y una sesión larga |
| Hasta el 15/11, `0b1e23a`: una cuenta «títere» con rol Admin; el login confirmaba qué mails existían; un `javascript:` en una lista compartida se ejecutaba | Sin casos de abuso | Escalar, enumerar e inyectar en cada cambio de cuentas o links |
| 15/10 a 16/11, `2b3d50e`: un arreglo de cenefas quedó sin commitear en otra copia y producción siguió con la regla vieja | Se verificó una copia, no lo que se sube | Verificar en la rama, nunca en la copia de alguien |
| 19/11, `b32f204`: dos entregas con ZIP grande a la vez pasaban las dos el tope | Sin pruebas de concurrencia | Dos conexiones en paralelo, de verdad |
| 24/11, `31e5f4d`: Mi pedido guardaba lo escrito antes de la última tecla («12» guardaba «1») | Se miró la pantalla, no lo guardado | Escribir rápido y confirmar recargando |
| 24/11, `24d00bc`: Mis tareas decía «Estás al día» cuando no había podido traer todo | No se probaban los estados de error | Forzar la falla y mirar que no se disfrace de vacío (la campanita tiene esa sospecha en el mapa) |
| Hasta el 25/11, `0e123a0`: un pedido confirmado de Redexpres se podía cambiar por la API | La regla vivía solo en la pantalla | Repetir por API lo que la pantalla prohíbe |

Una inferencia sobre estos once casos, no una estadística: casi todos son
de chequeo (validaciones y permisos que faltaban) o de sincronización
(carreras, tiempos, guardado). Por eso la biblioteca insiste en límites, en
repetir por API y en carreras. **Lo que no hay que hacer:** sobrecorregir
(no todo cambio necesita un ZIP de 40 MiB ni dos conexiones), copiar la
lección sin mirar si aplica, ni repetir cifras folclóricas como «arreglar en
producción cuesta 100 veces más», que circula sin una fuente sólida (Laurent
Bossavit la rastrea en *The Leprechauns of Software Engineering*). Lo que
convence es la evidencia de este repo.

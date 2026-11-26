# Técnicas de diseño de pruebas (ISTQB) y riesgo

El programa Foundation de ISTQB (versión 4.0, de 2023) es el vocabulario
común de la profesión. Acá van sus técnicas con casos de Core Tienda. Los
números salen del mapa (`docs/equipo-nocturno/plataforma/`, del 24/11) y del
código: **si la rama cambia un número, ese borde se prueba primero**, y si
el mapa y el código no coinciden, manda el código.

De sus siete principios, tres pesan cada noche: probar todo es imposible
(unas 30 pantallas × 3 cuentas × 4 vistas × datos: se elige por riesgo);
las pruebas se gastan (antes, «paradoja del pesticida»: el ciclo de todas
las noches deja de encontrar cosas si siempre es igual; cambiá datos, orden,
cuenta y vista); y sin errores no alcanza (una pantalla sin defectos que la
agencia no entiende sola no cumple la vara de CONTEXTO).

## Particiones de equivalencia

Agrupá las entradas y salidas que el sistema debería tratar igual y probá un
caso por grupo; los inválidos, de a uno, para saber cuál falló.

- **Cuentas**, la partición más rentable: superadmin, interna común (rol
  Usuario), interna recortada, externa con «No lo ve», externa con «1 mes»,
  local. Un permiso nuevo se prueba con una de cada grupo que lo debería
  tener y con una que no.
- **Contraseña nueva:** menos de 6, de 6 a 20, más de 20, igual a la actual.
- **Lo que se entrega:** imágenes, ZIP con imágenes, ZIP sin imágenes ni PDF,
  link `http(s)`, link sin `http`, `javascript:…`.
- **Salidas:** cada columna donde puede terminar una tarjeta y cada cartel de
  error. Si un cartel nunca apareció en tus pruebas, no lo probaste.

## Valores límite

Los errores viven en los bordes. ISTQB 4.0 distingue el análisis de dos
valores (el borde y su vecino del otro lado) y el de tres (el borde y sus
dos vecinos); en lo de más riesgo, tres.

| Regla | Valores a probar |
|---|---|
| Contraseña de 6 a 20 caracteres | 5, 6, 20, 21; y 20 con ñ o emoji (¿cuenta caracteres o bytes?) |
| Hasta 4 imágenes por versión (`MAX_IMAGENES`) | 4 y 5; y sumar archivos a la versión que espera hasta pasar el tope |
| ZIP de hasta 40 MB: navegador y servidor cuentan `40 * 1024 * 1024` | 41.943.040 bytes (entra) y 41.943.041 (no entra, con el aviso del link) |
| Hasta 3 fotos por pedido de colocación | 3 y 4 |
| Login: bloqueo a los 5 fallos, por 15 minutos; 10 intentos por minuto | 4 fallos y la buena (entra), 5 y la buena (no); minutos 14 y 16; el 10.º y el 11.º intento (429) |
| Buscador del tablero: desde 2 letras | 1 y 2 |
| Don Tino: hasta 2.000 caracteres y 15 mensajes por minuto | 2.000 y 2.001; el 15.º y el 16.º |
| Fechas del calendario entre 2000 y 2100 | 31/12/1999, 01/01/2000, 31/12/2100, 01/01/2101 y el año a medio escribir |
| Headers por día: verde hasta 7, ámbar en 8, rojo arriba | 7, 8 y 9 |
| Alcance «N meses»: el actual, los N−1 siguientes y los últimos 7 días del anterior | el primer y el último día de la ventana, y uno afuera de cada lado |
| Archivado a los 10 días de finalizada; a los 30 en Archivado deja de cargarse | días 9, 10 y 11; 29, 30 y 31 |
| La contraseña vence a los 60 días | 59, 60 y 61 (en pruebas del backend: desde la pantalla no se provoca) |
| Topes de Mi pedido («Máximo N por sucursal») | N, N + 1, 0, negativo, «2,5» y «1.000» |

## Tablas de decisión

Cuando el resultado depende de una combinación de condiciones: una fila por
condición, una columna por combinación; cada columna es un caso. La decisión
del revisor, como quedó el 25/11 («Avanzar» es nuevo; si la rama la toca,
armala de nuevo desde `decidir` en `backend/app/api/routes/entregas.py`):

| | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|
| Botón | Aprobar | Aprobar | Avanzar | Aprobar o Avanzar | Pedir cambios |
| ¿Hay marcas? | no | no | no | sí | sí, o un comentario |
| ¿Último de la cadena? | sí | no | — | — | — |
| **Resultado** | Si era la última fase: Finalizado y «la tarea quedó hecha» | «Aprobaste tu parte: ahora la revisa el siguiente de la cadena» | «OK para avanzar»: vuelve a En proceso; fase y tarea siguen abiertas | No se puede: con marcas se piden cambios | En proceso, «Volvió con cambios» en rojo, aviso a toda la agencia |

Lo que falta en la tabla también es un caso: ¿qué pasa al aprobar una fase
que no es la última? El mapa no lo dice: miralo en el código y probalo, no
lo supongas. Otra tabla que rinde: el orden de chequeos de cada pantalla
(`layout.tsx`, mapa C, 2.2). Caso que sale de ahí: una agencia recién creada,
con la contraseña pendiente, abre `/calendario`: ¿qué gana?

## Transición de estados

Probá todos los estados, todas las transiciones válidas y las inválidas que
más daño harían. La tarjeta del tablero:

```
Ingresado ─arrancar─▶ En proceso ─entregar─▶ Esperando feedback ─aprobar (última fase)─▶ Finalizado
                          ▲                          │                                    │
                          └─ pedir cambios / avanzar ┘                       10 días ─▶ Archivado
Ingresado o En proceso ─archivar = cancelar (pide confirmación)─▶ Archivado ─sacar─▶ su columna
Finalizado ─«Devolver para corregir»─▶ vuelve a trabajo, con una fase nueva
```

La versión: esperando revisión → aprobada, con cambios u «OK para avanzar»;
o **reemplazada**, si la agencia entrega otra antes de que alguien decida
(desde el 25/11; antes eso daba 409). Inválidas que conviene intentar:

- Decidir sobre una versión reemplazada o ya decidida en otra pestaña: 409
  con el porqué, y la pantalla lo explica sin romperse.
- Entregar en una pieza cancelada: no se puede hasta sacarla del archivo.
- Mover una tarjeta que otro ya movió: «Esta tarjeta ya se movió: ahora
  está en X».
- La agencia lleva su tarjeta a Finalizado: «No podés llevarla a X…».
- Cambiar un pedido de Redexpres confirmado, también por API: 409.

Cada transición tiene efectos al costado (campanita, Mis tareas, el «2/5» y
el semáforo de la acción): el oráculo no es solo la columna.

## Casos de uso y criterios de aceptación

La prueba de casos de uso estaba en el programa de 2018; la 4.0 pone en su
lugar historias de usuario, criterios de aceptación y ATDD. Acá conviven: el
ciclo central es un caso de uso (los 7 pasos de `tareas.md`) y cada «bien
hecha si» del plan de Tomás es un criterio de aceptación con su prueba.
Flujos alternativos que suelen quedar sin probar: faltan piezas («Mandar
igual»); ZIP de más de 40 MB («pegá el link de WeTransfer»); el control
previo tarda («Mandar sin esperar»); se corta la red al entregar; la agencia
suma imágenes a la versión que espera; el revisor da «OK para avanzar».

## Caja blanca: el diff con lupa

ISTQB mide cobertura de sentencias y de ramas (todas las ramas cubren todas
las sentencias; al revés, no). En la práctica: por cada decisión nueva de
`git diff origin/main...HEAD`, ¿qué caso pasa por cada lado?

- Cada `if` de permiso (`es_externo`, `puedo`, `require_permission`): ¿hay
  prueba del sí y del no?
- Cada `except` o `catch`: ¿qué ve la persona? Los errores disfrazados de
  vacío viven ahí.
- Endpoint nuevo: ¿pasa por la puerta de `deps.py` (sesión, contraseña
  vencida, freno de externas)? ¿Filtra por mundo y por alcance?
- Topes y tiempos: ¿navegador y servidor usan el mismo número?
- `dangerouslySetInnerHTML`, un `href` armado con datos de la gente,
  `localStorage` nuevo (¿se borra al salir?), consultas dentro de un bucle,
  textos que faltan en algún idioma.

```bash
git diff origin/main...HEAD -- backend/app | grep -nE '^\+.*(if |except|require_permission|es_externo)'
pip install -q coverage && cd backend && coverage run --branch -m pytest tests/test_x.py -q \
  && coverage report -m --include="app/services/entregas.py"   # coverage, solo en el venv
```

Las líneas sin ejecutar son preguntas, no una meta: cuando una medida se
vuelve objetivo, deja de medir (ley de Goodhart).

## Pruebas basadas en riesgo

ISTQB define el nivel de riesgo por su probabilidad y su impacto. El riesgo
de proyecto (build roto, Postgres que no levanta, poco tiempo) no se mezcla:
va a «No se pudo probar».

| Puntaje | Impacto | Probabilidad |
|---|---|---|
| 3 | Fuga a una cuenta externa o a un local, pérdida de datos o imágenes, ciclo central cortado, login roto, datos de clientes | Código compartido (`layout.tsx`, `core/deps.py`, `lib/api.ts`, stores, `globals.css`), concurrencia, fechas, archivos, zona con historia de defectos, diff grande |
| 2 | Traba una tarea diaria de mucha gente; una pantalla del núcleo rota en el celular | Lógica nueva acotada a una pantalla |
| 1 | Desprolijo, o en una pantalla que casi nadie usa | Un texto o un estilo local |

Riesgo = impacto × probabilidad. **De 6 a 9:** primero, con dos técnicas y
también por API. **3 o 4:** caso feliz y bordes principales. **1 o 2:** que
el barrido no muestre nada raro. Si la falla sería **silenciosa** (una fuga
sin síntoma, un dato mal guardado que la pantalla muestra bien), sumale un
punto: nadie más la va a ver. Un ejemplo armado para mostrar el método (no
son defectos encontrados), sobre «adjuntos en el pedido»:

| Riesgo | I × P | Cómo se prueba |
|---|---|---|
| La agencia B baja el adjunto de la agencia A por su id | 3 × 2 = 6 | Por API con el token de B; por pantalla, pegando el link |
| Un archivo grande llena la base de 500 MB | 3 × 2 = 6 | El tope justo; qué se ve cuando frena `BASE_TOPE_MB` |
| Un nombre con tildes o muy largo rompe la descarga | 2 × 2 = 4 | «Planilla Ñandú ÁÉÍ – versión final (2).xlsx» |
| Al copiar la acción, el adjunto no viaja | 1 × 3 = 3 | Es así por diseño (mapa): solo que no se rompa nada |

# Calendario

Las tres partes del calendario, una debajo de la otra, en `/calendario`.

Se desarrolló aparte (carpeta `Calendario banners` del escritorio) para no
frenar lo que ya estaba andando acá, y se armó desde el principio con el mismo
stack que la plataforma — Next 16, React 18, Tailwind, zustand, lucide — así
que al entrar no hubo que agregar ni una dependencia.

## Las tres secciones

**1. Calendario comercial.** Las acciones de marketing por tipo (Mega evento,
Mailing GRAL, Especiales, Sin mailing, Actividades tácticas, Seasonal…), igual
que el Excel. Tocar una acción abre su ficha lateral.

**2. Calendario Retail Media.** Los espacios vendidos a marcas, agrupados en
eComm y Express, con un carril por slot de cada formato. `HOME SLIDER (Retail
Media)` está marcado aparte porque es el que alimenta al header.

**3. Cronograma de envíos.** Cuándo sale cada mailing, cada WhatsApp y cada
push, un carril por canal. No se carga acá: sale de las piezas de Email,
WhatsApp y Push que ya tiene cada acción en su ficha, y ahí se les pone el día
y la hora. Una pieza sin fecha propia cae el día que arranca su acción y queda
avisada arriba, para que se note que falta ponérsela. Tocar un envío lleva a la
ficha de su acción, que es donde se edita.

**4. Headers de la home.** El conteo día por día —verde hasta 7, ámbar en 8,
rojo arriba de 8— y, detrás del botón **Ver headers activos por fecha**, un
panel que entra desde la derecha con las 10 posiciones de UN día, una abajo de
la otra. Era una rejilla de 10 por 31: para saber qué se ve un día había que
leer una columna entre treinta, y ocupaba un tercio de la pantalla. El conteo
queda a la vista porque es la alarma; tocar un día abre el panel en ese día.

## La regla que no se toca

**El sistema cuenta y avisa, nunca decide qué banner bajar.** Qué se baja se
resuelve por venta, dato que la app no tiene.

Si una acción pide header y no hay posición libre, no se le saca el lugar a
nadie: la acción cae en `mes.sinLugar` y aparece un aviso rojo arriba de la
sección con qué quedó afuera y qué días estaba lleno.

## Cómo se llena el header

Casi nada se carga a mano. El header se **deriva**, desde dos lados:

- **Retail Media** → las 3 filas de `HOME SLIDER (Retail Media)` caen en las
  posiciones que RM tenga reservadas, por defecto 4, 5 y 6.
- **Marketing** → las otras 7. Cada acción que en su ficha tenga la pieza
  **Web · Home → Header** baja sola a la primera posición de marketing libre en
  todo su rango.

Una barra derivada se reconoce por el borde negro a la izquierda: no se edita
en el header, se hace clic y te lleva a donde sí se edita (el calendario de
retail o la ficha de la acción). Ese contrato vive en `OrigenHeader`, que es
`retail`, `accion` o `manual`.

## La ficha de la acción

Clic en una acción abre un panel lateral que entra desde la derecha. Adentro:
nombre, tipo, fechas y duración; el progreso de piezas publicadas; y la
estructura por áreas — **Web · Home**, **Web · Landing de la acción**,
**Físico**, **Email**, **WhatsApp**, **Push** — donde se agregan y se sacan
piezas y se les mueve el estado (pendiente → en proceso → aprobado →
publicado). Si la acción lleva header, dice en qué posición quedó, o avisa que
no entró. Arriba de todo están sus **avisos** (ver Avisos).

Se cierra con Escape, con la X o tocando afuera.

## Una acción que cruza de mes es UNA sola

Desde el 28/09/2026 cada barra va de una fecha a otra (`'YYYY-MM-DD'`), no "del
día X al Y de su mes". Algo del 25/09 al 05/10 es una sola acción: se ve en
setiembre (del 25 al 30, con una flecha a la derecha) y en octubre (del 1 al 5,
con una flecha a la izquierda), con las mismas piezas y avisos, y lo que se le
cambia en un mes cambia en el otro. Antes quedaba recortada a fin de mes y había
que cargarla dos veces.

Para que eso funcione, el mes ya no se guarda: se **arma** cada vez con las
barras que lo tocan (`construirMes` / `vistaDelMes` en `derivar.ts`). Cada
barra guarda su renglón (`carril`), así una acción que cruza queda a la misma
altura en los dos meses; al crearla o moverle las fechas, si el renglón está
ocupado en algún día de su rango, va al primero libre.

El header también se calcula sobre todas las fechas: una acción que cruza de
mes queda en la misma posición en los dos, y una campaña de Retail Media que
cruza sigue a RM si RM cambia de posición de un mes al otro.

**Las bandas son las mismas todos los meses** (`catalogo.ts`): todos los tipos
de acción y formatos de RM que aparecen en los Excel importados. Antes cada mes
traía las suyas del Excel, y de noviembre en adelante no había ni un renglón
donde cargar nada. Cada banda tiene además un **+** para crear aunque todos sus
renglones estén ocupados ese día.

Lo que el Excel traía partido en dos meses (por ejemplo "(OI) ELECTRO SALE" del
25 al 30/09 y "ELECTRO SALE OI" del 1 al 7/10, o "Conaprole" en HOME SLIDER)
quedó como estaba: dos barras. No se juntaron solas porque los nombres no
siempre coinciden y juntar dos datos es decisión de una persona.

## Permisos

Salen del usuario logueado, no de un selector de prueba. Los tres están en
`backend/app/models/role.py` y se tildan por usuario desde el panel de
administración:

| Permiso | Qué habilita |
|---|---|
| `calendario.view` | Entrar. Es el que decide si aparece el link en el menú. |
| `calendario.edit` | Crear, editar y borrar barras, mover el estado de las piezas y configurar avisos. |
| `calendario.retail_media` | Mover las posiciones que Retail Media tiene reservadas en el header. |

Mover las posiciones de Retail Media las guarda y le avisa a quien lleva Retail
Media en la misma llamada (`PUT /calendario/posiciones-rm/{clave}`). Antes eran
dos, y la de guardar pedía `calendario.edit`: alguien con solo el permiso de RM
las movía y no se guardaban.

## Zoom

Las tres secciones se alejan y se acercan juntas, con los botones `−` y `+`.
El porcentaje vuelve al tamaño normal si lo tocás, y el botón de las flechas
ajusta el ancho para que **el mes entero entre en la pantalla sin scroll** —
mide la caja real de una sección, por eso la página necesita el `id="calendario"`.
Al alejar, primero desaparece la inicial del día de la semana y después los
números quedan solo cada 5 días. El zoom se guarda.

Cuando no entra, cada sección tiene scroll horizontal propio y las tres se
mueven juntas; la columna de etiquetas y la fila de días quedan fijas.

## Guardado

**En el servidor, una fila por barra**, desde el 28/09/2026 (migración 0057,
modelos en `backend/app/models/calendario.py`). Hasta ahí se subía el mes entero
en cada cambio y **dos personas editando el mismo mes se pisaban**: ganaba la
última que guardaba y el cambio de la otra se perdía sin aviso.

Ahora cada cambio viaja solo y el servidor escribe solo eso:

- una barra: `POST /calendario/barras`, `PATCH` y `DELETE /calendario/barras/{id}`.
  El `PATCH` lleva **solo los campos que cambiaron**: si una persona le cambia
  el nombre a una acción mientras otra le mueve las fechas, quedan las dos cosas.
- una pieza: `POST /calendario/barras/{id}/piezas`, `PATCH` y `DELETE /calendario/piezas/{id}`.
  Dos personas moviendo el estado de dos piezas de la misma acción no se pisan,
  y dos agregando la misma pieza a la vez no la duplican.
- un aviso: `POST /calendario/barras/{id}/avisos`, `DELETE /calendario/avisos/{id}`.

Lo local cambia antes de que conteste el servidor, así la pantalla no espera.
Si el servidor dice que no (la acción la borró otra persona, se cortó la
conexión), sale un aviso y se trae lo que hay de verdad.

**Lo que hacen los demás aparece solo**, sin recargar: cada 15 segundos (y al
volver a la pestaña) se pregunta `GET /calendario/datos?rev=N`. Cada escritura
sube `calendario_revision` en la misma transacción, así que si nadie cambió
nada la respuesta es una línea; si cambió, viene todo y reemplaza lo local.
Mientras haya un cambio propio en viaje no se reemplaza nada, para que la
respuesta vieja no lo haga "desaparecer".

Si se edita algo que otra persona acaba de borrar, el servidor contesta 404 con
"la borró otra persona" y se recarga. Borrar queda en el registro de auditoría
(`calendario.borrar`), con qué era.

`localStorage` (clave `calendario-mktg-v2`) queda solo como caché para pintar al
instante. La revisión no se guarda ahí a propósito: al abrir siempre se trae
todo, así un cambio que quedó a medio subir al cerrar la pestaña no queda como
si existiera. Sin conexión la barra de arriba lo dice, y los cambios no se
guardan.

`calendario_meses` (el documento por mes de antes) quedó en la base sin tocar,
como respaldo de cómo estaba todo el 28/09/2026. Nada lo lee ni lo escribe.

## Avisos

**No hay bandeja propia del calendario**: los avisos entran en las
notificaciones de la plataforma, la campanita del menú, que ya es por persona.

- **Los que alguien configuró en la ficha de una acción.** No hay ninguno por
  defecto: el aviso automático de 10 días antes de cada acción a todo el mundo
  se apagó el 28/09/2026, a pedido de Ivan ("cuando realmente nos llegue una
  notificación, es porque alguien la configuró y porque realmente vale la
  pena"). En la ficha se elige cuántos días antes (60, 50, 40, 30, 20 o 10) y
  a quién (cualquiera que pueda abrir el calendario); una acción puede tener
  varios. Se guarda la anticipación, no la fecha: si la acción se corre, el
  aviso se corre con ella. Lo hace `backend/app/services/calendario_avisos.py`,
  que revisa cada 6 horas. La ventana es "faltan N días o menos y todavía no
  arrancó": un servidor caído un par de días no se come el aviso, y un aviso
  cuya fecha ya pasó al configurarlo sale en el momento. Sale una sola vez por
  persona dentro de su ventana: correr la acción un día no lo repite, correrla
  a otro mes lo vuelve a armar. Tocarlo en la campanita abre la ficha de la
  acción (`/calendario?accion=...`).
- **Cuando alguien mueve las posiciones de Retail Media**, a quien tenga
  `calendario.retail_media`, menos el que las movió.

Los 308 avisos automáticos que ya habían salido quedaron en la campanita de
cada uno; no se borraron.

## Los colores

Vienen del Excel y **no cambian entre temas**: son pastel, y el texto encima se
calcula por contraste (`textoSobre` en `colores.ts`), así que se leen igual en
claro y en oscuro. Es a propósito.

## Los datos

La fuente de verdad es la base. `seed.ts` es el **muestreo** de setiembre y
octubre 2026 sacado de los dos Excel reales; esas barras ya están en la base
(las copió la 0057 desde lo que se había guardado) y de `seed.ts` hoy solo se
usan los **nombres de las bandas**, para armar el catálogo. Una base nueva
arranca con el calendario vacío y todas las bandas.

Para regenerarlo, con los dos Excel en Descargas:

```
python backend/scripts/importar_calendario_excel.py
```

Ese script es referencia de cómo se parsean esos Excel, no parte del producto.

## Estructura

```
lib/calendario/derivar.ts     LA LÓGICA: armar el mes con las barras que lo tocan, derivar el header y los envíos, contar
lib/calendario/tipos.ts       el modelo, el catálogo de piezas y las reglas (7/8/10)
lib/calendario/catalogo.ts    las bandas, iguales para todos los meses
lib/calendario/rejilla.ts     medidas y zoom
lib/calendario/store.ts       estado, guardado cambio por cambio y la revisión cada 15 s
lib/calendario/permisos.ts    quién puede qué, contra el usuario de la plataforma
lib/calendario/seed.ts        el muestreo de los Excel (hoy solo se usan los nombres de las bandas)
lib/calendario/colores.ts     paleta y contraste
lib/calendario/fechas.ts      meses, días de la semana, findes, y las cuentas con fechas reales
components/calendario/        las 9 pantallas
app/(dashboard)/calendario/   la página
```

`derivar.ts` y `rejilla.ts` no dependen de React ni de zustand a propósito: son
lo único que hay que portar con cuidado, y así se pueden probar sin levantar
nada.

## Pruebas

```
cd frontend && npm run test:calendario
```

113 comprobaciones, sin framework: se compilan con `tsc` y corren con node.
Fijan las reglas del header, el zoom, el cronograma de envíos, el header
mirado por fecha y las acciones que cruzan de mes. No borrarlas al
reescribirlas con otro runner. Del lado del backend,
`tests/test_calendario_avisos.py` y `tests/test_calendario_migracion.py`.

## Lo que falta

- **Subtareas por pieza** (arte desktop, arte mobile, aprobación comercial) y
  responsable con vencimiento. Hoy el modelo llega hasta acción → pieza.
- **Envíos y headers sueltos**, sin una acción detrás. Hoy un envío sale
  siempre de la pieza de una acción.
- **Avisos por mail.** Hoy llegan solo a la campanita.
- **Que un aviso pueda mirar la fecha de un envío** y no solo el arranque de la
  acción.
- **Traer una ventana de meses y no todo.** Hoy, cuando otra persona cambia
  algo, cada pestaña abierta se baja el calendario entero y recalcula el
  header de todas las fechas. Con 170 barras no se nota; con años de historia
  va a convenir pedir solo los meses alrededor del que se mira.
- **`Pieza.enSharePoint`** existe en el modelo pero no se usa en ninguna
  pantalla y no sube nada. Está puesto a futuro.
- **Los textos están solo en español.** El link del menú sí está en los tres
  idiomas; el cuerpo del calendario no.
- El **apartado Retail Media** con el resto de las hojas del Excel (campañas,
  SKUs, reportes, benchmarks).
- Vista de semana y arrastrar barras para mover fechas.

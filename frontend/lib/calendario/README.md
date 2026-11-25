# Calendario

Las tres partes del calendario, una debajo de la otra, en `/calendario`.

Se desarrolló aparte (carpeta `Calendario banners` del escritorio) para no
frenar lo que ya estaba andando acá, y se armó desde el principio con el mismo
stack que la plataforma — Next 16, React 18, Tailwind, zustand, lucide — así
que al entrar no hubo que agregar ni una dependencia.

## Mundos: la plataforma entera, separada por negocio

Desde el 12/11/2026 (migración 0060) la plataforma se divide en **mundos**:
Tienda Inglesa, Tienda Express, Redexpres, Tienda Viajes y Tienda Farma. Pedido
de Ivan: "Los mundos tienen que ser de toda la plataforma. La persona que entra
a ese mundo va a ver todo hecho para ese mundo".

- Cada persona tiene la lista de los mundos a los que entra (`users.mundos`, se
  tilda en el panel de administración; un Super Admin entra a todos). Nadie
  queda sin mundo.
- Quien tiene **un solo mundo** entra derecho. Quien tiene **varios** pasa por
  `/mundos` a elegir antes de ver nada, y cambia cuando quiere desde el menú.
- **El menú es el del mundo**: cada herramienta aparece solo donde tiene sentido
  (`RUTAS_DE_MUNDO` en `lib/mundos.ts`). La planilla de pedidos es solo de
  Redexpres; los precios, la validación de redes y el diccionario son de Tienda
  Inglesa; las cenefas están en los dos; los medios y finanzas, en todos (Ivan,
  20/11/2026: son los mismos datos, no se separan). Abrir una herramienta de
  otro mundo (un link guardado, un aviso) muestra dónde está y ofrece pasar.
- **Lo que se guarda por mundo**, y que el servidor no deja leer ni escribir
  desde otro (`app/core/mundos.py`, `exigir_mundo`): el calendario con sus
  tareas (`calendario_barras.mundo`) y los tipos de cenefa
  (`cenefa_destinos.mundo`). Redexpres dejó de ser una opción más del selector
  de cenefas: sus cenefas se ven entrando a Redexpres, y como es un solo tipo,
  se entra derecho.
- **Los permisos valen igual que siempre.** El mundo dice de qué negocio; el
  permiso, qué se puede hacer.
- El header de la home y Retail Media son de la web de Tienda Inglesa: los
  otros mundos tienen calendario comercial y cronograma de envíos.
- Las categorías de Tienda Inglesa siguen saliendo de los Excel
  (`catalogo.ts`). Los otros mundos arrancan con una lista genérica
  (`lib/mundos.ts`, `BANDAS_GENERICAS`).
- Al migrar: lo cargado quedó en Tienda Inglesa; los logins de sucursal y
  quien tenía permisos de Redexpres entran a Redexpres; el resto, a Tienda
  Inglesa. Los otros tres mundos se tildan a mano.

El catálogo de mundos está en dos lugares que tienen que coincidir:
`backend/app/core/mundos.py` y `frontend/lib/mundos.ts`.

## Tareas: quién hace qué en cada acción

Pedido de Ivan (12/11/2026): quien lidera abre una acción, le crea tareas y
se las asigna a cada persona. Tabla `calendario_tareas`, una fila por tarea.
Desde el 24/11/2026 (0090) **una tarea = un pedido**, todas en un solo nivel:
"las tareas y el pedido de piezas deberían ser uno... tener así dividido en
tarea, pedido de piezas y luego subtareas me parece al pedo y confuso". No hay
más subtareas ni piezas adentro de otra tarea (el servidor lo rechaza).

| Quién | Qué puede |
|---|---|
| Con `calendario.tareas` | Crear, asignar, reasignar, poner vencimiento y borrar tareas; el responsable de Tienda, plantillas y entregas por fases. |
| Con `calendario.pedidos` | Crear tareas en la acción, también para una agencia (Banners, Mailing, Cenefas…). Desde el 17/11/2026 es aparte de `calendario.edit`: la acción la arma quien lidera, y las tareas las crea el equipo de analistas. La 0071 se lo dio a todos los que tenían `calendario.edit`. |
| A quien se le asignó | Mover el estado de SUS tareas (pendiente → en proceso → hecha), aunque no tenga `calendario.edit`. |
| Los demás | Ver. |

- Asignar una tarea le manda un aviso a la campanita de esa persona; cuando la
  termina, le llega a quien la creó. Tocar el aviso abre la ficha de la acción,
  aunque sea de otro mundo (`GET /calendario/ubicar/{id}`).
- Solo se le puede asignar a alguien que pueda abrir ese mundo.
- **Mis tareas** (`/mis-tareas`) muestra lo que cada uno tiene asignado en el
  mundo en el que está, ordenado por vencimiento, y avisa si le queda algo
  pendiente en otro. También lo que lleva por Tienda (su responsable) aunque
  lo haga una agencia.
- `calendario.tareas` lo recibieron Superadmin y Admin en la 0060. A quien
  lidere el equipo sin ser Admin hay que tildárselo a mano.

**Cómo se arma (24/11/2026).** En la ficha de una acción hay un solo botón:
**Crear tarea**, que es el pedido entero (`NuevaTarea` en BloqueTareas.tsx):
**¿Qué se pide?** (cada tipo abre su modal con todas las opciones del catálogo
de `tipos_de_tarea.py`: Banners con sus medidas, Redes sociales, Mailing, EMM,
Push, WhatsApp, Cartelería... u **Otra cosa**, sin tipo), **¿Quién la hace?**
(Publicis, Another Monday, Diseñadores o alguien de Tienda), el detalle, los
archivos, el **responsable de Tienda** (si la hace una agencia: quien la
sigue, `responsable_id`) y para cuándo. Se crea UNA tarea; si la hace una
agencia, esa misma tarea es su tarjeta en el tablero. Con un tipo, el nombre
se arma solo ("<Acción> - <Tipo>") y se puede cambiar. Con dos tipos a la vez
se crean dos tareas, una al lado de la otra, con el mismo detalle y archivos.
Lo que antes colgaba de una tarea de afuera lo aplanó la 0090. El formulario
está en `FormularioDeTarea.tsx`, porque es también el de "Nueva tarjeta".

**Tarjetas sin acción (24/11/2026).** En **Tableros**, "Nueva tarjeta" abre el
mismo formulario para algo que no es de una acción del calendario (Ivan:
"deberíamos poder crear tarjetas también de cosas que estén por fuera del
calendario"). El nombre lo escribe la persona y siempre hay que elegir quién
la hace; sin tipo ("Otra cosa") va como "Otro", así siempre es tarjeta. La
crean los mismos que crean tareas, nunca la agencia. Cuelgan de una acción de
sistema por mundo, `sin-accion-<mundo>`, que no se ve en el calendario ni se
abre (`backend/app/services/sin_accion.py` explica por qué así y no con
`barra_id` vacío); donde va el nombre de la acción dice "Sin acción". Su
nombre, fecha y responsable se cambian en la tarjeta (`EditarTarjetaSinAccion`).

**Los tres tableros (17/11/2026).** En «¿Quién la hace?» se elige **a qué
tablero va**: Publicis, Another Monday o Diseñadores
(`backend/app/core/tableros.py`). La pieza no lleva persona: la toma, la hace
y la responde cualquiera de ese tablero. Cada tablero es una agencia de la
0069: sus usuarios son cuentas externas de esa empresa (desde el 19/11/2026 se
elige de una lista en el panel, y se compara sin tildes ni mayúsculas:
«Disenadores» es Diseñadores), entran directo a su tablero y ven solo lo suyo.
En una tarea de Tienda, el responsable es siempre alguien de Tienda: las
cuentas de las agencias se ofrecen solo en sus piezas. Se puede mandar una
pieza a uno de los tres aunque todavía no tenga usuarios: espera ahí. El
equipo ve los tres en pestañas en **Tableros** (y "Otras", si hay tarjetas de
antes que no son de ninguno).

**Comentarios (0073).** Cada tarjeta tiene comentarios al costado, como en
Trello: los escribe cualquiera que la ve (el equipo y su tablero), y a los
demás que la siguen (quien la hace, quien la pidió, quienes la aprueban y el
responsable de la tarea) les llega a la campanita.
Una tarea común ya no lleva entregas propias: ni "Lleva entregas para
aprobar" al crearla ni el botón "Entregas" (traían otra lista de tipos, más
corta, y confundía). En todo el bloque hay un solo formulario abierto a la vez.

**Devolver una pieza aprobada (0072).** Con todas sus fases aprobadas, quien
la aprueba o quien lidera ve **Devolver para corregir**: escribe qué cambiar y
se abre una fase nueva al final (Entrega 2, Entrega 3… sin tope), que guarda
ese texto. Quien entrega lo ve arriba de la entrega y le llega a la campanita
(`POST /calendario/tareas/{id}/devolver`). Antes, con la única fase aprobada,
la tarjeta quedaba cerrada y no había dónde escribir.

### Plantillas de tareas (0065)

Cada tipo de acción lleva casi siempre las mismas tareas. Una **plantilla**
(tabla `calendario_plantillas`, una por mundo) las guarda con su vencimiento
relativo: N días antes o después del **inicio** o del **fin** de la acción, y
opcionalmente un responsable fijo y la categoría a la que va.

- **Usar plantilla**, en la pestaña Tareas de la ficha, crea sus tareas con la
  fecha ya calculada. Si la acción tiene una categoría con plantilla, la ficha
  la sugiere ("¿Usar la plantilla Mega evento?"); "Ahora no" la saca de esa
  acción en ese navegador. A cada responsable le llega UN aviso con todas sus
  tareas, no uno por tarea.
- **Las tareas se mueven con la acción.** Cada tarea de plantilla guarda su
  ancla (`ancla`, `ancla_dias`): si la acción cambia de fecha, las que no
  están hechas se recalculan solas, en el mismo cambio. Si alguien les cambia
  el vencimiento a mano, se sueltan y quedan donde las pusieron.
- El retiro de lo que se colgó (cenefas, carteles) es una tarea más, anclada
  al fin: "Empezar con un ejemplo" la trae, junto con el brief, las entregas,
  la aprobación, las cenefas a los locales y la foto de colocación.
- Armarlas, editarlas, borrarlas y usarlas pide `calendario.tareas`. Borrar
  una plantilla no toca las tareas que ya creó.
- Las cuentas están dos veces a propósito: en `lib/calendario/plantillas.ts`
  (para que la pantalla cambie al instante) y en el backend
  (`app/api/routes/calendario.py`), que es el que manda.

## Categorías: la fila, la cocarda y 'Sin categoría'

Pedido de Ivan (12/11/2026): "Para mí debería de ser nueva acción y punto.
Nueva acción, y esa nueva acción adentro tener la categoría de mega evento,
evento general, especial". Y que en los listados tenga "esa cocarda visible...
para saber también lo que es la importancia".

- **La categoría es la fila.** No es un dato nuevo: es lo que la pantalla
  llamaba "tipo de acción", la fila del calendario comercial donde va la acción
  (`banda`). Un solo campo, sin cambios en la base ni en la API: cambiarla es
  un `PATCH /calendario/barras/{id}` con `{ banda, carril }`.
- **Nueva acción y punto.** El botón **Nueva acción** (`NuevaAccion.tsx`, el
  mismo en la lista y en el encabezado del calendario comercial) no pregunta
  de qué tipo es: pide nombre, fechas y color, la acción nace con
  `banda = 'Sin categoría'` (`SIN_CATEGORIA` en `categorias.ts`) y se abre su
  ficha. La categoría se pone ahí, tocando la cocarda del encabezado, que es el
  único lugar donde se elige y se cambia; también puede quedar sin poner. Al
  cambiarla, la acción pasa a esa fila, al primer renglón libre en sus fechas.
  Crear desde una fila del calendario (el **+** o un día vacío) sigue dejando
  la acción en esa fila, y no abre la ficha: ahí se suelen cargar varias
  seguidas.
- **La fila "Sin categoría"** va primera en el calendario comercial y existe
  solo el mes en que hay alguna acción así (`bandasDe` en `derivar.ts`).
- **La cocarda** es la categoría dibujada siempre igual, con más o menos peso
  según cuánto importa, y no con el color de la acción (`Cocarda.tsx`). Tiene
  cuatro aspectos: **mega** (MEGA EVENTO: fondo negro y una estrella),
  **general** (Mailing GRAL: fondo índigo claro), **especial** (Especiales:
  solo el borde) y **común** (todas las demás: gris). La importancia es
  cantidad de tinta y no un color nuevo, porque ámbar, rojo y verde ya quieren
  decir "falta poco", "vencida" y "hecha". Dice el mismo texto que la fila.
  Está en las tarjetas de la lista, en el encabezado de la ficha y, solo las
  tres destacadas, en Mis tareas; en las barras del calendario no, que ya están
  en su fila. Una acción sin categoría no lleva cocarda. El peso no se guarda:
  para destacar una categoría nueva alcanza con sumarla a `DESTACADAS` en
  `categorias.ts`.
- **"TIENDA FARMA" se retiró** del calendario de Tienda Inglesa
  (`BANDAS_RETIRADAS` en `categorias.ts`): "Tienda Farma debería de tener su
  propio calendario", y lo tiene, es un mundo. Ya no figura entre las
  categorías ni se le carga nada nuevo. Las acciones viejas que siguen en esa
  fila no se movieron ni se borraron: se ven en su mes, en una fila al final
  que dice **Ya no se usa**. Pasarlas al mundo Tienda Farma es una decisión de
  Ivan que está pendiente.
- **Pendiente con Fernanda:** si Carpas, Pasillos Laterales y Galería y/o
  Estacionamiento se usan ("no se usan, pero mantengámosla por ahora hasta
  confirmar con Fernanda"), y qué quieren decir Mailing NF y Evento NF. Hasta
  entonces esas filas quedan como están.

## Cómo se mira

- **Filtro por parte** (Todo · Comercial · Envíos · Retail Media · Headers):
  las cuatro juntas marean a quien entra por primera vez.
- **Calendario o Lista.** El calendario es el mes entero, como en el Excel. La
  lista muestra las mismas acciones como tarjetas (en curso, lo que viene, ya
  terminaron), con su cocarda y el avance de piezas y tareas. Es lo que se usa
  en un teléfono, y ahí arranca sola la primera vez. El botón del calendario
  decía "Mes": al lado del selector de mes se leía como "este mes", e Ivan
  buscó "el calendario general de todo" sin encontrarlo (12/11/2026). En un
  teléfono los dos botones ocupan todo el ancho.
- **El mes se ajusta solo al ancho de la pantalla** mientras nadie toque el
  zoom: en una notebook entra entero. Tocar el zoom lo deja fijo.
- **Ocultar categorías vacías** en el calendario comercial.

## Mi agenda: el calendario de cada persona (0074)

Arriba de todo, una fila con el calendario de Outlook o Google de quien mira.
Pedido de Ivan (17/11/2026): "que la gente pueda importar su propio
calendario a la aplicación y que se vaya actualizando con los eventos que
vayan agregando". **Solo la ve su dueño**: no hay forma de pedir la agenda de
otro, ni siquiera siendo admin.

- **Se conecta pegando un link**, una vez: en Outlook, *Publicar un
  calendario* (el link ICS); en Google, la *Dirección secreta en formato
  iCal*. Los pasos están en el modal de "Conectar mi calendario". El link se
  guarda cifrado y nunca vuelve al navegador.
- **Se actualiza solo**: el servidor lo relee cuando alguien mira y pasaron
  15 minutos (`GET /calendario/mi-agenda`); la pantalla vuelve a preguntar
  cada 15 minutos y al volver a la pestaña. "Actualizar" lo relee ya. Si el
  link deja de andar, se ven los eventos de la última vez con el motivo.
- **Una barra por día con eventos**, en hora de Uruguay: "10:00 Daily +1"
  (con el zoom chico, solo cuántos hay). Tocarla abre los eventos de ese día.
  Las reuniones que se repiten ya vienen expandidas del servidor, de dos meses
  atrás a un año adelante.
- **Es solo de ida.** Antes había un link para llevar las acciones de Tienda a
  Outlook (0064); se sacó: "no me gusta que las acciones del calendario de
  Tienda puedan estar en un calendario cualquiera". La columna
  `users.calendario_link_version` quedó sin uso.
- El servidor sale a buscar un link que pegó una persona, así que solo va a
  https, a servidores de internet (nunca a una dirección interna, tampoco en
  una redirección) y con topes de tamaño, tiempo y redirecciones. Ver
  `backend/app/services/agenda_externa.py`.

Lo de la pantalla está en `lib/calendario/mi-agenda.ts` (en qué día cae cada
evento y cómo se dice) y `components/calendario/MiAgenda.tsx`.

## Lo del 18/11/2026

- **Redexpres como su Excel.** Sus filas son las de "PAC 2026 Tareas.xlsx"
  (`BANDAS_REDEXPRES` en `lib/mundos.ts`) y la migración 0076 cargó sus
  acciones de 2026 (aditiva: no duplica ni pisa nada). La hoja "Valen" son las
  tareas de Valentina en cada acción (Lanzar, Cierre, Imprenta...): todavía
  no se cargan, primero se validan con ella.
- **Tareas minimizadas.** En la ficha, cada tarea muestra solo su título (y
  qué agencia la hace); se despliega tocándola.
- **Una tarea sin tipo.** «Otra cosa»: puede ser solo el nombre y el detalle
  (idea de Valentina).
- **El tablero, libre como Trello** para el equipo (0075): lleva la tarjeta a
  cualquier columna. Si no le toca entregar o decidir, es "a mano": no se
  entrega ni se aprueba nada, y lo próximo que pase de verdad (una entrega,
  una decisión) vuelve a mandar. La agencia sigue con sus reglas.
- **"Lo que se pidió"** en la tarjeta va como lista: cada opción con su
  medida y los datos aparte, sin repetir el pedido en el detalle.
- **Lanzar (0077), solo en Redexpres.** Cada acción nace con la tarea Lanzar
  (60 días antes, anclada a la acción) y dos avisos a todo el equipo del
  mundo, a los 60 y a los 30 días. Si se carga tarde, el aviso sale en el
  momento, una sola vez. No va en "BOMBAS". Ver
  `backend/app/services/controles_redexpres.py`.
- **Sin Cierre automático ni Super FDS (0083, 20/11/2026).** El Cierre lo crea
  Valentina a mano ("tema fechas es muy complejo"). Los Super FDS se dejaron
  de hacer: su fila se ve hasta noviembre de 2026 (`bandasRetiradas` en
  `lib/mundos.ts`) y ya no se ofrece para acciones nuevas; Lanzar FDS y Cierre
  FDS (0078) se sacaron.
- **Un aviso contado desde un envío (0084, 20/11/2026).** Al configurar un
  aviso se elige si los días se cuentan desde que arranca la acción o desde
  uno de sus envíos (email, WhatsApp, push): `calendario_avisos.pieza_id`. Se
  mueve con el envío, sale aunque la acción ya haya arrancado, se va si se
  saca el envío y, al copiar la acción, pasa al envío de la copia
  (`lib/calendario/avisos.ts` y `fecha_base` en el servidor).
- **Las tareas se renombran y se ordenan arrastrando (20/11/2026).** Quien
  gestiona las tareas les cambia el nombre ("Nombre") y las ordena con la
  manija ⋮⋮, con el mouse, el dedo o las flechas; entre hermanas
  (`lib/calendario/orden.ts`, `PUT /barras/{id}/tareas/orden`).
- **Piezas de Redexpres:** Imprenta, Video monitores, Bases escribana y
  Afiche bombas se ofrecen solo en sus acciones (`mundos` en el catálogo).
- **La campanita, arriba a la derecha** (`components/layout/Campanita.tsx`),
  con su nombre y el número. En el teléfono la abre "Avisos", abajo.
- Una tarea minimizada se abre tocando cualquier parte del renglón.
- **Los avisos, también por mail (0079).** Todo lo que llega a la campanita sale
  por mail al minuto, uno por aviso (`backend/app/services/avisos_por_mail.py`).
  Cada uno lo apaga en "Mi perfil". No se mandan avisos de hace más de un día.

## Las tres secciones

**1. Calendario comercial.** Las acciones de marketing por categoría (Mega
evento, Mailing GRAL, Especiales, Sin mailing, Actividades tácticas,
Seasonal…), igual que el Excel. Tocar una acción abre su ficha lateral.

**2. Calendario Retail Media.** Los espacios vendidos a marcas, agrupados en
eComm y Express, con un carril por slot de cada formato. `HOME SLIDER (Retail
Media)` está marcado aparte porque es el que alimenta al header.

**3. Cronograma de envíos.** Cuándo sale cada mailing, cada WhatsApp y cada
push, un carril por canal. La mayoría no se carga acá: sale de las piezas de
Email, WhatsApp y Push que ya tiene cada acción en su ficha, y ahí se les pone
el día y la hora. Una pieza sin fecha propia cae el día que arranca su acción y
queda avisada arriba, para que se note que falta ponérsela. Tocar un envío de
una acción lleva a la ficha de su acción, que es donde se edita.

**Envíos sueltos** (desde el 28/09/2026, migración 0058): un mailing, un
WhatsApp o una push SIN una acción detrás ("de repente no hay una promoción y
tenemos que salir con un email marketing, con una push, con un WhatsApp"). Se
crean acá, con el **+** de cada canal o tocando un día libre. Son barras de la
sección `envio`, con el canal en `banda`, un solo día (`desde` = `hasta`) y lo
que en un envío de acción lleva la pieza: formato, hora y estado. Tienen su
propia ficha (estado y avisos) y en el cronograma se ven sin el borde de los
que salen de una acción. El aviso de un envío dice "sale", no "arranca".

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
categoría, nombre, fechas y duración; el progreso de piezas publicadas; y la
estructura por áreas — **Web · Home**, **Web · Landing de la acción**,
**Físico**, **Email**, **WhatsApp**, **Push** — donde se agregan y se sacan
piezas y se les mueve el estado (pendiente → en proceso → aprobado →
publicado). Si la acción lleva header, dice en qué posición quedó, o avisa que
no entró. Arriba de todo están sus **avisos** (ver Avisos).

**La categoría se elige en el encabezado**, arriba del nombre, y en ningún
otro lado. Quien puede editar ve la cocarda con una flechita (o "Sin
categoría" en punteado, si todavía no tiene): la toca y elige otra de la lista
del mundo. Lo que se toca es un `select` de verdad, invisible, así en un
teléfono se abre la lista del sistema. Si la acción está en una fila que ya no
figura (una retirada, una que vino del Excel con otro nombre), esa también
aparece en la lista: si faltara, parecería que la categoría cambió sola. Los
demás ven la cocarda, sin poder tocarla.

**Editar nombre, fechas y color** abre el editor por encima de la ficha (antes
la ficha lo tapaba, y en un teléfono lo cubría entero). El editor no pregunta
la categoría: dice cuál tiene la acción, o que se le pone después. En un
teléfono sube desde abajo y tiene scroll propio.

Se cierra con Escape, con la X o tocando afuera.

### Copiar a otra fecha ("copiar del año pasado")

Pedido de Ivan (15/11/2026): las acciones se repiten cada año, y el Ciberlunes
2026 tiene que nacer del 2025 con todo lo que tenía. Al lado de **Editar** está
**Copiar a otra fecha** (en las acciones y en los envíos sueltos, para quien
tiene `calendario.edit`). Abre un cuadro que:

- arranca en **Al año que viene**: 364 días después (52 semanas), así cae el
  mismo día de la semana. Se puede elegir otra fecha con el mismo campo de
  fecha que el resto del calendario. La duración se mantiene;
- propone el nombre con el año corrido ("Ciberlunes 2025" → "Ciberlunes
  2026"), si la copia arranca en otro año y el nombre tiene un año de cuatro
  cifras que es el de la acción (el "Mundial 2030" de una acción de 2025 no se
  toca). Se puede cambiar antes de copiar;
- dice qué se lleva y qué se resetea, y avisa (sin frenar) si en esas fechas ya
  hay una acción con ese nombre: es la señal de que alguien ya la copió.

Lo copia el servidor (`POST /calendario/barras/{id}/copiar`), en el MISMO mundo,
en una transacción y con una sola subida de revisión:

| Qué | Cómo queda |
|---|---|
| La acción | Todos sus campos (categoría, color, formato, hora...), fechas corridas, firmada por quien copia. Un envío suelto vuelve a pendiente. |
| Piezas | En pendiente, sin la marca de SharePoint, con sus fechas propias corridas lo mismo. |
| Tareas | Solo si quien copia tiene `calendario.tareas` (si no, se copia el resto y se dice). En pendiente, vencimiento corrido e ids nuevos, todas en el primer nivel. La persona asignada y el responsable de Tienda siguen solo si todavía abren ese mundo. |
| Avisos | Los mismos días antes. Sale quien ya no abre el mundo; un aviso que se queda sin nadie no se copia. |

A cada responsable le llega **un** aviso con todas sus tareas, no uno por tarea.
Las columnas de piezas y tareas se copian leyendo el modelo
(`backend/app/services/calendario_copia.py`): una columna nueva viaja sola (una
fecha se corre, un timestamp no se copia). El id de la acción nueva lo pone el
front, así un reintento (se cortó la conexión) no la duplica. Después de copiar
se abre la ficha de la nueva, en su mes.

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

**Las bandas son las mismas todos los meses** (`catalogo.ts`): todas las
categorías y formatos de RM que aparecen en los Excel importados, menos las
filas retiradas (ver Categorías). Antes cada mes traía las suyas del Excel, y
de noviembre en adelante no había ni un renglón donde cargar nada. Cada banda
tiene además un **+** para crear aunque todos sus renglones estén ocupados ese
día.

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
| `calendario.pedidos` | Crear tareas en una acción, también para una agencia. |
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

**Los cambios de una misma acción salen de a uno y en orden** (desde el
12/11/2026; `escribir` y `colas` en `store.ts`). Ahora la ficha se abre apenas
se crea la acción, y la persona le pone la categoría o le carga una tarea en
el mismo segundo. Antes cada cambio viajaba por su cuenta: el segundo podía
llegar al servidor antes que el alta, el servidor contestaba que la acción no
existía y ese cambio se perdía. Cada cambio espera a que termine el anterior
de su misma acción; los de acciones distintas siguen saliendo a la vez.

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
lib/calendario/categorias.ts  la categoría de una acción: "Sin categoría", cuánto pesa cada una y las filas retiradas
lib/calendario/rejilla.ts     medidas y zoom
lib/calendario/store.ts       estado, guardado cambio por cambio y la revisión cada 15 s
lib/calendario/permisos.ts    quién puede qué, contra el usuario de la plataforma
lib/mundos.ts                 los mundos: nombre, color, qué partes tiene cada uno y el nombre de la plataforma
lib/calendario/seed.ts        el muestreo de los Excel (hoy solo se usan los nombres de las bandas)
lib/calendario/colores.ts     paleta y contraste
lib/calendario/fechas.ts      meses, días de la semana, findes, y las cuentas con fechas reales
components/calendario/        las pantallas (VistaLista, BloqueTareas y Cocarda son del 12/11/2026)
app/(dashboard)/calendario/   la página
app/(dashboard)/mundos/       el selector de mundos
app/(dashboard)/mis-tareas/   lo que cada uno tiene asignado
```

`derivar.ts`, `rejilla.ts` y `categorias.ts` no dependen de React ni de zustand
a propósito: son lo único que hay que portar con cuidado, y así se pueden
probar sin levantar nada.

## Pruebas

```
cd frontend && npm run test:calendario
```

179 comprobaciones, sin framework: se compilan con `tsc` y corren con node.
Fijan las reglas del header, el zoom, el cronograma de envíos, el header
mirado por fecha, las acciones que cruzan de mes y las categorías
(`categorias.test.ts`: qué cuenta como "Sin categoría", cuánto pesa cada una,
las filas retiradas y qué ofrece el selector; en `derivar.test.ts`, dónde va
cada fila y a qué renglón pasa una acción al cambiarle la categoría) y lo que
dice el cuadro de "Copiar a otra fecha" (`copiar.test.ts`: la fecha del año que
viene, el año del nombre, el choque y qué se lleva). No borrarlas al
reescribirlas con otro runner. Del lado del backend,
`tests/test_calendario_avisos.py`, `tests/test_calendario_migracion.py`,
`tests/test_calendario_envios_sueltos.py` y `tests/test_calendario_copiar.py`.
Mi agenda: `mi-agenda.test.ts` y, en el backend, `tests/test_mi_agenda.py`
(leer el link y el calendario) y las de `tests/test_tablero_agencia_api.py`
(conectar, que solo la vea su dueño, releer, desconectar).

## Lo que falta

- **Las categorías reales de Redexpres, Tienda Express, Tienda Viajes y
  Tienda Farma.** Hoy arrancan con una lista genérica.
- **Lo que todavía no está separado por mundo.** Los medios, finanzas, los
  precios y la planilla de pedidos se muestran en un solo mundo, pero sus
  datos no llevan mundo: si un día Redexpres tiene sus propios medios, hay
  que agregárselo. Las plantillas de cenefas se separan por su tipo
  (`cenefa_destinos.mundo`); el diccionario y el convertidor son compartidos.
- **Cargar los calendarios en Excel de los otros mundos.** El de Tienda Inglesa
  ya está; el de Redexpres y el cronograma de push, mails y WhatsApp (que
  incluye Tienda Viajes) siguen en sus planillas.
- **Ligar una tarea a una pieza.** Las tareas cuelgan de la acción; todavía no
  se puede decir "esta tarea es el arte de este header".
- **Los avisos configurados no miran el mundo**: se le puede avisar solo a
  quien abre ese mundo, pero si después se lo sacan, el aviso le llega igual.
- **Permisos por calendario.** Hoy hay tres permisos que valen para los cuatro
  calendarios juntos (`calendario.view`, `calendario.edit`,
  `calendario.retail_media`): quien puede ver, ve los cuatro. Lo pedido es ver,
  crear, editar y borrar por separado en cada uno.
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

# Mapa de la plataforma, zona A: calendario, tareas (pedidos) y entregas

Revisado contra el código de `main` al 24/11/2026 (último merge: PR #66, commit 57aae70).
Todas las rutas de la API llevan delante `/api/v1` (por ejemplo `GET /api/v1/calendario/datos`).
Acá se escriben sin el prefijo.

## Antes de empezar: lo que hay que saber del entorno de pruebas

- **Cuentas** (`backend/app/services/cuentas_de_prueba.py`):
  - `equipo-nocturno@example.com`: superadmin, todos los permisos, **los cinco mundos**
    (pasa por `/mundos` al entrar), alcance del calendario "Todo".
  - `agencia-de-prueba@example.com`: cuenta externa, empresa **«Agencia de prueba»**, solo
    `calendario.view`, solo Tienda Inglesa, alcance **"No lo ve"** (entra directo a su tablero).
  - `local-de-prueba@example.com`: local de Redexpres, sin `calendario.view` (no aparece en esta zona).
- **La base no está del todo vacía:** la migración 0076 carga las acciones 2026 de Redexpres (unas
  140, del Excel "PAC 2026"). Tienda Inglesa sí arranca vacía. Los otros tres mundos, vacíos.
- **Solo hay UNA persona interna.** Con eso no se puede probar: una cadena de varios aprobadores, la
  vista Equipo con varias personas, ni que alguien apruebe una pieza que se hizo uno mismo (la regla
  es "nadie decide sobre lo que subió"). Para eso hay que crear más usuarios en `/admin` (otra zona).
- **Importante (sospecha fuerte):** el README del equipo nocturno dice "pedirle una pieza a «Agencia
  de prueba»" desde la pestaña Tareas. Pero «Crear tarea» → «¿Quién la hace?» ofrece **solo los tres
  tableros fijos** (Publicis, Another Monday, Diseñadores; `GET /calendario/tableros` en
  `backend/app/core/tableros.py`) más la gente de Tienda. «Agencia de prueba» no aparece. Caminos que
  sí funcionan según el código:
  1. Crear la tarea para «Publicis» y, en la tarea ya creada (desplegada), en el selector
     «Quién la hace», elegir «Agencia de prueba (Agencia de prueba)». Sale un `confirm` ("Se la sacás
     a Publicis…"); al aceptar, el servidor la pasa a la agencia «Agencia de prueba» y su cuenta la ve.
  2. Armar una plantilla (las plantillas listan como agencias las empresas de las cuentas externas,
     incluida «Agencia de prueba») y usarla en la acción.
  3. Por API: `POST /calendario/barras/{id}/tareas` con `para: "agencia", agencia: "Agencia de prueba"`.
  En el tablero del equipo esas tarjetas caen en la pestaña **«Otras»** (no son de los tres tableros).
- **La IA está simulada** (`scripts/servidor_ia_simulada.py`): el control previo, la revisión de la
  pieza y el dictado contestan con reglas. Sirve para ver pantallas y permisos, no para juzgar lo que
  diría Claude.
- **Mails:** las cuentas de prueba tienen los avisos por mail apagados y no hay servicio de mail
  configurado: todo queda solo en la campanita.

---

## Pantallas

### Selector de mundos — `/mundos`
- **Para qué sirve:** elegir en qué negocio se trabaja (Tienda Inglesa, Tienda Express, Redexpres,
  Tienda Viajes, Tienda Farma). Lo elegido vale para toda la plataforma: menú, calendario, tareas,
  tablero.
- **Quién la ve:** cualquier usuario logueado con **más de un mundo** (`users.mundos`; superadmin =
  todos). Con uno solo, la pantalla se salta sola y manda al inicio. Se llega: al entrar (el layout
  redirige si hay varios mundos y ninguno elegido), con el botón «Cambiar mundo» de la barra del
  calendario (solo en pantallas ≥640 px) o desde el menú. Las cuentas externas pueden entrar (está en
  sus rutas) pero la agencia de prueba tiene un solo mundo, así que nunca la ve.
- **Qué hay en la pantalla:** "Hola, <nombre>. ¿En qué mundo vas a trabajar?", una bajada, y una
  tarjeta por mundo con su color, iniciales, nombre, bajada y la marca «el último que usaste».
- **Qué se puede hacer:** tocar una tarjeta → guarda el mundo en el navegador (`localStorage`,
  clave `core-tienda-mundo`) y va al inicio (`/calendario` si ve el calendario; `/entregas` si es
  externo o su alcance es "No lo ve"; si no, `/home`). No llama a la API.
- **Estados:** cargando = esqueleto de dos tarjetas. Sin estado de error (si `/auth/me` falla, el
  layout manda a `/login`).
- **Celular:** las tarjetas se apilan.
- **Datos para probarla:** entrar con `equipo-nocturno` (tiene los cinco).
- **Código:** `frontend/app/(dashboard)/mundos/page.tsx`, `frontend/lib/mundos.ts`,
  `frontend/app/(dashboard)/layout.tsx`; servidor: `backend/app/core/mundos.py`.
- **Puntos a mirar:**
  - El mundo elegido vive solo en ese navegador: en otro dispositivo vuelve a preguntar (sospecha de
    confusión menor).
  - El catálogo de mundos está duplicado a mano en `lib/mundos.ts` y `core/mundos.py`.

**Cómo el mundo cambia esta zona:**
- `/calendario`: trae solo las acciones de ese mundo (`GET /calendario/datos?mundo=`). Tienda
  Inglesa tiene cuatro partes (Comercial, Envíos, Retail Media, Headers); los otros mundos, solo
  Comercial y Envíos. Las categorías (filas) cambian: Tienda Inglesa sale del Excel, Redexpres tiene
  las suyas (`BANDAS_REDEXPRES`), los otros una lista genérica (Campañas, Promociones, Cartelería,
  Redes sociales, Otras acciones). Las plantillas, las personas asignables y los tipos de pedido
  también son por mundo (Imprenta, Video monitores, Bases escribana y Afiche bombas solo en Redexpres).
  En Redexpres cada acción nueva nace con la tarea «Lanzar» y dos avisos a todo el equipo (0077).
- `/entregas`: el tablero es del mundo elegido.
- `/mis-tareas`: muestra lo del mundo actual y avisa "También tenés pendientes en: <mundo>" con un
  botón para pasar.
- Un aviso de la campanita de otro mundo: al abrir la ficha, la pantalla cambia sola de mundo
  (`GET /calendario/ubicar/{id}`).

---

### Calendario (vista «Calendario», el mes) — `/calendario`
- **Para qué sirve:** ver el mes entero como en el Excel: las acciones de marketing por categoría,
  los envíos (mailing, WhatsApp, push), Retail Media y los headers de la home.
- **Quién la ve:** permiso `calendario.view` y alcance del calendario distinto de "No lo ve"
  (`users.calendario_alcance`: No lo ve / 1 mes / 2 meses / 12 meses / Todo). Internos y externos con
  alcance habilitado. Quien tiene "No lo ve" es redirigido a `/entregas` por el layout. Se llega por
  el menú «Calendario» (lateral y barra de abajo en el teléfono), al entrar, y por links
  `/calendario?accion=br-…` (campanita, Mis tareas, mails).
- **Qué hay en la pantalla:**
  - **Barra superior:** cuadradito con el color del mundo + "Calendario / <mundo>" y botón
    «Cambiar mundo» (si tiene varios); flechas de mes, selector de mes y de año (2025–2032), botón
    «Hoy» (apagado si ya estás en el mes actual). Segunda línea: selector de vista «Calendario /
    Lista / Equipo» (Equipo solo con `calendario.tareas`), chips de qué parte se ve («Todo · Comercial
    · Envíos · Retail Media · Headers», según el mundo) y, solo en vista Calendario y pantallas ≥768 px,
    el grupo de tamaño: «−», porcentaje (vuelve al 100), «+», «que entre el mes entero a lo ancho» y
    «Pantalla completa».
  - **Aviso de ventana** (arriba, solo si el alcance es 1, 2 o 12 meses): "Ves el calendario del mes
    actual (del 8 de noviembre al…)…" (`AvisoDeVentana.tsx`).
  - **Mi agenda** (fila de arriba de todo; ver su ficha más abajo).
  - **Calendario comercial:** título, contador "N acciones", botón «Ocultar categorías vacías / Ver
    las N categorías vacías» (si hay vacías) y «Nueva acción» (con `calendario.edit`). Rejilla: columna
    de categorías (MEGA EVENTO con estrella; Mailing GRAL y Especiales con un punto; «Sin categoría»
    en cursiva y primera, solo si hay alguna; «TIENDA FARMA» al final con «Ya no se usa»), una columna
    por día (hoy resaltado, fines de semana), barras de color con el nombre, "2/5" de tareas hechas,
    punto del **semáforo** (verde/amarillo/rojo) y flechas si la acción cruza de mes. Cada fila tiene
    un «+» para crear en esa categoría.
  - **Cronograma de envíos:** un carril por canal (email, WhatsApp, push). Muestra los envíos que
    salen de las piezas Email/WhatsApp/Push de cada acción y los **envíos sueltos** (sin acción). Aviso
    arriba de los envíos de acción que no tienen fecha propia. «+» por canal.
  - **Calendario Retail Media** (solo Tienda Inglesa): formatos de RM en eComm y Express, un carril
    por slot. HOME SLIDER (Retail Media) baja solo al header.
  - **Headers de la home** (solo Tienda Inglesa): conteo de banners por día (verde hasta 7, ámbar en 8,
    rojo arriba de 8), aviso rojo si una acción pidió header y no entró, y botón «Ver headers activos
    por fecha» que abre un panel lateral con las 10 posiciones de un día (flechas de día; las de RM
    se mueven con `calendario.retail_media`).
- **Qué se puede hacer:**
  - Navegar meses (flechas, selects, «Hoy»). Atajos: `←` `→` mes, `T` hoy, `+` `-` `0` zoom, `N`
    nueva acción (con `calendario.edit`), `Esc` saca las marcas. No andan mientras se escribe, con una
    ficha o el editor abiertos, ni con Ctrl/Alt/Cmd.
  - **Marcar columna:** tocar el número de un día pinta la columna entera de ámbar; tocar de nuevo o
    `Esc` la desmarca. **Marcar fila:** tocar el nombre de una categoría. Solo en el navegador.
  - **Zoom:** mientras nadie lo toque, el mes se ajusta solo al ancho. Tocarlo lo deja fijo (se guarda
    en el navegador). Pantalla completa usa la API del navegador; si la bloquea, ajusta al ancho.
  - **Ocultar categorías vacías:** se guarda en el navegador.
  - **Filtrar por parte:** chips (se guarda en el navegador; al cambiar de mundo vuelve a «Todo»).
  - **Crear:** «Nueva acción» (nace en «Sin categoría» y abre su ficha), «+» de una fila o tocar un
    día vacío de una fila (crea en esa categoría y **no** abre la ficha) → abre el **Editor** (ver
    abajo). En el cronograma, «+» de un canal o un día libre → envío suelto.
  - **Abrir:** tocar una barra comercial o un envío → **Ficha de la acción**. Una barra de Retail
    Media abre el editor (si puede editar). Una barra derivada en headers lleva a donde se edita.
  - Endpoints: `GET /calendario/datos?mundo=&rev=` (al entrar, cada 15 s con la pestaña visible, al
    volver a la pestaña o a la ventana; si no cambió nada contesta `sinCambios`), `GET
    /calendario/personas?mundo=`, `GET /calendario/mi-agenda`, `PUT /calendario/posiciones-rm/{clave}`
    (mover posiciones de RM).
- **Estados:**
  - Cargando: esqueleto gris de la barra y la rejilla ("Cargando el calendario…").
  - Sin permiso: escudo rojo y "No tenés acceso al calendario".
  - Sin ningún mundo: "Todavía no tenés ningún calendario asignado" + pedirle acceso a quien administra.
  - Varios mundos sin elegir: redirige a `/mundos`.
  - Sin conexión: franja ámbar bajo la barra: "No hay conexión con el servidor: lo que ves puede no
    estar al día." + cuántos cambios tuyos esperan ("No cierres esta pestaña"). Los cambios quedan en
    una cola en memoria y se mandan solos cuando vuelve; toast al recuperarse.
  - Error al guardar (el servidor dijo que no): toast con el motivo y vuelve a traer todo.
  - Link a una acción que no está: toast "Esa acción ya no está en el calendario, o es de un mundo al
    que no tenés acceso" (o, con alcance recortado, "queda fuera de lo que ves… Tus tareas están en
    Mis tareas").
  - Vacío: la vista Calendario no tiene mensaje de vacío: muestra las filas sin barras y "0 acciones".
- **Celular:** el bloque del mundo se esconde (lo dice la barra de arriba del layout); el mes ocupa la
  línea entera; el selector de vista va primero y a todo el ancho; los chips se deslizan de costado
  (el elegido siempre a la vista); **el grupo de zoom no aparece debajo de 768 px**; el zoom automático
  muestra una semana cómoda y el resto con el dedo; la columna de categorías es más angosta; las
  bajadas de las secciones se esconden; «Ocultar vacías» tiene texto corto.
- **Datos para probarla:** como `equipo-nocturno`, en Tienda Inglesa: crear 3 o 4 acciones en el mes
  actual (una con categoría MEGA EVENTO, otra que cruce de mes, otra «Sin categoría»), un envío suelto
  y una acción con la pieza Web · Home → Header. Para ver headers llenos hacen falta 8 o más acciones con
  header el mismo día. En Redexpres ya hay acciones 2026 cargadas.
- **Código:** `frontend/app/(dashboard)/calendario/page.tsx`, `frontend/components/calendario/`
  (`BarraSuperior.tsx`, `CalendarioComercial.tsx`, `CalendarioEnvios.tsx`, `CalendarioRetail.tsx`,
  `HeaderHome.tsx`, `PanelHeaders.tsx`, `Rejilla.tsx`, `MarcoScroll.tsx`, `Seccion.tsx`),
  `frontend/lib/calendario/store.ts`, `derivar.ts`, `rejilla.ts`, `semaforo.ts`, `categorias.ts`;
  servidor `backend/app/api/routes/calendario.py`, `backend/app/core/alcance.py`.
- **Puntos a mirar:**
  - Sin botones de zoom entre 0 y 767 px (teléfono y tablet en vertical): solo el ajuste automático
    (sospecha: alguien que quiera ver el mes entero en una tablet no tiene cómo).
  - Con «Ocultar categorías vacías» prendido en un mes sin nada, se ve solo la fila de días, sin
    ningún mensaje.
  - El README del calendario dice que sin conexión "los cambios no se guardan", pero el código los
    deja en cola y los manda después: documentación vieja.
  - Todo el cuerpo del calendario está en español fijo; solo el menú pasa por los archivos de idioma.

---

### Calendario (vista «Lista») — `/calendario` con la vista «Lista»
- **Para qué sirve:** las mismas acciones del mes como tarjetas grandes, agrupadas en «En curso», «Lo
  que viene» y «Ya terminaron». Pensada para leer en notebook o teléfono.
- **Quién la ve:** igual que el calendario. Se elige con el selector «Calendario / Lista / Equipo»
  (queda guardado en el navegador).
- **Qué hay en la pantalla:** arriba, con `calendario.edit`: «Nueva acción» y «Envío suelto por»
  Email / WhatsApp / Push (según el filtro). Cada tarjeta: cocarda de la categoría, semáforo (si avisa
  algo) o "Faltan N días", nombre, fechas cortas, "N/M piezas", "N/M tareas", iniciales de las
  personas asignadas y barra de tareas hechas. Si el filtro es «Headers», muestra el conteo de headers
  (no es una lista).
- **Qué se puede hacer:** tocar una tarjeta → ficha (una campaña de Retail Media abre el editor).
  Crear acción o envío suelto → editor. Sin endpoints propios (usa lo ya traído por `/datos`).
- **Estados:** vacío: "No hay nada cargado en <mes>" + "Creá la primera con el botón de arriba…" (o
  "Cuando se cargue una acción va a aparecer acá", sin permiso de editar). Cargando y sin conexión:
  igual que la vista Calendario.
- **Celular:** una tarjeta por fila (2 columnas en ≥640 px, 3 en ≥1280 px); los tres botones de envío
  suelto del mismo ancho en una fila.
- **Datos para probarla:** acciones en curso, futuras y pasadas dentro del mismo mes, con tareas y
  piezas.
- **Código:** `frontend/components/calendario/VistaLista.tsx`, `NuevaAccion.tsx`, `Cocarda.tsx`.
- **Puntos a mirar:** "Ya terminaron" dice "De este mes" pero agrupa por fecha de fin; una acción que
  cruza de mes aparece en los dos meses (es a propósito).

---

### Calendario (vista «Equipo») — `/calendario` con la vista «Equipo»
- **Para qué sirve:** ver cuántas tareas abiertas tiene cada persona por semana antes de repartir.
- **Quién la ve:** solo con `calendario.tareas` (si alguien la tenía elegida y pierde el permiso, ve
  el calendario).
- **Qué hay en la pantalla:** título, explicación ("Amarillo desde 3 en una semana, rojo desde 5") y una
  fila por persona: iniciales, "N tareas abiertas", celdas «Vencidas», una por semana (esta semana y
  las siguientes), «Más adelante», «Sin fecha», y «Ver tareas / Ocultar tareas».
- **Qué se puede hacer:** desplegar las tareas de una persona; tocar el nombre de la acción abre su
  ficha. Sin endpoints propios.
- **Estados:** vacío: "Nadie tiene tareas abiertas en este mundo."
- **Celular:** títulos cortos en las celdas ("Esta sem.", "16/11").
- **Datos para probarla:** tareas asignadas a personas con distintos vencimientos (vencidas, esta
  semana, más adelante, sin fecha). En el entorno de pruebas solo hay una persona interna.
- **Código:** `frontend/components/calendario/VistaEquipo.tsx`, `frontend/lib/calendario/carga.ts`.
- **Puntos a mirar:**
  - Cuenta solo por `asignadoA`: lo que hace una agencia (sin persona asignada) y lo que cada uno
    **lleva como responsable de Tienda** (0090) no suma carga a nadie (sospecha: desde que "una tarea =
    un pedido", buena parte del trabajo del equipo es seguir piezas de agencias, y no se ve acá).
  - Una persona que ya no abre el mundo aparece como "Persona <id>".

---

### Editor de acción / envío / campaña (cuadro) — se abre sobre `/calendario`
- **Para qué sirve:** crear o cambiar nombre, fechas y color de una acción (o de un envío suelto, una
  campaña de RM o un banner manual), y eliminarla.
- **Quién la ve:** `calendario.edit`. Se abre con «Nueva acción», `N`, el «+» de una fila, un día vacío,
  o «Editar nombre, fechas y color» en la ficha.
- **Qué hay en la pantalla:** título («Nueva acción», «Editar acción», «Nuevo envío», «Nueva campaña»…),
  categoría que tiene (o que se pone después, en la ficha), «Nombre», «Arranca» y «Termina» (en un envío:
  «Sale el», «A las» y «Qué es»), resumen "Va del… · N días" (y en qué meses se ve si cruza), paleta de
  colores, vista previa «Así se va a ver», y abajo «Eliminar» (solo al editar), «Cancelar», «Crear /
  Guardar».
- **Qué se puede hacer:**
  - Crear → `POST /calendario/barras` (el id lo pone el navegador). Una acción "Sin categoría" abre su
    ficha sola; creada desde una fila, no.
  - Guardar → `PATCH /calendario/barras/{id}` (solo lo que cambió; si la acción se corre, las tareas de
    plantilla ancladas se corren solas y sale un toast con cuántas).
  - Eliminar → pide confirmación en el pie: "¿Eliminar <nombre>? Se van con ella N tareas, N piezas y N
    avisos (y el pedido de fotos). No se puede deshacer." → `DELETE /calendario/barras/{id}` (queda en
    auditoría `calendario.borrar`).
  - Cerrar con `Esc`, la X, «Cancelar» o tocando afuera.
- **Estados:** «Crear/Guardar» apagado si falta el nombre o las fechas no son válidas (fin antes del
  inicio, año irreal); el resumen de fechas se pone rojo. Error del servidor: toast. Fuera del alcance
  del usuario: el servidor contesta 422 "Esa fecha queda fuera de lo que ves del calendario…".
- **Celular:** sube desde abajo como hoja, con manija y scroll propio; se cierra deslizando hacia abajo.
- **Datos para probarla:** ninguna (sirve para crear). Para eliminar, una acción con tareas, piezas y
  avisos.
- **Código:** `frontend/components/calendario/EditorBarra.tsx`, `store.ts` (`guardarBarra`,
  `borrarBarra`); servidor `calendario.py` (`crear_barra`, `cambiar_barra`, `borrar_barra`).
- **Puntos a mirar:**
  - **Eliminar una acción borra en cascada sus tareas y, con ellas, las entregas con sus imágenes y
    ZIP** (`ondelete="CASCADE"` en `calendario_entregas`, `calendario_versiones`,
    `calendario_version_imagenes`, `calendario_version_zips`). La confirmación dice "N tareas", no que
    se van imágenes entregadas por la agencia. Choca con la regla "las imágenes de las entregas no se
    borran nunca" (sospecha fuerte).
  - Tocar afuera cierra sin preguntar y se pierde lo escrito.
  - Los campos de fecha son nativos (`type="date"`) acá, y en otros lugares se usa `CampoFecha`.

---

### Ficha de la acción (panel lateral) — `/calendario?accion=br-…` (o tocando una acción)
- **Para qué sirve:** todo lo de una acción: sus tareas (pedidos), sus piezas, sus avisos y, en mundos
  con locales, las fotos de colocación.
- **Quién la ve:** quien ve el calendario y la acción cae en su alcance. Una cuenta externa ve la ficha
  recortada (ver «Cómo lo ve una cuenta externa»). Se llega tocando una barra o tarjeta, desde un aviso
  de la campanita, desde Mis tareas («Abrir la acción»), desde los choques de otra ficha, o con
  `?accion=` en la URL (`&pestana=fotos` la abre en Fotos).
- **Qué hay en la pantalla:**
  - **Encabezado** con el color de la acción: categoría (con `calendario.edit` es un selector: la
    cocarda con flechita o "Sin categoría" punteado; sin permiso, la cocarda sola), píldora de momento
    («Arranca en N días», «En curso», «En curso · termina hoy», «Terminó»), píldora del **semáforo**
    con lo que falta ("Faltan 2 piezas y 1 tarea"), nombre, rango de fechas y días, X para cerrar. Con
    `calendario.edit`: «Editar nombre, fechas y color» y «Copiar a otra fecha».
  - **Choques** (franja ámbar, si hay): "Se superpone con otro mega evento: X (fechas)" o "El 25/11 sale
    otro envío por Email: X". Tocar el texto abre la otra acción.
  - Franja de progreso: "N de M piezas publicadas" con barra (o "Todavía no tiene piezas cargadas").
  - Si tiene la pieza Header: "Ocupa la posición N del header de la home" (violeta) o "Pide header pero
    no entró… Hay que bajar algo, y eso lo decidís vos" (rojo).
  - **Pestañas** con número: «Tareas» (para un externo «Mis tareas»), «Piezas», «Avisos» (no para
    externos), «Fotos» (con `calendario.edit`, acción comercial y mundo con locales o pedido ya hecho).
- **Qué se puede hacer:**
  - Cambiar la categoría (un `select` real, invisible) → `PATCH /calendario/barras/{id}` con `{banda,
    carril}`; la acción pasa a esa fila.
  - Moverse entre pestañas con el mouse o con `←` `→`. Cerrar con `Esc`, X o tocando afuera.
- **Estados:** si la acción la borra otra persona mientras está abierta, el servidor contesta 404 "la
  borró otra persona" al editar y se recarga.
- **Celular:** sube desde abajo como hoja (deja ver un poco de la página), con manija; se cierra
  deslizando hacia abajo. En la notebook entra por la derecha (600 px).
- **Datos para probarla:** una acción con tareas, piezas, avisos; dos MEGA EVENTO superpuestos o dos
  envíos del mismo canal el mismo día para ver choques; una acción que arranque en ≤3 días con algo
  pendiente (semáforo rojo), en ≤10 días (amarillo).
- **Código:** `frontend/components/calendario/PanelAccion.tsx`, `Cocarda.tsx`, `lib/calendario/choques.ts`,
  `semaforo.ts`, `useDialogo.ts`, `useDeslizarParaCerrar.ts`.
- **Puntos a mirar:**
  - Los choques solo miran lo que el navegador tiene cargado: con el alcance recortado, un choque con
    algo fuera de la ventana no se ve.
  - El semáforo marca rojo con "Ya arrancó" cualquier acción en curso a la que le falte algo, aunque
    termine en un mes.

#### Ficha › pestaña «Tareas» (las tareas = pedidos)
- **Para qué sirve:** desde el 24/11/2026 "una tarea = un pedido", todo en un solo nivel (migración
  0090). Una tarea puede ser común (de alguien de Tienda) o un pedido de piezas; si la hace una agencia,
  esa misma tarea es su **tarjeta** en el tablero.
- **Quién la ve / qué puede:**
  - Ver: todos los que ven la ficha (un externo, solo sus tareas).
  - «Crear tarea»: `calendario.tareas` o `calendario.pedidos` (nunca una cuenta externa).
  - Asignar, cambiar responsable, vencimiento, nombre, detalle, ordenar, borrar y usar plantillas:
    `calendario.tareas`.
  - Tildar o cambiar el estado: quien gestiona, o quien la tiene asignada **si no lleva entregas** (una
    con entregas "queda hecha sola cuando se aprueba la última fase").
- **Qué hay en la pantalla:** "N de M hechas" o "¡Todas hechas!" con barra; sugerencia de plantilla
  ("¿Usar la plantilla «X»?" con «Usar plantilla», «Ver las tareas» y X «Ahora no»); la lista de
  tareas **minimizadas** (solo título, «Vencida» y "· <agencia>"); al desplegar: detalle, "Vence N días
  antes del inicio · se mueve con la acción" (si está anclada), **archivos del pedido**, pastillas
  «Quién la hace» (selector para quien gestiona: "Sin asignar", "La agencia (X)", personas),
  «Responsable de Tienda» (solo si la hace una agencia), «Vence el», estado (Pendiente / En proceso /
  Hecha), y botones «Nombre», «Detalle», papelera. Si lleva entregas, una caja con las fases, en qué
  fase está, "La hace X", el próximo paso y «Abrir la tarjeta». Abajo: «Crear tarea» y, para quien
  gestiona, «Usar plantilla».
- **Formulario «Nueva tarea»** (uno solo abierto a la vez):
  - **¿Qué se pide?** chips con los tipos del mundo (Banners, Email marketing (EMM), Redes sociales,
    Mailing, Envío WhatsApp, Push, Cenefas, Pantallas, Cartelería, Tótem, Otro; en Redexpres además
    Imprenta, Video monitores, Bases escribana, Afiche bombas) y «Otra cosa» (sin tipo). Tocar un tipo
    abre su **modal de opciones** (medidas, CTA, bloques, "Otra (escribila)", links que deben empezar
    con https://). Se pueden elegir varios: se crea una tarea por tipo.
  - **Nombre** (con un tipo se arma solo "<Acción> - <Tipo>" y se puede cambiar) o **Qué hay que
    hacer** (con «Otra cosa»).
  - **¿Quién la hace?** grupo «Agencias» (Publicis, Another Monday, Diseñadores, con "(todavía sin
    usuarios)" si no tienen cuentas) y grupo «Tienda Inglesa» (personas internas del mundo). Con agencia:
    "Le nace su tarjeta en el tablero de X y le avisamos."
  - **Detalle (opcional)** con «Dictar el pedido» (la IA lo ordena; sin dictado en el navegador, se
    escribe), **Archivos (opcional)** (hasta 5, 10 MB c/u: Excel, CSV, PDF, Word, imágenes, ZIP),
    **Responsable de Tienda** (solo con agencia) y **Vence el (opcional)**.
  - Pie: el motivo si falta algo ("Escribí qué hay que hacer, o elegí qué se pide." / "Elegí quién la
    hace."), «Cancelar», «Crear tarea» o «Crear N tareas».
- **Qué se puede hacer y endpoints:**
  - Crear → `POST /calendario/barras/{id}/tareas` (y si hay archivos, `POST
    /calendario/tareas/{id}/adjuntos` después, en la cola de la acción). Si es pieza (tiene tipo o la hace
    una agencia), el servidor le crea las entregas por defecto (una fase "Entrega", la aprueba quien la
    creó) y avisa a quien la hace. Toast: "Listo: nació su tarjeta en el tablero, en «Ingresado»…".
  - Tildar / estado → `PATCH /calendario/tareas/{id}` `{estado}`. Si la termina otro, le llega aviso a
    quien la creó. Cerrar a mano una pieza sin terminar la manda a Archivado.
  - Asignar → `PATCH … {asignadoA}`. Pasar una pieza de agencia a alguien de Tienda pide `confirm` y la
    saca del tablero de la agencia. Elegir una cuenta de otra agencia la pasa a esa agencia.
  - Responsable → `PATCH … {responsable}` (solo en lo que hace una agencia; avisa al nuevo responsable).
  - Vencimiento → `PATCH … {vence}` (suelta el ancla). Nombre (Enter guarda, Esc cancela) y detalle →
    `PATCH`.
  - Ordenar arrastrando la manija ⋮⋮ (mouse o dedo) o con `↑` `↓` → `PUT /calendario/barras/{id}/tareas/orden`.
  - Borrar → confirmación en el mismo botón ("Sí, borrar" o "Borrar con sus entregas") → `DELETE
    /calendario/tareas/{id}`.
  - Plantilla sugerida → `POST /calendario/barras/{id}/plantilla`; «Ahora no» se guarda solo en el
    navegador (`calendario-plantillas-descartadas`).
  - Archivos de una tarea ya creada: `GET /calendario/tareas/{id}/adjuntos`, bajar `GET
    /calendario/adjuntos/{id}`, sacar `DELETE /calendario/adjuntos/{id}`.
  - «Abrir la tarjeta» → abre la **ficha de la tarjeta** encima (modo "ver").
- **Estados:** vacío con texto según permiso ("Esta acción todavía no tiene tareas. Creá la primera…" /
  "Las crea el equipo."). Lista de personas que no llegó: "No se pudo traer la lista de personas. Se
  vuelve a intentar sola". Tipos que no llegaron: "No se pudieron traer los tipos. Probar de nuevo".
  Errores del servidor: toast.
- **Celular:** botones grandes (44–48 px); el modal de opciones va con portal a la pantalla.
- **Datos para probarla:** una acción; personas internas en el mundo; para la tarjeta de agencia, ver
  la nota del entorno de pruebas arriba.
- **Código:** `frontend/components/calendario/BloqueTareas.tsx`, `OpcionesDelTipo.tsx`, `Adjuntos.tsx`,
  `components/ia/DictarBrief.tsx`, `lib/calendario/tipos-de-tarea.ts`, `orden.ts`, `plantillas.ts`;
  servidor `calendario.py` (`crear_tarea`, `cambiar_tarea`, `borrar_tarea`, `ordenar_tareas`,
  `_nacer_tarjetas`), `services/tipos_de_tarea.py`, `api/routes/adjuntos.py`, `services/adjuntos.py`.
- **Puntos a mirar:**
  - **Borrar una tarea con entregas borra sus imágenes y ZIP en cascada** (el botón dice "Borrar con
    sus entregas", pero no "y las imágenes que mandó la agencia").
  - «Agencia de prueba» no aparece en «¿Quién la hace?» (ver arriba). En general, cualquier agencia que
    no sea una de las tres solo se puede elegir por plantilla o reasignando después.
  - Inconsistencia: el servidor y las plantillas siguen aceptando "Otra agencia (fuera de la
    plataforma)" (`para = 'fuera'`), pero «Crear tarea» ya no la ofrece.
  - El aviso "te pidió" a la agencia sale en el alta, **antes** de que terminen de subir los archivos:
    si la agencia abre enseguida, puede no verlos todavía.
  - Si la lista de archivos de una tarea no carga, no se muestra nada (sin aviso de error).
  - Links: en el modal de opciones tienen que empezar con `https://`; en «Entregar», también vale
    `http://`.
  - El vencimiento usa `input type="date"` al crear y `CampoFecha` al editar (dos controles distintos).

#### Ficha › pestaña «Piezas»
- **Para qué sirve:** la lista de piezas que lleva la acción, por área: **Web · Home**, **Web ·
  Landing de la acción**, **Físico**, **Email**, **WhatsApp**, **Push**, con su estado (Pendiente → En
  proceso → Aprobado → Publicado).
- **Quién la ve:** todos los que ven la ficha (externos incluidos, en solo lectura). Agregar, sacar y
  cambiar estado: `calendario.edit`.
- **Qué hay en la pantalla:** por área: título, cantidad, «Agregar» (abre los formatos que faltan; Header
  va en violeta con "↓ header"), cada pieza con su estado en una pastilla de color y X. Las de
  Email/WhatsApp/Push tienen «Sale» (fecha) y hora; sin fecha propia: "sin fecha propia: sale el <día>,
  con la acción" o «que salga con la acción».
- **Qué se puede hacer:** agregar `POST /calendario/barras/{id}/piezas`, estado/fecha/hora `PATCH
  /calendario/piezas/{id}`, sacar `DELETE /calendario/piezas/{id}`. Agregar Header baja la acción al
  calendario de headers; una pieza de envío aparece en el cronograma.
- **Estados:** "Sin piezas en esta área."
- **Celular:** igual, apilado.
- **Datos para probarla:** una acción; agregar Header, un Email con fecha y otro sin fecha.
- **Código:** `PanelAccion.tsx` (`BloqueArea`), `lib/calendario/tipos.ts` (`CATALOGO_PIEZAS`), `derivar.ts`.
- **Puntos a mirar:**
  - **Dos "aprobado" que no se hablan:** el estado de una pieza acá se mueve a mano y no tiene nada que
    ver con la aprobación de la tarjeta de la agencia en el tablero (el README lo lista como pendiente:
    "Ligar una tarea a una pieza"). Confuso para una persona (sospecha).
  - Quitar una pieza no pide confirmación.

#### Ficha › pestaña «Avisos»
- **Para qué sirve:** configurar recordatorios a la campanita (y mail) N días antes de que arranque la
  acción o de uno de sus envíos. No hay ninguno por defecto (salvo «Lanzar» en Redexpres).
- **Quién la ve:** internos (a externos no se les muestra ni les viaja). Agregar y quitar:
  `calendario.edit`.
- **Qué hay en la pantalla:** explicación, la lista (cuadrito con los días, "10 días antes de que
  arranque · sale el 15/11" o "ya salió", a quién, etiqueta «Lanzar» si es automático) con X; y el
  bloque «Nuevo aviso»: «Avisar [60/50/40/30/20/10] días antes de [que arranque la acción / el envío X]»
  con la fecha en que sale, la lista «A quién» (personas internas con tilde, arranca tildado quien mira)
  y «Agregar aviso».
- **Qué se puede hacer:** agregar `POST /calendario/barras/{id}/avisos` (si la fecha ya pasó, sale en
  el momento: toast "La fecha de ese aviso ya pasó, así que salió ahora."), quitar `DELETE
  /calendario/avisos/{id}`. El servicio `calendario_avisos.py` revisa cada 6 horas.
- **Estados:** vacío "Esta acción no tiene avisos. Configurá el primero acá abajo." Acción ya arrancada
  sin envíos pendientes: no se puede agregar. Personas cargando: esqueleto; error: "No se pudo traer la
  lista de personas…".
- **Celular:** el botón ocupa el ancho.
- **Datos para probarla:** una acción que arranque en menos de 10 días (el aviso de 10 sale ya) y otra
  más lejos; una acción con una pieza Email con fecha para contar desde el envío.
- **Código:** `PanelAccion.tsx` (`BloqueAvisos`), `lib/calendario/avisos.ts`, servidor
  `calendario.py` (`configurar_aviso`), `services/calendario_avisos.py`.
- **Puntos a mirar:**
  - Se puede elegir como destinatario a alguien del equipo con alcance "No lo ve" (la lista no mira el
    alcance); al tocar el aviso lo lleva a `/calendario` y el layout lo rebota a `/entregas` sin
    explicación (sospecha).
  - El README dice que un aviso no mira si después le sacan el mundo a la persona: le sigue llegando.

#### Ficha de un envío suelto (misma hoja)
- **Para qué sirve:** un mailing, WhatsApp o push sin acción detrás.
- **Qué hay:** encabezado "<Canal> · envío suelto", momento («Sale en N días», «Sale hoy», «Ya salió»),
  nombre, formato, "Sale el … a las …"; «Editar nombre, fecha, hora y color» y «Copiar a otra fecha»;
  choques; selector de **Estado**; bloque de Tareas (igual que arriba) y Avisos.
- **Endpoints:** estado `PATCH /calendario/barras/{id}` `{estado}`; el resto, igual que una acción.
- **Código:** `PanelAccion.tsx` (`FichaEnvio`).

---

### Copiar a otra fecha (cuadro) — desde la ficha
- **Para qué sirve:** "copiar del año pasado": crear una acción nueva igual a otra, con las fechas
  corridas.
- **Quién la ve:** `calendario.edit`. Las tareas se copian solo con `calendario.tareas`.
- **Qué hay en la pantalla:** opción «Al año que viene» (364 días, mismo día de la semana) u «Otra
  fecha»; resumen de fechas; «Nombre» con el año corrido sugerido ("Ciberlunes 2025" → "2026"); «Qué se
  copia»: piezas (en Pendiente, sin marca de SharePoint), tareas (en Pendiente, vencimiento corrido;
  o "no se copian: cargar tareas pide un permiso que no tenés"), avisos (mismos días; quién sale y por
  qué); aviso si en esas fechas ya hay una acción con ese nombre.
- **Qué se puede hacer:** «Copiar» → `POST /calendario/barras/{id}/copiar` (id nuevo lo pone el
  navegador: un reintento no duplica). Después abre la ficha de la copia en su mes. `Esc` cierra (no
  mientras copia).
- **Estados:** fecha inválida: "Revisá la fecha…". Ya copiada: "«X» ya estaba copiada: no se duplicó."
  Algo que no se copió: toast de advertencia con el detalle. Copia hecha pero no se pudo abrir: "La
  copia quedó guardada, pero no se pudo abrir: buscala en su mes."
- **Celular:** hoja desde abajo.
- **Datos para probarla:** una acción con piezas, tareas (incluida una de agencia), avisos.
- **Código:** `frontend/components/calendario/CopiarAccion.tsx`, `lib/calendario/copiar.ts`; servidor
  `calendario.py` (`copiar_barra`), `services/calendario_copia.py`.
- **Puntos a mirar:**
  - Copiar una acción con piezas de agencia **crea tarjetas nuevas en el tablero de la agencia y le
    avisa en el acto** (`_nacer_tarjetas`), con el pedido del año anterior. El cuadro no lo dice.
  - Los archivos adjuntos del pedido **no se copian** (no aparecen en `calendario_copia.py`), y el
    cuadro tampoco lo dice.

---

### Plantillas de tareas (cuadro) — desde la pestaña Tareas
- **Para qué sirve:** guardar las tareas que lleva casi siempre un tipo de acción, con vencimiento
  relativo (N días antes/después del inicio o del fin = "ancla"), y crearlas de una en una acción.
- **Quién la ve:** `calendario.tareas`. Se abre con «Usar plantilla» o desde la sugerencia.
- **Qué hay en la pantalla:** lista de plantillas del mundo (nombre, categoría o "Cualquier categoría",
  «Sugerida»), usar, editar, borrar (con "No, dejarla"), nueva, «Empezar con un ejemplo». Editor:
  «Nombre», «Para qué categoría», y por tarea: título, «Vence» (días, desde el inicio/fin, antes/después
  o sin fecha), «¿Qué es?» (tarea común o tipo de pieza), «¿Quién la hace?» (Alguien de Tienda, una
  agencia de la plataforma —las empresas de las cuentas externas—, u «Otra agencia (fuera de la
  plataforma)» con su nombre), responsable.
- **Qué se puede hacer:** guardar `PUT /calendario/plantillas/{id}`, borrar `DELETE
  /calendario/plantillas/{id}` (no toca las tareas ya creadas), usar `POST
  /calendario/barras/{id}/plantilla` (a cada responsable le llega UN aviso con todas; toast de
  advertencia si alguna agencia no tiene cuentas). Las tareas creadas quedan ancladas: si la acción
  cambia de fecha, se mueven solas (las no hechas); si alguien cambia el vencimiento a mano, se sueltan.
  `Esc` vuelve del editor a la lista; mientras se edita, tocar afuera no cierra.
- **Estados:** lista vacía; errores por toast.
- **Datos para probarla:** ninguna (se arman acá); una acción con categoría para ver la sugerencia.
- **Código:** `frontend/components/calendario/DialogoPlantillas.tsx`, `lib/calendario/plantillas.ts`;
  servidor `calendario.py` (plantillas).
- **Puntos a mirar:** las cuentas de vencimiento están dos veces (front y servidor) a propósito; si
  divergen, la pantalla muestra una fecha y el servidor guarda otra.

---

### Mi agenda (fila arriba del calendario + cuadros)
- **Para qué sirve:** ver el calendario personal de Outlook o Google al lado de las acciones. Solo lo ve
  su dueño. Es **solo de ida**: el link para llevar las acciones de Tienda a Outlook/Google/iPhone (0064)
  **se sacó**; hoy no existe exportar.
- **Quién la ve:** quien ve el calendario (externos con alcance habilitado también).
- **Qué hay en la pantalla:** sin conectar: una línea "Mi agenda. Traé tus reuniones de Outlook o
  Google…" con el botón para conectar. Conectada: una barra por día con eventos ("10:00 Daily +1"),
  «Actualizar» y engranaje. Si el link falló: "No se pudo leer tu calendario: <motivo>. Se ven los
  eventos de la última vez." + «Revisar el link». Panel de un día con flechas al día anterior/siguiente
  con eventos. Cuadro de conexión con pestañas Outlook / Google y los pasos, campo del link, y si ya está
  conectado «¿Desconectarlo?».
- **Qué se puede hacer:** `GET /calendario/mi-agenda` (cada 15 min y al volver a la pestaña), conectar
  `PUT /calendario/mi-agenda`, actualizar `POST /calendario/mi-agenda/actualizar`, desconectar `DELETE
  /calendario/mi-agenda`.
- **Estados:** link mal pegado: "Pegá el link entero: empieza con https:// (o webcal://)". Errores del
  servidor: toast.
- **Datos para probarla:** un link ICS público de internet. En la nube de pruebas puede no haber salida a
  internet (no lo pude confirmar).
- **Código:** `frontend/components/calendario/MiAgenda.tsx`, `lib/calendario/mi-agenda.ts`; servidor
  `api/routes/mi_agenda.py`, `services/agenda_externa.py`.
- **Puntos a mirar:** acepta `webcal://` (iCloud/iPhone) pero los pasos solo explican Outlook y Google.

---

### Mis tareas — `/mis-tareas`
- **Para qué sirve:** lo que la persona tiene asignado (y lo que lleva como responsable de Tienda) en el
  mundo actual, ordenado por vencimiento, más las entregas que esperan su decisión y las que le
  volvieron con cambios.
- **Quién la ve:** `calendario.view`. Internos **siempre**, aunque su alcance sea "No lo ve" (sus tareas
  le llegan igual). Externos: solo si su alcance no es "No lo ve" y no está en su menú. Se llega por el
  menú «Mis tareas» (lateral y barra de abajo), y la campanita lleva acá los avisos de tareas de quien
  tiene el calendario recortado.
- **Qué hay en la pantalla:** título «Mis tareas» con resumen (vencidas, esta semana); avisos fijos si
  algo no cargó con «Probar de nuevo»; "También tenés pendientes en: <mundo>" con botones para pasar;
  sección de entregas: «Para revisar · esperan tu decisión» y «Volvieron con cambios» (tarjetas del
  tablero); grupos «Vencidas», «Para esta semana», «Más adelante», «Sin fecha». Cada tarea: tilde (o, si
  lleva entregas, un ícono de capas "Queda hecha sola cuando se aprueba la última fase"), título, acción
  con link «Abrir la acción en el calendario» (sin link si queda fuera de su alcance), cocarda si es
  destacada, vencimiento, selector de estado (si no lleva entregas), y en las piezas la fase, el próximo
  paso y el botón a la tarjeta. Al final «Hechas · últimos 30 días» desplegable.
- **Qué se puede hacer:** tildar (toast "Hecha: X" con «Deshacer») o cambiar estado → `PATCH
  /calendario/tareas/{id}`; abrir la tarjeta (ficha de entregas encima); abrir la acción; cambiar de
  mundo. Endpoints de carga: `GET /calendario/mis-tareas` y `GET /calendario/mis-entregas` (se vuelven a
  pedir cuando se entrega o decide algo).
- **Estados:** cargando: esqueleto ("Cargando tus tareas…"); sin permiso: "No tenés acceso al
  calendario."; vacío: "Todavía no te asignaron ninguna tarea" o "Estás al día" (no se muestran si algo
  falló); falla: aviso fijo arriba con «Probar de nuevo»; error al guardar: toast "No se pudo guardar el
  cambio." y recarga.
- **Celular:** en la barra de abajo; nombres de acción cortados con el nombre entero al pasar.
- **Datos para probarla:** tareas asignadas a `equipo-nocturno` con vencimientos variados (una vencida,
  una esta semana, una sin fecha), una pieza de agencia con él como responsable, y una entrega en
  revisión donde él sea el aprobador de turno; tareas en otro mundo (Redexpres) para ver el aviso.
- **Código:** `frontend/app/(dashboard)/mis-tareas/page.tsx`, `lib/calendario/mis-tareas.ts`; servidor
  `calendario.py` (`mis_tareas`), `entregas.py` (`mis_entregas`).
- **Puntos a mirar:**
  - «Para revisar» solo muestra lo que espera al aprobador **de turno**: quien puede decidir como
    respaldo (`calendario.tareas`) no ve ahí lo que está trabado.
  - No se actualiza sola cada tanto (solo al entrar y cuando cambia algo desde la ficha de entregas).

---

### Tablero(s) / Mi tablero — `/entregas`
- **Para qué sirve:** el tablero estilo Trello de las piezas pedidas a las agencias (y a gente de
  Tienda): columnas **Ingresado** ("Nueva: todavía no se arrancó"), **En proceso** ("La están
  trabajando"), **Esperando feedback** ("Entregada: le toca al equipo"), **Finalizado** ("Aprobada") y
  **Archivado** ("Las finalizadas llegan solas a los 10 días").
- **Quién la ve:** `calendario.view`, **sin importar el alcance** (es el trabajo de cada uno). Interno:
  título «Tableros», ve todas las tarjetas del mundo dentro de su alcance más las suyas. Externo: título
  «Tablero de <empresa>» (o «Mi tablero»), solo las tarjetas de su empresa o asignadas a él. Se llega por
  el menú («Tablero» / «Mi tablero»), es el inicio de los externos y de quien tiene "No lo ve", y la
  campanita lleva acá con `?tarea=ta-…` (abre esa tarjeta encima).
- **Qué hay en la pantalla:**
  - Cabecera con ícono, título, bajada (para la agencia: "Lo que te pidieron… para mandarla a revisar,
    soltala en «Esperando feedback» y subí los materiales") y el **buscador** ("Buscar: Ciberlunes -
    Banners").
  - Para el equipo, **pestañas de tableros**: Publicis, Another Monday, Diseñadores y «Otras» (si hay
    tarjetas de otras agencias o de Tienda), cada una con su número.
  - Las cinco columnas con su número y bajada; tarjetas con: acción (y color del mundo), nombre, tipo
    corto, opciones pedidas, fases compactas si hay varias, para cuándo ("Para el 25/11 · 3 días antes
    del Ciberlunes", rojo si venció), quién la hace (el equipo ve el nombre de la agencia), a quién le toca
    ("Te toca…"), miniatura, y botón «Mover». Archivado: «Ver más (N)» y "A los 30 días en Archivado
    dejan de cargarse: las encontrás con el buscador."
  - Solo internos: «Análisis de entregas» desplegable (período 30 / 90 / 365 días: rondas hasta
    aprobar, aprobado a la primera, fases aprobadas, tiempos por agencia, se pasaron de fecha, tablas por
    tipo y por quién).
- **Qué se puede hacer:**
  - **Arrastrar** una tarjeta (mouse: apenas se mueve; dedo: mantener apretado). Las columnas válidas se
    marcan con borde punteado; las que no, se apagan. `Esc` cancela. O usar **«Mover a…»** (menú con lo
    que hace cada columna).
  - Reglas (las decide el servidor, cada tarjeta trae `puedo.mover`):
    - Quien la hace (la agencia): Ingresado ↔ En proceso; a **Esperando feedback** abre «Entregar» (la
      tarjeta pasa recién cuando se mandan los materiales). No aprueba, no finaliza, no archiva.
    - Quien decide (aprobador de turno o respaldo con `calendario.tareas`): Esperando → En proceso abre
      «¿Qué hay que cambiar?» (pedir cambios, con «Ver la revisión completa»); Esperando → Finalizado
      aprueba.
    - Archivar lo que no se terminó = **cancelar** la pieza: `confirm` "¿Cancelar «X»? Queda en
      Archivado y no se entrega ni se revisa…". Sacar del archivo vuelve a su columna.
    - **Cualquier persona interna** puede llevar la tarjeta a cualquier columna "a mano" (libre como
      Trello, 18/11): no se entrega ni se decide nada y no se avisa a nadie.
  - Tocar la tarjeta → ficha de la tarjeta (encima).
  - Endpoints: `GET /calendario/entregas?mundo=&rev=` (al entrar y cada **6 s**, más al volver a la
    pestaña o ventana), `GET /calendario/entregas/archivadas?mundo=&desde=`, `GET
    /calendario/entregas/buscar?mundo=&q=` (desde 2 letras), `GET /calendario/entregas/metricas?mundo=&dias=`
    (externos: 403), `POST /calendario/tareas/{id}/mover` `{desde, a, comentario}`, `GET
    /calendario/tableros?mundo=`.
- **Estados:** cargando: cinco columnas grises; error en la primera carga: "No se pudo traer el tablero.
  Se vuelve a intentar solo en unos segundos."; vacío: "Todavía no hay tarjetas" + "Se piden desde la
  ficha de una acción del calendario: «Crear tarea»…" (agencia: "Todavía no tenés tarjetas… aparece acá
  en «Ingresado» y te llega un aviso a la campanita"); columna vacía: "Nada por acá." (o "Soltá acá: …"
  mientras se arrastra); sin permiso: "No tenés acceso al tablero."; movimiento rechazado: toast con el
  motivo y la tarjeta vuelve; soltar donde no se puede: "No podés llevarla a X. Desde acá: …"; tarjeta ya
  movida por otro: "Esta tarjeta ya se movió: ahora está en X"; buscador fallido: "No se pudo buscar.
  Probá de nuevo."; análisis fallido: "No se pudo traer el análisis." con reintentar.
- **Celular:** se ve **una columna por vez** con un selector arriba (número + nombre; "Feedback" corto);
  arranca en la que tiene algo tuyo. Al arrastrar con el dedo aparece abajo la barra «Soltala en:» con las
  cinco columnas. «Mover» de 44 px.
- **Datos para probarla:** varias piezas pedidas a agencias en distintos estados (una sin arrancar, una
  arrancada, una entregada, una aprobada, una cancelada). Para el análisis, entregas con varias rondas.
  Con la cuenta de la agencia, al menos una tarjeta de «Agencia de prueba» (ver nota del entorno).
- **Código:** `frontend/app/(dashboard)/entregas/page.tsx`, `components/calendario/entregas/TarjetaEntrega.tsx`,
  `lib/calendario/tablero.ts`, `lib/calendario/entregas.ts`; servidor `api/routes/entregas.py`
  (`tablero`, `mover`, `buscar`, `metricas`), `services/entregas.py` (`columna_de`, `movimiento`,
  `archivar_finalizadas`).
- **Puntos a mirar:**
  - **Cualquier interno con `calendario.view` puede arrastrar una tarjeta de Esperando feedback a
    Finalizado** y queda aprobada (tarea hecha) sin estar en la cadena y **sin avisarle a nadie**, ni a la
    agencia (`_mover_a_mano`, `libre=not externo`). Igual con Esperando → En proceso: vuelve sin comentario
    y la agencia no se entera de qué cambiar (sospecha fuerte: la regla de aprobación se saltea por
    arrastre).
  - Después de la primera carga, si se corta la conexión **no se avisa**: el tablero queda viejo en
    silencio (solo hay mensaje si nunca cargó).
  - Las tarjetas de agencias que no son las tres (como «Agencia de prueba») van a «Otras».

---

### Ficha de la tarjeta (entregas) — cuadro global, `/entregas?tarea=ta-…`
- **Para qué sirve:** todo de una pieza: dónde está, a quién le toca, la ronda en curso grande, lo que hay
  que corregir, lo que se pidió, las rondas anteriores, comentarios; y desde acá se entrega, se revisa, se
  devuelve o se cambia la configuración.
- **Quién la ve:** quien puede ver la tarea (el equipo del mundo; la agencia dueña). Vive una sola vez en
  el layout: la abren el tablero, la ficha de la acción («Abrir la tarjeta»), Mis tareas y la campanita.
  En el tablero, la abierta queda en la dirección (`/entregas?tarea=…`): recargar, o volver a entrar
  cuando venció la sesión, la abre de nuevo; al cerrarla se saca (H-039 y H-040, 26/11/2026).
- **Qué hay en la pantalla (modo «ver»):**
  - Encabezado: tipo, nombre, acción, "Vence el / Venció el", X.
  - 1) Línea de fases (si hay varias), "Ronda 2 · Volvió con cambios" (en rojo), el **próximo paso** en
    grande ("Te toca entregar", "Esperando que revise X"…), cadena de aprobación si hay varios ("Marta ✓ →
    Carlos (le toca)"), y el botón: «Entregar» / «Entregar ronda N» (quien la hace) o «Revisar ahora» /
    «Revisar como respaldo» (quien decide).
  - «Devolver para corregir» (con todo aprobado, para aprobadores o quien gestiona).
  - "Volvió después de aprobada: <fase>" con el motivo, si la abrió una devolución.
  - 2) La ronda en curso grande con miniaturas, link, «Bajar el ZIP (peso)», «Abrir el link / Bajar el
    original», «Bajar imágenes» (vistas previas 1600 px). Si volvió con cambios: «Lo que hay que corregir
    (N)» con lo escrito por quien revisó y las marcas sobre la imagen. Si faltan piezas del pedido: lo que
    falta y el porqué.
  - 3) «Lo que se pidió» (abierto antes de la primera entrega): lista de opciones con medidas, detalle,
    **archivos del pedido**.
  - 4) «Rondas»: cada una en un renglón ("Ronda 1 · Volvió con cambios · Publicis · 19/11") que se abre.
  - Comentarios (al costado en ≥1024 px; al final en pantallas chicas): "Escribí un comentario…",
    Ctrl/Cmd+Enter manda.
  - «Cambiar el pedido, las fases o quiénes aprueban» (con `puedo.configurar` y que vea el calendario).
- **Qué se puede hacer:** `GET /calendario/tareas/{id}/entregas` (y cada 4 s con `huella` mientras se
  mira; no mientras se entrega o revisa), imágenes `GET /calendario/entregas/imagenes/{id}?tam=mini|grande`,
  ZIP `GET /calendario/versiones/{id}/zip`, comentar `POST /calendario/tareas/{id}/comentarios`,
  devolver `POST /calendario/tareas/{id}/devolver`, configurar `PUT /calendario/tareas/{id}/entregas`.
  `Esc` cierra solo en modo "ver".
- **Estados:** cargando: esqueleto ("Cargando las entregas…"); error: mensaje + «Probar de nuevo» (y se
  puede cerrar); sin comentarios: "Todavía no hay comentarios. Usalos para explicar cambios o hacer
  preguntas."; pedido vacío: "El pedido no tiene detalles cargados."; ZIP que no entró: "Sin link al
  original: pedíselo a quien la hace."
- **Celular:** pantalla entera, sube desde abajo; comentarios al final.
- **Datos para probarla:** una pieza con al menos una entrega; otra con dos rondas (una con cambios);
  otra aprobada (para «Devolver»).
- **Código:** `components/calendario/entregas/VistaEntregas.tsx`, `LineaDeFases.tsx`, `LoQueFalta.tsx`,
  `ImagenConMarcas.tsx`, `useImagen.ts`, `store/entregas.ts`; servidor `api/routes/entregas.py`.
- **Puntos a mirar:**
  - «Cambiar el pedido…» se esconde a quien gestiona tareas pero tiene el calendario en "No lo ve", aunque
    el servidor se lo permite a propósito (`listar_personas`): inconsistencia front/servidor.
  - `DELETE /calendario/tareas/{id}/entregas` (`entregasApi.quitar`) y `configurarEntregas` del store no
    se usan en ninguna pantalla: endpoint sin botón.

#### Entregar (modo «entregar» de la ficha de la tarjeta)
- **Quién:** quien la hace (`puede_entregar`): la persona asignada o cualquier cuenta de la agencia dueña.
- **Qué hay:** "Entregar los materiales" / "Entregar la ronda N"; "Lo que pidieron cambiar" si fue
  devuelta; **Las imágenes** "N de 4" con «Sacar foto» (cámara), «Elegir imágenes / Agregar más»; «¿Están
  en una carpeta? Subí el ZIP (hasta 40 MB)» (saca las imágenes de adentro y, al entregar, el servidor
  completa con PDF u otras); aviso de que las imágenes se achican (1600 px, JPEG) y que el original es el
  ZIP o el link (resaltado en la última fase si no hay ninguno); «Comentario (opcional)»; «Link al original
  (WeTransfer, Smash…)».
- **Al tocar «Entregar»:** si hay imágenes, primero el **control previo de la IA** (`POST
  /calendario/tareas/{id}/control-previo`, hasta un minuto, con «Mandar sin esperar»). Mira la primera
  entrega contra el pedido inicial y una ronda con cambios contra esos cambios. Si la plataforma ve que
  **faltan piezas del pedido** (por las medidas) o la IA ve algo, aparece el aviso con lo que falta, lo
  dudoso, lo que encontró en la pieza, «¿Por qué no va todo? (opcional)», y «Corregir» o «Mandar igual».
  Después `POST /calendario/tareas/{id}/versiones` (multipart; espera según el peso). Toast "Entregaste la
  ronda N. Quedó en «Esperando feedback»: le avisamos a quien la revisa." La IA revisa en segundo plano.
- **Estados:** más de 4 imágenes: "Entran hasta 4 imágenes por ronda…"; ZIP muy grande: "pesa X: el
  máximo es 40 MB. Si es más grande, pegá el link de WeTransfer."; ZIP sin imágenes ni PDF; link sin http;
  error: "No se pudo entregar. Revisá la conexión y probá de nuevo: no se pierde nada."; ZIP no guardado
  por espacio: toast de advertencia (la entrega se hace igual).
- **Si se sale con algo cargado:** Cancelar («¿Descartar lo que cargaste?») y «atrás» («¿Salir sin
  mandar?») preguntan y, si se dice que sí, se descarta; recargar o cerrar la pestaña preguntan con el
  aviso del navegador (el iPhone no pregunta). Lo cargado (la nota, el link, el porqué y las imágenes sueltas; el ZIP no) queda guardado en
  ese navegador un día y vuelve al entregar de nuevo esa tarjeta, con «Recuperamos lo que estabas
  cargando» y «Descartar». Se borra al mandar, al descartar y al cerrar sesión (H-039, 26/11/2026).
- **Código:** `entregas/FormularioEntrega.tsx`, `LoQueVioLaIA.tsx`, `borradores.ts`, `lib/calendario/zip.ts`,
  `piezas.ts`, `control-previo.ts`, `borrador.ts`; servidor `entregas.py` (`entregar`, `control_previo`),
  `services/revision_ia.py`, `services/espacio.py`.

#### Revisar (modo «revisar»: aprobar o pedir cambios)
- **Quién:** el aprobador de turno, o quien tiene `calendario.tareas` como respaldo. Nunca una cuenta
  externa, nunca quien subió esa versión (salvo agencia "de afuera").
- **Qué hay:** la imagen grande (tocar pone un pin numerado con su texto), miniaturas, «Comparar con la
  ronda N / la fase anterior» (lado a lado en notebook, pestañas en el teléfono); al costado (arriba en el
  teléfono), todo abierto: piezas que faltan, «Lo que se pidió» / «Lo que se pidió en la ronda N» con lo
  que ve la IA de cada punto (rojo falta, ámbar dudoso, verde hecho; "dice que lo corrigió"), y lo que
  encontró la IA en la pieza (con «Hacer marca» y descartar). Bloque con borde rojo si algo está mal.
  «Ya marcado en esta ronda», «Tus marcas» con texto y borrar, «Comentario para la agencia (opcional)»,
  **nota interna** ("Solo la ve el equipo: la agencia no"). Dos botones: **«Aprobar»** (sin marcas) o
  **«Pedir cambios»** (con marcas o comentario); la línea de arriba dice cuál va.
- **Endpoints:** `POST /calendario/versiones/{id}/decision`, `GET /calendario/versiones/{id}/revision-ia`
  (se reintenta mientras está pendiente), `PATCH /calendario/versiones/{id}/revision-ia/{obs}` (descartar).
- **Toasts:** "Listo: volvió a la agencia con tus marcas.", "¡Aprobada! Era la última fase: la tarea quedó
  hecha.", "Aprobaste tu parte: ahora la revisa el siguiente de la cadena."; error "No se pudo guardar la
  decisión…"; marca sin texto: "Escribí qué hay que cambiar en la marca N."; versión ya decidida: 409
  "Esa versión ya no es la que está en revisión: recargá".
- **Código:** `entregas/Revisor.tsx`, `PanelRevisionIA.tsx`, `ImagenConMarcas.tsx`,
  `lib/calendario/revision-ia.ts`, `comparar.ts`; servidor `entregas.py` (`decidir`), `revision_ia.py`.

#### Configurar (modo «configurar»)
- **Qué hay:** formulario para cambiar el tipo de pieza, el pedido (brief), las **fases** (Boceto, Final…
  hasta 100) y **quiénes aprueban** (hasta 6, en orden: la cadena). Toast "Listo: se guardaron los
  cambios."; "No se pudo traer la lista de personas." si falla.
- **Endpoint:** `PUT /calendario/tareas/{id}/entregas`.
- **Código:** `entregas/FormularioEntregas.tsx`, `VistaEntregas.tsx` (`EditarConfiguracion`).

---

### Campanita / Avisos — arriba a la derecha (en el teléfono, «Avisos» en la barra de abajo)
- **Para qué sirve:** los avisos de cada persona, incluidos todos los de este flujo.
- **Quién la ve:** cualquier usuario logueado (externos: recortado a lo que pueden ver).
- **Qué hay en la pantalla:** botón con campana, texto y número de no leídas (se pide cada minuto y al
  volver a la pestaña). Al abrir: «Notificaciones», «Marcar todas como leídas», lista de los 50 más nuevos
  con ícono por tipo (tarea = lista azul; entrega = capas ámbar; aviso de acción = reloj; RM/header =
  calendario violeta; fotos = cámara), mensaje, "hace 5 minutos", y «Marcar como leída» en cada no leída.
- **Qué se puede hacer:** tocar un aviso → lo marca leído y navega:
  - `calendario_tarea` (tarea asignada, terminada, responsable, tareas de plantilla/copia) →
    `/calendario?accion=…` (o `/mis-tareas` si el alcance no es "Todo").
  - `calendario_aviso` (avisos configurados, Lanzar) → `/calendario?accion=…`.
  - `calendario_header` (movieron posiciones de RM) → `/calendario`.
  - `calendario_entrega` (tarjeta nueva, para revisar, cambios pedidos, aprobada, finalizada, devuelta,
    comentario) → `/entregas?tarea=…` (abre la tarjeta encima del tablero).
  - `colocacion_completa` → `/calendario?accion=…&pestana=fotos`.
  - Endpoints: `GET /notificaciones`, `GET /notificaciones/no-leidas/count`, `POST
    /notificaciones/{id}/marcar-leida`, `POST /notificaciones/marcar-todas-leidas`.
- **Mails que salen de este flujo** (`backend/app/services/avisos_por_mail.py`, cada minuto, un mail por
  aviso, se apaga en «Mi perfil»; no salen avisos de hace más de un día):
  - **Sí por mail:** `calendario_tarea`, `calendario_aviso`, `calendario_header`. El botón del mail lleva
    al mismo lugar que la campanita.
  - **Nunca por mail (solo campanita):** todo lo del tablero, `calendario_entrega` (decisión de Ivan,
    19/11/2026, por el tope de 3.000 mails/mes). O sea: **la agencia no recibe mail** cuando le piden una
    pieza o le piden cambios; se entera solo si entra.
- **Estados:** cargando: esqueleto; vacío: "Todavía no tenés notificaciones"; falla al marcar todas:
  toast "No se pudieron marcar como leídas".
- **Celular:** hoja abajo de todo; la abre «Avisos» de la barra inferior.
- **Datos para probarla:** asignar una tarea a otra persona, pedir una pieza a la agencia, entregar,
  pedir cambios, aprobar, comentar, configurar un aviso con fecha ya pasada (sale en el momento).
- **Código:** `frontend/components/layout/Campanita.tsx`, `store/avisos.ts`; servidor
  `api/routes/watchlist.py` (notificaciones), `services/entregas.py` (`avisar`, mensajes),
  `calendario.py` (`_avisar`), `services/calendario_avisos.py`, `services/avisos_por_mail.py`.
- **Puntos a mirar:**
  - **Si falla la carga de la lista, muestra "Todavía no tenés notificaciones"** (el `catch` deja la
    lista vacía): un error se ve como "no hay nada" (sospecha).
  - La lista trae 50; el número cuenta todas las no leídas.

---

### Cómo lo ve una cuenta EXTERNA (Publicis, Another Monday, «Diseñadores», Agencia de prueba)
- **Quién es:** `users.es_externo = true` + `users.empresa`. Como mucho `calendario.view` (la base y el
  servidor lo impiden). Las tres agencias son iguales: «Diseñadores» es una agencia externa.
- **Menú:** «Mi tablero» (`/entregas`) y, solo si su alcance no es "No lo ve", «Calendario». Nada más (sin
  Mis tareas en el menú, sin herramientas). Abajo del menú, el nombre de su empresa en lugar de «Mi
  perfil». En el teléfono, barra inferior con Mi tablero, (Calendario), Avisos y Menú.
- **Rutas permitidas:** `/entregas`, `/perfil`, `/mundos` y, con calendario, `/calendario` y
  `/mis-tareas`. Cualquier otra la manda a `/entregas`. En la API solo llega a `/auth/`, `/calendario/` y
  `/notificaciones` (lo demás 403).
- **Alcance del calendario por usuario** (lo elige un admin en `/admin`; la agencia arranca en "No lo
  ve"): No lo ve (solo su tablero) / 1 mes (el actual) / 2 meses / 12 meses / Todo. "N meses" = el mes
  actual y los N−1 siguientes, más los últimos 7 días del mes anterior. Fuera de la ventana, una acción
  "no existe" (404). Arriba del calendario: "Ves el calendario del mes actual (del… al…). Solo tus
  tareas. Lo que viene más adelante aparece a medida que se acerca. Tus tarjetas las ves siempre en el
  tablero."
- **En el calendario ve:** **todas** las acciones de su ventana (nombres, fechas, piezas), pero de cada
  acción solo **sus** tareas; sin avisos, sin plantillas, sin fotos; sin vista Equipo; sin crear, editar,
  copiar ni pedir. En la ficha la pestaña se llama «Mis tareas»; «Piezas» en solo lectura. Puede tildar
  una tarea asignada a su cuenta si no lleva entregas. Puede conectar su Mi agenda.
- **En el tablero ve:** solo las tarjetas de su empresa (o asignadas a él), **siempre**, aunque la acción
  quede fuera de su alcance. Puede arrancar (Ingresado ↔ En proceso) y entregar. No aprueba, no pide
  cambios, no finaliza, no archiva, no ve el análisis de entregas, no ve la nota interna ni (salvo en su
  control previo) la revisión de la IA. De las personas ve solo las de su empresa y quienes aprueban sus
  entregas, sin mail ("Alguien del equipo" si no tiene nombre).
- **Campanita:** recortada a lo que puede ver. Le llegan: tarjeta nueva ("Iván te pidió: …"), cambios
  pedidos, aprobaciones, devoluciones, comentarios. Ningún mail de esto.
- **Datos para probarla:** entrar como `agencia-de-prueba`; tener una tarjeta de «Agencia de prueba» (ver
  la nota del entorno); para el calendario recortado, que un admin le cambie el alcance en `/admin`.
- **Código:** `frontend/lib/externos.ts`, `lib/alcance.ts`, `components/layout/Sidebar.tsx`,
  `NavegacionInferior.tsx`, `AvisoDeVentana.tsx`, `app/(dashboard)/layout.tsx`; servidor
  `backend/app/core/externos.py`, `core/alcance.py`, `core/tableros.py`.
- **Puntos a mirar:**
  - Con alcance habilitado, la agencia ve los nombres y piezas de **todas** las acciones de su ventana, no
    solo las suyas (es el diseño de la 0070, pero conviene tenerlo presente al probar permisos).
  - Si la empresa de la cuenta no coincide con uno de los tres tableros, el equipo no puede elegirla en
    «Crear tarea».

---

## Recorridos de punta a punta

### 1. El ciclo completo de una pieza con la agencia
**Quién:** equipo (`equipo-nocturno`) y agencia (`agencia-de-prueba`).

1. **Equipo** entra, elige «Tienda Inglesa» en `/mundos` y cae en `/calendario`.
2. Toca **«Nueva acción»** (o `N`). En el editor escribe "Ciberlunes 2026", pone del 30/11 al 02/12,
   elige color y toca **«Crear»**. Se abre la ficha.
3. En el encabezado toca **«Sin categoría»** y elige "MEGA EVENTO". La acción pasa a esa fila.
4. En la pestaña **«Tareas»** toca **«Crear tarea»** → en «¿Qué se pide?» toca **Banners** → en el modal
   tilda Header y Slider → cierra. El nombre se arma solo: "Ciberlunes 2026 - Banners".
5. En «¿Quién la hace?» elige **Publicis** (en el entorno de pruebas: ver el paso 5b). Pone un detalle,
   adjunta un Excel, elige su **responsable de Tienda** y la fecha. Toca **«Crear tarea»**.
   - Toast: "Listo: nació su tarjeta en el tablero, en «Ingresado»…". La tarea muestra "Entrega ·
     Te toca…/Le toca a Publicis" y «Abrir la tarjeta».
   - Repercute: tarjeta nueva en `/entregas` (pestaña Publicis) en **Ingresado**; aviso "<nombre> te
     pidió: Ciberlunes 2026 - Banners (Header, Slider). Es para el …" en la campanita de **cada cuenta de
     Publicis** (sin mail); aviso al responsable de Tienda (con mail si lo tiene prendido); el semáforo de
     la acción cuenta la tarea pendiente.
   - **5b (entorno de pruebas):** despliega la tarea, en «Quién la hace» elige «Agencia de prueba (Agencia
     de prueba)», acepta el `confirm`. La tarjeta pasa a la agencia de prueba (pestaña «Otras» del equipo).
6. **Agencia** entra con su cuenta → cae en **«Tablero de Agencia de prueba»**. Ve la tarjeta en
   Ingresado y el aviso en la campanita. Toca la tarjeta: lee «Lo que se pidió» y baja el Excel.
7. Arrastra la tarjeta a **En proceso** (arrancar). Después la arrastra a **Esperando feedback** (o toca
   «Entregar») → se abre **Entregar**: elige 2 imágenes (o un ZIP), pega un link de WeTransfer, toca
   **«Entregar»**. La IA hace el control previo (simulada); si faltan piezas del pedido, avisa y deja
   escribir por qué; toca «Mandar igual».
   - Repercute: la tarjeta pasa a **Esperando feedback**; aviso "Agencia… entregó la ronda 1 de Entrega en
     «…». Te toca revisarla." al aprobador (quien creó la tarea); en Mis tareas del aprobador aparece en
     «Para revisar»; la IA revisa la versión en segundo plano.
8. **Equipo** abre el aviso → `/entregas?tarea=…` → ficha de la tarjeta → **«Revisar ahora»**. Ve la
   imagen, lo que vio la IA; toca la imagen y escribe "Precio más grande"; agrega un comentario para la
   agencia y una nota interna; toca **«Pedir cambios»**. (Alternativa: en el tablero arrastrar Esperando →
   En proceso abre "¿Qué hay que cambiar?".)
   - Repercute: tarjeta a **En proceso** con "Volvió con cambios" en rojo; aviso "… pidió cambios en la
     ronda 1 … (1 marca). Te toca entregar la ronda 2." a todas las cuentas de la agencia; en Mis tareas de
     la agencia (si tuviera calendario) y en la tarjeta: «Lo que hay que corregir (1)».
9. **Agencia** abre la tarjeta: ve la marca y el comentario (no la nota interna). Toca **«Entregar ronda
   2»**, sube la imagen corregida; el control previo mira si la marca se ve hecha; manda.
   - Repercute: Esperando feedback, aviso al aprobador.
10. **Equipo** revisa: en el costado ve la marca de la ronda 1 con el veredicto de la IA; usa «Comparar con
    la ronda 1»; sin marcas, toca **«Aprobar»**. (O arrastra Esperando → Finalizado.)
    - Repercute: tarjeta a **Finalizado**; la tarea queda **hecha** en la ficha y en el semáforo; aviso de
      aprobación a la agencia ("Era la última fase: la tarea quedó hecha.") y "«…» quedó finalizada" a
      quien la pidió si no es quien la hace.
11. **Archivo:** a los 10 días pasa sola a **Archivado** (pasada diaria `archivar_finalizadas`); también se
    puede arrastrar Finalizado → Archivado. A los 30 días en Archivado deja de cargarse y se encuentra con
    el buscador. Las imágenes no se borran solas.

### 2. Una tarea interna (para Tienda)
**Quién:** quien lidera (`calendario.tareas`) o analista (`calendario.pedidos`), y la persona asignada.
1. En la ficha, «Crear tarea» → «Otra cosa» → "Brief a la agencia" → «¿Quién la hace?» una persona de
   Tienda → vence → «Crear tarea». Toast "Tarea creada. Le llegó el aviso a quien la tiene asignada."
2. La persona recibe aviso (campanita + mail) "… te asignó …"; la ve en **Mis tareas** («Para esta
   semana») y en la vista **Equipo** de quien reparte.
3. La persona la tilda en Mis tareas (toast con «Deshacer») o en la ficha.
4. Quien la creó recibe "… terminó …" en la campanita (y mail). El "2/5" de la barra y el semáforo cambian.
- Variante: con un tipo (ej. Cenefas) para alguien de Tienda, es una pieza con tarjeta (en «Otras»), y la
  persona entrega como una agencia. Si se la asignó a sí misma, nadie de la cadena la aprueba: decide
  quien tiene `calendario.tareas` como respaldo (en pruebas, con una sola persona interna, no hay quién:
  solo arrastrando "a mano").

### 3. Plantilla con ancla
**Quién:** `calendario.tareas`.
1. Ficha → «Usar plantilla» → nueva plantilla "Mega evento" para la categoría MEGA EVENTO, con tareas:
   "Brief" 30 días antes del inicio, "Banners" (tipo Banners, agencia) 10 días antes, "Retiro" 1 día
   después del fin. «Guardar plantilla».
2. En una acción MEGA EVENTO, la pestaña Tareas sugiere "¿Usar la plantilla «Mega evento»?" → «Usar
   plantilla». Se crean las tareas con fecha calculada ("Vence 30 días antes del inicio · se mueve con la
   acción"); a cada responsable, UN aviso; a la agencia, UN aviso con todas sus tarjetas.
3. «Editar nombre, fechas y color» y correr la acción una semana → toast con cuántas tareas se movieron.
4. Cambiar a mano el vencimiento de una → se suelta y ya no se mueve.

### 4. Copiar del año pasado
**Quién:** `calendario.edit` (+ `calendario.tareas` para que viajen las tareas).
1. Abrir una acción → «Copiar a otra fecha» → «Al año que viene» → revisar el nombre propuesto → «Copiar».
2. Se abre la ficha de la copia en su mes, con piezas y tareas en Pendiente y avisos con los mismos días.
3. Repercute: las piezas de agencia nacen como tarjetas nuevas en Ingresado y **la agencia recibe aviso
   en el momento**; los responsables reciben UN aviso con sus tareas; un aviso cuya fecha ya pasó sale ya.
   Los adjuntos del pedido no viajan.

### 5. Aviso configurado
1. Ficha → «Avisos» → "Avisar 10 días antes de que arranque la acción" → tildar personas → «Agregar
   aviso».
2. Si la fecha ya pasó, sale ahora (toast). Si no, el servicio lo manda dentro de su ventana (revisa cada
   6 h). Llega a la campanita (y por mail) y abre la ficha de la acción.

### 6. Devolver una pieza ya aprobada
1. En una tarjeta en Finalizado, quien aprueba o lidera toca «Devolver para corregir», escribe qué cambiar
   y manda (`POST /calendario/tareas/{id}/devolver`).
2. Se abre la fase "Entrega 2" (sin tope); la tarjeta vuelve a trabajo; la agencia recibe "… devolvió «…»
   para corregir: … Te toca entregar Entrega 2." y lo ve arriba al entregar.

### 7. Cancelar y retomar una pieza
1. En el tablero, arrastrar una tarjeta de Ingresado o En proceso a Archivado → `confirm` "¿Cancelar «…»?"
   → queda en Archivado y la tarea cerrada; la agencia ya no la puede entregar.
2. Para retomarla: «Mover a…» desde Archivado → vuelve a su columna. (Cerrar a mano la tarea desde la ficha
   también la archiva; reabrirla la devuelve.)

### 8. Arrastre "a mano" del equipo (para probar el punto a mirar)
1. Con una tarjeta en Esperando feedback, entrar con un usuario interno que **no** sea el aprobador ni
   tenga `calendario.tareas` (hay que crearlo en `/admin`).
2. Arrastrarla a Finalizado → toast "Quedó en Finalizado." → la tarea queda hecha, sin aviso a nadie.
3. Comparar con la campanita de la agencia y del aprobador (no les llegó nada).

### 9. Cambiar el alcance de una cuenta externa
1. Admin en `/admin` cambia el alcance de `agencia-de-prueba` a "1 mes".
2. La agencia (al recargar o en la próxima pregunta) ve «Calendario» en el menú, el aviso de la ventana, las
   acciones del mes con solo sus tareas. Navegar a dos meses adelante: vacío.
3. Volver a "No lo ve" con el calendario abierto: la próxima pregunta da 403, la pantalla vuelve a pedir
   quién es y la manda a su tablero.

### 10. Aviso de otro mundo
1. Asignar una tarea en Redexpres a una persona que está mirando Tienda Inglesa.
2. Esa persona toca el aviso → la pantalla pasa sola a Redexpres y abre la ficha.
3. En Mis tareas, desde Tienda Inglesa, ve "También tenés pendientes en: Redexpres" con el botón.

### 11. Sin conexión en el calendario
1. Con el calendario abierto, cortar la red (o apagar el backend) y cambiar el nombre de una acción.
2. Toast "Sin conexión con el servidor: el cambio quedó pendiente…" y franja ámbar "1 cambio tuyo espera…".
3. Volver la red → toast "Volvió la conexión: se guardó el cambio pendiente." y se trae todo.
4. Hacer lo mismo en el tablero: después de la primera carga no hay ningún aviso de que se perdió la
   conexión (punto a mirar).

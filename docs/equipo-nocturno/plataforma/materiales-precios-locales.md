# Mapa B — Materiales, precios y locales

Zona: cenefas (y todo lo que cuelga de `/materiales`), Tinín, precios y listas de
monitoreo, Redexpres (Mi pedido y Planilla), colocación (fotos de los locales) y
validación de redes sociales. Cómo lo ve una cuenta de local y cómo cambia según
el mundo.

Hecho leyendo el código de `main` al 24/11/2026. Lo que dice "sospecha" es eso:
algo que en el código parece frágil o confuso, sin haberlo probado en un
navegador. Todos los endpoints van con el prefijo `/api/v1` (en pruebas,
`http://localhost:8000/api/v1`).

---

## Antes de empezar: lo que vale para toda la zona

### Las cuentas de prueba (`backend/app/services/cuentas_de_prueba.py`)

| Cuenta | Qué es para esta zona |
|---|---|
| `equipo-nocturno@example.com` | Superadmin, entra a los 5 mundos. Ve todo, incluidas las pantallas "solo superadmin" de cenefas v2. Al entrar elige mundo. |
| `local-de-prueba@example.com` | Login de sucursal de Redexpres: permisos solo `ai.don_tino`, mundo solo `redexpres`, con un local asignado (el primero libre de la lista fija, en una base vacía es **"Nativo Florida"**). |
| `agencia-de-prueba@example.com` | Externa. No ve nada de esta zona (el layout la manda a su tablero). |

No hay una cuenta "del equipo sin superadmin". Para ver cómo se comporta alguien
con permisos parciales (por ejemplo solo `cenefas.view`, o `redexpres.view` sin
`redexpres.manage`) hay que crearla desde `/admin` con la cuenta superadmin.

### La IA en el entorno de pruebas

`scripts/servidor_ia_simulada.py` solo simula **Don Tino, el dictado y la
revisión de piezas** (`ia_cliente.cliente_anthropic`). Todo lo de esta zona que
usa IA llama a la API real con una clave falsa (`sk-ant-simulada-no-es-una-clave`)
y **va a fallar**:

- Tinín (chat flotante, sugerir columnas, mecánicas, alcohol, generar
  descripciones, unificar categorías): `services/cenefas/tinin_agent.py`,
  `convertidor_ai.py` (usa `debate_service._ask_claude`).
- Doña Tina en precios (filtro de relevancia, chat, reporte): `services/dona_tina_precios.py`.
- CatTi en la validación de RRSS (lectura del mailing PDF y de cada placa): `services/rrss/catti.py`.

Sirve para mirar los **estados de error** de esas pantallas, no para juzgar lo
que contestaría la IA. No reportarlo como "la pantalla no anda".

Otros apagados en pruebas: el chequeo diario de las listas de precios
(`WATCHLIST_CHECK_INTERVAL_HOURS=0`), la cotización automática del dólar
(`COTIZACION_AUTO_UPDATE=false`) y la curaduría diaria de lo que aprende Tinín
(`CENEFAS_CURADURIA=false`). La búsqueda de precios consulta los sitios reales
de los supermercados: necesita internet y puede venir vacía por bloqueo.

### Qué trae la base vacía (lo siembran las migraciones)

- Tipos de cenefa (`cenefa_destinos`, migraciones 0040, 0046, 0060):
  **Rompe Precios**, **Parrilla y Vinos** (con 2.700 cenefas "declaradas" que
  ya aparecen en el informe) y **Pruebas** (sin costo) en Tienda Inglesa;
  **Redexpres** (sin costo) en Redexpres.
- Ninguna plantilla de cenefa, ningún mes de Redexpres, ninguna descripción en
  el Diccionario, ninguna lista de precios, ningún pedido de fotos.
- La lista de los ~60 locales de Redexpres está fija en el código
  (`LOCALES` en `backend/app/api/routes/redexpres.py`), no en la base.

### Archivos de ejemplo que hay en el repo (en git)

- `backend/app/static/cenefa_templates/Base cenefa A4 1.pptx` (A4),
  `Base pinchos 1.pptx` (pinchos), `Bases cenefas BLACK 1.pptx` (3xA4): sirven
  para cargar plantillas.
- `backend/tests/data/planilla_rrss.xlsx`: planilla de campaña para la
  validación de RRSS.
- El botón **"Descargar plantilla Excel"** de Cenefas baja un Excel con las 26
  columnas del sistema **y filas de ejemplo** (`data_engine.generate_template_bytes`,
  `_EJEMPLOS`): sirve tal cual para generar cenefas.
- No hay un Excel "de gestión" para el Convertidor. Se arma con openpyxl con los
  encabezados que usan las pruebas (`backend/tests/test_listado_sin_convertir.py`):
  `CODIGO, SECCION, NRO_OFERTA, NOMBREARTICULO, MONEDA, PRECIOANT, PRECIO,
  COMENTARIOS, COMPRADOR, OFERTA, OFERTADET, DESCRIPCIONWEB`. El formato largo
  con stock por sucursal está en `test_division_stock_sucursal.py`
  (`id_producto, descripcion, proveedor, sucursal, stock, cantidad_vendida,
  dsc_categoria, dsc_subcategoria, dsc_familia, dsc_subfamilia`).
- Ojo: las carpetas `Gestion/` y `Claude outputs/` con Excel reales están en la
  PC de Ivan pero **no en git**: en la nube no existen.

### La puerta de entrada (vale para todas las pantallas)

`frontend/app/(dashboard)/layout.tsx`, en este orden:

1. Sin sesión → `/login`. Con contraseña vencida → formulario de cambio.
2. Con varios mundos y ninguno elegido → `/mundos`.
3. Si la ruta no es del mundo elegido (`lib/mundos.ts`, `RUTAS_DE_MUNDO`) →
   **FueraDeMundo**: "Los precios no son de Redexpres… Estás en el mundo X", con
   botones "Pasar a <mundo>" (solo los que la persona tiene) y "Volver al inicio".
   No cambia de mundo sola.
4. Si no tiene el permiso (`lib/acceso.ts`, `REQUISITOS`) → **SinAcceso**:
   "No tenés acceso a las cenefas. Tu cuenta no tiene ese permiso…" + "Volver al inicio".
5. Si no, la pantalla.

El servidor exige igual el permiso en cada endpoint (`require_permission`).

---

## Cómo cambia esta zona según el mundo

| Pantalla | Tienda Inglesa | Redexpres | Express / Viajes / Farma |
|---|---|---|---|
| Cenefas, editor, informe, conocimiento, Convertidor (`/materiales/*`) | Sí. Tipos: Rompe Precios, Parrilla y Vinos, Pruebas (+ los que se creen) | Sí. Tipo único Redexpres: se entra derecho, sin elegir | No (FueraDeMundo) |
| Diccionario | Sí | No (FueraDeMundo), aunque el Convertidor de Redexpres escribe en el mismo catálogo | No |
| Validación de RRSS | Sí | No | No |
| Buscar precios / Listas | Sí | No | No |
| Planilla de pedidos / Mi pedido | No | Sí | No |
| Colocación | Solo en el menú si hay locales de tipo `tienda` con usuario (en pruebas no hay) | En el menú si hay locales `redex` con usuario (en pruebas sí: el local de prueba) | La URL abre pero dice "no tiene locales con usuario" |
| Fotos para subir | Para un local de tipo `tienda` | Para un local `redex` | Sin locales |

Lo que se guarda separado por mundo en esta zona: solo los **tipos de cenefa**
(`cenefa_destinos.mundo`) y las acciones del calendario de las que cuelgan los
pedidos de foto. Las plantillas, el Diccionario, los mapeos del Convertidor, las
listas de precios y las validaciones de RRSS son comunes (no filtran por mundo).

---

## Cómo lo ve una cuenta de LOCAL (sucursal de Redexpres)

- **Al entrar** va a `/home` (el chat de Don Tino), no a lo suyo
  (`inicioDe` en `lib/mundos.ts`: sin `calendario.view` → `/home`). Las
  sugerencias del chat son "¿Cómo sincronizo Google Ads?", "¿Qué es el ROAS?"…
- **Menú lateral** (`components/layout/Sidebar.tsx`): arriba "Fotos para subir"
  con un número rojo de pendientes (se pregunta al entrar y cada 2 minutos).
  Abajo, siempre abiertas (no hay botón "Herramientas" porque no tiene
  `calendario.view`): sección Redexpres → "Mi pedido"; sección Guía → "Don Tino,
  el asistente" y "Guía de uso". Arriba del menú, el mundo Redexpres sin botón de
  cambiar (tiene uno solo).
- **Barra de abajo en el teléfono** (`NavegacionInferior.tsx`): Fotos (con
  número), Mi pedido, Avisos, Más.
- **Puede:** cargar y confirmar el pedido mensual de su local; ver lo que le
  pidieron fotografiar y subir hasta 3 fotos por pedido; sacar una foto no
  aprobada; leer avisos; chatear con Don Tino; cambiar su contraseña en `/perfil`.
- **No puede:** calendario, Mis tareas, tablero; cenefas y Convertidor
  (SinAcceso); Diccionario, precios, RRSS (FueraDeMundo, "Tu cuenta no entra al
  mundo donde está esta herramienta"); Planilla general (SinAcceso); Colocación
  (SinAcceso). Ver la fila de otro local: el servidor solo le devuelve la suya
  (`/redexpres/mi-planilla`).
- **No puede deshacer** un pedido confirmado: solo un gestor lo desconfirma
  desde la Planilla.

---

## Pantallas

### Materiales (portada) — `/materiales`

- **Para qué sirve:** portada con cuatro tarjetas: Generar cenefas, Editor de
  plantillas, Convertidor de Excel, Diccionario.
- **Quién la ve:** `cenefas.view` o `cenefas.edit`; mundos Tienda Inglesa y
  Redexpres. **No está en ningún menú ni link**: solo escribiendo la dirección.
- **Qué hay en la pantalla:** título "Materiales", subtítulo, 4 tarjetas con
  ícono, etiqueta (Clásico / Editor / Descripciones / Catálogo) y "Abrir herramienta".
- **Qué se puede hacer:** solo navegar. No llama a ningún endpoint.
- **Estados:** no tiene.
- **Celular:** 1 columna en pantallas chicas; padding fijo `p-8`.
- **Datos para probarla:** ninguno.
- **Código:** `frontend/app/(dashboard)/materiales/page.tsx`.
- **Puntos a mirar:**
  - Sospecha: los títulos de las tarjetas usan `text-slate-100` (casi blanco)
    sobre `.card`, que en modo claro es blanca → el título se vería casi
    invisible en modo claro.
  - Pantalla huérfana; la tarjeta "Editor de plantillas" lleva a una pantalla
    que exige `cenefas.edit`, y la de "Diccionario" en Redexpres termina en FueraDeMundo.

### Cenefas — `/materiales/cenefas`

- **Para qué sirve:** generar cenefas: se cargan uno o varios Excel de productos
  y a cada uno se le eligen hasta 5 plantillas; cada par Excel × plantilla es
  una cenefa.
- **Quién la ve:** `cenefas.view` (menú "Herramientas → MATERIALES → Cenefas").
  Mundos Tienda Inglesa y Redexpres. Generar exige `cenefas.generate`; crear o
  borrar tipos de cenefa, `cenefas.edit`; cargar plantillas, `cenefas.import` +
  `cenefas.edit`; borrar plantillas, `cenefas.delete`. También se llega desde el
  Convertidor ("Convertir a cenefa").
- **Qué hay en la pantalla:**
  - Cabecera: ícono, nombre del tipo elegido (o "Generador de Cenefas") y su
    descripción. A la derecha: links "Informe", "Lo que aprendió" y botón
    "Cambiar tipo de cenefa" (si hay más de un tipo o si puede editar).
  - **Paso 0, selector de tipo** (`DestinoModal`): "¿Qué cenefas vas a hacer?",
    tarjetas de cada tipo del mundo; con `cenefas.edit`, "Nuevo tipo de cenefa"
    (nombre, descripción, ícono, color, casilla "cobrable") y tacho para borrar.
    En Redexpres, con un solo tipo, se saltea.
  - **Paso 1, carga** (`CenefaPanel`), dos columnas:
    - Izquierda "Archivos": "Descargar plantilla Excel", zona "Agregar Excel"
      (.xlsx/.xlsm, varios a la vez), y por cada Excel sus plantillas como
      chips + "Elegir plantillas" / "Otra plantilla" (máx. 5).
    - Derecha "Configuración": "Vigencia *" (con opciones guardadas en el
      navegador), casilla "Usar legales" + texto de legales, "Cocarda" (imagen
      PNG/JPG/WebP opcional). Abajo: "Se van a generar N cenefas…" y botón
      "Generar y descargar PPTX".
  - **Modal "Plantillas de <tipo>"** (`TemplatePickerModal`): buscador, modo
    "Seleccionar varias", lista con Reemplazar (subir otro .pptx), Editar (abre
    el editor en pestaña nueva), Eliminar; vista "Cargar nueva plantilla" con
    Tipo (A4, 3xA4, 6xA4, A5, Pinchos), Nombre de la acción, Mes, Año, archivo
    .pptx y vista previa del nombre ("Accion-AAAAMM-Tipo"), aviso si ya existe.
  - **Paso 2, revisión del lote**: ver la sección siguiente.
  - Burbuja de **Tinín** abajo a la derecha (ver "Tinín").
- **Qué se puede hacer:**
  - Listar tipos: `GET /tools/cenefas/v2/destinos?mundo=<mundo>`.
  - Crear tipo: `POST /tools/cenefas/v2/destinos`; borrar:
    `DELETE /tools/cenefas/v2/destinos/{slug}` (con `confirm()`; el servidor
    lo frena si tiene plantillas).
  - Descargar plantilla Excel: `GET /tools/cenefas/template?destino=<slug>`.
  - Listar plantillas del tipo: `GET /tools/cenefas/v2/templates?category=<slug>`.
  - Cargar plantilla: `POST /tools/cenefas/v2/import-pptx` y después
    `POST /tools/cenefas/v2/templates`. Reemplazar: import + `PUT /templates/{id}`.
    Borrar: `DELETE /templates/{id}` (de a una o varias).
  - Generar: `POST /tools/cenefas/v2/lotes` (multipart: excels, pares_json,
    vigencia, usar_legales, legales, image_overrides_json) → pasa al paso 2.
  - `?destino=<slug>` en la URL abre ese tipo directo.
- **Estados:** cargando tipos: spinner en el selector; error: toast "No se
  pudieron cargar los tipos de cenefa"; sin tipos: "Todavía no hay ningún tipo
  de cenefa creado en este mundo."; picker vacío: "Todavía no hay plantillas
  guardadas para <tipo>"; Excel repetido: toast; error al generar: toast con el
  detalle del servidor (por ejemplo un listado de gestión sin convertir lo frena
  con "qué hacer"). Sin permiso: SinAcceso.
- **Celular:** el panel de carga es `grid-cols-2` fijo, sin variante angosta.
- **Datos para probarla:** elegir el tipo **Pruebas** (no suma al informe),
  cargar una plantilla con `Base cenefa A4 1.pptx` y usar el Excel de
  "Descargar plantilla Excel".
- **Código:** `frontend/app/(dashboard)/materiales/cenefas/page.tsx`,
  `components/cenefas/{DestinoModal,CenefaPanel,LotePreviewStep}.tsx`,
  `components/cenefas/rompeprecios/TemplatePickerModal.tsx`,
  `backend/app/api/routes/cenefas_v2.py`, `routes/tools.py`,
  `services/cenefas/jobs.py`.
- **Puntos a mirar:**
  - Sospecha fuerte: los links "Informe" y "Lo que aprendió" se muestran a
    todos, pero esas páginas son solo superadmin (`useSuperuserGuard`): a
    cualquier otra persona la devuelven a `/materiales/cenefas` sin decir nada.
  - Sospecha: la pantalla no mira permisos para los botones: alguien con solo
    `cenefas.view` ve "Generar", "Cargar nueva plantilla", "Eliminar" y recibe
    un error al usarlos.
  - "Vigencia *" parece obligatoria pero se puede generar sin ella (ni el
    navegador ni el servidor la exigen).
  - Los mensajes del servidor al crear/borrar tipos dicen "mundo" ("Ya existe
    un mundo llamado…", "El mundo tiene N plantilla(s)…") cuando la pantalla
    dice "tipo de cenefa", y "mundo" hoy es otra cosa en la plataforma.
  - El Excel que llega del Convertidor viaja por `sessionStorage`; un listado
    muy grande podría pasarse del cupo del navegador (sospecha, sin probar).

### Revisión del lote (paso 2 de Cenefas) — `/materiales/cenefas` (misma URL)

- **Para qué sirve:** recorrer de a una las cenefas del lote, ver la primera
  hoja con los datos reales, mover o agrandar cuadros, y recién ahí generar el
  PPTX final y bajarlo.
- **Quién la ve:** quien generó el lote desde Cenefas (`cenefas.generate`).
- **Qué hay en la pantalla:** "Volver a la carga", resumen "X de N listas",
  "procesando N…", aviso "N cenefas fallaron"; navegación "Anterior / N de M ·
  K productos / Siguiente"; barra de Tinín "N cosas para revisar antes de
  confirmar" (`TininRevision`); avisos de desborde y de solape; lienzo grande
  (`Canvas`, alto fijo 820 px) con panel de propiedades y de reglas; vista de
  capacidad (cuántas "X" entran por cuadro). Abajo: "Generar las N" y
  "Descargar ZIP (N)". Al generar con cambios: modal "Vimos que hiciste cambios
  en el diseño… ¿Querés guardarlos?" → "Solo esta vez" / "Guardar en la
  plantilla". Con todo listo: "¿Confirmás que las cenefas salieron bien?" →
  "Sí, salieron bien" / "No, salieron mal" (sin confirmar, el archivo se borra a
  los 7 días).
- **Qué se puede hacer:**
  - Estado del lote cada 2,5 s: `GET /tools/cenefas/v2/lotes/{id}`.
  - Vista de una cenefa: `GET /tools/cenefas/v2/jobs/{id}`; capacidad:
    `POST /tools/cenefas/v2/capacidad`.
  - Generar: `POST /tools/cenefas/v2/lotes/{id}/confirm` (con lo movido y las
    reglas por cenefa); guardar en plantilla: `PUT /templates/{id}`.
  - Bajar una: `GET /jobs/{id}/download`; bajar todas:
    `GET /lotes/{id}/download` (ZIP).
  - Verificar: `PATCH /tools/cenefas/v2/informe/{jobId}/verificar` por cada cenefa.
  - Ctrl + clic para elegir varios cuadros (como en el editor).
- **Estados:** "Preparando las cenefas..." mientras no llegó el lote; por
  cenefa: en cola / procesando / lista para revisar / generada / error.
- **Celular:** no está pensado (lienzo de 820 px, paneles laterales).
- **Datos para probarla:** un lote generado como en la sección anterior.
- **Código:** `components/cenefas/LotePreviewStep.tsx`, `components/cenefas/editor/*`,
  `components/cenefas/{AvisosSolape,AvisosDesborde}.tsx`.
- **Puntos a mirar:**
  - Sospecha: si falla la consulta del lote, se calla ("reintenta en el próximo
    tick") y sigue consultando; si falla la de una cenefa, queda cargando para
    siempre. No hay mensaje de error ni corte.
  - Sospecha: el lote vive solo en la memoria de la página: recargar o salir
    pierde la revisión (no hay forma de volver a ese lote salvo el historial
    `/v2/jobs`, que es solo superadmin y no está enlazado).

### Editor de plantillas — `/materiales/cenefas/v2`

- **Para qué sirve:** diseñar o retocar una plantilla de cenefa: cuadros,
  variables del Excel, reglas de visibilidad.
- **Quién la ve:** `cenefas.edit` (si no, redirige a `/materiales/cenefas`).
  No está en el menú: se llega con "Editar" en el modal de plantillas
  (`?template_id=…`, pestaña nueva) o desde la portada `/materiales`.
- **Qué hay en la pantalla:** barra superior: volver, nombre editable, "● Sin
  guardar", contadores (comp., reglas, vars), "Guía de variables" (modal con
  `<<variable>>`), "Cargar" (menú de plantillas guardadas con renombrar y borrar,
  "+ Nuevo template"), "Guardar y Generar"/"Generar" (solo superadmin),
  "Guardar". Sin plantilla cargada: panel "Elegir base para el template"
  (predeterminadas, importar .pptx, "Empezar desde cero"). Con plantilla: panel
  izquierdo con pestañas Componentes / Reglas / Variables, lienzo al centro,
  panel derecho "Propiedades".
- **Qué se puede hacer:** `GET /tools/cenefas/v2/formats`,
  `GET /templates` (todas, sin filtrar por tipo), `GET /templates/{id}`,
  `POST /templates`, `PUT /templates/{id}`, `PATCH /templates/{id}/rename`,
  `DELETE /templates/{id}`, `POST /slot-bands`, `GET /builtin-definitions`,
  `POST /import-pptx`. "Generar" guarda y navega a `/v2/generar`.
- **Estados:** toasts de error al cargar formatos o plantillas; "Agregá
  componentes desde el panel izquierdo…" con la plantilla vacía; "Sin templates
  guardados" en el menú.
- **Celular:** no está pensado (paneles de 224 y 256 px fijos).
- **Datos para probarla:** una plantilla cargada desde el modal de Cenefas, o
  importar uno de los .pptx de `backend/app/static/cenefa_templates/`.
- **Código:** `frontend/app/(dashboard)/materiales/cenefas/v2/page.tsx`,
  `store/editor.ts`, `components/cenefas/editor/*` (Canvas 1.640 líneas,
  PropertiesPanel 1.242, RulesPanel 679).
- **Puntos a mirar:**
  - Sospecha: una plantilla creada o importada acá queda **sin tipo de cenefa**
    (el editor no manda `category`), así que no aparece en el modal de ningún
    tipo: solo en el menú "Cargar" del editor.
  - No avisa al salir con cambios sin guardar.
  - Textos escritos a mano en castellano fuera de los archivos de idioma; usa
    `-m-8` y `h-[calc(100vh-2rem)]` contra un contenedor con otro padding
    (posible desborde).

### Generar cenefas (motor v2) — `/materiales/cenefas/v2/generar`

- **Para qué sirve:** herramienta vieja de depuración: un Excel contra una
  plantilla (propia o predeterminada A4 / Pinchos / 3xA4), en 3 pasos.
- **Quién la ve:** solo superadmin. Se llega desde "Generar" del editor.
- **Qué hay en la pantalla:** stepper; paso 1 (plantilla v2 o predeterminada,
  formato, Excel, vigencia, legales con texto por defecto "Bases y condiciones
  en redexpres.uy", imágenes de las variables de imagen); paso 2 validación
  (filas, variables faltantes, resumen de reglas); paso 3 resultado ("¡Listo!",
  variables no encontradas, "Descargar PPTX", "Nueva generación").
- **Qué se puede hacer:** `POST /tools/cenefas/v2/validate`,
  `POST /tools/cenefas/v2/jobs`, `GET /jobs/{id}` cada 2 s,
  `GET /jobs/{id}/download`, renombrar/borrar plantillas.
- **Estados:** toasts de error; paso 3 con spinner, listo o "Error en la generación".
- **Celular:** columna de 672 px, usable.
- **Datos para probarla:** Excel de "Descargar plantilla Excel" + predeterminada A4.
- **Código:** `frontend/app/(dashboard)/materiales/cenefas/v2/generar/page.tsx`.
- **Puntos a mirar:**
  - Sospecha fuerte: el servidor deja cada trabajo en estado "preview"
    (esperando confirmación, `jobs.run_generation_job`), pero esta pantalla solo
    entiende pending/running/done/error: con "preview" muestra **"Error en la
    generación — Error desconocido"** y sigue consultando cada 2 s sin fin.
    Nadie confirma el trabajo (`PreviewStep.tsx`, que lo hacía, no se usa en
    ningún lado).
  - Legales por defecto de Redexpres aunque se esté en Tienda Inglesa.

### Historial de generaciones — `/materiales/cenefas/v2/jobs`

- **Para qué sirve:** lista de corridas del motor con estado y descarga.
- **Quién la ve:** solo superadmin. **Ningún link lleva acá.**
- **Qué hay en la pantalla:** tabla Fecha / Formato / Estado / Filas / Issues;
  "Actualizar"; modal de detalle con errores y avisos por fila.
- **Qué se puede hacer:** `GET /tools/cenefas/v2/jobs` (cada 3 s si hay alguna
  en curso), `GET /jobs/{id}`, `GET /jobs/{id}/download`.
- **Estados:** "Sin generaciones aún"; descarga vencida: "El archivo ya no está
  disponible — las corridas sin verificar se borran a los 7 días".
- **Celular:** tabla ancha sin adaptación.
- **Datos para probarla:** haber generado algo.
- **Código:** `frontend/app/(dashboard)/materiales/cenefas/v2/jobs/page.tsx`.
- **Puntos a mirar:** error al listar es silencioso (queda la lista vacía como
  si no hubiera nada); colores de estado sin variante oscura; los rótulos de
  formato no incluyen 6xA4 ni A5.

### Informe de producción — `/materiales/cenefas/v2/informe`

- **Para qué sirve:** cuántas cenefas se hicieron de verdad y cuánto vale ese
  trabajo (costo vigente $49 por cenefa).
- **Quién la ve:** solo superadmin (el link "Informe" de Cenefas se ve para todos).
- **Qué hay en la pantalla:** volver (va al editor), "Bajar en PDF", "Bajar en
  Excel"; filtros Desde, Hasta, Plantilla, Costo por cenefa (si se cambia, aviso
  amarillo de "simulación"); tarjetas Cenefas reales, Valor real, Con «Salió
  bien» tildado (solo si hay), Bruto medido; avisos/críticos; tabla "Qué se
  factura" (medido, declarado, TOTAL REAL, bruto, sin costo, pruebas iniciales);
  tablas Por mundo, Por mes, Por plantilla; "Historial de intentos" desplegable.
- **Qué se puede hacer:** `GET /tools/cenefas/v2/informe`,
  `GET /informe/export` (Excel), `GET /informe/export/pdf`,
  `PATCH /informe/{jobId}/verificar`. El costo se aplica al salir del campo o con Enter.
- **Estados:** spinner; error: solo un toast "No se pudo cargar el informe" y
  la página queda vacía bajo los filtros.
- **Celular:** grillas de 1 columna en angosto; tablas con scroll horizontal.
- **Datos para probarla:** con la base vacía ya muestra "Declarado · Parrilla y
  Vinos" (2.700). Para más, generar y confirmar lotes en un tipo cobrable.
- **Código:** `.../v2/informe/page.tsx`, `services/cenefas/informe.py`.
- **Puntos a mirar:** sin estado de error con reintento; el botón volver lleva
  al editor y no a Cenefas.

### Lo que aprendió (conocimiento de Tinín) — `/materiales/cenefas/v2/conocimiento`

- **Para qué sirve:** aprobar, corregir o descartar lo que el módulo fue
  aprendiendo (nombres de columnas, avisos, correcciones) antes de que Tinín lo use.
- **Quién la ve:** solo superadmin (link "Lo que aprendió" visible para todos).
  Decidir exige `cenefas.edit` en el servidor.
- **Qué hay en la pantalla:** pestañas Esperando / Aprobado / Descartado /
  Archivado con contador; cada ítem con tipo, origen ("de un mapeo de columnas
  que guardaste", "de una corrección hecha a mano"…), texto, y botones aprobar,
  editar ("Guardar y aprobar"), descartar.
- **Qué se puede hacer:** `GET /tools/cenefas/v2/conocimiento?estado=…` (4
  llamadas a la vez), `PATCH /conocimiento/{id}`.
- **Estados:** cargando; error: toast "No se pudo cargar lo que aprendió".
- **Celular:** sin adaptación específica.
- **Datos para probarla:** se llena al guardar un mapeo en el Convertidor,
  corregir descripciones en la grilla o generar cenefas.
- **Código:** `.../v2/conocimiento/page.tsx`, `services/cenefas/conocimiento.py`.
- **Puntos a mirar:** el permiso de la página (superadmin) no coincide con el
  del servidor (`cenefas.edit`) ni con quién ve el link.

### Convertidor de Excel — `/materiales/convertidor`

- **Para qué sirve:** convertir el Excel crudo de gestión en uno limpio con las
  descripciones correctas (buscadas por SKU en el Diccionario), revisar y
  corregir, y bajarlo o mandarlo directo a Cenefas.
- **Quién la ve:** `cenefas.view` (menú "MATERIALES → Convertidor de Excel").
  Mundos Tienda Inglesa y Redexpres. La IA exige `ai.tinin`; confirmar alias
  de columnas/mecánicas y guardar grupos, `cenefas.edit`.
- **Qué hay en la pantalla:**
  - Paso 1 "subir": texto de introducción, campo de archivo (.xlsx/.xlsm/.csv),
    "Continuar".
  - Si el archivo tiene varias hojas: barra "Hojas" (1, 2, 3… con nombre, filas
    y ✓ cuando ya se convirtió).
  - Paso 2 "Mapeo de columnas": "Tu archivo tiene N filas y M columnas";
    panel de Tinín con columnas que no reconoció (sugerir/confirmar); "Plantilla
    de mapeo" guardada (elegir, borrar, guardar con nombre); variables extra:
    para cada una, elegir columna o escribir un texto fijo; banco calculado
    (nombre + multiplicador, guardable); avisos (columna OFERTA con precios,
    formato largo con sucursal); "Volver" / "Convertir".
  - Paso 3 "grilla": "Subir otro archivo", leyenda de colores (falta, tipo
    inválido, aviso), "X de N productos matcheados automáticamente"; bloque de
    avisos de Tinín (`TininRevision`), en orden:
    sin descripción → "Generar descripciones y confirmar precios con IA";
    posibles duplicados (dos SKU del mismo producto) → unificar;
    mecánicas (OFERTADET) que no reconoce → `TininMecanica`;
    **"N artículo(s) de 100 g con precio de kilo"** → "Pasar los N a 100 g" o
    uno por uno "Pasar a 100 g" / "Está bien así" (divide el precio entre 10 en
    la grilla, no guarda nada);
    **"N descripción(es) guardada(s) con una marca que el listado no dice"** →
    "Corregir las N" o por fila "Quitar/Cambiar la marca" / "Está bien así"
    (guarda en el Diccionario);
    bebidas con alcohol → buscar con IA;
    grupos guardados parciales/completos → aplicar;
    "Unificar categorías".
    Aviso de formato largo ("4.773 filas se volvieron 274 cenefas"). Barra de
    celda (muestra la celda bajo el mouse). Grilla virtualizada: solo la
    descripción se edita (Enter guarda ya, si no a los 800 ms). Abajo:
    "Convertir a cenefa", "Descargar Excel", "Descargar dividido".
  - Modales: IA de descripciones (aprobar, editar, aprobar todas, insignias
    "Fiambre por kg → 100 g", "Sin marca"), unificar productos, unificar
    categorías, descargar dividido (por sucursal y/o por categoría, ZIP).
  - Burbuja de Tinín con las filas de la grilla como contexto.
- **Qué se puede hacer:** `POST /tools/cenefas/convertidor/columnas`,
  `POST /convertidor/preview`, `GET|POST /convertidor/mapeos`,
  `DELETE /convertidor/mapeos/{id}`, `GET|POST /convertidor/bancos`,
  `DELETE /convertidor/bancos/{id}`, `POST /convertidor/columnas/sugerir-ia`,
  `POST /convertidor/columnas/confirmar-alias`,
  `POST /convertidor/mecanica/sugerir-ia`, `POST /convertidor/mecanica/confirmar-alias`,
  `PATCH /convertidor/descripciones/{sku}`, `POST /convertidor/descripciones/generar-ia`,
  `POST /convertidor/alcohol/detectar-ia`, `POST /convertidor/categorias/unificar-ia`,
  `POST /convertidor/grupos-unificados`, `POST /convertidor/grupos-unificados/buscar`,
  `POST /convertidor/export`, `POST /convertidor/export-dividido`,
  `POST /convertidor/tinin/consultar`. "Convertir a cenefa" exporta, guarda el
  Excel en `sessionStorage` y navega a `/materiales/cenefas`.
- **Estados:** "Procesando…" en los botones; errores del servidor en toast;
  IA no configurada: "La generación con IA no está configurada en este
  ambiente" (503); otros errores de IA: "Probá de nuevo en unos minutos".
- **Celular:** sin ninguna clase responsive en la grilla; la barra de celda
  depende del mouse (en el teléfono no muestra nada) y los motivos de cada aviso
  van en `title` (tooltip).
- **Datos para probarla:** un Excel de gestión armado con los encabezados de
  arriba. Para ver el aviso de 100 g: texto con "100 g" y PRECIO ≥ 400. Para
  ver duplicados/grupos: SKU repetidos o parecidos. **El aviso de marcas
  guardadas no se puede provocar en pruebas desde la pantalla**: solo sale con
  descripciones guardadas por una persona antes del 16/11/2026 15:00 UTC
  (`REGLA_DE_MARCA_DESDE` en `convertidor_ai.py`), y todo lo que se guarde hoy
  tiene fecha de hoy. La IA va a fallar (clave falsa).
- **Código:** `frontend/app/(dashboard)/materiales/convertidor/page.tsx`,
  `components/cenefas/convertidor/*` (ConvertidorGrid 1.374 líneas,
  MapeoStep 727, AiModal 508, UnifyModal 524, DividirModal 399, MergeModal 162,
  TininMapeo, TininMecanica, TininRevision), `lib/cenefaHandoff.ts`,
  `backend/app/api/routes/cenefas_convertidor.py`,
  `services/cenefas/{convertidor,convertidor_ai,convertidor_variables}.py`.
- **Puntos a mirar:**
  - "Subir otro archivo" descarta sin preguntar todas las correcciones hechas
    en la grilla.
  - Jerga en pantalla: los modales muestran nombres de variables como
    "precioRegular (anterior)" y "precioOferta"; "Plantilla de mapeo · todos
    los mundos" usa "mundos" con el sentido viejo (tipos de cenefa).
  - Sospecha: el aviso de 100 g se resuelve solo en la grilla; si se vuelve a
    convertir la hoja (revalidar) vuelve a aparecer.

### Diccionario — `/materiales/diccionario`

- **Para qué sirve:** el catálogo compartido de descripciones por SKU
  (Singulares) y de grupos de varios SKU con un mismo cartel (Plurales).
- **Quién la ve:** `cenefas.diccionario` (menú "MATERIALES → Diccionario").
  Solo mundo Tienda Inglesa.
- **Qué hay en la pantalla:** título, "Descargar Excel"; pestañas Singulares /
  Plurales con su explicación; buscador (SKU o descripción / grupo,
  descripción o SKU); tabla SKU–Descripción con lápiz para editar; en
  Plurales, Grupo–Descripción–SKUs con editar y eliminar; total y paginación de
  100 en 100.
- **Qué se puede hacer:** `GET /convertidor/descripciones?q=&limit=&offset=`,
  `PATCH /convertidor/descripciones/{sku}`,
  `GET /convertidor/grupos-unificados`, `PATCH|DELETE /convertidor/grupos-unificados/{id}`
  (borrar con `confirm()`), `GET /convertidor/descripciones/export` o
  `/grupos-unificados/export`. Búsqueda con espera de 350 ms.
- **Estados:** spinner; vacío: "Todavía no hay nada cargado — se completa al
  usar el Convertidor de Excel" / "Todavía no hay grupos — se crean al unificar
  en el Convertidor"; sin resultados; error: toast.
- **Celular:** sin clases responsive; `p-8` fijo; tabla de 3 columnas.
- **Datos para probarla:** convertir un Excel y corregir descripciones, o
  unificar productos en el Convertidor. No hay forma de agregar una entrada
  nueva desde acá (solo editar).
- **Código:** `frontend/app/(dashboard)/materiales/diccionario/page.tsx`,
  `routes/cenefas_convertidor.py`.
- **Puntos a mirar:** pide la lista dos veces al abrir (carga inicial + la
  búsqueda vacía); búsquedas que se pisan sin cancelar la anterior (sospecha);
  en Redexpres no se ve, aunque el Convertidor de Redexpres escribe acá.

### Tinín — dónde vive (no es una pantalla)

El asistente de cenefas y descripciones. Exige `ai.tinin` en el servidor.

- **Burbuja flotante** abajo a la derecha en `/materiales/cenefas` (contexto =
  tipo de cenefa) y `/materiales/convertidor` (con las filas de la grilla). Chat
  que explica y puede **guardar una descripción en el Diccionario** por pedido
  ("guardá SKU 12345: …"). `POST /tools/cenefas/convertidor/tinin/consultar`.
  Código: `components/cenefas/TininFloating.tsx`, `services/cenefas/tinin_agent.py`.
- **En el Convertidor:** sugerir qué es cada columna (`TininMapeo`), clasificar
  mecánicas (`TininMecanica`), generar descripciones y pasar fiambres de kilo a
  100 g con precio ÷ 10 (`ConvertidorAiModal`), buscar alcohol, unificar
  categorías, y el bloque de avisos (`TininRevision`), que también incluye el
  aviso de 100 g con precio de kilo y el de marcas guardadas.
- **En la revisión del lote:** "N cosas para revisar antes de confirmar".
- **Lo que sabe:** reglas de estilo en `_STYLE_RULES`
  (`services/cenefas/convertidor_ai.py`, no tocar sin pedido de Ivan; "la marca
  nunca se deduce") + lo aprobado en "Lo que aprendió".
- **Puntos a mirar:** la burbuja se muestra a todos, tengan o no `ai.tinin`;
  sin el permiso la respuesta es 403 y dice "No pude procesar tu consulta —
  probá de nuevo en unos minutos" (engañoso). Sospecha: en el teléfono la
  burbuja (`fixed bottom-5 right-5`) puede quedar encima de la barra de abajo.

### Buscar precios — `/precios`

- **Para qué sirve:** buscar un producto en vivo en 15 cadenas (supermercados,
  farmacias, electrodomésticos), comparar precios y seguir productos.
- **Quién la ve:** `precios.search` (menú "COMERCIAL → Buscar precios"). Solo
  Tienda Inglesa. Doña Tina (chat y reporte) exige `ai.dona_tina`.
- **Qué hay en la pantalla:**
  - Antes de buscar: lupa, "Buscar precios en vivo", buscador ("Ej: arroz 5kg…
    (Enter para buscar)"), botón "Fuentes (N/M)" con panel por categorías
    (Supermercados, Farmacia, Electrónica, Otros), "Restablecer" y nota de que
    LOi queda afuera por defecto; chips de cadenas; "15 cadenas · 134+ sucursales".
  - Buscando: "Doña Tina está trabajando para usted…" con mascota.
  - Al terminar: modal "Búsqueda lista — Encontramos N producto(s) relevantes,
    agrupados por marca" → "Continuar".
  - Resultados: chips "Todas (N)" y por cadena; "N cadenas sin datos"
    desplegable (sin resultados / sin respuesta tachada); selector de sucursal;
    orden (relevancia, precio ↑, precio ↓); "Filtrar por producto" (modal con
    buscador y casillas); "Descargar Excel"; "Ver gráfico"; "Más barato: X en
    Y"; lista con "mejor precio", "×N sucursales" (modal de sucursales),
    "en realidad es de…", "Ver" (abre la tienda) y estrellita para seguir.
  - Modal "Comparar precios": nuestro precio y moneda, moneda del gráfico,
    cotización compra/venta, gráfico de barras con línea punteada de nuestro
    precio, casillas, estrellita, Doña Tina con reporte.
  - Burbuja de Doña Tina (chat; puede filtrar la lista y abrir el gráfico).
- **Qué se puede hacer:** `GET /precios/buscar-vivo-stream?q=&cadenas=` (fetch
  con lectura por partes), `GET /precios/cotizacion-dolar`,
  `POST /precios/ia/consultar`, `POST /precios/ia/reporte`, listas:
  `GET|POST /watchlist`, `POST /watchlist/{id}/items`. El Excel se arma en el
  navegador. Un término de solo números se toma como código de barras.
- **Estados:** menos de 2 letras no busca; error: toast "Error al buscar";
  "Sin resultados para '…'" + consejo; "Ningún resultado de X para este término"
  con filtros; sin cotización: aviso en el gráfico.
- **Celular:** sin clases responsive en la página.
- **Datos para probarla:** no necesita nada de la base; necesita internet.
  Doña Tina falla en pruebas → el servidor manda todo sin filtrar y el modal
  dice que no pudo agrupar. Sin cotización (apagada).
- **Código:** `frontend/app/(dashboard)/precios/page.tsx` (1.131 líneas),
  `components/precios/*`, `components/DonaTinaFloating.tsx`,
  `backend/app/api/routes/precios.py`, `services/scraper/live_search.py`,
  `services/dona_tina_precios.py`.
- **Puntos a mirar:**
  - Sospecha: si la conexión se corta sin el mensaje final ("done"), la
    pantalla queda en "Doña Tina está trabajando" para siempre (solo se libera
    con done o con error).
  - Código de barras no encontrado: el servidor manda "Código N no encontrado.
    Probá buscar por nombre", pero la pantalla no lo muestra (solo "Sin resultados").
  - La burbuja de Doña Tina aparece aunque no se tenga `ai.dona_tina`.

### Listas de monitoreo — `/precios/listas`

- **Para qué sirve:** los productos de la competencia que se siguen; se
  chequean solos una vez por día y avisan si cambia el precio.
- **Quién la ve:** `precios.search` (menú "COMERCIAL → Listas de monitoreo").
  Solo Tienda Inglesa.
- **Qué hay en la pantalla:** subtítulo; pestañas Mis listas / Compartidas
  conmigo / Finalizadas con contador; por lista: nombre, N productos,
  "Compartida por…", "Finalizada", duración ("Sin límite" / "Hasta…",
  editable), botones compartir, finalizar ahora, exportar historial, eliminar o
  "Dejar de ver esta lista"; por producto: tienda, nombre, "Último chequeo",
  precio actual, "Ver en tienda", "Dejar de seguir". Modal "Compartir lista"
  (buscar por nombre o email, quitar acceso).
- **Qué se puede hacer:** `GET /watchlist`, `PATCH /watchlist/{id}` (duración,
  finalizar), `DELETE /watchlist/{id}`, `DELETE /watchlist/items/{id}`,
  `GET /watchlist/{id}/historial` (Excel en el navegador),
  `GET /watchlist/usuarios-compartibles`, `GET /watchlist/{id}/compartidos`,
  `POST /watchlist/{id}/compartir`, `DELETE /watchlist/{id}/compartir/{userId}`.
- **Estados:** spinner; vacíos con texto propio por pestaña ("Todavía no seguís
  ningún producto. Andá a Buscar precios…"); errores en toast.
- **Celular:** sin clases responsive.
- **Datos para probarla:** buscar en `/precios` y tocar la estrellita (crea la
  lista). Para "Compartidas" hace falta un segundo usuario con `precios.search`.
  En pruebas el chequeo diario está apagado: siempre "todavía sin chequear".
- **Código:** `frontend/app/(dashboard)/precios/listas/page.tsx`,
  `components/precios/{SeguirButton,CompartirListaModal,WatchlistsContext}.tsx`,
  `routes/watchlist.py`, `services/watchlist_service.py`.
- **Puntos a mirar:** "Eliminar lista" borra sin pedir confirmación.

### Mi pedido — `/redexpres/mi-pedido`

- **Para qué sirve:** que cada local cargue cuánto material necesita este mes
  y lo confirme.
- **Quién la ve:** quien tiene un local asignado (cuenta de local) o
  `redexpres.manage`/superadmin (con selector de sucursal). En el menú
  ("Redexpres → Mi pedido") y en la barra de abajo del teléfono, solo en el
  mundo Redexpres. El menú lo muestra a locales y superadmins, no a un gestor
  `redexpres.manage` sin local.
- **Qué hay en la pantalla:** "Mi pedido" + subtítulo; chip con el nombre del
  local (o selector "Sucursal" para gestores) y "Confirmado" si corresponde;
  selector de año + 12 meses (los que no existen, apagados con "Este mes todavía
  no está habilitado"; para gestores, punteados para crearlos); para gestores
  "Editar planilla de este mes"; una tarjeta por grupo (Ofertas, VDS y Supremo,
  Bombas, Stickers, Otros items) con un campo por columna (con tope); "Notas
  libres"; pie con "Los cambios se guardan automáticamente al dejar de
  escribir" y "Confirmar pedido".
- **Qué se puede hacer:** `GET /redexpres/meses`,
  `GET /redexpres/estructura/{año}/{mes}`, `GET /redexpres/mi-planilla/{año}/{mes}`
  (gestores con `?local=`), `PATCH /redexpres/planilla/{año}/{mes}/{local}`
  (800 ms después de dejar de escribir), `POST …/{local}/confirmar`; gestores:
  `GET /redexpres/locales`, `POST /redexpres/meses`, `PUT /redexpres/estructura/{año}/{mes}`.
  Pasarse del tope lo baja al máximo con aviso "Máximo N por sucursal".
- **Estados:** cargando: spinner; sin local: "Todavía no tenés una sucursal
  asignada. Hablá con Valentina…"; gestor sin elegir: "Elegí una sucursal arriba…";
  mes sin datos: "No hay datos para este mes."; guardando: spinner en el pie y
  el botón dice "Guardando..."; errores en toast ("Error al guardar <local>").
  Confirmado: campos deshabilitados.
- **Celular:** grilla de 2 columnas que pasa a 4 en `sm`; botones del selector
  de meses envuelven.
- **Datos para probarla:** como superadmin, crear el mes (en la Planilla o con
  el selector) en el mundo Redexpres; después entrar como `local-de-prueba`.
- **Código:** `frontend/app/(dashboard)/redexpres/mi-pedido/page.tsx`,
  `components/redexpres/{SelectorMes,EditorPlanilla}.tsx`,
  `lib/redexpres/{estructura,ediciones}.ts`, `backend/app/api/routes/redexpres.py`,
  `services/redexpres_estructura.py`.
- **Puntos a mirar:**
  - **No existe "mes cerrado"** en el código: un mes existe o no. Cualquier mes
    existente, también los pasados, se puede editar mientras no esté confirmado.
  - Sospecha fuerte: escribir y cambiar de mes antes de 800 ms **pierde lo
    escrito** (al cargar el otro mes se vacían los cambios pendientes y el
    guardado diferido ya no encuentra nada). Lo mismo pasa en la Planilla.
  - Sospecha: si un guardado falla, el cambio queda pendiente y "Confirmar
    pedido" se queda en "Guardando..." sin reintento ni explicación.
  - Sin ningún mes creado (base vacía) el local ve solo los 12 meses apagados
    y nada más, sin mensaje (la clave `redexpres.noMeses` existe y no se usa).
  - Confirmar no pide confirmación y el local no puede deshacerlo; no se le
    dice a quién pedirle que lo desconfirme.
  - El servidor no impide editar una fila confirmada (`update_row` no mira
    `confirmado`): solo lo frena la pantalla.
  - Con dos locales asignados muestra solo la primera fila que devuelve el
    servidor, que puede no ser el local del chip.
  - Texto con un nombre propio fijo ("Hablá con Valentina").

### Planilla de pedidos — `/redexpres/planilla`

- **Para qué sirve:** la planilla general con los ~60 locales: ver qué pidió
  cada uno, completar, confirmar o desconfirmar, abrir meses, armar las
  columnas del mes y bajar todo a Excel.
- **Quién la ve:** `redexpres.view` (menú "Redexpres → Planilla de pedidos").
  Solo mundo Redexpres. Gestor completo (`redexpres.manage` o superadmin):
  edita cualquier fila, crea meses, edita la estructura, desconfirma. Con solo
  `redexpres.view`: ve todas las filas y edita solo las de sus locales asignados.
- **Qué hay en la pantalla:** título "Planilla de pedidos · Redexpres ·
  cartelería mensual"; "N/M confirmados"; "Descargar Excel"; "Solo mi local" /
  "Ver todos" (no gestores con local); "Nuevo mes" (formulario mes + año);
  selector de año y meses; "Editar planilla de este mes" (modal: grupos con
  nombre, color, subir/bajar, sacar; columnas con nombre, tope, texto o
  número, subir/bajar, sacar; "Agregar columna", "Agregar grupo"); tabla con
  la columna del local fija a la izquierda y encabezados fijos, una columna por
  ítem, "Notas libres", estado (Confirmado + desconfirmar / Confirmar pedido /
  Pendiente); pie con confirmados y "Los cambios se guardan automáticamente…".
- **Qué se puede hacer:** `GET /redexpres/meses`, `GET /redexpres/planilla/{año}/{mes}`,
  `PATCH /redexpres/planilla/{año}/{mes}/{local}`, `POST …/confirmar`,
  `POST …/desconfirmar`, `POST /redexpres/meses`, `GET|PUT /redexpres/estructura/{año}/{mes}`.
  Excel en el navegador (`xlsx`). Un mes nuevo copia las columnas del mes
  anterior más cercano.
- **Estados:** spinner; "No hay datos para este mes."; errores en toast; sin
  meses: nada debajo del selector.
- **Celular:** tabla con scroll horizontal y columna de local fija; cabecera
  que se apila en angosto.
- **Datos para probarla:** como superadmin en Redexpres, "Nuevo mes".
- **Código:** `frontend/app/(dashboard)/redexpres/planilla/page.tsx`,
  `components/redexpres/EditorPlanilla.tsx`, `routes/redexpres.py`.
- **Puntos a mirar:**
  - Sospecha fuerte: en el Excel descargado, la columna Estado de un pedido
    confirmado dice **"Confirmar pedido"** (usa el texto del botón) en vez de
    "Confirmado".
  - El modal de edición de la planilla se cierra al tocar afuera y pierde lo
    que no se guardó.
  - Cambiar de mes con cambios sin guardar los pierde (igual que Mi pedido).
  - La columna "Otros / notas" del Excel toma lo guardado, no lo que se está
    escribiendo.
  - Dos maneras de crear un mes ("Nuevo mes" y tocar un mes punteado).

### Colocación — `/colocacion`

- **Para qué sirve:** vista general de las fotos de colocación que mandan los
  locales: qué acciones tienen pedidos abiertos, cuánto se cumplió y qué
  locales están atrasados.
- **Quién la ve:** `calendario.edit` y que el mundo tenga locales con usuario
  (menú, arriba, "Colocación", si además ve el calendario). La ruta no está
  limitada por mundo.
- **Qué hay en la pantalla:** "Colocación" + "Las fotos que mandan los locales
  de cómo quedó la cartelería de cada acción de <mundo>", botón actualizar; una
  tarjeta por acción abierta (color de la acción, nombre, "Va del… al…", % de
  cumplimiento, barra aprobadas/por revisar/atrasadas, "X de N aprobadas", "N
  por revisar", "N devueltas", "Límite: …", "N atrasados: …", "Abrir el
  tablero"); "Completas en los últimos 30 días · N" desplegable; pie "Las fotos
  ocupan X MB de Y MB. Se borran solas N días después de que termina cada acción."
- **Qué se puede hacer:** `GET /colocacion/resumen?mundo=<mundo>`. Cada tarjeta
  lleva a `/calendario?accion=<id>&pestana=fotos`.
- **Estados:** sin permiso: "Esta pantalla es de quien edita el calendario…";
  cargando: 3 esqueletos; error: "No se pudo traer el resumen" + "Probar de
  nuevo"; mundo sin tipo de local: "<mundo> no tiene locales con usuario…";
  vacío: "No hay pedidos de foto abiertos. Se piden desde la ficha de cada
  acción del calendario, en la pestaña Fotos" + "Ir al calendario".
- **Celular:** columna de 768 px, pensada para leerse bien.
- **Datos para probarla:** en Redexpres, crear una acción del calendario
  comercial y pedir fotos al local de prueba (ver recorrido F).
- **Código:** `frontend/app/(dashboard)/colocacion/page.tsx`,
  `lib/colocacion/{estados,store}.ts`, `backend/app/api/routes/colocacion.py`,
  `services/colocacion.py`.
- **Puntos a mirar:** en Tienda Inglesa sin locales `tienda` con usuario (el
  caso de pruebas y hoy de producción) la URL dice "No hay pedidos abiertos, se
  piden en la pestaña Fotos", pero esa pestaña no aparece en las acciones de ese
  mundo: callejón sin salida.

### Pestaña Fotos de la acción (lado del equipo) — `/calendario?accion=<id>&pestana=fotos`

(Vive en el calendario, otra zona; se incluye porque es el otro lado de la colocación.)

- **Para qué sirve:** pedirles la foto a los locales y después revisar: aprobar o devolver.
- **Quién la ve:** `calendario.edit`, en acciones de un mundo con locales con
  usuario (o que ya tengan un pedido).
- **Qué hay:** "Pedir foto de colocación a los locales": lista de locales con
  buscador, fecha límite (por defecto el día siguiente al inicio), "Qué
  fotografiar", "Pedir foto a N locales". Después, el tablero: filtros por
  estado, cada local con sus fotos (visor grande), aprobar, devolver con
  comentario, cambiar locales/límite/indicación, cancelar el pedido. Se
  actualiza cada 30 s.
- **Endpoints:** `GET /colocacion/acciones/{barraId}`, `POST /colocacion/acciones/{barraId}`,
  `PATCH /colocacion/pedidos/{id}`, `DELETE /colocacion/pedidos/{id}`,
  `POST /colocacion/locales/{id}/aprobar`, `POST /colocacion/locales/{id}/devolver`,
  `GET /colocacion/fotos/{id}?tamano=mini|grande`.
- **Código:** `components/colocacion/{BloqueFotos,VisorFoto,FotoProtegida}.tsx`,
  `components/calendario/PanelAccion.tsx`.

### Fotos para subir — `/fotos`

- **Para qué sirve:** la pantalla del local: qué foto le pidieron, hasta
  cuándo, sacarla con el teléfono y subirla; si se la devuelven, ver por qué.
- **Quién la ve:** quien tiene un local asignado (menú arriba "Fotos para
  subir" con número; barra de abajo "Fotos"). Sin requisito de permiso ni de mundo.
- **Qué hay en la pantalla:** encabezado con el/los locales; secciones "Para
  subir · N" y "Ya enviadas"; tarjeta por pedido: acción, fechas, estado,
  límite, "Qué fotografiar", comentario de la devolución entre comillas, fotos
  subidas con cruz para sacarlas ("¿Sacar esta foto? Marketing deja de verla."),
  botón grande "Sacar foto" / "Sacar otra foto" (abre la cámara trasera), opción
  de galería, "Podés subir hasta 3 fotos. Te quedan N."; progreso
  "achicando / subiendo".
- **Qué se puede hacer:** `GET /colocacion/mis-fotos` (también al volver a la
  pestaña), `POST /colocacion/locales/{id}/fotos` (foto + miniatura achicadas en
  el navegador, hasta 3 MB, 60 s de espera), `DELETE /colocacion/fotos/{id}`,
  `GET /colocacion/fotos/{id}`.
- **Estados:** quien no es local: "Esta pantalla es la de los locales…" (+ link
  a Colocación si edita el calendario); cargando: esqueletos; error: "No
  pudimos traer tus fotos. Revisá la señal." + "Probar de nuevo"; vacío: "No
  tenés fotos para subir. Cuando marketing te pida una, te llega un aviso…";
  errores de subida: "No se pudo subir la foto. Revisá la señal…", "No pudimos
  abrir esa foto…", "Ya subiste 3 fotos…", foto ya aprobada.
- **Celular:** es la pantalla pensada para el teléfono (letra grande, botones
  de 48 px, cámara directa).
- **Datos para probarla:** un pedido de foto hecho por el equipo al local de
  prueba (recorrido F); cualquier JPG/PNG sirve como foto.
- **Código:** `frontend/app/(dashboard)/fotos/page.tsx`,
  `lib/colocacion/{imagen,store,estados}.ts`, `routes/colocacion.py`.
- **Puntos a mirar:** el "3" de "Podés subir hasta 3 fotos" está escrito a mano
  aunque el servidor manda `maxFotos`.

### Validación de RRSS — `/redes-sociales/validacion`

- **Para qué sirve:** CatTi compara cada placa de redes sociales contra el
  mailing (PDF/imagen) o la planilla (Excel) de la campaña y marca diferencias
  de precio, descripción, legales, fecha.
- **Quién la ve:** `rrss.view` (menú "REDES SOCIALES → Validación de RRSS").
  Solo Tienda Inglesa. Validar: `rrss.validate`; sin él solo se ve "Las de
  hoy". Borrar: con `rrss.validate`, solo las propias (superadmin, todas); el
  tacho aparece solo donde el servidor deja (`puede_borrar` de la lista).
- **No hay historial (26/11/2026):** cada validación dura 24 horas, terminada o
  no, y después se borra entera (páginas del mailing, placas y recortes) y se
  compactan las tablas (`services/rrss/retencion.py`, `RRSS_RETENCION_HORAS`).
  Ivan: «no tiene sentido que mantengamos historial de validaciones». La
  compactación no traba a nadie: si una tabla está en uso, o lo recién borrado
  quedó retenido por una transacción más vieja, se compacta en la pasada
  siguiente (una por hora), así que el lugar puede tardar una hora en volver.
  Si una validación vence mientras CatTi mira una placa, esa placa dice que ya
  no está.
- **Qué hay en la pantalla:** título y subtítulo; pestañas "Nueva validación"
  / "Las de hoy" (o "Volver a las de hoy" / "Nueva validación" al revisar).
  Carga (`UploadStep`): "Mailing o planilla" (uno solo; arrastrar o elegir),
  explicación de cómo se lee la planilla y su tope de filas; "Fecha de la
  campaña"; "Placas" (arrastrar carpeta, "Elegir imágenes", "Elegir carpeta",
  "Quitar todas", JPG/PNG/WebP); "Legales que se exigen" (Bases y condiciones,
  Leyenda de alcohol; vacío = el de siempre); "Validar placas (N)". Mientras lee:
  "CatTi está leyendo el mailing/la planilla…". Revisión (`ReviewStep`): placa
  por placa con estado, campos Coincide / Distinto / Falta en la placa / Sobra,
  recorte del mailing o tira de la planilla, "Siguiente con problemas",
  reintentar las que dieron error, "Descargar Excel de correcciones". Las de
  hoy: un renglón que dice que se borran solas a las 24 horas y la tabla con
  abrir y borrar, para retomar una si se cerró la pestaña (en el celular la
  tabla se desliza de costado para llegar a "Abrir").
- **Qué se puede hacer:** `GET /rrss/config`, `POST /rrss/validaciones`
  (fuente + legales, hasta 5 min), `POST /rrss/validaciones/{id}/imagenes` (3
  placas a la vez, con reintentos), `POST /rrss/validaciones/{id}/cerrar`,
  `GET /rrss/validaciones`, `GET /rrss/validaciones/{id}`,
  `GET /rrss/validaciones/{id}/excel`, `DELETE /rrss/validaciones/{id}`.
- **Estados:** sin configuración: "No pude cargar la configuración de la
  pantalla. Recargá la página." (la carga no se dibuja); servidor caído: "El
  servidor no responde…"; error de fuente: "No pude leer el archivo…"; error por
  placa: "No pude validar esta placa"; ninguna de hoy: "Hoy no hay
  validaciones."; abrir o bajar el Excel de una que ya se borró: "Esa
  validación ya no está: las validaciones se borran solas a las 24 horas…"
  (y la lista se vuelve a pedir, ya sin ella); borrar una que el servidor
  rechaza: "Solo quien creó la validación puede borrarla." (la lista queda).
- **Celular:** pocas clases responsive (algunas en carga y revisión).
- **Datos para probarla:** `backend/tests/data/planilla_rrss.xlsx` como fuente
  (leer la planilla no usa IA) + cualquier imagen como placa. En pruebas, la
  validación de cada placa va a dar error (CatTi usa la API real): sirve para
  ver errores, reintentos y la lista de las de hoy.
- **Código:** `frontend/app/(dashboard)/redes-sociales/validacion/page.tsx`,
  `components/rrss/*` (ReviewStep 828 líneas, UploadStep 444, Historial = la
  lista de las de hoy), `backend/app/api/routes/rrss.py`, `services/rrss/*`,
  `app/data/rrss_archivos.json`.
- **Puntos a mirar:**
  - Arreglado el 26/11/2026 (Ramiro, visto en el navegador): el tacho aparecía
    en las validaciones de todas las personas y, al tocarlo en una ajena, el
    403 reemplazaba la lista entera por "No se pudieron cargar las validaciones
    de hoy" (H-016). Y en el celular (390 px) la tarjeta cortaba la tabla:
    "Abrir" quedaba fuera de la pantalla, sin forma de llegar.
  - Una validación que se abandona a mitad de camino queda sin cerrar hasta
    que se borra sola, a las 24 horas.

---

## Recorridos de punta a punta

### A. El local carga su pedido del mes → quien arma la planilla lo ve

Quién: la cuenta del local (y después un gestor de Redexpres).
Antes: un superadmin o `redexpres.manage` creó el mes (recorrido B).

1. El local entra con su usuario: cae en Don Tino (`/home`).
2. Toca "Mi pedido" (menú o barra de abajo). Ve el chip con su local y el mes
   más reciente elegido.
3. Escribe cantidades en cada grupo. Si se pasa del tope, se baja al máximo con
   un aviso. A los 800 ms se guarda solo (spinner en el pie).
4. Escribe "Notas libres" si quiere.
5. Toca "Confirmar pedido" → "Pedido confirmado"; los campos quedan bloqueados.
6. Repercute: en `/redexpres/planilla` la fila del local aparece con lo cargado
   y "Confirmado"; sube el contador "N/M confirmados"; el Excel lo incluye.
7. Si hay que corregir: el gestor toca desconfirmar en la Planilla; el local
   vuelve a poder editar.

Para probar el riesgo: escribir un número y cambiar de mes enseguida; cortar la
red y escribir (el botón queda en "Guardando...").

### B. El gestor abre un mes y arma sus columnas

Quién: superadmin o `redexpres.manage`, en el mundo Redexpres.

1. Menú → "Planilla de pedidos".
2. "Nuevo mes" (o toca un mes punteado del año) → "Mes X creado": nacen las ~60
   filas vacías y las columnas copiadas del mes anterior más cercano (o las de
   siempre).
3. "Editar planilla de este mes": renombra grupos, agrega una columna (nombre,
   tope), mueve, saca; "Guardar".
4. Repercute: el local ve esas columnas en "Mi pedido" de ese mes; sacar una
   columna no borra lo ya cargado, solo deja de verse.
5. A fin de mes: "Descargar Excel" de la planilla.

### C. Del listado de gestión a las cenefas impresas

Quién: el equipo de promo (`cenefas.view`, `cenefas.generate`; IA con `ai.tinin`).

1. Menú → "Convertidor de Excel". Sube el Excel de gestión → "Continuar".
2. Si tiene varias hojas, elige cuál. En "Mapeo de columnas" revisa lo que
   Tinín propone para columnas desconocidas, elige o guarda una plantilla de
   mapeo, completa variables extra (o texto fijo) → "Convertir".
3. En la grilla: mira "X de N matcheados" y los avisos de Tinín. Genera
   descripciones con IA y las aprueba; pasa a 100 g los que vinieron con precio
   de kilo; corrige marcas guardadas; unifica duplicados; corrige a mano
   descripciones (cada una se guarda en el Diccionario).
4. "Convertir a cenefa" → salta a Cenefas con el Excel ya cargado
   ("Excel traído del Convertidor").
5. Elige el tipo (Rompe Precios, Parrilla y Vinos…; en Redexpres entra directo).
6. "Elegir plantillas" para el Excel (hasta 5), vigencia, legales, cocarda →
   "Generar y descargar PPTX".
7. Revisión del lote: recorre cada cenefa, mueve lo que no entra, mira los
   avisos de desborde → "Generar las N" (si movió cosas, elige "Solo esta vez" o
   "Guardar en la plantilla").
8. "Descargar ZIP", abre los PPTX y responde "Sí, salieron bien" / "No".
9. Repercute: el Diccionario tiene las descripciones nuevas (la próxima vez
   matchean solas); "Lo que aprendió" recibe propuestas; el Informe suma las
   corridas (las del tipo Pruebas y Redexpres van "sin costo"); las corridas
   verificadas guardan el archivo, las otras se borran a los 7 días.

Variante: subir el Excel de gestión directo a Cenefas sin convertir → el
servidor lo frena con un mensaje de qué hacer.

### D. Cargar una plantilla nueva y retocarla

Quién: `cenefas.import` + `cenefas.edit`.

1. Cenefas → elegir tipo → "Elegir plantillas" → "Cargar nueva plantilla".
2. Tipo (A4, 3xA4…), nombre de la acción, mes, año, archivo .pptx → ve "Se va
   a guardar como: Accion-AAAAMM-Tipo" → "Guardar plantilla".
3. La plantilla aparece en la lista del tipo; "Editar" abre el editor en otra
   pestaña con esa plantilla; ahí se mueven cuadros, se agregan reglas →
   "Guardar".
4. "Reemplazar" sube otro .pptx manteniendo nombre y tipo.
5. Repercute: todos los que generan en ese tipo la ven; en el informe sale por
   nombre de plantilla.

### E. Crear un tipo de cenefa nuevo

Quién: `cenefas.edit`, en Tienda Inglesa o Redexpres.

1. Cenefas → "Cambiar tipo de cenefa" (si ya estaba adentro) → "Nuevo tipo de
   cenefa": nombre, descripción, ícono, color, cobrable → "Crear tipo de cenefa".
2. Nace en el mundo en el que se está. Aparece en el selector de ese mundo.
3. Borrarlo: tacho → confirmar; si tiene plantillas el servidor lo frena.
4. Repercute: en Redexpres, con dos tipos, deja de entrarse directo; en el
   informe aparece como mundo cobrable o sin costo.

### F. Pedido de foto de colocación (equipo ↔ local)

Quién: el equipo (`calendario.edit`) y la cuenta del local.

1. Equipo, en el mundo Redexpres: crea una acción en el calendario comercial.
2. Abre la ficha → pestaña "Fotos" → elige locales (en pruebas, el del local de
   prueba), fecha límite, "Qué fotografiar" → "Pedir foto a N locales".
   Toast "Les llegó el aviso".
3. Local: aviso en la campanita; "Fotos para subir" muestra el número rojo.
4. Local: entra, ve la tarjeta, "Sacar foto" (cámara) → se achica y sube →
   "¡Listo! Tu foto se envió a marketing." Puede subir hasta 3 o sacar una.
5. Equipo: en `/colocacion` la acción muestra "1 por revisar"; "Abrir el
   tablero" → pestaña Fotos → ve la foto → "Aprobar" o "Devolver" con comentario.
6. Si la devuelve: el local recibe aviso, ve el comentario y sube otra.
7. Cuando todos aprobados: la acción pasa a "Completas en los últimos 30 días"
   y le llega un aviso al equipo.
8. Si vence el límite sin foto: el local aparece como atrasado en la tarjeta.

### G. Seguir el precio de un producto de la competencia

Quién: `precios.search` (Doña Tina: `ai.dona_tina`).

1. Menú → "Buscar precios". Opcional: "Fuentes" para sumar o sacar cadenas.
2. Escribe "aceite 900 ml" + Enter. Ve "Doña Tina está trabajando…", después el
   modal por marcas → "Continuar".
3. Filtra por cadena, sucursal o producto; ordena; "Ver gráfico", carga
   "Nuestro precio" y compara; pide el reporte a Doña Tina.
4. Toca la estrellita en un producto → elige lista o crea una nueva →
   "Agregado a la lista de monitoreo".
5. "Listas de monitoreo": ve la lista, le pone fecha de fin, la comparte con
   otro usuario, exporta el historial, la finaliza.
6. Repercute: el otro usuario la ve en "Compartidas conmigo"; el chequeo
   diario actualiza precios y manda aviso a la campanita si cambian (apagado en pruebas).

### H. Validar las placas de una campaña

Quién: `rrss.validate`, en Tienda Inglesa.

1. Menú → "Validación de RRSS" → "Nueva validación".
2. Sube el mailing (PDF) o la planilla (Excel), fecha si hace falta, arrastra la
   carpeta de placas, revisa legales → "Validar placas (N)".
3. Ve las placas analizándose de a 3; las que fallan se pueden reintentar.
4. Recorre con "Siguiente con problemas"; descarga el "Excel de correcciones"
   para la agencia.
5. Repercute: queda 24 horas en "Las de hoy" para todo el equipo con
   `rrss.view` y después se borra sola, con sus imágenes; antes, solo quien la
   creó (o un superadmin) puede borrarla.

### I. Corregir el Diccionario y verlo en el Convertidor

Quién: `cenefas.diccionario` (Tienda Inglesa).

1. Menú → "Diccionario" → busca un SKU → lápiz → corrige → guardar.
2. En Plurales, corrige o elimina un grupo.
3. Repercute: el próximo Excel convertido con ese SKU trae la descripción
   nueva; los grupos se ofrecen en la grilla del Convertidor; Tinín puede
   leerlas al contestar.

### J. Llegar a una herramienta desde el mundo equivocado

Quién: alguien con varios mundos (por ejemplo, el superadmin).

1. Estando en Redexpres, abre un link a `/precios` (o un aviso de una lista).
2. Ve "Los precios no son de Redexpres" con "Pasar a Tienda Inglesa" y "Volver
   al inicio de Redexpres".
3. Toca "Pasar a Tienda Inglesa": se cambia el mundo y aparece la pantalla.
4. El local, en la misma situación, ve "Tu cuenta no entra al mundo donde está
   esta herramienta" y solo "Volver al inicio".

---

## Los puntos a mirar más importantes de la zona (resumen)

1. `/materiales/cenefas/v2/generar`: un trabajo en "preview" se muestra como
   "Error en la generación — Error desconocido" y la pantalla consulta sin fin.
2. `/materiales/cenefas`: links "Informe" y "Lo que aprendió" para todos, pero
   las páginas son solo superadmin: a los demás los devuelve sin explicación.
3. Redexpres (Mi pedido y Planilla): cambiar de mes antes de 800 ms pierde lo
   escrito; un guardado fallido deja "Guardando..." trabado; sin meses la
   pantalla del local queda vacía sin mensaje; el Excel dice "Confirmar pedido"
   en los confirmados; el servidor deja editar filas confirmadas; no existe
   "mes cerrado".
4. Validación de RRSS: borrar aparece en validaciones ajenas y, si falla, la
   lista entera se cambia por "No se pudo cargar el historial".
5. Cenefas: la portada `/materiales` está huérfana y con títulos casi invisibles
   en modo claro; las plantillas creadas en el editor quedan sin tipo y no
   aparecen en ningún selector.
6. Otros: el local entra al chat de Don Tino (sugerencias de Google Ads) en vez
   de a lo suyo; Tinín y Doña Tina flotantes sin chequear su permiso de IA (403 →
   "probá en unos minutos"); "Eliminar lista" de precios sin confirmar; precios
   puede quedar en "Doña Tina está trabajando" si se corta la conexión; el
   mensaje de código de barras no encontrado no se muestra; Cenefas, Convertidor,
   Diccionario y Precios sin adaptación al teléfono; jerga camelCase en modales
   del Convertidor; "Hablá con Valentina" fijo; Colocación en Tienda Inglesa
   manda a una pestaña que no aparece; el lote de cenefas se pierde al recargar.

# Mapa C: la entrada, la estructura, los permisos y el sistema visual

Leído del código de `main` el 24/11/2026 (solo lectura). Cubre lo transversal de
Core Tienda: cómo se entra, cómo se arma la pantalla, quién ve qué y con qué
criterio visual está hecha. El calendario, las tareas, el tablero, cenefas,
precios, colocación y Redexpres los mapean otras zonas: acá se nombran solo
cuando hace falta para entender el menú o los permisos.

Cómo leerlo:
- Lo que dice "sospecha" es una sospecha leyendo el código: hay que confirmarla
  usando la pantalla.
- Lo que dice "no confirmado" es algo que no pude verificar en el código.
- Los endpoints van sin el prefijo `/api/v1`.

## 0. Antes de recorrer

**Las tres cuentas del entorno de pruebas** (`backend/app/services/cuentas_de_prueba.py`):

| Cuenta | Usuario | Cómo queda | Dónde cae al entrar |
|---|---|---|---|
| Equipo nocturno | `equipo-nocturno@example.com` | Superadmin (`is_superuser`), los 32 permisos, los 5 mundos, calendario "Todo" | `/mundos` (tiene 5 mundos, siempre elige) y después `/calendario` |
| Agencia de prueba | `agencia-de-prueba@example.com` | Externa, empresa "Agencia de prueba", solo `calendario.view`, mundo Tienda Inglesa, calendario "No lo ve" | `/entregas` (su tablero) |
| Local de prueba | `local-de-prueba@example.com` | Login de sucursal: solo `ai.don_tino`, mundo Redexpres, un local asignado | `/home` (el chat de Don Tino, no "Mi pedido") |

- Las tres se resetean en cada arranque (contraseña, bloqueo, activa, sin cambio de contraseña pendiente).
- El README dice que el superadmin elige "Tienda Inglesa o Redexpres". En realidad un superadmin entra a los **5 mundos** (`mundos_de` en `backend/app/core/mundos.py`), así que el selector le muestra 5 tarjetas.
- **No hay cuenta "interna común".** Para ver la plataforma como alguien del equipo sin superadmin, hay que crearla desde `/admin` (Nuevo usuario → Del equipo → rol "Usuario"). La primera vez que entra le pide cambiar la contraseña.
- La IA está simulada (`scripts/servidor_ia_simulada.py`): Don Tino contesta con reglas, sirve para probar permisos y links, no la calidad de las respuestas.
- La base arranca vacía: medios, finanzas y auditoría van a estar vacíos salvo que se carguen datos (ver cada pantalla).
- **Cuidado al probar:** no bloquear ni desactivar la cuenta Equipo nocturno (ver los puntos de `/login` y `/admin`). Para eso, crear una cuenta descartable.

---

## 1. Pantallas

### Iniciar sesión — `/login`
- **Para qué sirve:** entrar con mail y contraseña. Los locales de Redexpres entran con el nombre del local en el campo del mail.
- **Quién la ve:** cualquiera, sin sesión. La raíz `/` siempre manda acá (`frontend/app/page.tsx`), **aunque ya haya una sesión abierta**: la pantalla no se fija si ya entraste.
- **Qué hay en la pantalla:**
  - Notebook (≥1024 px): panel izquierdo azul oscuro con un ícono de gráfico de barras y "Core Tienda", Don Tino (el robot) saludando "¡Hola! Soy Don Tino 👋", el lema "Marketing, precios y creatividad en un solo lugar" y cuatro tarjetas: Analytics multiplataforma (Meta, Google, TikTok, DV360, GA4), Análisis con IA, Precios en vivo, Cenefas con IA.
  - Derecha: "Bienvenido", "Ingresá con tu cuenta de trabajo", campos Email y Contraseña (con el ojito para ver la contraseña), botón "Ingresar", link "¿Olvidaste tu contraseña?" y al pie "Marketing Intelligence Platform · 2026".
- **Qué se puede hacer:**
  - Entrar: `POST /auth/login` (10 por minuto por conexión). Después `GET /auth/me` para decidir a dónde va (ver la sección 2).
  - Si tarda más de 4 segundos aparece debajo del botón: "El servidor se está despertando: la primera vez puede tardar hasta un minuto."
- **Estados:**
  - Mail o contraseña mal (401): aviso rojo de 10 s "Email o contraseña incorrectos. A los 5 intentos fallidos la cuenta se bloquea 15 minutos." con botón "¿Olvidaste tu contraseña?".
  - Bloqueo: a los 5 errores la cuenta queda bloqueada 15 minutos. Mientras tanto, aun con la contraseña correcta, sale el mismo mensaje (a propósito, para no confirmar que el mail existe).
  - Demasiados intentos desde la misma conexión (429): "Demasiados intentos seguidos desde esta conexión. Esperá un minuto y probá de nuevo."
  - Cualquier otra falla: "No hay conexión con el servidor. Probá de nuevo en un momento."
  - Cargando: el botón dice "Ingresando..." con el circulito.
- **Celular:** el panel izquierdo desaparece; arriba queda el robot chiquito y "Core Tienda".
- **Datos para probarla:** las tres cuentas. Para el bloqueo, una cuenta descartable creada en `/admin`: 5 contraseñas mal y después la buena (tiene que fallar 15 min).
- **Código:** `frontend/app/(auth)/login/page.tsx`, `backend/app/api/routes/auth.py` (`login`), textos en `frontend/lib/locales/es.json` → `login`.
- **Puntos a mirar:**
  - Sospecha: **el contador de intentos no vuelve a cero cuando vence el bloqueo**, solo cuando se entra bien. Pasados los 15 minutos, un solo error más vuelve a bloquear otros 15.
  - Sospecha: **el mail se compara tal cual**, sin pasarlo a minúsculas ni sacar espacios. "Juan@..." o un espacio que agrega el autocompletar del celular dan "incorrectos" (y ahí ni siquiera cuenta como intento). Lo mismo en "Olvidé mi contraseña".
  - La pantalla vende la plataforma vieja: analytics, precios y cenefas. No nombra el calendario, las tareas ni el tablero, que hoy son el centro. El pie dice "Marketing Intelligence Platform" (nombre viejo, en inglés).
  - El logo: en la notebook es un **ícono de gráfico de barras**; en el celular, el robot. No está la margarita (ver la sección 4).
  - Los campos usan la clase `.input` (letra de 14 px): sospecha de que el iPhone agranda la página al tocarlos.
  - El ojito de la contraseña no tiene nombre para el lector de pantalla.

### Olvidé mi contraseña — `/forgot-password`
- **Para qué sirve:** pedir por mail un link para elegir una contraseña nueva.
- **Quién la ve:** cualquiera, sin sesión. Se llega desde el link del login o desde el botón del aviso de error.
- **Qué hay:** el mismo ícono de barras con "Core Tienda", "Olvidaste tu contraseña", campo Email, botón "Enviar link de recuperación", "Volver al login".
- **Qué se puede hacer:** `POST /auth/forgot-password` (5 por minuto). El servidor manda como mucho 3 mails por hora a la misma persona, y el link dura 1 hora. Contesta lo mismo exista o no el mail.
- **Estados:**
  - Enviado: tilde verde, "Email enviado", "Si el email está registrado, vas a recibir el link en los próximos minutos. Revisá también la carpeta de spam."
  - Sin mail configurado en el servidor (503): aviso de 10 s "La recuperación por mail todavía no está activada. Pedile a quien administra la plataforma que te genere una contraseña nueva."
  - Otro error: "Error al enviar el email. Intentá de nuevo."
- **Celular:** una columna, igual que en la notebook.
- **Datos para probarla:** en el entorno de pruebas lo más probable es que no haya mail configurado, así que debería salir el aviso del 503 (no confirmado: depende de las variables del entorno).
- **Código:** `frontend/app/(auth)/forgot-password/page.tsx`, `auth.py` (`forgot_password`).
- **Puntos a mirar:**
  - **No tiene modo oscuro**: el fondo es `bg-slate-50` fijo y los textos no tienen variante oscura, pero el campo sí se oscurece. Con el tema oscuro queda una página clara con un campo oscuro.
  - Los locales no pueden usarla (su "mail" es el nombre del local y el campo exige un mail válido). Correcto por diseño, pero la pantalla no lo dice.

### Nueva contraseña (link del mail) — `/reset-password?token=...`
- **Para qué sirve:** elegir una contraseña nueva con el link que llegó por mail.
- **Quién la ve:** quien abre el link. Sin `token` en la dirección muestra "El link de recuperación es inválido. Solicitá uno nuevo." con link a pedir otro.
- **Qué hay:** "Nueva contraseña", "Elegí una contraseña segura para tu cuenta.", Nueva contraseña (con ojito) con la ayuda "Entre 6 y 20 caracteres.", Confirmar contraseña, botón "Guardar contraseña".
- **Qué se puede hacer:** `POST /auth/reset-password`. El link sirve una sola vez; al usarlo se cierran todas las sesiones de esa persona y se desbloquea la cuenta.
- **Estados:** no coinciden → "Las contraseñas no coinciden" (texto rojo). Link vencido o usado → "Token inválido o expirado" (texto y aviso). Contraseña de menos de 6 o más de 20 → el mensaje del servidor. Listo → tilde verde, "Contraseña actualizada", y a los 3 segundos vuelve al login.
- **Celular:** una columna.
- **Datos para probarla:** sin mail no hay token real. Se puede probar sin token y con un token inventado (`?token=abc`).
- **Código:** `frontend/app/(auth)/reset-password/page.tsx`, `auth.py` (`reset_password`).
- **Puntos a mirar:** sin modo oscuro, igual que la anterior. "Token inválido o expirado" es jerga ("token"): para una persona es "el link venció o ya se usó".

### Tenés que actualizar tu contraseña (pantalla obligatoria, sin dirección propia)
- **Para qué sirve:** obliga a elegir una contraseña propia antes de usar la plataforma.
- **Quién la ve:** quien tiene una contraseña que le puso otra persona (cuenta recién creada o reseteada desde el panel) o quien no la cambia hace **más de 60 días** (`_PASSWORD_MAX_AGE_DAYS` en `backend/app/core/deps.py`). **Los locales nunca**: comparten la contraseña a propósito.
- **Qué hay:** una tarjeta con escudo ámbar, "Tenés que actualizar tu contraseña", la explicación (primera vez o más de 60 días) y el formulario: Contraseña actual, Contraseña nueva ("Entre 6 y 20 caracteres"), Confirmar, botón "Actualizar contraseña". Sin menú.
- **Qué se puede hacer:** `POST /auth/change-password`. Mientras está pendiente, el servidor contesta 403 `PASSWORD_CHANGE_REQUIRED` a todo menos `/auth/me`, `/auth/change-password`, `/auth/logout` y `/auth/refresh`.
- **Estados:** contraseña actual mal → "La contraseña actual no es correcta". Igual a la anterior → "La nueva contraseña tiene que ser distinta de la actual". Listo → aviso verde y entra.
- **Datos para probarla:** crear una cuenta en `/admin` y entrar con ella, o resetearle la contraseña desde el panel. Los 60 días no se pueden provocar desde la pantalla.
- **Código:** `frontend/app/(dashboard)/layout.tsx`, `frontend/components/ChangePasswordForm.tsx`.
- **Puntos a mirar:**
  - Sospecha: si los 60 días se cumplen con la sesión abierta, todo empieza a dar 403 y cada pantalla muestra sus errores sueltos hasta recargar (la pantalla obligatoria aparece recién al recargar).
  - No hay botón "Cerrar sesión" en esta pantalla: quien no se acuerda la contraseña actual no tiene salida a la vista.
  - Un comentario en `backend/app/models/user.py` todavía dice "cada 20 días" (solo el comentario; la regla es 60).

### Don Tino, el asistente — `/home`
- **Para qué sirve:** el chat con Don Tino. Es también la pantalla de inicio de quien no ve el calendario (los locales, por ejemplo).
- **Quién la ve:** en el menú, "Don Tino, el asistente" (sección GUÍA de Herramientas) sale solo con `ai.don_tino`. La dirección no tiene candado en la pantalla: cualquiera con sesión puede abrirla, pero mandar mensajes pide `ai.don_tino` en el servidor. Una cuenta externa no llega (la manda a su tablero).
- **Qué hay:** el robot con un punto verde, "CORE TIENDA", "Hola, {nombre} 👋", "Don Tino está listo para ayudarte". Una tarjeta "Don Tino / Preguntame sobre la plataforma" **cerrada**: hay que tocarla para abrir el chat. Adentro: el saludo, cuatro sugerencias ("¿Cómo sincronizo Google Ads?", "¿Cómo genero cenefas?", "¿Qué es el ROAS?", "¿Cómo busco precios de la competencia?"), el campo "Escribí tu pregunta..." y el botón de enviar. Al pie: "Asistente con IA real · Powered by Claude Sonnet 5".
- **Qué se puede hacer:** `POST /chat/message` (15 por minuto, hasta 2.000 caracteres, manda los últimos 10 mensajes). Cada respuesta tiene botón de copiar y dice cuántos "tokens" gastó. Los links de las respuestas (por ejemplo, a una acción del calendario) se abren adentro de la plataforma.
- **Estados:** escribiendo → tres puntitos. Error → "Lo siento, hubo un error al contactar el asistente. Intentá de nuevo." (el mismo para sin permiso, sin IA configurada o caída).
- **Celular:** tarjeta a todo el ancho; los mensajes ocupan hasta el 60% de la altura.
- **Datos para probarla:** con el superadmin y con el local. Preguntas que la IA simulada reconoce: "¿qué tengo que hacer hoy?", "¿quién está más cargado esta semana?", "¿qué piezas vencen esta semana?", "¿cómo viene {nombre de una acción}?". Para que contesten algo, primero crear acciones y tareas en el calendario.
- **Código:** `frontend/app/(dashboard)/home/page.tsx`, `frontend/components/chat/RespuestaDelBot.tsx`, `backend/app/api/routes/chat.py`, `backend/app/services/calendario_consultas.py`.
- **Puntos a mirar:**
  - La conversación **no se guarda**: al recargar o cambiar de pantalla se pierde.
  - Las sugerencias son de medios (Google Ads, ROAS). Ninguna es del calendario, que es lo que más sabe hacer.
  - El chat arranca cerrado: un toque de más para algo que es lo único de la pantalla.
  - "Powered by Claude Sonnet 5" y "1.234 tokens" son jerga en inglés.
  - Quien entra sin `ai.don_tino` (por ejemplo una cuenta interna sin calendario, que cae acá) ve un chat que siempre contesta con error.
  - Sospecha: el campo usa letra de 14 px y el iPhone agranda la página al tocarlo.

#### Don Tino: dónde está y qué puede hacer
- **Dónde se abre:** solo en `/home`. No hay botón flotante de Don Tino en otras pantallas. (Los botones flotantes que hay son de otros personajes: Doña Tina en Precios y en Análisis IA, DogTi en Finanzas.)
- **Qué sabe:** un texto largo fijo (`_SYSTEM_PROMPT` en `chat.py`) con el mapa de secciones, roles, medios, cenefas, precios y calendario, más la fecha de hoy, el nombre de quien pregunta y qué parte del calendario ve.
- **Herramientas**, cada una con el permiso de quien pregunta (sin el permiso, ni se le ofrece):

| Herramienta | Qué hace | Permiso |
|---|---|---|
| `buscar_precio` | Precio en vivo de un producto en las cadenas | `precios.search` |
| `consultar_estado_cenefa` | Estado de un trabajo de cenefas propio, por su ID | `cenefas.view` |
| `resumen_ultimo_debate` | El último debate de La Triada de la persona | `ai.triada` |
| `calendario_acciones` | Acciones de un período o buscadas por nombre | `calendario.view` |
| `calendario_accion` | Todo sobre una acción: piezas, tareas, avisos | `calendario.view` |
| `calendario_piezas` | Piezas que salen en un período, atrasadas incluidas | `calendario.view` |
| `calendario_tareas` | Tareas por responsable ("yo", "sin asignar", un nombre) | `calendario.view` |
| `calendario_carga` | Cuántas tareas abiertas tiene cada persona | `calendario.view` |
| `calendario_avisos` | Avisos configurados que salen en un período | `calendario.view` |

  - Las del calendario respetan los mundos y el alcance de cada persona. Sus propias tareas le llegan siempre, aunque la acción quede fuera de lo que ve.
  - Hasta 4 vueltas de herramientas por pregunta.
- **Dictado:** Don Tino **no tiene micrófono**. El dictado de la plataforma es otra cosa: "Dictar el pedido" en una tarea o en el formulario de entregas (`frontend/components/ia/DictarBrief.tsx`, reconocimiento de voz del navegador). La IA lo ordena en campos (`POST /ia/brief/ordenar`, pide `calendario.tareas`, `calendario.edit` o `calendario.pedidos`). Lo mapea la zona del calendario.
- **Puntos a mirar (lo que sabe Don Tino):** el texto fijo está desactualizado. Se presenta como "MKTG Platform"; dice que hay "19 permisos" (son 32) y lista solo algunos; dice que Administración es "solo Superadmin" (entra cualquiera con `platform.admin`); usa "mundos" en el sentido viejo de cenefas ("Redexpres, Rompe Precios, Parrilla y Vinos... un mundo solo agrupa las plantillas"), que choca con los mundos de hoy. Además pide "tono formal, sin coloquialismos" mientras el personaje es "cálido, rioplatense". Y la cantidad de cadenas de precios no coincide entre lugares: 17 (Don Tino), 14 y 13 (Guía de uso), "más de 10" (login).

### Dashboard de medios — `/dashboard`
- **Para qué sirve:** resumen de la pauta digital: inversión, clics, conversiones y ROAS por plataforma.
- **Quién la ve:** `analytics.view`. Menú: Herramientas → MEDIOS → "Dashboard". Está en todos los mundos. La traen los roles Admin y Usuario.
- **Qué hay:** la fecha de hoy, "Dashboard / Todas las plataformas", "Datos hasta {fecha}", un puntito verde "Auto-sync · cada N h" si está activo, botones de período (7D, 30D, 90D, personalizado), modo de comparación (período anterior, año anterior, a medida), botón "Sync datos". Cuatro tarjetas (Inversión total, Clicks totales, Conversiones, ROAS global) con su variación. Alertas automáticas en ámbar (ROAS bajo 1, inversión más de 50% arriba, clics sin conversiones, plataforma con ROAS bajo 0,5). Gráficos de inversión y ROAS por plataforma (actual contra anterior), torta por objetivo (Branding, Tráfico, Conversión) y tabla "Rendimiento por plataforma".
- **Qué se puede hacer:**
  - Ver datos: `GET /metrics/summary` (dos veces: actual y comparación), `GET /metrics/spend-by-objective`, `GET /metrics/auto-sync/status` (cada 5 minutos).
  - Sincronizar: `POST /metrics/sync` para Google Ads, TikTok y DV360 (Meta no: está pausado desde el 06/07/2026 y muestra datos de ejemplo marcados "DEMO").
- **Estados:** cargando → tarjetas grises que brillan. Sin datos → "Sin datos — sincronizá tus plataformas para ver métricas aquí", con botón. Error → aviso "Error al cargar los datos del dashboard". Sin permiso → "No tenés acceso al dashboard de medios".
- **Celular:** el encabezado se apila; la tabla se corre de costado (mínimo 600 px).
- **Datos para probarla:** vacía en la base de pruebas. Con `backend/scripts/load_fake_campaign_data.py` apuntando a la base de pruebas se cargan los datos de ejemplo de Meta, GA4 y TikTok. "Sync datos" sin conexiones va a dar errores (no hay cuentas conectadas).
- **Código:** `frontend/app/(dashboard)/dashboard/page.tsx`, `frontend/components/ui/KPICard.tsx`, `backend/app/api/routes/metrics.py`, `backend/app/services/metrics_service.py`.
- **Puntos a mirar:**
  - Sospecha: **sincronizar pide solo `analytics.view`**, un permiso "de ver": un Viewer puede disparar sincronizaciones.
  - Jerga en inglés: Dashboard, Sync, ROAS, CTR, Auto-sync, 7D/30D/90D.
  - El menú tiene dos "Dashboard" (este y el de Finanzas), solo distintos por el título de la sección.

### Mi perfil — `/perfil`
- **Para qué sirve:** ver tu cuenta, prender o apagar los avisos por mail y cambiar la contraseña.
- **Quién la ve:** todos, incluidas las cuentas externas y los locales. Se llega tocando el nombre al pie del menú.
- **Qué hay:** "Mi perfil / Tu cuenta, tus avisos y tu contraseña". Tarjeta con la inicial, el nombre, una cocarda del rol (SUPER ADMIN en rosa, ADMIN, USUARIO, VIEWER) y el mail. Tarjeta "Recibir los avisos por mail" con un interruptor: explica que lo de la campanita llega también al mail, salvo lo del tablero. Tarjeta "Cambiar contraseña" (actual, nueva, confirmar, "Actualizar contraseña").
- **Qué se puede hacer:** `PATCH /auth/me/preferencias` (avisos por mail); `POST /auth/change-password`.
- **Estados:** cargando → circulito. Interruptor guardado → "Listo: los avisos te van a llegar también por mail." / "Listo: los avisos quedan solo en la campanita."; error → "No se pudo guardar. Probá de nuevo en un momento." (y vuelve a como estaba).
- **Celular:** una columna angosta, anda bien.
- **Datos para probarla:** las tres cuentas. Ojo: cambiar la contraseña del Equipo nocturno la cambia hasta el próximo arranque.
- **Código:** `frontend/app/(dashboard)/perfil/page.tsx`, `frontend/components/ChangePasswordForm.tsx`.
- **Puntos a mirar:**
  - Sospecha: **al local le aparece "Cambiar contraseña", pero el servidor siempre se lo rechaza** ("Los usuarios de sucursal no pueden cambiar su propia contraseña — pedile a un administrador que la resetee"). Un formulario que nunca puede andar.
  - Las cocardas del rol no tienen colores para el modo oscuro.
  - La cuenta externa no ve su empresa en el perfil (sí al pie del menú).

### Conexiones — `/settings`
- **Para qué sirve:** cargar las cuentas de publicidad (Meta, Google Ads, Google Analytics, TikTok, DV360) para traer sus métricas.
- **Quién la ve:** `connections.view` para entrar; agregar y borrar piden `connections.manage`. Menú: Herramientas → MEDIOS → "Conexiones". Todos los mundos. El rol Usuario trae `connections.view` pero no `connections.manage`.
- **Qué hay:** "Conexiones / Conectá tus cuentas de advertising", botón "Nueva conexión". El formulario: elegir plataforma, guía de cómo sacar el token con link al portal, Account ID, nombre de cuenta, Access Token, Refresh Token (opcional) y **tu contraseña** para confirmar. La lista de conexiones (activa o inactiva) con el tacho para borrar (pide la contraseña). Abajo, "Almacenamiento seguro de tokens".
- **Qué se puede hacer:** `GET /connections/`, `POST /connections/`, `DELETE /connections/{id}` (las dos últimas piden la contraseña y `connections.manage`).
- **Estados:** sin conexiones → "Sin conexiones configuradas / Agregá tu primera plataforma...". Sin permiso → primero el candado general "No tenés acceso a las conexiones de medios" (layout); la pantalla también tiene el suyo. Guardado → "Conexión guardada correctamente".
- **Celular:** encabezado apilado; en la fila de borrar quedan el campo de contraseña y dos botones en una sola línea (sospecha de que no entra a 390 px).
- **Datos para probarla:** con el superadmin se pueden cargar datos inventados (no se conecta a nada real al guardar). Para ver el problema de abajo, con una cuenta de rol Usuario.
- **Código:** `frontend/app/(dashboard)/settings/page.tsx`, `backend/app/api/routes/connections.py`.
- **Puntos a mirar:**
  - Sospecha fuerte: **"Nueva conexión" y el tacho aparecen aunque no tengas `connections.manage`**, y el 403 del servidor se muestra como **"Contraseña incorrecta"** (la pantalla toma cualquier 403 como contraseña mal). Quien tiene el rol Usuario escribe bien su contraseña y le dicen que está mal.
  - No hay estado "cargando": mientras llega la lista se ve "Sin conexiones configuradas".
  - Si falla la red no se avisa nada (solo se maneja el 403).
  - El botón de borrar usa el estilo de botón principal azul, no uno rojo de peligro.
  - Jerga: "advertising", "Account ID *", "Access Token *", "Refresh Token", "AES-256".
  - La dirección es `/settings` pero la pantalla se llama "Conexiones" (y el i18n la llama "Configuración" en `common.settings`).

### Guía de uso — `/ayuda`
- **Para qué sirve:** explicar cómo se usa la plataforma "según lo que tu cuenta puede ver y hacer".
- **Quién la ve:** todo el que tenga sesión, sin permiso. Menú: Herramientas → GUÍA → "Guía de uso". Una cuenta externa no llega (la manda al tablero).
- **Qué hay:** el robot, "¿Cómo funciona la plataforma?", chips (Analytics, IA integrada, Cenefas, Precios, Pedidos, Asistente) y secciones que aparecen según el permiso: Dashboard y Campañas (`analytics.view`), Análisis IA – La Triada (`ai.triada`), Precios (`precios.search`), Cenefas, Editor de plantillas e Historial (`cenefas.view`), Conexiones (`connections.view`), Planilla de pedidos (siempre), Asistente virtual (siempre), Roles y permisos (`platform.users.view`).
- **Qué se puede hacer:** solo leer; algunos links (por ejemplo al panel de administración).
- **Estados:** cargando → circulito. No tiene error ni vacío propios.
- **Celular:** una columna (máximo 4xl).
- **Datos para probarla:** comparar con el superadmin, con una cuenta Usuario y con el local.
- **Código:** `frontend/app/(dashboard)/ayuda/page.tsx`, textos en `es.json` → `ayuda`.
- **Puntos a mirar:**
  - **Está desactualizada.** No menciona el calendario, Mis tareas, el tablero de entregas, los mundos, las agencias, colocación, Finanzas ni la validación de RRSS. Lo que hoy es el centro de la plataforma no está.
  - Dice cosas que ya no son así: "Solo el Super Admin puede abrir un mes nuevo" (hoy es `redexpres.manage`); el asistente "está en Home, abrí la tarjeta de chat"; las cadenas de precios son 14 en un lado y 13 en otro.
  - "Planilla de pedidos" y "Asistente" se muestran a todos, aunque no puedan usarlos.
  - La sección de roles depende de `platform.users.view`, que el rol Usuario trae: la gente común ve cómo funcionan los roles del panel.
  - Jerga: "Spend", "WYSIWYG basado en Konva.js", "OAuth 2.0", "Service Account JSON", estados en inglés ("done — listo para descargar", "running", "pending").

### Panel de Administrador — `/admin`
- **Para qué sirve:** dar de alta, editar, desactivar y eliminar cuentas; manejar roles y permisos, mundos, el alcance del calendario por persona y las cuentas externas con su agencia. También la auditoría y el gasto de IA.
- **Quién la ve:** `platform.admin` (o superadmin). Menú: Herramientas → CONFIGURACIÓN → "Administrador", en todos los mundos. **Cambiar** cualquier cosa pide además `platform.users.manage`.
- **Qué hay:**
  - "Panel de Administrador / Gestión de usuarios, roles y permisos", botón "Nuevo usuario" (solo en las listas Usuarios y Externas).
  - Tres pestañas: "Usuarios y Roles", "Auditoría", "Uso de IA".
  - **Usuarios y Roles:**
    - Formulario de alta: "Del equipo" / "Externa (agencia)", nombre, mail, contraseña (6 a 20), y rol (del equipo) o agencia (externa, de una lista con los tres tableros Publicis, Another Monday, Diseñadores, las agencias que ya existen y "Otra agencia"). La externa elige además "Mundos donde trabaja", con un recuadro celeste que explica qué ve.
    - Cartel ámbar con la contraseña temporal cuando se resetea una.
    - Tarjeta "Roles y permisos": los roles con cuántos permisos tienen, los primeros 6 permisos en letra de código, editar y borrar (los del sistema, marcados "SISTEMA", no se borran) y "Nuevo rol".
    - Tarjeta "Usuarios (N)" con cuatro listas: Usuarios, Externas, Sucursales Redex, Sucursales Tienda (cada una con su cantidad). "Seleccionar todo", "Eliminar (N)" y, en Usuarios, filtro por rol (Todos, Super Admin, Admin, Usuario, Viewer). Cada fila: inicial, nombre, cocarda del rol, marca de externa con la empresa, "Calendario: 1 mes" si se sale de lo normal, "INACTIVO", mail, último ingreso y cantidad de ingresos. Botones: ver actividad, desplegable de rol, editar, resetear contraseña, activar/desactivar y eliminar.
  - **Editar usuario** (ventana): nombre; mail (o "Usuario del local", fijo, para las sucursales); Mundos (chips; los que vos no tenés salen apagados); "Cuenta externa" con su agencia (no para el superadmin ni para las sucursales); "Calendario" con 5 opciones (No lo ve, 1 mes, 2 meses, 12 meses, Todo); Permisos agrupados con tilde, la clave y la descripción (para una externa, un texto fijo). Si es la única cuenta de una agencia y se la pasa a otra, antes de guardar pregunta si se lleva las tarjetas y plantillas.
  - **Editar rol** (ventana): nombre (los del sistema no se renombran), descripción y permisos.
  - **Auditoría:** tabla con fecha, usuario, acción, recurso y detalle, con "Cargar más".
  - **Uso de IA:** 7D, 30D, 90D; costo total en dólares, tokens de entrada y salida, costo diario, por proveedor, por función y los 10 usuarios que más gastan (tocar uno abre su actividad).
  - **Actividad de {nombre}** (ventana): ingresos, último ingreso, cenefas generadas, costo de IA de 30 días e historial.
- **Qué se puede hacer:**

| Acción | Endpoint | Pide |
|---|---|---|
| Ver usuarios, roles, permisos, mundos, agencias | `GET /admin/users`, `/admin/roles`, `/admin/permissions`, `/admin/mundos`, `/admin/agencias` | `platform.admin` |
| Crear cuenta (del equipo o externa) | `POST /admin/users` | `platform.users.manage` |
| Cambiar nombre o mail | `PATCH /admin/users/{id}` | ídem |
| Resetear contraseña | `POST /admin/users/{id}/reset-password` | ídem |
| Cambiar rol (pisa los permisos con los del rol) | `PATCH /admin/users/{id}/role` | ídem |
| Cambiar permisos | `PATCH /admin/users/{id}/permissions` | ídem |
| Pasar a externa o cambiar agencia | `GET /admin/users/{id}/pase-de-agencia`, `PATCH /admin/users/{id}/externo` | ídem |
| Alcance del calendario | `PATCH /admin/users/{id}/alcance` | ídem |
| Mundos | `PATCH /admin/users/{id}/mundos` | ídem |
| Activar o desactivar | `PATCH /admin/users/{id}/activate` | ídem |
| Eliminar una o varias | `DELETE /admin/users/{id}`, `POST /admin/users/eliminar` | ídem |
| Crear, editar o borrar roles | `POST/PATCH/DELETE /admin/roles...` | ídem |
| Actividad, auditoría, IA | `GET /admin/users/{id}/stats`, `/admin/audit-log`, `/admin/ai-usage/summary` | `platform.admin` |

  Reglas del servidor: nadie da un permiso, un mundo o más calendario que los que tiene él mismo; un Admin no toca a otro Admin ni al superadmin, ni su propio rol, permisos o alcance; a una externa solo se le puede dar `calendario.view` (la base también lo impide); no se elimina a quien aprueba entregas en curso (409, con el motivo), ni a uno mismo, ni al superadmin.
- **Estados:** cargando → circulito en cada tarjeta. Lista vacía → "Todavía no hay ninguna en esta lista." Error al cargar → aviso "Error cargando datos de administración". Sin permiso → "No tenés acceso al panel de administración" (layout). Los errores de cada acción muestran el texto del servidor en un aviso.
- **Celular:** sospecha de que no anda bien. Cada fila tiene casilla, inicial, nombre y unos 6 controles en una sola línea sin acomodarse. Los botones son de unos 27 px (lejos de los 44 que se usan en el núcleo) y las listas y el filtro de rol se apilan.
- **Datos para probarla:** al arrancar ya están las tres cuentas (una en cada lista: Usuarios, Externas, Sucursales Redex) y los 4 roles del sistema. Para probar crear, editar, pasar a externa y eliminar: cuentas descartables. Las sucursales **no se crean desde el panel** (el botón "Nuevo usuario" no aparece en esas listas; se crean con `backend/scripts/create_sucursal_users.py`). La auditoría muestra al menos los ingresos.
- **Código:** `frontend/app/(dashboard)/admin/page.tsx` (todo en un archivo de 1.427 líneas), `AuditLogTab.tsx`, `AiUsageTab.tsx`, `UserActivityModal.tsx`, `frontend/lib/admin/usuarios.ts`, `backend/app/api/routes/admin.py`.
- **Puntos a mirar:**
  - Sospecha seria: **el superadmin se puede desactivar a sí mismo.** El botón está en su propia fila y el servidor no lo frena (`toggle_active` no mira si sos vos). Quedaría afuera sin poder entrar. (Eliminarse sí está frenado.) **No probarlo con Equipo nocturno**: se arregla recién al reiniciar el servidor.
  - Sospecha: **cambiar el rol en el desplegable de la fila pisa sin avisar los permisos afinados a mano**: el servidor los reemplaza por los del rol.
  - Quien tiene `platform.admin` sin `platform.users.manage` ve todos los botones (crear, editar, eliminar) y cada uno falla con "Acceso denegado — permiso de gestión de usuarios requerido".
  - Los permisos se muestran con la **clave técnica en letra de código** (`calendario.pedidos`) y descripciones con jerga ("templates", "PPTX", "CatTi"). Los grupos Calendario, Precios y Redexpres no tienen nombre traducido y salen en minúscula ("calendario"). Las casillas son dibujos con clic, no casillas reales: no se tildan con el teclado.
  - La auditoría muestra la acción en código (`admin.user.update_permissions`, `user.login`) y el detalle como "permissions_antes: ...".
  - "Uso de IA" tiene nombre solo para 4 funciones. Las demás (dictado, revisión de piezas, convertidor, facturas) salen con su clave interna.
  - Las ventanas Editar usuario y Editar rol no se cierran con Escape (la de Actividad sí).
  - Confirmaciones con la ventanita del navegador (`confirm()`): resetear, eliminar, borrar rol.
  - El cartel de la contraseña temporal no tiene modo oscuro: sospecha de texto ámbar oscuro sobre fondo oscuro. Las cocardas de rol tampoco tienen modo oscuro.
  - "Nuevo usuario" usa un botón azul plano distinto del botón principal del resto (ver la sección 4).
  - El permiso `platform.users.view` ("Ver la lista completa de usuarios") no abre el panel: hace falta `platform.admin`.

### Análisis IA (La Triada) — `/analytics`
- **Para qué sirve:** un debate con IA sobre los datos de campañas: tres modelos (Claude, ChatGPT, Llama) en rondas, con síntesis al final.
- **Quién la ve:** `ai.triada`. Menú: Herramientas → MEDIOS → "Análisis IA". Todos los mundos. La traen Admin y Usuario.
- **Qué hay:** título **"La Triada"** ("Claude · ChatGPT · Llama — debate con tus datos de campañas"). Panel izquierdo con las plataformas (las que no tienen conexión salen grises), período e historial de debates. A la derecha el chat del debate con turnos por modelo, la pregunta propia y el veredicto. Botón flotante de Doña Tina.
- **Qué se puede hacer:** `GET /analytics/available-platforms`, `GET /analytics/history`, `GET /analytics/history/{id}`, `POST /analytics/analyze/debate/stream`, `POST /analytics/debate/turn`, `POST /analytics/debate/verdict` (respuestas que van llegando de a poco).
- **Estados:** sin plataforma elegida → "Seleccioná al menos una plataforma". Error → "Error al generar análisis". Sin permiso → "No tenés acceso al análisis con IA".
- **Celular:** una columna (las dos columnas recién desde 1280 px). Sospecha: la pantalla tiene alto fijo (`100vh - 140px`) y en el teléfono el panel de arriba le come lugar al chat.
- **Datos para probarla:** sin datos de campañas ni claves de OpenAI o Groq no va a debatir de verdad; la IA simulada cubre Don Tino, no está confirmado que cubra La Triada.
- **Código:** `frontend/app/(dashboard)/analytics/AnalyticsClient.tsx`, `backend/app/api/routes/analytics.py`, `backend/app/services/debate_service.py`.
- **Puntos a mirar:** el nombre cambia según dónde: "Análisis IA" en el menú, "La Triada" en el título, "El análisis con IA" en el candado. Es la pantalla más "de medios" de todas: no se relaciona con el calendario.

### Campañas — `/campaigns`
- **Para qué sirve:** tabla de métricas por campaña de todas las plataformas.
- **Quién la ve:** `analytics.view`. Menú: Herramientas → MEDIOS → "Campañas". Todos los mundos.
- **Qué hay:** "Campañas / Métricas por campaña · todas las plataformas", botones para sincronizar cada plataforma (Google Ads, TikTok, DV360), "CSV", buscador "Buscar campaña...", filtros por plataforma y fechas, "Comparar" (período anterior o año anterior), totales, tabla ordenable (plataforma, campaña, fecha, inversión, clics, CTR, conversiones, ROAS) y elegir campañas para compararlas.
- **Qué se puede hacer:** `GET /metrics/` (dos veces si compara), `POST /metrics/sync` por plataforma. El CSV se arma en el navegador.
- **Estados:** cargando → 8 filas grises. Vacío → "Sin datos para este rango / Sincronizá una plataforma o ajustá las fechas". Búsqueda sin resultados → "Sin campañas para "{texto}"". Error → "Error cargando métricas".
- **Celular:** la tabla se corre de costado (mínimo 640 px) con alto limitado.
- **Datos para probarla:** igual que el Dashboard (`load_fake_campaign_data.py`).
- **Código:** `frontend/app/(dashboard)/campaigns/page.tsx`, `metrics.py`.
- **Puntos a mirar:** el CSV lo baja cualquiera con `analytics.view`: **el permiso `analytics.export` no se controla en ningún lado.**

### Analytics GA4 — `/canales`
- **Para qué sirve:** sesiones, embudo de compra y canales de adquisición de la web (Google Analytics).
- **Quién la ve:** `analytics.view`. Menú: Herramientas → MEDIOS → "Analytics GA4". Todos los mundos.
- **Qué hay:** tarjetas (Sesiones, Usuarios, Tasa de conversión, Revenue), embudo (Sesiones → Page views → Vio producto → Agregó al carrito → Inició checkout → Compró), "Canales de adquisición" ordenado por revenue, "Tendencia de sesiones" con métrica a elegir, período personalizado y comparar.
- **Qué se puede hacer:** `GET /metrics/ga4-funnel` (dos veces si compara).
- **Estados:** cargando → 4 tarjetas grises. Vacío → "Sin datos de Analytics para este período". Error → "No se pudo cargar la data de Analytics". Sin permiso → "No tenés acceso a Analytics".
- **Celular:** tabla con scroll de costado (mínimo 600 px).
- **Datos para probarla:** `load_fake_campaign_data.py ga4` (GA4 se muestra con datos de ejemplo: `FIXTURE_PLATFORMS` en `metrics_service.py`).
- **Código:** `frontend/app/(dashboard)/canales/page.tsx`, `metrics.py`.
- **Puntos a mirar:** mucha jerga en inglés: Page views, checkout, Revenue, Engagement rate, "la data". La dirección `/canales` no coincide con el nombre "Analytics GA4".

### Finanzas — `/facturacion`
- **Para qué sirve:** presupuesto (entradas y salidas) y canjes con marcas y proveedores; subir facturas en PDF que lee DogTi (IA).
- **Quién la ve:** `facturacion.view` (o `facturacion.manage`). Menú: Herramientas → FINANZAS → "Dashboard". Todos los mundos. **No la trae el rol Usuario**: en la práctica, solo admins.
- **Qué hay:** "Finanzas / Presupuesto y canjes con marcas y proveedores.", botón "Subir factura" (con `facturacion.upload`), tortas General, Presupuesto y Canjes, la lista "Movimientos" con "Cargar más" y el botón flotante de DogTi (con `ai.dogti`).
- **Qué se puede hacer:** `GET /facturacion/dashboard`, `GET /facturacion/cuentas`; subir y revisar: `POST /facturacion/documentos/upload`, `GET /facturacion/documentos/{id}` y `/pdf`, `POST .../confirmar`, `POST .../descartar`; chat con DogTi: `POST /facturacion/dogti/consultar`.
- **Estados:** vacío → "Todavía no hay datos cargados — subí tu primera factura." / "Todavía no hay cuentas creadas.". Leyendo → "DogTi está leyendo N facturas…". DogTi no pudo → "DogTi no pudo leer este PDF — completá los datos a mano.". Sin permiso → "No tenés acceso a Finanzas".
- **Celular:** no verificado en detalle.
- **Datos para probarla:** primero crear una cuenta en `/facturacion/cuentas`. `backend/scripts/seed_facturacion_fixtures.py` carga 6 meses de datos de ejemplo (pide confirmación y está pensado contra producción: usar solo con la base de pruebas).
- **Código:** `frontend/app/(dashboard)/facturacion/page.tsx`, `frontend/components/facturacion/*`, `backend/app/api/routes/facturacion.py`.
- **Puntos a mirar:** la dirección dice "facturación" y la pantalla "Finanzas". Las claves internas también son "facturacion".

### Cuentas de Finanzas — `/facturacion/cuentas`
- **Para qué sirve:** crear, renombrar, desactivar y reactivar las cuentas a las que van los movimientos y canjes.
- **Quién la ve:** `facturacion.manage`. Menú: Herramientas → FINANZAS → "Cuentas".
- **Qué hay:** "Cuentas / Administrá las cuentas a las que ingresan movimientos y canjes.", campo "Nombre de la cuenta" con "Crear", "Ver inactivas / Ocultar inactivas" y la lista con Editar, Desactivar (con confirmación en la misma fila) y Reactivar.
- **Qué se puede hacer:** `GET /facturacion/cuentas?incluir_inactivas=`, `POST /facturacion/cuentas`, `PATCH /facturacion/cuentas/{id}`.
- **Estados:** cargando → 3 barras grises. Vacío → "Todavía no hay cuentas creadas.". Error → "Ocurrió un error — probá de nuevo.". Sin permiso → "No tenés acceso a las cuentas de Finanzas".
- **Celular:** una tarjeta angosta, debería andar.
- **Datos para probarla:** vacía; crear 2 o 3 cuentas y desactivar una.
- **Código:** `frontend/app/(dashboard)/facturacion/cuentas/page.tsx`.
- **Puntos a mirar:** confirma desactivar en la misma fila (bien), al revés del panel de admin, que usa la ventanita del navegador.

### ¿Siguen en el menú `/analytics`, `/campaigns`, `/canales`, `/facturacion` y `/facturacion/cuentas`?

| Pantalla | ¿En el menú? | Para quién | ¿Parece vieja? |
|---|---|---|---|
| `/dashboard`, `/canales`, `/campaigns` | Sí, MEDIOS | `analytics.view` (Admin y Usuario la traen) | Heredada de cuando la plataforma era "MKTG Platform" de medios. Meta pausado desde el 06/07/2026 con datos de ejemplo; GA4 y TikTok con datos de ejemplo. Ivan decidió el 20/11/2026 "medios para todos" (`frontend/lib/mundos.ts`): siguen a propósito, en todos los mundos. |
| `/analytics` | Sí, MEDIOS | `ai.triada` (Admin y Usuario) | Igual que medios. Depende de que haya datos de campañas. |
| `/settings` | Sí, MEDIOS ("Conexiones") | `connections.view` (Admin y Usuario) | Igual que medios. |
| `/facturacion` y `/cuentas` | Sí, FINANZAS | `facturacion.*` (solo Admin y Superadmin por defecto) | Más nueva (DogTi). "Finanzas para todos" (20/11/2026). |

No se puede saber por el código si alguien las usa: la auditoría registra ingresos y cambios, no visitas a pantallas.

---

## 2. La estructura

### 2.1 Del login a la primera pantalla

`/login` → `POST /auth/login` → `GET /auth/me` → destino (`inicioDe` en `frontend/lib/mundos.ts`):

| Tipo de cuenta | A dónde va |
|---|---|
| Tiene más de un mundo (el superadmin siempre, tiene los 5) | `/mundos` a elegir y después lo de abajo |
| Externa (agencia) | `/entregas` (su tablero) |
| Del equipo con `calendario.view` y alcance distinto de "No lo ve" | `/calendario` |
| Del equipo con `calendario.view` pero alcance "No lo ve" | `/entregas` |
| Del equipo sin `calendario.view` (por ejemplo, alguien solo de medios) | `/home` |
| Local de Redexpres (solo `ai.don_tino` y su local) | `/home` |
| Si `/auth/me` falla justo después del login | `/home` (y el layout decide) |

Sospecha: el local cae en el chat de Don Tino y no en lo suyo ("Fotos para subir" o "Mi pedido"), que está en el menú.

### 2.2 El orden de los chequeos en cada pantalla interna

`frontend/app/(dashboard)/layout.tsx`, en este orden:
1. **Pantalla de carga** mientras llega `/auth/me`: el cuadrado azul con el calendario y un trazo que da la vuelta por el borde, y "Core Tienda". Si contesta 401 o 403 → `/login`. Si falla la red, deja pasar (cada pantalla maneja su error).
2. **Contraseña pendiente** → "Tenés que actualizar tu contraseña", sin menú.
3. **Varios mundos y ninguno elegido** → `/mundos`.
4. **Externa fuera de sus pantallas** (`/entregas`, `/perfil`, `/mundos`, y `/calendario` y `/mis-tareas` si ve el calendario) **o calendario vedado** (alcance "No lo ve"; a alguien del equipo Mis tareas no se le cierra) → `/entregas`.
5. **`/mundos`** se dibuja sin menú.
6. El resto: menú lateral, barra de arriba, el aviso de qué parte ve (en `/calendario`, a quien lo ve recortado), y adentro:
   - **Herramienta de otro mundo** → "{Herramienta} no es de {Mundo}", con "Pasar a {otro mundo}" y "Volver al inicio de {Mundo}" (`FueraDeMundo.tsx`).
   - **Sin el permiso** → candado, "No tenés acceso a {la herramienta}", "Tu cuenta no tiene ese permiso. Si lo necesitás, pedíselo a quien administra Core Tienda." y "Volver al inicio" (`SinAcceso.tsx`, reglas en `frontend/lib/acceso.ts`).
   - Si no, la pantalla.
7. La barra de abajo (celular) y la ventana de entregas, que se abre encima de cualquier pantalla.

Sospecha: la pantalla de carga no dice nada si el servidor está dormido. Quien ya tiene sesión y abre la plataforma ve el logo girando hasta un minuto sin explicación (el aviso "se está despertando" está solo en el login).

### 2.3 El menú lateral

`frontend/components/layout/Sidebar.tsx`. Notebook: fijo a la izquierda, 256 px, con botón para ocultarlo (queda una franja de 48 px con el botón para volver a mostrarlo; se recuerda en el navegador). Celular: hoja que entra desde la izquierda (288 px) con velo, X para cerrar y Escape.

De arriba abajo:
1. **Marca:** cuadrado azul con ícono de calendario, "Core Tienda / Calendario y tareas". Lleva al inicio de cada uno.
2. **Mundo:** con varios mundos, una tarjeta con la franja del color del mundo, "MUNDO / {nombre}" y el botón "Cambiar" (va a `/mundos`). Con uno solo, una pastilla sin botón.
3. **El núcleo**, siempre a la vista, letra grande:

| Link | Se ve si |
|---|---|
| Fotos para subir (`/fotos`, con número de pendientes) | tiene un local asignado |
| Calendario | `calendario.view` y alcance distinto de "No lo ve" |
| Mis tareas | `calendario.view` |
| Tablero (`/entregas`) | `calendario.view` |
| Colocación | `calendario.edit`, ve el calendario y el mundo tiene locales con usuario |

   A una externa: "Mi tablero" y, si se lo habilitaron, "Calendario". Nada más.
4. **Herramientas** (botón con llave inglesa que pliega y despliega; arranca plegado, salvo que estés parado en una; se recuerda en el navegador). Solo se pliega si la persona tiene `calendario.view`; si no (los locales), siempre abierto. Las externas no tienen herramientas. Orden fijado por Ivan el 23/09/2026:

| Sección | Link | Permiso | Mundos |
|---|---|---|---|
| MATERIALES | Cenefas | `cenefas.view` | Tienda Inglesa, Redexpres |
| MATERIALES | Convertidor de Excel | `cenefas.view` | Tienda Inglesa, Redexpres |
| MATERIALES | Diccionario | `cenefas.diccionario` | Tienda Inglesa |
| REDES SOCIALES | Validación de RRSS | `rrss.view` | Tienda Inglesa |
| MEDIOS | Dashboard | `analytics.view` | todos |
| MEDIOS | Analytics GA4 | `analytics.view` | todos |
| MEDIOS | Campañas | `analytics.view` | todos |
| MEDIOS | Análisis IA | `ai.triada` | todos |
| MEDIOS | Conexiones | `connections.view` | todos |
| REDEXPRES | Planilla de pedidos | `redexpres.view` | Redexpres |
| REDEXPRES | Mi pedido | tener un local asignado, o superadmin | Redexpres |
| FINANZAS | Dashboard | `facturacion.view` | todos |
| FINANZAS | Cuentas | `facturacion.manage` | todos |
| COMERCIAL | Buscar precios | `precios.search` | Tienda Inglesa |
| COMERCIAL | Listas de monitoreo | `precios.search` | Tienda Inglesa |
| CONFIGURACIÓN | Administrador | `platform.admin` | todos |
| GUÍA | Don Tino, el asistente (`/home`) | `ai.don_tino` | todos |
| GUÍA | Guía de uso | ninguno | todos |

   Regla: primero el mundo decide qué herramientas existen, después el permiso cuáles se ven. Los mundos de cada herramienta están en `RUTAS_DE_MUNDO` (`frontend/lib/mundos.ts`); el permiso es el mismo que en `acceso.ts` y en el servidor.
5. **Perfil:** círculo con iniciales, nombre y "Mi perfil" (o la empresa, si es externa).
6. **Pie:** idioma (globo y bandera, menú con Español, English, Português), tema claro u oscuro (luna o sol) y salir (rojo al pasar). Al salir se borra la copia del calendario y el mundo elegido de ese navegador.

### 2.4 La barra de arriba
- **Celular:** botón de menú, marca chica "Core Tienda" y, a la derecha, el mundo (con varios, una pastilla que lleva a `/mundos`).
- **Notebook:** solo la campanita "Notificaciones", arriba a la derecha.

### 2.5 La barra de abajo (solo celular, menos de 768 px)
`frontend/components/layout/NavegacionInferior.tsx`:

| Cuenta | Botones |
|---|---|
| Del equipo con `calendario.view` | Calendario (si lo ve), Mis tareas, Tablero, Avisos, Más |
| Externa | Mi tablero, Calendario (si lo ve), Avisos, Más |
| Local | Fotos (con número), Mi pedido (en Redexpres), Avisos, Más |
| Cualquier otra (por ejemplo, alguien solo de medios o precios) | **ninguna barra** |

"Avisos" abre la campanita como hoja desde abajo; "Más" abre el menú lateral.

Sospecha: quien no tiene barra **no tiene cómo ver sus avisos en el celular** (la campanita de arriba está escondida en pantallas chicas y nada más la abre). Por ejemplo, quien recibe avisos de precios o de campañas.

### 2.6 El selector de mundo — `/mundos`
- Pantalla entera sin menú: "Hola, {nombre}." / "¿En qué mundo vas a trabajar?", la explicación ("Cada mundo es la plataforma entera para ese negocio...") y una tarjeta por mundo con su color, iniciales, nombre, bajada y la marca "el último que usaste".
- Los cinco mundos: Tienda Inglesa (azul `#2563eb`), Tienda Express (verde), Redexpres (rojo), Tienda Viajes (celeste), Tienda Farma (violeta).
- Quien tiene un solo mundo nunca la ve. Lo elegido se guarda en el navegador (`core-tienda-mundo`).
- Código: `frontend/app/(dashboard)/mundos/page.tsx`, `frontend/lib/mundos.ts`, `backend/app/core/mundos.py`.

### 2.7 La campanita
- **Notebook:** botón con campana, "Notificaciones" y el número en rojo (hasta 99+). Abre una lista de 26rem debajo.
- **Celular:** "Avisos" en la barra de abajo, hoja desde abajo (75% del alto).
- **Contenido:** los últimos 50 avisos, con ícono por tipo: tarea, entrega, aviso de acción, header, colocación, precio que sube o baja, alerta de campaña. Lo no leído tiene fondo azulado y una rayita. Cada aviso dice "hace 5 minutos" y tiene "Marcar como leída"; arriba, "Marcar todas como leídas". Tocar un aviso lleva a su lugar (la ficha de la acción, Mis tareas, el tablero, Fotos, Listas de monitoreo, Campañas).
- **El número** se pregunta al entrar, cada minuto con la pestaña a la vista y al volver a ella.
- **Endpoints:** `GET /notificaciones`, `GET /notificaciones/no-leidas/count`, `POST /notificaciones/{id}/marcar-leida`, `POST /notificaciones/marcar-todas-leidas`. El servidor filtra por permiso y por alcance.
- **Estados:** cargando → 3 renglones grises. Vacío → campana tachada, "Todavía no tenés notificaciones". Error al marcar todas → "No se pudieron marcar como leídas".
- **Código:** `frontend/components/layout/Campanita.tsx`, `backend/app/api/routes/watchlist.py`.

### 2.8 Tema, idioma y zoom
- **Tema:** clase `dark` en el `<html>`. Se guarda en el navegador (`theme`); si no hay nada, sigue al sistema. Se aplica después de cargar la página (sin guion previo): sospecha de un destello claro al abrir con el tema oscuro.
- **Idioma:** español, inglés y portugués (`frontend/lib/i18n.ts`, se guarda como `mktg_lang`). El inglés y el portugués tienen 75 textos menos que el español, y muchas pantallas nuevas tienen el texto fijo en castellano (perfil, mundos, sin acceso, avisos, buena parte del panel). Sospecha: en inglés la pantalla sale mezclada.
- **Zoom:** no hay zoom general de la plataforma. El zoom (+, −, 0) es solo del calendario (lo mapea la otra zona). En el teléfono se puede pellizcar para agrandar (no hay `maximumScale`).

### 2.9 Otras piezas de la estructura
- **Cartel del entorno de pruebas:** con `NEXT_PUBLIC_ENTORNO=pruebas`, la pestaña dice "Core Tienda · Pruebas" y abajo al centro hay una pastilla ámbar "Entorno de pruebas: no es la plataforma de verdad" (en el celular, encima de la barra de abajo).
- **Algo salió mal** (`frontend/components/ErrorBoundary.tsx`): si una pantalla se rompe, triángulo rojo, "Algo salió mal", **el mensaje técnico del error** y "Reintentar".
- **La sesión:** dura 30 minutos y se renueva sola durante 7 días. Se guarda en el navegador (localStorage, por Safari) además de la cookie. Si la renovación falla por la red, no echa al login.
- Sospecha: "Cerrar sesión" (`POST /auth/logout`) borra la sesión del navegador, pero **no la invalida en el servidor**: una copia de la sesión seguiría sirviendo hasta que venza. Cambiar la contraseña sí las invalida.
- Los permisos se leen una vez al entrar: si un admin te cambia los permisos, el menú no cambia hasta recargar.

---

## 3. Matriz de permisos

### 3.1 Cómo funciona
- **El permiso vive en cada usuario** (`users.permissions`). El rol solo **siembra** la lista al asignarlo; después se afina tildando uno por uno. Cambiar de rol vuelve a sembrar (pisa lo afinado).
- **Superadmin** no es un permiso: es la marca `is_superuser`. Pasa cualquier chequeo y entra a los 5 mundos. No se asigna desde el panel (el rol "Superadmin" no se ofrece).
- **Cuenta externa** (`es_externo` + `empresa`): como mucho `calendario.view`, aunque tuviera otros (el servidor los ignora y la base no deja guardarlos). Solo llega a `/auth/*`, `/calendario/*` (incluye el tablero, las entregas y los adjuntos) y `/notificaciones`. Todo lo demás contesta 403 "Una cuenta externa no tiene acceso a esto" (`backend/app/core/externos.py`, en la puerta de todas las rutas en `deps.py`).
- **Mundo:** dice DE QUÉ negocio. **Permiso:** QUÉ se puede hacer. **Alcance:** cuánto calendario ve (No lo ve, 1 mes, 2 meses, 12 meses, Todo; N meses = el actual y los siguientes, más los últimos 7 días del anterior). Externas arrancan en "No lo ve", el equipo en "Todo".
- **Local (login de sucursal):** un usuario con un local asignado (`LocalAsignacion`). Su llave es el local, no un permiso: "Mi pedido" y "Fotos para subir". No cambia su contraseña ni vence a los 60 días.
- En la pantalla, `hasPermission` (`frontend/lib/permissions.ts`) deja pasar al superadmin igual que el servidor. Lo que de verdad cuida es el servidor (`require_permission` en `backend/app/core/deps.py`).

### 3.2 Los 32 permisos

Catálogo: `ALL_PERMISSIONS` en `backend/app/models/role.py`. Columnas de roles = con qué arranca cada rol en una base nueva (A = Admin, U = Usuario, V = Viewer, que puede tenerlo tildado).

| Permiso | Qué habilita, en simple | A | U | V |
|---|---|---|---|---|
| `platform.super` | **Nada por sí solo.** Solo marca la cuenta como "administrador protegido" (un Admin común no la puede tocar). | sí | | |
| `platform.admin` | Entrar al panel de administración y verlo todo (usuarios, roles, auditoría, uso de IA). Muestra el link "Administrador". | sí | | |
| `platform.users.view` | **Ninguna pantalla ni ruta.** Solo muestra la sección "Roles y permisos" de la Guía de uso. | sí | sí | puede |
| `platform.users.manage` | Cambiar cuentas y roles en el panel (crear, editar, permisos, mundos, alcance, externa, activar, eliminar, resetear). Sin `platform.admin` no ve el panel. | sí | | |
| `cenefas.view` | Cenefas y Convertidor de Excel (y la herramienta de Don Tino para el estado de un trabajo). | sí | sí | puede |
| `cenefas.diccionario` | El Diccionario de descripciones (solo en Tienda Inglesa). | sí | sí | |
| `cenefas.generate` | Generar cenefas desde un Excel y bajar el PPTX. | sí | sí | |
| `cenefas.edit` | El editor de plantillas de cenefas. | sí | sí | |
| `cenefas.import` | Importar plantillas desde un PPTX. | sí | sí | |
| `cenefas.delete` | Borrar plantillas (propias y ajenas). | sí | sí | |
| `analytics.view` | Dashboard de medios, Analytics GA4 y Campañas, **y sincronizar plataformas**. | sí | sí | puede |
| `analytics.export` | **Nada:** no se controla en ningún lado (el CSV lo baja cualquiera con `analytics.view`). | sí | sí | |
| `connections.view` | Ver Conexiones. | sí | sí | puede |
| `connections.manage` | Agregar y borrar conexiones (con la contraseña). | sí | | |
| `precios.search` | Buscar precios, Listas de monitoreo, avisos de precio y la búsqueda de precios de Don Tino. | sí | sí | |
| `redexpres.view` | Ver y completar la Planilla de pedidos de Redexpres. | sí | | puede |
| `redexpres.manage` | Administrar Redexpres: abrir meses, asignar locales, desconfirmar pedidos; también abre "Mi pedido". | sí | | |
| `facturacion.view` | Finanzas (presupuesto y canjes). | sí | | puede |
| `facturacion.upload` | Subir facturas, revisar lo que leyó DogTi y confirmar o descartar. | sí | | |
| `facturacion.manage` | Cuentas de Finanzas. | sí | | |
| `rrss.view` | Validación de RRSS y su historial (solo en Tienda Inglesa). | sí | | puede |
| `rrss.validate` | Validar placas de redes contra el mailing (CatTi) y borrar las propias. | sí | | |
| `calendario.view` | Calendario, Mis tareas, el Tablero y sus avisos; las herramientas de calendario de Don Tino. Es lo único que puede tener una externa. | sí | sí | puede |
| `calendario.edit` | Crear, editar y borrar acciones y banners, mover el estado de las piezas, configurar avisos; Colocación. | sí | sí | |
| `calendario.pedidos` | Crear tareas y pedir piezas a la agencia; el dictado del pedido. | sí | sí | |
| `calendario.retail_media` | Mover las posiciones del header reservadas para Retail Media. | sí | | |
| `calendario.tareas` | Liderar tareas: crear, asignar, borrar, plantillas, aprobar entregas como respaldo; le llegan los avisos de entregas. | sí | | |
| `ai.don_tino` | El chat de Don Tino (`/home`). Es el único permiso de los locales. | sí | sí | |
| `ai.dona_tina` | Doña Tina: consultas y reportes de precios con IA. | sí | sí | |
| `ai.tinin` | Tinín: descripciones con IA en el Convertidor. | sí | sí | |
| `ai.triada` | La Triada / Análisis IA (`/analytics`) y el resumen de debates de Don Tino. | sí | sí | |
| `ai.dogti` | DogTi: lectura de facturas y chat del presupuesto en Finanzas. | sí | | |

Notas:
- El rol **Usuario** trae 18 permisos y **no** trae `calendario.tareas`, `calendario.retail_media`, Redexpres, Finanzas, RRSS ni DogTi.
- **Viewer** arranca vacío y solo acepta permisos que terminan en `.view` (incluido `platform.users.view`). Ojo: con `analytics.view` igual puede sincronizar.
- En producción los roles existentes recibieron los permisos nuevos por migraciones (por ejemplo, Finanzas y RRSS solo a Superadmin y Admin). En una base nueva los roles salen tal cual `DEFAULT_ROLES` (los siembra el servidor al arrancar).

### 3.3 Los roles

| Rol | Arranca con | Notas |
|---|---|---|
| Superadmin | los 32 | De sistema. "No asignable desde el panel". El que de verdad manda es la marca `is_superuser`. |
| Admin | los 32 | De sistema. Se pueden destildar por persona. No puede modificar a otro Admin ni al superadmin, ni sus propios permisos. |
| Usuario | 18 (cenefas, medios, precios, calendario view, edit y pedidos, IA menos DogTi) | De sistema. |
| Viewer | ninguno | De sistema. Solo puede tener permisos `.view`. |
| Roles nuevos | lo que se elija | Los crea quien tiene `platform.users.manage`, con permisos que él mismo tenga. |

Los roles de sistema no se borran ni se renombran. Sus permisos solo los cambia el superadmin.

### 3.4 Qué ve cada tipo de cuenta

| | Superadmin | Interna común (rol Usuario, 1 mundo) | Externa (agencia) | Local (Redexpres) |
|---|---|---|---|---|
| Entra a | `/mundos` → `/calendario` | `/calendario` | `/entregas` | `/home` |
| Mundos | los 5 | Tienda Inglesa | Tienda Inglesa (o los que le den) | Redexpres |
| Calendario | sí, todo | sí, todo | solo si le dan alcance; recortado y solo sus tareas | no |
| Mis tareas | sí | sí | no | no |
| Tablero | sí ("Tablero") | sí | "Mi tablero", solo lo suyo y lo de su agencia | no |
| Colocación | si el mundo tiene locales | si el mundo tiene locales (tiene `calendario.edit`) | no | no |
| Fotos para subir | solo si tuviera un local | no | no | sí |
| Cenefas, Convertidor | sí | sí | no | no |
| Diccionario | sí (Tienda Inglesa) | sí (Tienda Inglesa) | no | no |
| Validación de RRSS | sí (Tienda Inglesa) | no | no | no |
| Medios (Dashboard, GA4, Campañas, Análisis IA) | sí | sí | no | no |
| Conexiones | sí, y puede agregar | la ve; "Nueva conexión" aparece pero falla | no | no |
| Planilla de Redexpres | sí (en Redexpres) | no | no | no |
| Mi pedido | sí, con selector de local | no | no | sí, su local |
| Finanzas y Cuentas | sí | no | no | no |
| Precios y Listas | sí (Tienda Inglesa) | sí | no | no |
| Administrador | sí | no | no | no |
| Don Tino | sí, con todas las herramientas | sí (precios, cenefas, Triada, calendario) | no (403 en el servidor) | sí, sin herramientas |
| Guía de uso | sí | sí, con la sección de roles | no (la manda al tablero) | sí |
| Mi perfil | sí | sí | sí | sí (el cambio de contraseña falla) |
| Campanita | sí | sí | sí, sus avisos | sí (fotos) |
| Barra de abajo | Calendario, Mis tareas, Tablero | ídem | Mi tablero (+ Calendario) | Fotos, Mi pedido |

### 3.5 Rarezas para mirar
- Tres permisos no hacen lo que dice su nombre: `analytics.export` (nada), `platform.users.view` (solo una sección de la guía) y `platform.super` (solo protege la cuenta).
- `analytics.view` habilita una acción que escribe (sincronizar).
- Don Tino decide sus herramientas mirando la lista de permisos a mano (`_puede_usar_tool` en `chat.py`), no con el freno de externas. Hoy no importa: una externa no llega a `/chat`.
- El panel mira `platform.admin` y `platform.users.manage` también a mano (sin el freno de externas). Tampoco importa hoy: el freno general de rutas ya corta a las externas.

---

## 4. El sistema visual

### 4.1 Colores
- **Azul de la marca (`brand`)**: es el **índigo** de Tailwind: 500 `#6366f1`, 600 `#4f46e5`, 700 `#4338ca` (`frontend/tailwind.config.ts`). Botones, activos, links y foco.
- **Navy:** 800 `#0f1629`, 900 `#080d1a`, el fondo del menú y de la barra en modo oscuro y el panel del login.
- **Plataformas:** Meta `#1877F2`, Google `#4285F4`, TikTok `#FF0050`, DV360 `#34A853`, SFMC `#00A1E0` (y GA4 `#FF9900` en el dashboard).
- **Mundos:** Tienda Inglesa `#2563eb`, Express `#059669`, Redexpres `#dc2626`, Viajes `#0891b2`, Farma `#7c3aed`.
- **Logo:** azul `#0047BA` y rojo `#F6323E`.
- **Grises:** slate. Fondo `slate-50` / `slate-950`, superficies `white` / `slate-900`.
- **Estados:** verde emerald (bien), rojo red/rose (error, número de avisos), ámbar (atención, entregas), celeste sky (información, el aviso de alcance).
- Inconsistencia: **tres azules distintos**. La marca de la plataforma es índigo, el mundo Tienda Inglesa es otro azul y la margarita es un tercero. Ninguno de los de la interfaz es el azul del logo.

### 4.2 Modo oscuro
- Por clase (`darkMode: "class"`), con `color-scheme` para que los controles del sistema (fecha, select) también se oscurezcan.
- El núcleo (menú, calendario, campanita, mundos) está cuidado en los dos modos.
- **Sin modo oscuro o a medias:** Olvidé mi contraseña, Nueva contraseña, "Algo salió mal", el cartel de la contraseña temporal del panel, las cocardas de rol (panel y perfil), el borde blanco del puntito verde de Don Tino, el ícono del vacío de Conexiones.

### 4.3 Tipografía
- **Inter**, cargada **dos veces**: con `next/font` en `frontend/app/layout.tsx` y con un `@import` de Google Fonts en `globals.css`. Además se cargan Libre Franklin, Archivo, Anton y Carlito, que son de las plantillas de cenefas, no de la interfaz.
- Tamaños: títulos de página `text-2xl font-bold` (clase `.page-header`, pero muchas pantallas lo escriben a mano, a veces `text-xl sm:text-2xl`), subtítulos `text-sm slate-500`, títulos de sección `text-base font-semibold`.
- Mucho texto chico: `text-xs` 822 veces, `text-[11px]` 200, `text-[10px]` 193, **`text-[9px]` 26** (cocardas del panel, precios, editor de cenefas, la ficha de la acción). Choca con la regla "ojos cansados".
- Regla del núcleo: los campos con letra de **16 px en el celular** para que el iPhone no agrande la página.

### 4.4 Espacios, radios y sombras
- Contenido: `p-3` en el celular, `sm:p-5`, `lg:p-6`. Abajo se deja lugar (`pb-24`) para la barra del celular.
- Radios: `rounded-2xl` lo que contiene (tarjetas, ventanas), `rounded-xl` los controles, `rounded-full` las pastillas.
- Alto de control del núcleo: 40 px en la notebook, 44 px en el celular.
- Sombras, "tres escalones y nada más": `shadow-card` (apoyado), `shadow-pop` (menús, campanita), `shadow-panel` (lo que tapa la pantalla). Hay dos más en la configuración (`glow`, `brand`) y varias pantallas usan `shadow-xl` de Tailwind (ventanas del panel, La Triada), que no es ninguno de los tres.
- Animaciones con una sola curva (`ease-suave`) y respetando "menos movimiento" del sistema, salvo el circulito de carga, que sigue girando (a propósito).

### 4.5 Componentes base (`frontend/app/globals.css`)

| Pieza | Cómo es | Dónde |
|---|---|---|
| `.btn-primary` | Degradé índigo 500→600, texto blanco, `text-sm font-semibold`, `py-2.5` (~40 px), `rounded-xl`, se achica al tocar | 58 usos: login, contraseñas, panel, conexiones, finanzas |
| Botón principal del núcleo | **Plano** `bg-brand-600`, `min-h-[44px]` (40 en la notebook), `rounded-xl`, `px-4`/`px-5` | Escrito a mano en el calendario, las tareas y las entregas |
| `.btn-secondary` | Blanco con borde slate-200 y sombra | 78 usos |
| `.btn-ghost` | Sin fondo, gris | 10 usos |
| `.boton-icono` | Cuadrado de 44 px (36 en la notebook), ícono gris | Menú, barras |
| `.input` | 14 px siempre, borde slate-200, `rounded-xl` | Pantallas viejas: login, perfil, panel, conexiones, finanzas |
| `.campo` | 16 px en el celular (14 en la notebook), alto 44/40, borde slate-300 | Núcleo |
| `.etiqueta-campo` | `text-xs font-semibold slate-600` | Núcleo |
| `.card` / `.card-hover` | Blanco, `rounded-2xl`, borde slate-200, `shadow-card` | 134 usos |
| `.segmentado` / `.segmento` | Control de opciones (Calendario / Lista), la elegida en blanco | Núcleo y alta del panel |
| `.badge-*` | Pastillas verde, roja, ámbar, azul y gris, `text-xs` | Conexiones, medios |
| Cocardas de rol | Pastillas `text-[9px]`/`[10px]` en mayúscula, sin modo oscuro | Panel, perfil |
| Tablas `.table-th/td/tr` | Encabezado en mayúscula `text-xs`, filas con borde `slate-50` (casi invisible) | Medios, auditoría |
| `.velo` + `.hoja-abierta/cerrada` | Velo oscuro con desenfoque; panel que entra deslizándose y se esconde del teclado al cerrarse | Ficha del calendario, menú del celular |
| Ventanas viejas | `fixed inset-0 bg-black/40 backdrop-blur-sm` con caja `rounded-2xl shadow-xl` | Panel, convertidor, precios, finanzas (24 lugares) |
| Avisos (toasts) | Sonner, arriba a la derecha, colores fuertes, siguen el tema elegido y se ven en pantalla completa | Toda la plataforma (191 `toast.error`) |
| Circulito de carga | `Loader2` girando, gris `slate-400` | 165 usos |
| Esqueleto | `.skeleton`, gris con brillo que pasa | 53 usos (núcleo, campanita, mundos, medios) |
| Pantalla de carga | Cuadrado índigo con el calendario y un trazo que recorre el borde | Al entrar |

### 4.6 Vacío, cargando y error
- **Cargando:** el núcleo usa esqueletos con la forma de lo que viene. Las pantallas viejas, un circulito centrado (perfil, guía, panel). Conexiones no muestra nada (enseña el vacío mientras carga).
- **Vacío:** el modelo bueno es un ícono en un cuadrado o círculo suave más una frase que dice qué hacer (campanita: "Todavía no tenés notificaciones"; conexiones: "Agregá tu primera plataforma..."). Otros son solo un texto gris chico (panel: "Todavía no hay ninguna en esta lista.").
- **Error:** casi siempre un aviso rojo (`toast.error`) con el texto del servidor si lo hay. Los datos mal formados (422) se pasan a una frase en `frontend/lib/api.ts` para no romper la pantalla. Si la pantalla se rompe: "Algo salió mal" con el mensaje técnico.
- **Sin permiso / otro mundo:** pantalla entera con candado o globo y una salida (bien resuelto, `SinAcceso` y `FueraDeMundo`).

### 4.7 Textos
- Castellano rioplatense con "vos": "Ingresá", "Probá de nuevo", "Pedíselo a quien administra Core Tienda". Las pantallas nuevas explican en frases completas y con el porqué.
- Jerga o inglés que queda: "Dashboard", "Sync datos", "Auto-sync", ROAS, CTR, CPM, "Page views", "checkout", "Revenue", "Engagement rate", "Account ID", "Access Token", "advertising", "Powered by Claude Sonnet 5", "tokens", "Marketing Intelligence Platform", "Token inválido o expirado", "Viewer", "SUPER ADMIN", "INACTIVO", "Top usuarios", "Costo por feature", las claves de permisos y de auditoría en letra de código, y los estados de la guía ("done", "running", "pending").
- "Bienvenido" en masculino en el login.

### 4.8 El logo
- La margarita completa de 7 pétalos (`frontend/app/icon.svg`, la cuida `backend/tests/test_logo_margarita.py`) **solo está como ícono de la pestaña del navegador**.
- Adentro de la plataforma no aparece. La "marca" que se ve es otra según dónde:
  - un cuadrado índigo con un **ícono de calendario** (menú, barra del celular, selector de mundo, pantalla de carga);
  - un **ícono de gráfico de barras** (login en la notebook, olvidé y nueva contraseña);
  - el **robot de Don Tino** (login en el celular).
- No es la margarita de 5 pétalos (eso estaría prohibido), pero tampoco es la margarita. Para el agente de diseño: no proponer otro logo; si algo se propone, es usar la margarita completa que ya existe.

### 4.9 Inconsistencias que se ven
1. **Dos botones principales:** el `.btn-primary` en degradé y ~40 px (pantallas viejas) contra el plano de 44 px del núcleo. Hay un tercero en el panel ("Nuevo usuario": plano, `py-2`, `font-medium`). Y en Conexiones el botón de **borrar** usa el principal azul en vez de uno rojo.
2. **Dos campos:** `.input` (14 px, el iPhone agranda la página) en login, perfil, panel, conexiones y finanzas, contra `.campo` (16 px) en el núcleo.
3. **Dos grises de borde:** `.card` e `.input` con slate-200, cuando el propio CSS dice que slate-200 "no se distinguía" y el núcleo pasó a slate-300.
4. **Dos ventanas:** la hoja con velo del núcleo contra la caja con `bg-black/40` y `shadow-xl` de las pantallas viejas. Algunas no cierran con Escape.
5. **Confirmaciones:** la ventanita del navegador (`confirm()`, 12 lugares, sobre todo el panel) contra la confirmación en la misma fila (Finanzas, conexiones, la pregunta del pase de agencia).
6. **Contraste:** las pantallas viejas usan `text-slate-400` para texto que importa (mails y último ingreso en el panel: 33 veces; dashboard: 17), que en modo claro no llega a un contraste cómodo. El núcleo (menú, calendario) no lo usa.
7. **Tres marcas** distintas (calendario, gráfico de barras, robot) y la margarita ausente.
8. **Títulos:** clase `.page-header` contra tamaños escritos a mano. Nombres que cambian para lo mismo ("Análisis IA" / "La Triada" / "El análisis con IA"; "Conexiones" en `/settings`; "Finanzas" en `/facturacion`; dos "Dashboard" en el menú).
9. **Tamaños táctiles:** el núcleo respeta 44 px. El panel de admin, conexiones y algunas listas tienen botones de ícono de unos 27 a 32 px.

---

## 5. Los puntos a mirar más importantes (para elegir qué probar primero)

1. **Conexiones dice "Contraseña incorrecta" a quien no tiene permiso.** Quien tiene `connections.view` sin `manage` (el rol Usuario) ve "Nueva conexión" y el tacho, y el 403 se le muestra como contraseña mal. Probar con una cuenta de rol Usuario.
2. **El bloqueo del login se vuelve a disparar con un solo error** después de los primeros 15 minutos (el contador no vuelve a cero), y **el mail distingue mayúsculas y espacios**. Probar con una cuenta descartable.
3. **El superadmin se puede desactivar a sí mismo** desde su propia fila del panel (el servidor no lo frena). Desde el panel no se puede crear otro superadmin para probarlo: confirmarlo en el código (`toggle_active` en `admin.py`), o probarlo al final de la noche sabiendo que Equipo nocturno vuelve a estar activa recién cuando se reinicia el servidor. Relacionado: cambiar el rol en el desplegable pisa los permisos afinados sin avisar.
4. **Los locales y la gente sin calendario quedan mal ubicados:** el local entra al chat de Don Tino en vez de a "Fotos" o "Mi pedido"; en Mi perfil le aparece un cambio de contraseña que siempre falla; y quien no tiene barra de abajo no tiene campanita en el celular.
5. **Lo que explica la plataforma está desactualizado:** la Guía de uso no menciona calendario, tareas, tablero, mundos ni agencias; Don Tino se cree "MKTG Platform" con 19 permisos y sugiere preguntas de Google Ads y ROAS; el login vende medios, precios y cenefas.
6. **Dos sistemas visuales conviviendo:** las pantallas viejas (login, contraseñas, panel, perfil, conexiones, medios, finanzas) con botón en degradé, campos de 14 px, bordes y textos de bajo contraste, ventanas viejas y sin modo oscuro en algunas; el núcleo con el criterio nuevo. Más los permisos que no hacen nada (`analytics.export`, `platform.users.view`, `platform.super`) y sincronizar con un permiso "de ver".

# Seguridad en el código

En Core Tienda trabajan unas 50 personas de Tienda Inglesa y 4 agencias
externas. Lo que más importa: que nadie vea ni toque lo que no le corresponde
(las promos antes de salir, lo de otra agencia, las notas internas, el
análisis de la IA). Es el primer lugar del OWASP Top 10 2021 (A01, control de
acceso roto) y del OWASP API Security Top 10 2023 (API1, BOLA).

## Control de acceso

- **Del lado del servidor, siempre.** Esconder un botón es comodidad, no
  seguridad: cualquiera con su token puede hacer el pedido a mano.
- **Denegar por defecto** (OWASP, *Authorization Cheat Sheet*).
  `get_current_user` ya frena a las cuentas externas fuera de
  `RUTAS_DE_EXTERNOS`; una ruta nueva bajo `/calendario/` les llega, así que
  se filtra adentro.
- **Nivel función** (API5, BFLA): `require_permission(...)` en cada ruta.
- **Nivel objeto** (API1, BOLA o IDOR, CWE-639): cada id que llega en la URL
  o en el cuerpo se carga **y** se chequea que sea de quien pide
  (`_tarea_y_barra`, `es_tarea_propia`, el alcance). Para una agencia, lo
  ajeno contesta **404 igual que lo que no existe**: así no puede ni adivinar
  qué ids hay. Los ids al azar (`ad-` + `secrets.token_hex(8)`) ayudan, pero
  no reemplazan el chequeo.
- **Ids indirectos:** `bajar_adjunto` busca la tarea del adjunto y chequea
  la tarea. Un id que viaja en el cuerpo (un aprobador, un responsable)
  también se chequea.
- **Nivel propiedad** (API3): devolvé solo los campos que esa persona puede
  ver (la agencia ve nombres sin mail, y nada de notas internas ni del
  análisis de la IA), y aceptá solo los que puede escribir.
- **Prueba obligatoria del "no":** la otra agencia (404), sin permiso (403),
  y la agencia de la pieza (ve, pero no adjunta).

## Validar en el servidor

- La validación del navegador es para avisar rápido (`problemaConArchivo`);
  la que cuenta es la del servidor (`reglas.validar`).
- **Topes en todo lo que entra** (API4, consumo de recursos sin límite):
  largo de textos, cantidad de elementos, peso de cada archivo, archivos por
  tarea, espacio total.
- **Lista blanca, no lista negra:** extensiones permitidas **y** contenido
  que coincide (`TIPOS`, con la firma de cada formato); links solo `http` o
  `https` (`link_valido`).

## Inyección (A03)

- SQLAlchemy arma las consultas con parámetros: usalo. Nunca f-strings ni
  `+` con datos en un `text()`: `sa.text("... WHERE id = :id")` y `{"id": valor}`.
- Columnas u orden que pide la pantalla se mapean contra una lista
  permitida; nunca se pegan en el SQL.
- Nombres de archivo: `nombre_limpio` saca carpetas y caracteres de control
  (path traversal); el `Content-Disposition` se arma con `_adjunto(nombre)`.
- Lo que la gente le escribe a la IA (Don Tino, la revisión) es dato, no
  instrucción, y las herramientas de la IA no pueden más que la persona que
  pregunta (las de Don Tino respetan permisos y alcance): no rompas eso.

## XSS

- React escapa todo lo que pintás con `{}`. La CSP de `next.config.mjs`
  permite scripts inline porque Next los necesita, y explica que el riesgo
  queda cerrado porque no hay ningún `dangerouslySetInnerHTML`: no agregues
  uno. Para markdown, como `RespuestaDelBot.tsx`: `skipHtml` y una lista de
  elementos permitidos.
- **Links que escribe la gente:** `javascript:...` en un `href` se ejecuta al
  tocarlo. El esquema se valida en el servidor (`link_valido` en
  `services/entregas.py`, de la auditoría del 15/11/2026).
- **Archivos que se bajan:** `Content-Disposition: attachment`,
  `X-Content-Type-Options: nosniff` (que el navegador no adivine que es HTML)
  y `Cache-Control: private, no-store` (ver `bajar_adjunto`).

## CSRF

La cookie de sesión viaja sola en un pedido armado por otro sitio (es
`SameSite=None`: la web y la API están en dominios distintos). Por eso
`get_current_user` exige el header `Authorization` en POST, PUT, PATCH y
DELETE: otro sitio no lo puede leer ni poner. Para vos: un GET nunca escribe;
un `fetch()` crudo agrega `authHeader()` a mano; y un 401 no se «arregla»
aceptando la cookie en un método que escribe.

## Secretos: el repo es público

- Ni claves, ni tokens, ni contraseñas, ni mails reales, ni URLs con
  credenciales en el código, las pruebas, los commits, el PR, el informe, las
  capturas o el cuaderno (también es público).
  Las claves viven en las variables de Render y Vercel; en la nube de la
  noche no hay claves: no las busques ni las pidas.
- `NEXT_PUBLIC_*` es público por definición.
- Datos de prueba con dominios reservados (RFC 2606): `example.com`, `.test`,
  `.invalid`, como `@prueba-tablero.test`. Las contraseñas de prueba se
  generan cada noche (README del equipo).
- Antes de cada commit, mirá lo que va (el `postgres:postgres@127.0.0.1` del
  README es de mentira; lo demás que salte, se saca):

```bash
git diff --cached | grep -nE 'sk-[A-Za-z0-9_-]{20,}|re_[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{20,}\.|://[^ :/@]+:[^ @/]+@|BEGIN [A-Z ]*PRIVATE KEY'
```

- Si algo se coló, sacalo del commit antes del push y avisale al coordinador.
  Los valores falsos del CI (`ci-dummy-secret-not-used-in-prod`, el
  `ENCRYPTION_KEY` de ejemplo) son públicos a propósito.

## Datos confidenciales

- Lo confidencial acá: precios y promociones antes de salir, los datos de
  Clientes VIP, lo de cada agencia, las notas internas y el análisis de la IA
  de las entregas (solo para Tienda), las fotos de los locales.
- **Logs:** qué pasó y con qué id, nunca el contenido (ni el archivo, ni el
  token, ni la contraseña, ni el mail). El `logger.error` de `adjuntar` dice
  cuánto ocupa, no qué hay.
- **Mensajes de error:** los tuyos, para la persona (`ValueError` propio →
  422 con qué hacer). Lo inesperado se loguea con `exc_info=True` y a la
  persona le llega algo genérico: `detail=f"...{e}"` con una excepción
  cualquiera puede mostrar rutas, SQL o datos (CWE-209). Hay rutas viejas que
  lo hacen (`cenefas_convertidor.py`); en lo nuevo, no.
- **Login y recuperación:** el mismo mensaje exista o no la cuenta
  (`_CREDENCIALES_INVALIDAS`); en la base va el hash del link de
  recuperación, no el link.

## Abuso, disponibilidad y dependencias

- `@limiter.limit(...)` en lo caro (subidas, IA, login).
- Leer con tope: `await archivo.read(MAX + 1)` dice que se pasó sin leer 2 GB.
- Topes de espacio (`entra`, `hay_lugar`, `BASE_TOPE_MB`): si no entra, no se
  guarda y se avisa. Nunca se borra nada solo: las imágenes de las entregas
  no se borran nunca.
- Cada dependencia nueva es código de terceros corriendo con tus permisos
  (OWASP A06; Dan McKinley, «Choose Boring Technology»): solo si no hay otra,
  liviana, mantenida, con versión fijada y dicha en el plan.

## Cinco preguntas para tu diff

1. ¿Qué entra de la persona y dónde se valida en el servidor?
2. ¿Cada id que entra se chequea contra quien pide? ¿Lo de otra agencia da 404?
3. ¿Qué devuelve la respuesta, y lo puede ver cualquiera que llega a esa ruta
   (la agencia incluida)?
4. ¿Qué queda en logs, errores, commits y capturas?
5. ¿Qué pasa si lo llaman mil veces seguidas o con un archivo de 1 GB?

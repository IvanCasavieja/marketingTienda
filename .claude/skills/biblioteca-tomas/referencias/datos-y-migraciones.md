# Datos: modelo, migraciones, índices y concurrencia

## Modelado relacional

- **Cada hecho en un solo lugar** (el modelo relacional de E. F. Codd, IBM,
  1970). Desnormalizar se acepta con tres condiciones, como el resumen de
  `calendario_entregas` (en qué fase va, a quién le toca): una lectura
  frecuente lo pide, una sola función lo recalcula, y se recalcula en la misma
  transacción que el cambio.
- **La base es la última defensa**: si una regla importa (seguridad, unicidad,
  que nada quede huérfano), va también como NOT NULL, FK, UNIQUE o CHECK.
  `ck_users_externo_no_es_superadmin` (0069) frena a un externo superadmin
  aunque un camino futuro se olvide del flag.
- **JSON en una columna** solo para lo que se lee y escribe en bloque; lo que se
  filtra, se cruza o se suma va en columnas.
- **Retirar en vez de borrar** cuando hace falta historia (`activo=False` en
  `agente_memoria`); a cambio, cada consulta filtra y la fila ocupa.
- **Fechas**: `DateTime(timezone=True)` y el «hoy» de Uruguay
  (`alcance.hoy_en_uruguay()`): el servidor no está en hora de Montevideo.
- **Tabla nueva, cuenta de espacio**: bytes por fila × filas por mes × tiempo
  guardado, como `_BYTES_POR_FILA` en `routes/clientes_vip.py`.

## Los 500 MB

- `pg_database_size` cuenta tablas, índices y TOAST, igual que la cuota
  (`app/services/espacio.py`). Cada índice también ocupa.
- **Borrar no achica la base al instante**: VACUUM vuelve reutilizables las
  filas muertas, pero el archivo no se devuelve sin VACUUM FULL, que bloquea la
  tabla (nunca sin OK). Quitar una columna no libera su lugar hasta reescribir.
- Las imágenes se comprimen en el navegador (1600 px, JPEG 0,75 y miniatura de
  320 px: 46 KB una gráfica plana y 247 KB una foto, según `models/entregas.py`)
  y sus bytes van `deferred`, para que listar no los traiga.
- **Desde el 19/11/2026 las imágenes de entregas no se borran**: lo guardado
  crece todos los meses. El docstring de `models/entregas.py` todavía dice que
  no crece porque «todo vence»; es de antes. Su estimación de uso normal: unos
  18 MB por mes. Margen en meses = (tope − tamaño actual) ÷ crecimiento por mes,
  con el tamaño de `tamano_de_la_base`.
- Dentro de las reglas (ni purgas de entregas ni planes pagos) queda:
  comprimir mejor, no duplicar, calcular lo derivado en vez de guardarlo, topes
  propios (`ZIP_TOPE_MB`, `ADJUNTOS_TOPE_MB`) y SharePoint más adelante.

## Migraciones sin bloquear

Por qué acá importa más: las migraciones corren al arrancar el servidor nuevo,
en segundo plano (`_run_migrations` en `app/main.py`), mientras atiende el viejo
o el nuevo (`/health` da 200 con `corriendo`). Si una espera un bloqueo sobre
`users` o `calendario_barras`, todo queda esperando detrás. Si falla, Postgres
deshace todo (DDL transaccional, salvo un `autocommit_block`) y `/health` da
503: si Render no había dado por bueno el deploy, sigue el anterior; si ya lo
había dado, queda el código nuevo con la base sin migrar hasta el próximo
arranque. Por eso viejo con base nueva y nuevo con base vieja tienen que andar:
**expandir y contraer** (*Refactoring Databases*, Ambler y Sadalage).

Los bloqueos (documentación de PostgreSQL, *Explicit Locking*):

- **ACCESS EXCLUSIVE**: casi todo ALTER TABLE, DROP, TRUNCATE, VACUUM FULL.
  Frena hasta los SELECT.
- **SHARE**: CREATE INDEX común. Deja leer, frena las escrituras.
- **SHARE UPDATE EXCLUSIVE**: CREATE INDEX CONCURRENTLY, VALIDATE CONSTRAINT,
  VACUUM. No frena ni lecturas ni escrituras.
- **La fila de espera**: un ALTER que espera su bloqueo frena a todos los que
  llegan después, aunque sean SELECT. En tablas con uso, empezá la migración con
  `op.execute("SET LOCAL lock_timeout = '5s'")`: si no consigue el bloqueo,
  falla y se reintenta, en vez de colgar a todos. Hoy ninguna migración lo usa.

| Operación (Postgres 12 o más) | Qué pasa | Cómo hacerla |
|---|---|---|
| Columna nueva que acepta nulo | Solo metadatos | Directo |
| Columna nueva con default constante | Desde la 11 no reescribe | Con `server_default` (la 0069 lo hace). Un default volátil (aleatorio, `clock_timestamp()`) sí reescribe |
| Volver NOT NULL una columna | Recorre la tabla con ACCESS EXCLUSIVE | CHECK (col IS NOT NULL) NOT VALID → VALIDATE → SET NOT NULL (no recorre si el CHECK lo prueba) → quitar el CHECK |
| FK o CHECK nuevos | Recorre la tabla bloqueada | `NOT VALID` y después `VALIDATE CONSTRAINT`, en pasos separados |
| Índice en tabla con escrituras | El común frena las escrituras | `postgresql_concurrently=True` en `autocommit_block()` (la 0027). Si falla deja un índice INVALID: borrar y repetir |
| Renombrar columna o tabla | Instantáneo, rompe el código viejo | Columna nueva, escribir en las dos, leer la nueva, borrar la vieja en otro PR. O no renombrar |
| Cambiar el tipo | Casi siempre reescribe | Columna nueva + copiar + cambiar el código + borrar la vieja |
| Borrar una columna | El código viejo la sigue pidiendo | Sacarla del modelo y publicar; borrarla después. SQLAlchemy pide todas las columnas mapeadas: si falta una, ese modelo da 500 |
| Llenar muchas filas | Transacción larga, filas bloqueadas | En tandas, idempotente, con una función pura probada (como `aplanar`, 0090) |
| Datos irreversible | No hay vuelta | Decirlo en el docstring (la 0090 lo dice), probar la función y decir cómo se recupera; si no hay forma, OK explícito de Ivan |

- **El número**: el siguiente al más alto de `main` que no use una rama
  abierta (`CLAUDE.md`). Mirá `git ls-tree --name-only origin/main
  backend/migrations/versions/` y lo mismo en cada rama de `git branch -r`. Los
  huecos de la secuencia (de la 0087 se pasa a la 0089) no se rellenan.
- **Autogenerate propone, no decide**: la migración se revisa a mano.
- **El CI migra una base vacía**, no una con datos: una migración de datos trae
  su prueba. Si es reversible, Ramiro corre `alembic downgrade -1 && alembic
  upgrade head` en la base de pruebas.

## Índices

- Indexá lo que filtrás, cruzás y ordenás, en el orden de la consulta: primero
  las columnas por igualdad, después la de rango u orden (Markus Winand). La
  0039 hace `(user_id, action)` porque la consulta filtra por las dos.
- **Postgres no indexa solo las FK** del lado que referencia: si se cruza o hay
  `ON DELETE CASCADE`, sin índice borrar un padre recorre la tabla hija entera.
- Parciales para el subconjunto de siempre (`WHERE activo`); únicos parciales
  para unicidad con condición. Nada «por las dudas»: cada índice ocupa lugar y
  cuesta en cada escritura.
- Se comprueba con `EXPLAIN (ANALYZE, BUFFERS)` en la base de pruebas con un
  volumen parecido al real; con una tabla chica Postgres la recorre igual.

## N+1 y consultas caras

- **El síntoma**: un `for` con `await db.execute(...)` o `await db.get(...)`
  adentro. Con SQLAlchemy async la carga perezosa implícita tira error, así que
  el N+1 queda a la vista en el diff.
- **El patrón de la casa** (`_armar_datos` en `routes/calendario.py`): una
  consulta por tipo de hijo con `IN (select ...)` y agrupar en un dict; o
  `selectinload` (`routes/auth.py`). Columnas pesadas, `deferred`.
- **El camino de cada pedido es sagrado**: `get_current_user` resuelve usuario
  y sucursal en un viaje, y cada calendario abierto pregunta por la revisión
  cada 15 s. Lo que se sume ahí se multiplica.
- **Para el diff**: ¿consultas en bucle? ¿`.all()` sin tope en una tabla que
  crece? ¿todo traído y filtrado en Python? ¿bytes para listar? ¿un `count(*)`
  grande en cada pedido?

## Transacciones y concurrencia

- **Una sesión por pedido**: `get_db` confirma al final y deshace si hay error.
- **Lo de afuera, después del commit**: mails, avisos, IA, HTTP, nunca con filas
  bloqueadas; y si fallan, el cambio igual quedó (`_avisar_sin_romper`).
- **Postgres trabaja en READ COMMITTED.** Pegan la actualización perdida (dos
  pedidos leen, cambian y escriben) y el *write skew* (Martin Kleppmann,
  *Designing Data-Intensive Applications*, cap. 7). Herramientas, de la más
  simple a la más pesada:
  1. UPDATE atómico (`SET n = n + 1`), sin leer antes.
  2. Restricción única con `INSERT ... ON CONFLICT` (la revisión usa
     `on_conflict_do_update`).
  3. `with_for_update()` (usado en `calendario.py` y `admin.py`): transacción
     corta y siempre en el mismo orden, para no trabarse entre dos.
  4. Versión en la fila y 409 o 412 si cambió (control optimista).
  5. SERIALIZABLE con reintentos: último recurso.
- **La revisión del calendario** sube en la misma transacción que la escritura:
  un camino nuevo que no la sube es un bug aunque las pruebas pasen.
- **Transacciones cortas**: el pool (15 + 20 de desborde, `database.py`) lo
  comparten los pedidos y los loops. Esperar a Claude o a Resend con una
  transacción abierta es tener una conexión tomada sin hacer nada.

## Supabase gratis

- Si `DATABASE_URL` va al pooler en modo transacción (puerto 6543) no hay
  sentencias preparadas: por eso `statement_cache_size=0`, que no se saca.
  Tampoco vive nada de la sesión entre pedidos: `SET` sin `LOCAL`,
  `LISTEN/NOTIFY`, bloqueos consultivos de sesión, tablas temporales.
- El límite de conexiones y los respaldos dependen del plan vigente: se
  verifican antes de sumar un proceso o de una migración irreversible.

## Fuentes

- E. F. Codd, «A Relational Model of Data for Large Shared Data Banks», *CACM* (1970).
- Scott Ambler y Pramod Sadalage, *Refactoring Databases: Evolutionary Database Design* (2006).
- Documentación de PostgreSQL: *Explicit Locking*, `ALTER TABLE`, `CREATE INDEX`, *Transaction Isolation*, *Routine Vacuuming*.
- Markus Winand, *SQL Performance Explained* y Use The Index, Luke.
- Martin Kleppmann, *Designing Data-Intensive Applications* (2017).
- Documentación de SQLAlchemy 2.0: extensión asyncio y carga de relaciones.

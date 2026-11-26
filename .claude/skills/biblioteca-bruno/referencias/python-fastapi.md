# Python, FastAPI, SQLAlchemy y Alembic

Python 3.11, FastAPI, SQLAlchemy 2.0 async (asyncpg), Pydantic v2, Alembic y
pytest. Ejemplo de referencia: `backend/app/api/routes/adjuntos.py` y su servicio.

## Tipado

- Firmas tipadas con la sintaxis de hoy: `str | None` (PEP 604), `list[dict]`
  (PEP 585), `Literal[...]` para conjuntos cerrados (`Seccion`). El retorno
  es el contrato: `validar(...) -> tuple[str, str]` se entiende sin el cuerpo.
- Booleanos solo por nombre, con `*`: `puede_adjuntar(uid, creador, *,
  gestiona, pide)`; una llamada `puede_adjuntar(1, 2, True, False)` no se lee.
  (No hay mypy en el CI: que los tipos digan la verdad igual.)

## async/await sin trabar el servidor

En Render gratis hay una sola CPU (comentario en `cenefas_convertidor.py`).
Un `async def` que hace algo pesado sin soltar el loop deja al proceso sin
atender a nadie: ni la pregunta del calendario cada 15 s, ni `/health`.

- **Traban el loop:** CPU (openpyxl, Pillow, pandas, PyMuPDF, bcrypt),
  `requests`, `time.sleep`, archivos grandes, librerías síncronas de red.
- **Lo pesado, a un hilo:** `await asyncio.to_thread(funcion, *args)`, como
  `hash_password_async` (`core/security.py`) o `armar_zip_dividido`
  (`cenefas_convertidor.py`). En código nuevo, `to_thread` y no
  `get_event_loop().run_in_executor(...)` (como en `precios.py`): es más
  corto y le pasa al hilo las variables de contexto.
- **Red:** `httpx.AsyncClient` con `timeout`. **Varias cosas a la vez:**
  `asyncio.gather` o `asyncio.TaskGroup` (3.11; si una falla, cancela las
  demás); techo con `asyncio.timeout()` o `wait_for`.
- **Una sesión por tarea:** la misma `AsyncSession` no se comparte entre
  tareas concurrentes (SQLAlchemy): nada de `gather` con la misma `db`.
- **Para cazar lo que traba:** `PYTHONASYNCIODEBUG=1` avisa de cada paso de más de 100 ms.

## SQLAlchemy 2 async

### La sesión de este repo

- `get_db` (`core/database.py`): una sesión por pedido, commit al final si
  no hubo error, rollback si lo hubo. Igual, las rutas que escriben hacen
  `await db.commit()` antes del `return` (ver `adjuntar`): si guardar falla,
  quien pidió recibe un error y no un «listo» falso.
- `flush()` manda el SQL sin cerrar la transacción (para tener ids o que la
  consulta siguiente vea lo nuevo: `adjuntar` antes de `lista_para`).
- `expire_on_commit=False` (en `AsyncSessionLocal`): después del commit los
  objetos conservan sus valores. Con el valor por defecto, leer un atributo
  después del commit dispara una carga perezosa, que en async revienta con
  `MissingGreenlet`.
- La contracara: lo conservado puede estar viejo. Si una columna la calcula
  la base (`server_default`, `onupdate`, un trigger) y la necesitás después
  de escribir: `await db.refresh(obj, ["columna"])`.

### Traer los datos sin N+1

En async una relación perezosa no se carga sola: explota. Es una ventaja: te
obliga a decir qué traés.

```python
# Mal: una consulta por tarjeta (50 tarjetas, 51 viajes a la base)
for t in tareas:
    persona = (await db.execute(select(User).where(User.id == t.asignado_a_id))).scalar_one_or_none()

# Bien: un viaje para todas, y un diccionario
ids = {t.asignado_a_id for t in tareas if t.asignado_a_id}
personas = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(ids)))).scalars()} if ids else {}
```

- Relación de un objeto: `.options(selectinload(User.role))` (`routes/auth.py`).
- Agregados en la base: `group_by` con `func.count`/`func.max` (los logins
  de todos en una consulta, `admin.py`); «el último de cada uno» con
  `.distinct(col).order_by(col, fecha.desc())`, el `DISTINCT ON` de Postgres
  (`entregas.py`); `func.coalesce(func.sum(...), 0)` para totales.
- Solo las columnas que usás. Los bytes del adjunto son `deferred=True` en
  el modelo: listar no baja los archivos.
- Para verlo: en development el engine tiene `echo=True`. Si los SELECT de
  un pedido crecen con la cantidad de filas, hay N+1.

### Carreras y bloqueos

- «Me fijo cuántos hay y después inserto» tiene una carrera: dos subidas a
  la vez pasaban juntas el tope de 5 adjuntos. El repo bloquea la tarea con
  `with_for_update()` (`_tarea_y_barra(bloquear=True)`) y la segunda espera.
- Siempre el mismo orden de bloqueo (la tarea, después la entrega:
  `_entrega_bloqueada`): dos cambios a la vez esperan en vez de trabarse.
- Lo único lo garantiza la base (índice único + `IntegrityError`), no un `SELECT` previo.

## Pydantic v2: el borde

«Parse, don't validate» (Alexis King): lo que entra se convierte en un
modelo con tipos y topes, y de ahí para adentro se confía.

- **Topes siempre:** `Field(..., min_length=1, max_length=200)`, `ge`/`le`,
  `pattern=_ID`, listas con `max_length`.
- **Reglas reusables:** `Fecha = Annotated[date, AfterValidator(_fecha_razonable)]`.
- **Un campo:** `@field_validator("nombre")` + `@classmethod`; **entre
  campos:** `@model_validator(mode="after")` (`_envio_suelto` en `BarraNueva`).
- **`min_length=1` deja pasar `" "`:** strip en el validador.
- **PATCH, solo lo que vino:** `payload.model_fields_set` o
  `model_dump(exclude_unset=True)`: «no lo mandó» no es «lo mandó vacío».
- **Sin asignación masiva:** `creado_por_id`, `es_externo`, `permissions` o
  `empresa` los pone el servidor; un modelo de entrada por caso de uso.
- Un `ValueError` en un validador es un 422 con tu mensaje; Pydantic le
  antepone «Value error, » y `extractErrorDetail` (`frontend/lib/errors.ts`) lo limpia.
- Si aparece estilo v1: `regex=` → `pattern=`, `.dict()` → `.model_dump()`.

## FastAPI: una ruta como las de la casa

Molde (la nota y sus nombres son inventados; el resto es como `adjuntos.py`):

```python
@router.post("/tareas/{tarea_id}/notas", status_code=201)
@limiter.limit("20/minute")                  # solo si es cara; slowapi exige `request: Request`
async def crear_nota(
    request: Request,
    tarea_id: str,
    payload: NotaNueva,                      # Pydantic con topes
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    tarea = await _tarea_visible(db, tarea_id, current_user, bloquear=True)   # 404 si es de otra agencia
    if not reglas.puede_anotar(current_user.id, tarea.creado_por_id, gestiona=_puede_gestionar_tareas(current_user)):
        raise HTTPException(status_code=403, detail=_QUIEN_ANOTA)             # dice quién sí puede
    db.add(CalendarioNota(id=reglas.nuevo_id(), tarea_id=tarea.id, texto=payload.texto, autor_id=current_user.id))
    await db.flush()
    notas = await lista_para(db, tarea, current_user)
    await db.commit()
    return {"notas": notas, "puedoAnotar": True}
```

- **Las capas del permiso, todas en el servidor:** 1) `require_permission`,
  qué puede hacer (los permisos son de cada persona, `User.permissions`); 2)
  `get_current_user` ya frena a las cuentas externas fuera de sus rutas
  (`ruta_permitida`), pero `/calendario/` les llega, así que adentro se
  filtra; 3) `exigir_mundo`, de qué negocio; 4) el objeto: ¿es de quien
  pide? (`_tarea_y_barra`, `es_tarea_propia`, el alcance).
- **El «puedo» de la respuesta sale de la misma función que el chequeo**
  (`puedoAdjuntar` y `puedoSacar`, de `reglas.puede_adjuntar`): no discrepan.
- **Códigos:** 201 creado · 401 sin sesión · 403 ve la cosa pero no puede
  hacer eso (y el mensaje dice quién sí) · 404 no existe **o es de otra
  agencia** · 409 choca con el estado · 422 datos inválidos · 429 límite ·
  507 sin lugar (convención de `services/espacio.py`; el front no lo reintenta).
- **Mensajes:** constantes arriba del archivo (`_YA_NO_ESTA`, `_LLENO`), en
  castellano y con qué hacer. Lo inesperado, con `logger.error(...,
  exc_info=True)` y un mensaje genérico (ver [seguridad.md](seguridad.md)).
- **El JSON es un contrato** con `frontend/lib/api.ts`: antes de renombrar o
  sacar un campo, `grep -rn "puedoAdjuntar" frontend`. Claves en camelCase.

## Alembic sin sustos

Las migraciones corren solas al arrancar (`_run_alembic` en `app/main.py`):
si una falla, `/health` lo dice y producción queda con una base que no es la
que el código espera.

- **Evitala** si alcanza con algo que ya existe. **Número:** el siguiente al
  más alto de `main` que no use ninguna rama abierta (`git branch -r`); si
  salteás uno, decilo en el docstring (como la 0089 con la 0088). El
  docstring cuenta el pedido, qué hace y si el downgrade es reversible (la
  0090 dice que no, y por qué).
- **Columna nueva en tabla con datos:** `nullable=True` o `server_default`;
  un `NOT NULL` sin default falla con las filas que ya hay.
- **Renombrar o borrar, en dos pasos** («Parallel Change», de Danilo Sato,
  en el sitio de Martin Fowler): primero agregar y usar lo nuevo; lo viejo se
  borra en otro PR. Al desplegar conviven código nuevo y base vieja, o al revés.
- **Migración de datos:** `sa.text(...)` con parámetros, sin importar los
  modelos de la app (cambian, y la migración vieja se rompe); la lógica, en
  funciones puras probadas sin base (la 0090 con `tests/test_una_tarea_un_pedido.py`).
- **Autogenerate es un borrador:** no detecta renombres (los ve como borrar
  y crear, y se pierden datos). Leé el archivo entero.
- **Probala desde cero:** base vacía + `alembic upgrade head`; si es
  reversible, `downgrade -1` y `upgrade head` otra vez. Que ande en tu
  máquina no prueba nada: en development la app hace `create_all` y crea
  sola las tablas nuevas.

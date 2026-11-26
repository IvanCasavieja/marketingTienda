# Pruebas como parte del desarrollo

La prueba no es un trámite para Ramiro: es cómo sabés que terminaste y cómo el
que venga después sabe que no rompió nada. *Software Engineering at Google*
lo llama la regla de Beyoncé: si te importaba, tendrías que haberle puesto
una prueba.

## Qué probar

- **Lo que una persona notaría si se rompe:** permisos, validaciones,
  cálculos, mensajes que dicen qué hacer, el contrato con la pantalla.
- **Comportamientos, no métodos** (SE@Google, cap. 12): una prueba por regla,
  con la regla en el nombre, como
  `test_adjunta_quien_gestiona_o_quien_creo_la_tarea_si_pide_piezas` o
  `test_lo_que_no_es_lo_que_dice_no_pasa`. El nombre es la especificación.
- **Por la puerta pública** (la función pura, la ruta HTTP), no por los
  detalles de adentro: así un refactor no rompe pruebas.
- **El «no» tanto como el «sí»:** la otra agencia (404), sin permiso (403),
  el archivo trucho (422), sin lugar (507), y que no quedó nada guardado.
- **No pruebes el framework** (que Pydantic respete un `max_length`) ni
  repitas la implementación adentro de la prueba.

## TDD, cuando conviene

Kent Beck (*Test-Driven Development: By Example*): rojo, verde, refactor, en
pasos chicos. **Conviene** cuando la regla se puede decir antes de programar:
un permiso, una validación, un cálculo, un bug con pasos. **Rinde poco** para
explorar una pantalla o un diseño: ahí primero el prototipo, y después la
prueba de lo que quedó como regla. Y siempre: **mirala fallar primero, por la
razón correcta**; una prueba que nunca viste en rojo puede no probar nada.

## Puras y con base: cómo está armado acá

**Puras** (casi todas; corren siempre). El servicio separa lo puro
(`validar`, `nombre_limpio`, `puede_adjuntar`) de lo que va a la base
(`lista`), y la ruta hace el IO: el «functional core, imperative shell» de
Gary Bernhardt. Si tu regla está mezclada con la sesión, sacala a una
función pura y probala así.

**Con base** (el Postgres de `TEST_DATABASE_URL`; sin él se saltean; el CI
las corre siempre). Las ayudas están en `tests/test_tablero_agencia_api.py`:

- `correr(prueba)` abre una transacción y la deshace al final (sesión con
  `join_transaction_mode="create_savepoint"`), cambia `get_db` con
  `app.dependency_overrides` y apaga el límite de pedidos.
- La siembra trae personas: `d.lucia` (pide piezas), `d.lider` (gestiona
  tareas), `d.aprob2` (del equipo, sin más permisos), `d.a1` (una agencia),
  `d.b1` (otra agencia); y `Cliente(d.http, usuario)` pide con su token.
- No hay pytest-asyncio: lo async se corre con `asyncio.run` (eso hace
  `correr`). No escribas `@pytest.mark.asyncio`.

```python
@_con_base
def test_otra_agencia_no_ve_las_notas():
    async def prueba(d):
        lucia, otra = Cliente(d.http, d.lucia), Cliente(d.http, d.b1)
        tarea_id, _ = await _pedir_banners(d, d.lucia)
        r = await lucia.post(f"/calendario/tareas/{tarea_id}/notas", json={"texto": "Sin precio"})
        assert r.status_code == 201, r.text
        assert (await otra.get(f"/calendario/tareas/{tarea_id}/notas")).status_code == 404
    correr(prueba)
```

La ruta de notas es inventada; el molde es el de `test_adjuntos_del_pedido.py`.
Lo de la app se importa adentro de `if URL:`, se marca con `skipif(not URL)`,
y la base se mira desde la prueba con `async with d.Sesion() as s:`.

## Ayudas, tablas y dobles

- **`@pytest.mark.parametrize`** para la tabla de casos, con datos que
  cuentan la historia («Listado ciberlunes.xlsx», «programa.exe»).
- **`monkeypatch.setattr(reglas, "MAX_BYTES_ADJUNTO", 1000)`** para achicar
  un tope en vez de mandar 10 MB.
- **Ayudas chicas y a la vista** (`_xlsx()`, `_adjuntar(...)`) mejor que
  fixtures mágicas lejos de la prueba: que cada prueba se lea sola aunque
  repita algo (SE@Google: «DAMP, not DRY»).
- **Dobles con criterio** (SE@Google, cap. 13; Freeman y Pryce, *GOOS*):
  preferí lo real (el Postgres de prueba) a un mock de la sesión. Simulá solo
  lo que sale de la máquina: la API de Claude, el mail, internet. Para la IA
  ya hay una simulada (`tests/ia_simulada.py`, `scripts/servidor_ia_simulada.py`).
- **Verificá el resultado, no las llamadas:** «se llamó a X con Y» ata la
  prueba a la implementación; «quedó guardado esto» o «respondió esto», no.
- **Fechas bajo control:** la fecha como argumento, y los bordes probados (fin
  de mes, año nuevo, la hora de Uruguay: `alcance.hoy_en_uruguay()`).

## Pruebas del frontend

- No hay Jest ni Vitest (y no se suman): la lógica pura de `lib/` se compila
  con `tsc` y se corre con `node`, con la ayuda `igual(nombre, obtenido,
  esperado)` (ver `lib/calendario/adjuntos.test.ts`).
- **Archivo de prueba nuevo:** sumalo a un script `test:*` de `package.json`
  que corra el CI (`test:calendario`, o uno encadenado en `test:externos`) y
  correlo. `tsc` elige la carpeta de salida según lo que importás: si es de
  otra carpeta, el `node .test-build/...` puede apuntar a un archivo que no
  existe (por eso `test:acceso` corre `.test-build/acceso/lib/acceso.test.js`).
- **Reglas que viven en los dos lados** (Python y TS): que una prueba las
  ate. `adjuntos.test.ts` fija los tipos que ofrece el selector («los mismos
  que acepta el servidor»); mejor todavía es leer el otro lado, como hace
  `test_sin_huerfanos.py` con su espejo en TS.
- Lo visual no tiene prueba automática: se mira (`navegador.py`, capturas).

## Cobertura útil

- La cobertura dice qué líneas **no** se ejecutaron, no qué está bien
  probado (Google Testing Blog, *Code Coverage Best Practices*, 2020). Mirá
  la del cambio, no un total.
- Mejores preguntas que un porcentaje: si borro el `if not
  _puede_adjuntar(...)`, ¿falla alguna prueba? Si cambio el 404 por un 200,
  ¿se entera alguien?
- **Mutación a mano:** rompé a propósito la línea clave, corré la prueba,
  tiene que fallar; volvé atrás. Dos minutos que valen más que un número.

## Bugs y pruebas que cuentan una decisión

- Lo que te devuelve Ramiro: primero la prueba que lo reproduce (roja),
  después el arreglo (verde). Esa prueba se queda para siempre.
- Si la prueba fija una decisión discutible, escribí el porqué:
  `test_alcohol_vaso_de_cerveza_es_exceso_aceptado` avisa que se invierte a
  propósito el día que se decida otra cosa: «no lo "arregles" sin esa decisión».
- Una prueba que falla a veces es un bug (orden, fecha, red, datos
  compartidos). No se reintenta hasta que pase: se encuentra la causa.
- Para iterar rápido, una sola: `python -m pytest
  tests/test_adjuntos_del_pedido.py -q -k agencia`; antes del HECHO, todas
  (comandos en el README del equipo, *Cómo probar*).

# Pruebas automáticas: pirámide, tamaños, confiabilidad, datos y contratos

## Pirámide, trofeo y tamaños

- **La pirámide** (Mike Cohn, *Succeeding with Agile*; la popularizó Martin
  Fowler): muchas unitarias, menos de servicio, pocas de interfaz. Las de
  abajo son rápidas y precisas; las de arriba, lentas y frágiles, pero las
  únicas que ven el todo.
- **El trofeo** (Kent C. Dodds, a partir de la frase de Guillermo Rauch
  «Write tests. Not too many. Mostly integration.»): base de chequeos
  estáticos y el grueso en integración, donde se rompe una app web.
- **Los tamaños de Google** (*Software Engineering at Google*, Google
  Testing Blog) miden qué recursos usa la prueba, no cuánto cubre: **chica**,
  un proceso, sin red ni disco ni esperas; **mediana**, una sola máquina,
  con `localhost` (una base, un servidor); **grande**, varias máquinas o
  servicios reales. Y **hermética**: trae todo lo que necesita.

| Nivel | En Core Tienda | Para qué |
|---|---|---|
| Estático | `lint`, `type-check`, `compileall`, `import app.main`, la prueba de camelCase | Barato y siempre |
| Chicas | La mayoría de `backend/tests` y los `frontend/lib/**/*.test.ts` | Reglas: tablero, piezas, acceso, externos, Redexpres |
| Medianas | `test_tablero_agencia_api.py`, `test_agencia_externa_api.py` (Postgres; cada prueba en una transacción que se deshace, como explica `conftest.py`) | Quién ve qué: las más valiosas para permisos |
| Grandes | Navegador, barrido y prueba a ciegas (capas 2 a 4) | Lo que ve la persona y lo que le llega a la otra cuenta |

Cada cosa se prueba en el nivel más bajo que la puede agarrar; arriba va
solo lo que únicamente arriba se ve. Lo que depende de internet (la
búsqueda de precios en sitios de supermercados) no es hermético: si falla,
primero se sospecha del entorno.

## Confiables: la intermitencia se trata, no se esquiva

Martin Fowler (*Eradicating Non-Determinism in Tests*) y la documentación
de Playwright coinciden en las causas:

| Causa | En Core Tienda | Remedio |
|---|---|---|
| Esperas fijas | `esperar 3000` «para que cargue» | Esperar a lo que se ve: un texto, un botón habilitado |
| Estado compartido u orden | Datos que dejó otra prueba o el barrido | Cada prueba crea lo suyo, con nombre único |
| Asincronía | Tablero cada 6 s, ficha cada 4 s, campanita cada minuto | Esperar al estado, no a «la red quieta» |
| Tiempo | «Hoy», fin de mes, de 21 a 24 h de Montevideo (en UTC ya es mañana) | Fechas fijas o inyectadas; zona horaria explícita |
| Servicios externos y límites | IA real, internet; 10 logins por minuto | IA simulada; una sesión por cuenta, reusada |

Una prueba que falla a veces **está fallando**: no se corre «hasta que dé
verde». Se repite cinco veces y se cuenta
(`for i in 1 2 3 4 5; do python -m pytest tests/test_x.py -q -p no:cacheprovider || echo "falló la vuelta $i"; done`)
y se informa así: «`test_x::test_y` falló 2 de 5, salida en `$S/…`». Si la
trae la rama, es ROJO; si ya fallaba en `main`, al cuaderno. La cuarentena
la decide el equipo de día.

## Salteada no es pasada

Hasta el 16/11/2026 el CI no tenía base: las pruebas de quién ve qué se
salteaban siempre, y un cambio que dejara a una agencia ver las tarjetas de
otra pasaba en verde (lo cuenta `.github/workflows/ci.yml`). Por eso:

- `pytest -rs` lista las salteadas con su motivo, y van en el resultado.
- Si se salteó algo que cuida lo que tocó la rama, esa parte **no es
  VERDE**: se levanta Postgres o va a «No se pudo probar».
- Al 25/11, el CI del frontend corre `test:calendario` y `test:externos`
  (que encadena acceso, usuarios, redexpres, adjuntos, guía y clientes VIP);
  `test:cenefas`, `test:chat` y `test:colocacion`, no: si la rama toca esas
  zonas, corrélas vos (el bucle del SKILL corre todas).

## Ver la prueba fallar

Kent Beck (*Test-Driven Development*) arranca por el rojo: una prueba que
nunca se vio fallar puede no probar nada. Si la rama arregla un defecto, la
prueba nueva **tiene que fallar en `main`** y pasar en la rama. Sin tocar la
rama de la noche:

```bash
git worktree add -q $S/wt-main origin/main
cp backend/tests/test_lo_nuevo.py $S/wt-main/backend/tests/
(cd $S/wt-main/backend && python -m pytest tests/test_lo_nuevo.py -q -p no:cacheprovider)  # esperado: falla
git worktree remove --force $S/wt-main
```

Tiene que fallar **la aserción del defecto**, no un `ImportError`. Para el
frontend, lo mismo con
`ln -s "$PWD/frontend/node_modules" $S/wt-main/frontend/node_modules`. Si
pasa en `main`, no agarra el defecto: se lo decís a Bruno.

## Datos de prueba

- La base arranca vacía: se crea lo necesario como lo haría la gente (y así
  se prueba la carga). Las recetas están en el mapa, «Datos para probarla».
- Nombres únicos y reconocibles, con la hora: `QA 0213 Ciberlunes`.
- **El antes y el después, con los mismos datos**; si no, la comparación
  miente.
- Archivos: `imagenes_de_prueba.py`, la plantilla Excel de Cenefas,
  `backend/tests/data/planilla_rrss.xlsx`.
- **Nunca datos reales.** Clientes VIP, con un CSV inventado con las columnas
  de `frontend/lib/clientes-vip/resumen.ts`; la pantalla queda vacía.
  `$S/cuentas.env` no se imprime ni se pega.

## Contratos de API

Front (Next.js) y back (FastAPI) se hablan por JSON con tipos escritos a
mano: si el servidor renombra un campo, `type-check` no se entera. Es lo que
resuelven los contratos guiados por el consumidor (Ian Robinson;
herramientas como Pact). A nivel QA:

1. **Los códigos que la pantalla sabe leer:** 401 sin sesión; 403 sin
   permiso, externa o contraseña pendiente; 404 fuera de tu alcance («no
   existe»); 409 conflicto (versión decidida o reemplazada, pedido
   confirmado); 422 validación; 429 demasiados intentos; 503 servicio sin
   configurar. Si la rama cambia uno, la pantalla puede mostrar el cartel
   equivocado.
2. **La forma:** el JSON de lo tocado, en `main` y en la rama, con los
   mismos datos (`$API` y tokens, como en permisos-y-seguridad):
   `curl -s -H "Authorization: Bearer $T_EQ" "$API/ruta" | python -m json.tool --sort-keys > $S/rama.json`
   y `diff`.
3. **El esquema:** con `APP_ENV=development` (el entorno de pruebas)
   FastAPI sirve `/api/openapi.json`. Con `main` y con la rama: un campo que
   desaparece, cambia de nombre o de tipo, o uno nuevo obligatorio en lo que
   se manda, rompe la pantalla.
4. **Errores legibles:** el 15/11, editar un usuario con un mail mal escrito
   tiraba la página entera, y el patrón estaba en unos 37 lugares (commit
   `737fcfe`). Toda validación nueva se prueba con el dato inválido, mirando
   la pantalla.

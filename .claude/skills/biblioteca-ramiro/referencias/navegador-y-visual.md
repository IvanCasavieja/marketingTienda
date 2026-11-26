# Punta a punta con navegador (Playwright) y regresión visual

## Lo que recomienda Playwright, y cómo ya lo hace el equipo

Playwright es de Microsoft. Su guía de buenas prácticas, aplicada:

1. **Lo que ve la persona**, con **localizadores por rol y nombre**
   (`get_by_role("button", name="Entregar")`), después etiqueta o texto;
   `get_by_test_id` al final; nunca CSS o XPath atados a la estructura.
   `navegador.py click` ya busca así: si algo solo aparece por CSS o con
   `elementos`, ya es hallazgo (`criterios.md`) y le falta nombre accesible.
2. **Aserciones que esperan solas** (`expect(loc).to_be_visible()`,
   `to_have_text`, `to_have_count`) y **sin esperas fijas para decidir**: la
   documentación de `wait_for_timeout` advierte que esperar un tiempo vuelve
   intermitente la prueba. `navegador.py esperar` es ritmo humano, no prueba.
3. **`networkidle`, desaconsejado para probar:** acá la red casi nunca queda
   quieta (tablero cada 6 s, ficha cada 4 s, campanita cada minuto).
4. **Aislamiento:** un contexto por persona y vista, con la sesión reusada
   por `storage_state` (como el barrido): respeta los 10 ingresos por minuto.
5. **Trazas** (`ctx.tracing.start(screenshots=True, snapshots=True)`,
   `stop(path=…)`, `playwright show-trace`) para lo que no se entiende;
   guardan lo tipeado y los tokens, así que quedan en `$S`. **Capturas
   comparables** (`animations="disabled"`, `caret="hide"`, `scale="css"`,
   `mask=[…]`) y `navegador.py errores` después de cada tarea.

## La matriz de punta a punta (capa 2)

Se escribe antes de abrir el navegador. Para un cambio en «Entregar»:

| Tarea | Equipo, notebook y celular | Agencia, notebook y celular | Agencia B / local |
|---|---|---|---|
| Pedir la pieza | ✓ | — | — |
| Entregar 2 imágenes y un link | — | ✓ | no llega (404 / 403) |
| Ver lo entregado y pedir cambios | ✓ | — | — |
| Ver la corrección y entregar de nuevo | — | ✓ | no llega |

- **«Cada cuenta que la toca» incluye a las que no tienen que llegar.**
- **El oráculo, primero:** anotá qué esperás ver antes del `ver`. Sin
  expectativa, todo parece razonable.
- **Lo guardado se confirma afuera de la pantalla que lo escribió:**
  recargando, desde la otra cuenta o por API. El 24/11 Mi pedido mostraba
  «12» y había guardado «1» (commit `31e5f4d`).

## Lo que el navegador paso a paso no hace: un guion en `$S`

Red lenta, sin red, doble clic de verdad, dos pestañas a la vez y traza.
Completá la acción que tocó la rama y corrélo desde la raíz del repo
(antes, `set -a; . $S/cuentas.env; set +a`):

```python
# $S/romper.py: lo que navegador.py no hace. Desde la raíz del repo: S=$S python $S/romper.py
import os, sys
from playwright.sync_api import sync_playwright, expect
sys.path.insert(0, ".claude/skills/recorrido-humano/scripts")
from recorrido_completo import entrar      # entra una sola vez por el formulario y devuelve la sesión

BASE, S = os.environ.get("NAVEGADOR_BASE", "http://localhost:3000"), os.environ["S"]
with sync_playwright() as pw:
    nav = pw.chromium.launch()
    sesion, _ = entrar(nav, BASE, "agencia-de-prueba@example.com", os.environ["CLAVE_AGENCIA_DE_PRUEBA"], None)
    ctx = nav.new_context(storage_state=sesion, locale="es-UY", timezone_id="America/Montevideo",
                          viewport={"width": 1366, "height": 768})
    ctx.tracing.start(screenshots=True, snapshots=True)   # guarda lo tipeado y los tokens: solo en $S
    p = ctx.new_page()
    escrituras = []
    p.on("request", lambda r: escrituras.append(f"{r.method} {r.url.split('/api/v1')[-1]}")
         if "/api/v1/" in r.url and r.method in ("POST", "PUT", "PATCH", "DELETE") else None)
    p.goto(BASE + "/entregas")
    expect(p.get_by_text("Ingresado").first).to_be_visible()   # esperar a lo que se ve, no a la red

    # 1. Red lenta (solo Chromium): 1,5 s de latencia y unos 50 KB/s
    cdp = ctx.new_cdp_session(p)
    cdp.send("Network.emulateNetworkConditions",
             {"offline": False, "latency": 1500, "downloadThroughput": 50_000, "uploadThroughput": 50_000})
    # 2. Doble clic de verdad, en lo que tocó la rama:
    # p.get_by_role("button", name="Entregar").dblclick()
    # 3. Sin red a mitad de camino, y de vuelta
    ctx.set_offline(True)
    # ... la acción ...
    p.screenshot(path=f"{S}/romper-sin-red.png", animations="disabled")
    ctx.set_offline(False)
    # 4. La misma persona en otra pestaña (carreras): otro contexto con la misma sesión
    otra = nav.new_context(storage_state=sesion).new_page()
    otra.goto(BASE + "/entregas")
    # ... decidir o mover lo mismo en las dos ...
    ctx.tracing.stop(path=f"{S}/traza-romper.zip")
    print("Escrituras que salieron:", *escrituras, sep="\n  ")   # dos iguales seguidas = se mandó dos veces
    nav.close()
```

Para el equipo: `entrar(nav, BASE, "equipo-nocturno@example.com",
os.environ["CLAVE_EQUIPO_NOCTURNO"], "Tienda Inglesa")`. Para iPhone, el
contexto con `pw.devices["iPhone 13"]` sin su `default_browser_type` (como
el barrido) o WebKit. Las capturas se miran con Read, como todas.

## Regresión visual: antes y después

1. **Mismas condiciones:** los mismos datos, la misma vista (1366 × 768 o
   iPhone 13), el mismo tema, `es-UY` y `America/Montevideo` (el barrido ya
   los fija), sin animaciones, con las fuentes cargadas.
2. **Tapá (con `mask`) o descontá lo que cambia solo:** «hace 5 minutos»,
   «Hoy», los números de la campanita, la pastilla «Entorno de pruebas».
3. **Quién saca qué:** Lucía, las de antes, antes de que Bruno toque nada
   (README, paso 6); vos, después, con
   `recorrido_completo.py … --rutas <tocadas y vecinas> --salida $S/recorrido-despues`.
4. **Con números y con los ojos:** el script marca dónde cambió. Donde se
   buscaba: bien. En una vecina que la rama no buscaba: hallazgo (típico de
   `globals.css` o de un componente compartido). El píxel solo señala dónde
   mirar; el juicio es la captura mirada. El JPEG mete ruido: si la caja
   abarca toda la pantalla, compará a ojo.

```python
# $S/diferencia.py ANTES.jpg DESPUES.jpg SALIDA.png
import sys
from PIL import Image, ImageChops, ImageDraw
a, b = (Image.open(x).convert("RGB") for x in sys.argv[1:3])
if a.size != b.size:
    sys.exit(f"Tamaños distintos {a.size} → {b.size}: cambió el alto o la vista; compará a ojo")
mapa = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > 32 else 0)
caja = mapa.getbbox()
if not caja:
    sys.exit("Iguales (el ruido del JPEG no cuenta)")
lado = Image.new("RGB", (a.width * 2 + 12, a.height), "white")
lado.paste(a, (0, 0)); lado.paste(b, (a.width + 12, 0))
dibujo = ImageDraw.Draw(lado)
for x in (0, a.width + 12):
    dibujo.rectangle((caja[0] + x, caja[1], caja[2] + x, caja[3]), outline="red", width=4)
lado.save(sys.argv[3])
print(f"Cambió {mapa.histogram()[255] / (a.width * a.height):.1%} de la imagen, en la zona {caja}: {sys.argv[3]}")
```

## Comparar dos barridos (capa 4)

`resumen.json` trae una fila por cuenta, vista y pantalla, con lo medido.
Esto compara el de la noche (`$S/recorrido/resumen.json`, te lo pasa el
coordinador) con el tuyo:

```python
# $S/comparar.py ANTES/resumen.json DESPUES/resumen.json
import json, sys
leer = lambda r: {(f["cuenta"], f["vista"], f["ruta"]): f for f in json.load(open(r, encoding="utf-8"))["filas"]}
antes, despues = leer(sys.argv[1]), leer(sys.argv[2])
for clave in sorted(despues):
    d, a = despues[clave], antes.get(clave)
    if a is None:
        print(" · ".join(clave), "   ⚪ no estaba en el barrido de antes: mirala a mano", sep="\n")
        continue
    notas = []
    if d.get("error") and not a.get("error"):
        notas.append(f"🔴 error nuevo: {d['error'][:120]}")
    if clave[0] in ("agencia", "local") and d.get("llego") and not a.get("llego"):
        notas.append("🔴 AHORA LLEGA y antes no: revisar permisos")
    if clave[0] == "equipo" and a.get("llego") and not d.get("llego"):
        notas.append("🔴 el equipo ya no llega")
    for campo, nombre in (("consola", "errores de consola"), ("red", "pedidos con error")):
        nuevos = set(d.get(campo) or []) - set(a.get(campo) or [])
        if nuevos:
            notas.append(f"🟠 {nombre} nuevos: {' | '.join(sorted(nuevos))[:200]}")
    if d.get("desborde") and not a.get("desborde"):
        notas.append("🟠 ahora se sale de costado")
    for campo, nombre in (("bajos", "textos con poco contraste"), ("chicos", "textos chicos"),
                          ("tocarChico", "cosas chicas para el dedo")):
        if (d.get(campo) or 0) > (a.get(campo) or 0):
            notas.append(f"🟡 más {nombre}: {a.get(campo) or 0} → {d[campo]}")
    sa, sd = a.get("segundos") or 0, d.get("segundos") or 0
    if sd > 1.5 * sa and sd - sa > 1:
        notas.append(f"🟡 más lenta: {sa} s → {sd} s")
    if notas:
        print(" · ".join(clave), *("   " + n for n in notas), sep="\n")
```

Un 🔴 de permisos es ROJO sin más. El resto se confirma en la captura: si
entre un barrido y otro cambiaron los datos, la diferencia puede venir de
ahí y no de la rama.

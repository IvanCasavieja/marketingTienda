#!/usr/bin/env python3
"""Pasa por TODAS las pantallas de Core Tienda con cada cuenta y saca capturas.

Es la base del recorrido de cada noche: en unos minutos deja una captura de
cada pantalla, para cada cuenta, en notebook y en celular (y en oscuro), con
lo que se mide solo (desborde, letra chica, contraste, errores, lo que tardó)
y a dónde llegó cada cuenta (si la agencia pudo entrar a algo que no debía).

    python recorrido_completo.py \
        --cuenta equipo=equipo-nocturno@example.com:"$CLAVE_EQUIPO_NOCTURNO" \
        --cuenta agencia=agencia-de-prueba@example.com:"$CLAVE_AGENCIA_DE_PRUEBA" \
        --cuenta local=local-de-prueba@example.com:"$CLAVE_LOCAL_DE_PRUEBA" \
        --mundo "Tienda Inglesa" --salida $S/recorrido

Deja en --salida:
- resumen.md: la tabla para leer (una fila por pantalla y vista) y las alertas.
- resumen.json: lo mismo para comparar con otra noche.
- <cuenta>/<vista>/<pantalla>.jpg: las capturas.
- hojas/<cuenta>-<vista>-N.jpg: hojas de contacto (9 capturas por hoja) para
  mirar muchas pantallas de un vistazo (necesita Pillow; si no está, no las hace).

Las pantallas salen solas de frontend/app (cada page.tsx), así que una pantalla
nueva entra al recorrido sin tocar nada. Las que llevan un dato en la ruta
([id]) se saltean: esas se recorren a mano.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import pathlib
import sys
import time

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from chequeos import MEDIDAS_JS  # noqa: E402

RAIZ_REPO = AQUI.parents[3]

# La pantalla dice que no tenés acceso (aunque la dirección siga siendo la pedida).
SIN_ACCESO_JS = r"""() => /no ten[eé]s (acceso|permiso)|sin permiso|no est[aá]s autorizad|tu cuenta no entra|no (es|son) de (redexpres|tienda)/i
                          .test((document.querySelector('main') || document.body).innerText || '')"""

# Las vistas: (nombre, celular, oscuro)
VISTAS = {
    "notebook-claro": (False, False),
    "celular-claro": (True, False),
    "notebook-oscuro": (False, True),
    "celular-oscuro": (True, True),
}

# A dónde debería poder llegar cada tipo de cuenta. Lo que no está acá, para una
# cuenta externa o de local es una alerta (no debería ver pantallas internas).
# Si una pantalla nueva es para ellos, sumala acá en el mismo PR.
PERMITIDAS = {
    "agencia": {"/entregas", "/calendario", "/mis-tareas", "/perfil", "/ayuda", "/settings"},
    "local": {"/redexpres/mi-pedido", "/colocacion", "/fotos", "/perfil", "/ayuda", "/settings", "/home"},
}


def rutas_del_front(raiz: pathlib.Path) -> list[str]:
    app = raiz / "frontend" / "app"
    rutas = set()
    for p in app.rglob("page.tsx"):
        partes = [x for x in p.relative_to(app).parent.parts if not (x.startswith("(") and x.endswith(")"))]
        if any(x.startswith("[") for x in partes):
            continue
        ruta = "/" + "/".join(partes)
        if ruta in ("/", "/login", "/forgot-password", "/reset-password"):
            continue
        rutas.add(ruta)
    return sorted(rutas)


def _seguro(ruta: str) -> str:
    return ruta.strip("/").replace("/", "__") or "raiz"


def entrar(browser, base: str, usuario: str, clave: str, mundo: str | None):
    """Entra una sola vez por el formulario y devuelve la sesión para reusarla."""
    ctx = browser.new_context(viewport={"width": 1366, "height": 768})
    p = ctx.new_page()
    p.goto(base + "/login", wait_until="domcontentloaded", timeout=60000)
    p.locator("input[name=email]").fill(usuario)
    p.locator("input[name=password]").fill(clave)
    p.locator("form button[type=submit]").first.click()
    p.wait_for_url(lambda u: "/login" not in u, timeout=60000)
    try:
        p.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    destino = p.url.replace(base, "")
    if "/mundos" in p.url and mundo:
        p.get_by_text(mundo, exact=False).first.click()
        try:
            p.wait_for_url(lambda u: "/mundos" not in u, timeout=20000)
        except Exception:
            pass
        p.wait_for_timeout(1500)
    estado = ctx.storage_state()
    ctx.close()
    return estado, destino


def calma(p, ms=15000):
    try:
        p.wait_for_load_state("networkidle", timeout=ms)
    except Exception:
        pass
    try:
        p.wait_for_function("() => ![...document.querySelectorAll('.animate-spin')].some(e => e.offsetParent !== null)",
                            timeout=ms)
    except Exception:
        pass
    p.wait_for_timeout(400)


def recorrer_cuenta(nombre: str, usuario: str, clave: str, base: str, mundo: str | None,
                    vistas: list[str], rutas: list[str], salida: str) -> list[dict]:
    from playwright.sync_api import sync_playwright
    filas = []
    salida_p = pathlib.Path(salida)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel=os.environ.get("NAVEGADOR_CANAL") or None)
        try:
            estado, destino = entrar(browser, base, usuario, clave, mundo)
        except Exception as e:  # noqa: BLE001
            browser.close()
            return [{"cuenta": nombre, "vista": "-", "ruta": "/login", "error": f"No pudo entrar: {e}"}]
        iphone = dict(pw.devices["iPhone 13"])
        iphone.pop("default_browser_type", None)
        for vista in vistas:
            celular, oscuro = VISTAS[vista]
            opciones = dict(iphone) if celular else {"viewport": {"width": 1366, "height": 768}}
            opciones.update(storage_state=estado, color_scheme="dark" if oscuro else "light",
                            locale="es-UY", timezone_id="America/Montevideo")
            ctx = browser.new_context(**opciones)
            tema = "dark" if oscuro else "light"
            ctx.add_init_script(f"try {{ localStorage.setItem('theme', '{tema}') }} catch (e) {{}}")
            p = ctx.new_page()
            consola, red = [], []
            p.on("console", lambda m: consola.append(m.text[:200]) if m.type == "error" else None)
            p.on("pageerror", lambda e: consola.append("excepción: " + str(e)[:200]))
            p.on("response", lambda r: red.append(f"{r.status} {r.request.method} {r.url.replace(base, '')[:120]}")
                 if r.status >= 400 else None)
            carpeta = salida_p / nombre / vista
            carpeta.mkdir(parents=True, exist_ok=True)
            for ruta in rutas:
                consola.clear()
                red.clear()
                fila = {"cuenta": nombre, "vista": vista, "ruta": ruta, "inicio": destino}
                t0 = time.time()
                try:
                    resp = p.goto(base + ruta, wait_until="domcontentloaded", timeout=60000)
                    calma(p)
                    fila["segundos"] = round(time.time() - t0, 1)
                    fila["estado"] = resp.status if resp else None
                    final = p.url.replace(base, "").split("?")[0]
                    fila["final"] = final
                    # Varias pantallas no redirigen: se quedan en la ruta y muestran «No tenés acceso».
                    fila["sinAcceso"] = p.evaluate(SIN_ACCESO_JS)
                    fila["llego"] = final.rstrip("/") == ruta.rstrip("/") and not fila["sinAcceso"]
                    archivo = carpeta / f"{_seguro(ruta)}.jpg"
                    p.screenshot(path=str(archivo), type="jpeg", quality=70, scale="css", animations="disabled")
                    fila["captura"] = str(archivo.relative_to(salida_p)).replace("\\", "/")
                    fila.update(p.evaluate(MEDIDAS_JS, celular))
                except Exception as e:  # noqa: BLE001
                    fila["error"] = f"{type(e).__name__}: {str(e)[:200]}"
                fila["consola"] = consola[:8]
                fila["red"] = [r for r in red if "/_next/" not in r][:8]
                filas.append(fila)
            ctx.close()
        browser.close()
    return filas


def alertas_de(filas: list[dict]) -> list[str]:
    """Una línea por (cuenta, pantalla, tipo de problema), con las vistas donde pasa."""
    grupos: dict[tuple, dict] = {}

    def anotar(nivel: str, f: dict, tipo: str, detalle: str) -> None:
        g = grupos.setdefault((nivel, f["cuenta"], f["ruta"], tipo), {"vistas": [], "detalle": detalle})
        g["vistas"].append(f["vista"])

    for f in filas:
        if f.get("error"):
            anotar("🔴", f, "error", f["error"])
            continue
        permitidas = PERMITIDAS.get(f["cuenta"])
        if permitidas is not None and f.get("llego") and f["ruta"] not in permitidas:
            anotar("🔴", f, "permiso", "esta cuenta ENTRÓ a una pantalla que no es para ella (revisar permisos)")
        if f.get("sinAcceso") or not f.get("llego"):
            continue  # el cartel de «sin acceso» o la redirección no se miden: se juzgan en las capturas
        if f.get("red"):
            anotar("🟠", f, "red", f"pedidos con error: {'; '.join(f['red'][:3])}")
        if f.get("consola"):
            anotar("🟠", f, "consola", f"errores en la consola: {'; '.join(f['consola'][:2])}")
        if f.get("desborde"):
            anotar("🟠", f, "desborde", f"se sale de costado ({f['anchoPagina']}px en {f['ancho']}px): "
                                       f"{'; '.join(f.get('anchos', [])[:2])}")
        if (f.get("segundos") or 0) > 6:
            anotar("🟡", f, "lenta", f"tardó {f['segundos']} s en quedarse quieta")
        if f.get("bajos"):
            anotar("🟡", f, "contraste", f"{f['bajos']} textos con contraste bajo (aprox.): {'; '.join(f.get('ejBajos', [])[:2])}")
        if f.get("chicos"):
            anotar("🟡", f, "letra", f"{f['chicos']} textos de menos de 12px: {'; '.join(f.get('ejChicos', [])[:2])}")
        if "celular" in f["vista"] and f.get("tocarChico", 0) >= 3:
            anotar("🟡", f, "dedo", f"{f['tocarChico']} cosas chicas para el dedo: {'; '.join(f.get('ejTocar', [])[:2])}")
    orden = {"🔴": 0, "🟠": 1, "🟡": 2}
    al = [f"{nivel} {cuenta} · `{ruta}`: {g['detalle']} ({', '.join(g['vistas'])})"
          for (nivel, cuenta, ruta, _), g in grupos.items()]
    return sorted(al, key=lambda a: orden.get(a[:1], 3))


def hojas_de_contacto(filas: list[dict], salida: pathlib.Path) -> list[str]:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return []
    hechas = []
    (salida / "hojas").mkdir(exist_ok=True)
    grupos: dict[tuple, list] = {}
    for f in filas:
        if f.get("captura") and (f.get("llego") or f.get("sinAcceso")):
            grupos.setdefault((f["cuenta"], f["vista"]), []).append(f)
    for (cuenta, vista), fs in grupos.items():
        ancho = 440 if "notebook" in vista else 220
        for n in range(0, len(fs), 9):
            lote = fs[n:n + 9]
            imgs = []
            for f in lote:
                im = Image.open(salida / f["captura"]).convert("RGB")
                im.thumbnail((ancho, 10_000))
                im = im.crop((0, 0, im.width, min(im.height, int(ancho * (0.62 if "notebook" in vista else 2.0)))))
                imgs.append((f["ruta"] + ("  · sin acceso" if f.get("sinAcceso") else ""), im))
            celda_w = ancho + 16
            celda_h = max(i.height for _, i in imgs) + 34
            hoja = Image.new("RGB", (celda_w * 3, celda_h * ((len(imgs) + 2) // 3)), "white")
            d = ImageDraw.Draw(hoja)
            for i, (ruta, im) in enumerate(imgs):
                x, y = (i % 3) * celda_w + 8, (i // 3) * celda_h + 26
                d.text((x, y - 20), ruta, fill="black")
                hoja.paste(im, (x, y))
            nombre = salida / "hojas" / f"{cuenta}-{vista}-{n // 9 + 1}.jpg"
            hoja.save(nombre, quality=75)
            hechas.append(str(nombre.relative_to(salida)).replace("\\", "/"))
    return hechas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cuenta", action="append", required=True, help="nombre=usuario:clave (repetible)")
    ap.add_argument("--base", default=os.environ.get("NAVEGADOR_BASE", "http://localhost:3000"))
    ap.add_argument("--mundo", default="Tienda Inglesa", help="mundo a elegir si la cuenta tiene varios")
    ap.add_argument("--vistas", default="notebook-claro,celular-claro,notebook-oscuro")
    ap.add_argument("--rutas", default="", help="solo estas rutas, separadas por coma (por defecto, todas)")
    ap.add_argument("--repo", default=str(RAIZ_REPO))
    ap.add_argument("--salida", default="recorrido")
    a = ap.parse_args()

    base = a.base.rstrip("/")
    salida = pathlib.Path(a.salida).resolve()
    salida.mkdir(parents=True, exist_ok=True)
    rutas = [r.strip() for r in a.rutas.split(",") if r.strip()] or rutas_del_front(pathlib.Path(a.repo))
    vistas = [v.strip() for v in a.vistas.split(",") if v.strip() in VISTAS]
    cuentas = []
    for c in a.cuenta:
        nombre, _, resto = c.partition("=")
        usuario, _, clave = resto.partition(":")
        cuentas.append((nombre, usuario, clave))

    t0 = time.time()
    print(f"Recorriendo {len(rutas)} pantallas × {len(vistas)} vistas × {len(cuentas)} cuentas…", flush=True)
    filas: list[dict] = []
    with cf.ProcessPoolExecutor(max_workers=len(cuentas)) as ex:
        futuros = [ex.submit(recorrer_cuenta, n, u, c, base, a.mundo, vistas, rutas, str(salida)) for n, u, c in cuentas]
        for fu in cf.as_completed(futuros):
            filas.extend(fu.result())
    filas.sort(key=lambda f: (f["cuenta"], f["vista"], f["ruta"]))
    alertas = alertas_de(filas)
    hojas = hojas_de_contacto(filas, salida)

    (salida / "resumen.json").write_text(json.dumps({"fecha": dt.datetime.now().isoformat(timespec="minutes"),
                                                     "rutas": rutas, "vistas": vistas, "filas": filas,
                                                     "alertas": alertas, "hojas": hojas},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    md = [f"# Recorrido completo — {dt.date.today():%d/%m/%Y}", "",
          f"{len(rutas)} pantallas × {len(vistas)} vistas × {len(cuentas)} cuentas = {len(filas)} capturas "
          f"en {int(time.time() - t0)} s.", ""]
    for nombre, usuario, _ in cuentas:
        f0 = next((f for f in filas if f["cuenta"] == nombre), {})
        llega = sorted({f["ruta"] for f in filas if f["cuenta"] == nombre and f.get("llego")})
        cartel = sorted({f["ruta"] for f in filas if f["cuenta"] == nombre and f.get("sinAcceso")})
        md.append(f"- **{nombre}** ({usuario}) entra a `{f0.get('inicio', '?')}` y llega a {len(llega)} pantallas: "
                  + ", ".join(f"`{r}`" for r in llega)
                  + (f". En {len(cartel)} le aparece «No tenés acceso» (mirá si esos carteles son claros y "
                     f"parejos entre sí)." if cartel else ""))
    md += ["", f"## Alertas automáticas ({len(alertas)})", "",
           "Son pistas, no veredictos: confirmalas mirando la captura.", ""]
    md += [f"- {x}" for x in alertas[:150]] or ["- Ninguna."]
    md += ["", "## Pantalla por pantalla", "",
           "| Cuenta | Vista | Pantalla | Llegó a | Tardó | Alto | Contraste bajo | Letra chica | Captura |",
           "|---|---|---|---|---|---|---|---|---|"]
    for f in filas:
        llego_a = "sin acceso" if f.get("sinAcceso") else f"`{f.get('final', '-')}`"
        md.append(f"| {f['cuenta']} | {f['vista']} | `{f['ruta']}` | {llego_a} | "
                  f"{f.get('segundos', '-')} s | {f.get('pantallasDeAlto', '-')} | {f.get('bajos', '-')} | "
                  f"{f.get('chicos', '-')} | {f.get('captura', f.get('error', '-'))} |")
    if hojas:
        md += ["", "## Hojas de contacto", ""] + [f"- {h}" for h in hojas]
    (salida / "resumen.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Listo en {int(time.time() - t0)} s: {salida / 'resumen.md'} ({len(alertas)} alertas, {len(hojas)} hojas)")


if __name__ == "__main__":
    main()

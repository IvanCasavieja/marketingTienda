#!/usr/bin/env python3
"""Un navegador para recorrer Core Tienda como lo haría una persona.

Queda abierto entre comando y comando (un servidorcito local guarda las
pestañas), así cada paso es una línea de Bash:

    python navegador.py abrir equipo                 # pestaña nueva, notebook 1366x768
    python navegador.py entrar equipo-nocturno@example.com "$CLAVE_EQUIPO_NOCTURNO"
    python navegador.py ver inicio                   # captura -> te dice dónde quedó
    python navegador.py click "Nueva acción"         # por lo que se LEE en la pantalla
    python navegador.py escribir "Nombre" "Ciberlunes"
    python navegador.py tecla Enter
    python navegador.py abrir agencia-cel --celular --oscuro

La regla de fondo: te movés por lo que una persona VE. `click` busca el texto
visible (botón, link, pestaña, etiqueta). Si no lo encuentra, te lo dice: es
una señal de que una persona tampoco lo encontraría. Con `--humano` la pestaña
no deja leer la página por dentro (solo capturas y clics por coordenadas):
es el modo de la usuaria a ciegas.

Variables: NAVEGADOR_BASE (por defecto http://localhost:3000),
NAVEGADOR_CAPTURAS (carpeta de capturas, por defecto ./capturas),
NAVEGADOR_PUERTO (por defecto 9333), NAVEGADOR_CANAL (vacío = el Chromium de
Playwright; "chrome" = el Chrome instalado en la máquina).

Necesita `pip install playwright` y `python -m playwright install chromium`.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

PUERTO = int(os.environ.get("NAVEGADOR_PUERTO", "9333"))
BASE = os.environ.get("NAVEGADOR_BASE", "http://localhost:3000").rstrip("/")
CAPTURAS = pathlib.Path(os.environ.get("NAVEGADOR_CAPTURAS", "capturas")).resolve()
AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

# Comandos que leen la página por dentro: en una pestaña --humano no se puede.
POR_DENTRO = {"texto", "elementos", "click", "escribir", "elegir", "pasar", "subir", "medidas", "js"}

AYUDA = """Comandos:
  abrir NOMBRE [--celular] [--oscuro] [--humano] [--como OTRA]
                                                   pestaña nueva (o vuelve a una que ya existe);
                                                   --como copia la sesión de otra pestaña (sin volver a entrar)
  pestanas                                         las pestañas abiertas y cuál es la actual
  entrar USUARIO CLAVE [--mundo "Tienda Inglesa"]  inicia sesión por el formulario de /login
  ir RUTA                                          /calendario, /entregas... (o una URL entera)
  ver [NOMBRE] [--completa]                        captura de lo que se ve (o de la página entera)
  click TEXTO [--n 2] [--exacto]                   clic en lo que dice TEXTO (botón, link, pestaña...)
  click-xy X Y                                     clic en un punto de la captura (en celular, toque)
  escribir CAMPO TEXTO                             escribe en el campo con esa etiqueta o ese ejemplo
  teclear TEXTO                                    escribe donde está el cursor
  tecla TECLA                                      Enter, Escape, Tab, ArrowDown, Control+a...
  elegir CAMPO OPCION                              elige una opción de una lista desplegable
  subir ARCHIVO [ARCHIVO...] [--campo TEXTO]       adjunta archivos al primer campo de archivo
  pasar TEXTO                                      pasa el mouse por encima (tooltips, menús)
  rueda [abajo|arriba|izquierda|derecha] [PIXELES] desplaza la página
  arrastrar X1 Y1 X2 Y2                            arrastra (tarjetas del tablero, por ejemplo)
  esperar MS                                       espera (por ejemplo, a que termine algo)
  atras | recargar
  texto                                            el texto que se ve en la pantalla
  elementos                                        lo que se puede tocar, con su posición
  medidas                                          chequeos de la pantalla: desborde, letra chica, contraste
  errores                                          errores de la consola y pedidos fallidos desde la última vez
  js CODIGO                                        evalúa JavaScript (solo para preparar datos, no para juzgar)
  cerrar                                           cierra todo
"""


# ---------------------------------------------------------------- cliente

def _pedir(cmd: str, args: list[str], timeout: float = 120) -> dict:
    data = json.dumps({"cmd": cmd, "args": args}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{PUERTO}/", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _servidor_vivo() -> bool:
    try:
        return _pedir("hola", [], timeout=3).get("ok", False)
    except Exception:
        return False


def _arrancar_servidor() -> None:
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    log = open(CAPTURAS / "navegador.log", "a", encoding="utf-8")
    kw: dict = {"stdout": log, "stderr": log, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    subprocess.Popen([sys.executable, str(pathlib.Path(__file__).resolve()), "servidor"], **kw)
    for _ in range(60):
        time.sleep(0.5)
        if _servidor_vivo():
            return
    sys.exit(f"El navegador no arrancó: mirá {CAPTURAS / 'navegador.log'}")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "ayuda"):
        print(AYUDA)
        return
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "servidor":
        Servidor().correr()
        return
    if cmd == "cerrar" and not _servidor_vivo():
        print("No había nada abierto.")
        return
    if not _servidor_vivo():
        _arrancar_servidor()
    try:
        r = _pedir(cmd, args, timeout=300)
    except urllib.error.URLError as e:
        sys.exit(f"No pude hablar con el navegador: {e}")
    print(r.get("salida", ""))
    if not r.get("ok", False):
        sys.exit(1)


# ---------------------------------------------------------------- servidor

class Error(Exception):
    """Un problema que se le explica a quien usa el navegador (no un fallo del script)."""


def _opcion(args: list[str], nombre: str, por_defecto=None, es_bandera=False):
    if nombre not in args:
        return False if es_bandera else por_defecto
    i = args.index(nombre)
    args.pop(i)
    if es_bandera:
        return True
    if i >= len(args):
        raise Error(f"Falta el valor de {nombre}")
    return args.pop(i)


class Servidor:
    def __init__(self) -> None:
        from playwright.sync_api import sync_playwright
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(headless=os.environ.get("NAVEGADOR_VISIBLE") != "1",
                                               channel=os.environ.get("NAVEGADOR_CANAL") or None)
        self.pestanas: dict[str, dict] = {}
        self.actual: str | None = None
        self.n_captura = 0
        CAPTURAS.mkdir(parents=True, exist_ok=True)

    # -- infraestructura
    def correr(self) -> None:
        from http.server import BaseHTTPRequestHandler, HTTPServer
        yo = self

        class Manejador(BaseHTTPRequestHandler):
            def log_message(self, *a):  # silencio
                pass

            def do_POST(self):
                largo = int(self.headers.get("Content-Length", 0))
                pedido = json.loads(self.rfile.read(largo).decode() or "{}")
                resp = yo.atender(pedido.get("cmd", ""), list(pedido.get("args", [])))
                cuerpo = json.dumps(resp, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)
                if pedido.get("cmd") == "cerrar":
                    raise SystemExit

        srv = HTTPServer(("127.0.0.1", PUERTO), Manejador)
        try:
            srv.serve_forever()
        except SystemExit:
            pass
        finally:
            try:
                self.browser.close()
                self.pw.stop()
            except Exception:
                pass

    def atender(self, cmd: str, args: list[str]) -> dict:
        try:
            if cmd == "hola":
                return {"ok": True, "salida": "hola"}
            fn = getattr(self, "c_" + cmd.replace("-", "_"), None)
            if fn is None:
                raise Error(f"No conozco el comando «{cmd}».\n{AYUDA}")
            if cmd in POR_DENTRO and self.actual and self.pestanas[self.actual]["humano"]:
                raise Error(f"«{cmd}» lee la página por dentro y esta pestaña es --humano: "
                            "usá ver, click-xy, teclear, tecla, rueda o arrastrar.")
            return {"ok": True, "salida": fn(args) or ""}
        except Error as e:
            return {"ok": False, "salida": f"✗ {e}"}
        except Exception as e:  # noqa: BLE001 — se le cuenta tal cual a quien maneja
            return {"ok": False, "salida": f"✗ {type(e).__name__}: {e}"}

    @property
    def pag(self):
        if not self.actual:
            raise Error("No hay ninguna pestaña: empezá con `abrir NOMBRE`.")
        return self.pestanas[self.actual]["page"]

    def _info(self) -> str:
        p = self.pag
        try:
            titulo = p.title()
        except Exception:
            titulo = "?"
        return f"[{self.actual}] {p.url}  ·  «{titulo}»"

    def _calma(self, ms: int = 8000) -> None:
        """Espera a que la pantalla se quede quieta: red tranquila y sin ruedita girando."""
        p = self.pag
        try:
            p.wait_for_load_state("networkidle", timeout=ms)
        except Exception:
            pass
        try:
            p.wait_for_function(
                """() => ![...document.querySelectorAll('.animate-spin')]
                         .some(e => e.offsetParent !== null)""",
                timeout=ms)
        except Exception:
            pass
        p.wait_for_timeout(250)

    def _url(self, ruta: str) -> str:
        # Git Bash en Windows convierte "/entregas" en "C:/Program Files/Git/entregas": se deshace.
        ruta = re.sub(r"^[A-Za-z]:/.*?/Git(?=/)", "", ruta.replace("\\", "/"))
        return ruta if ruta.startswith("http") else BASE + (ruta if ruta.startswith("/") else "/" + ruta)

    # -- pestañas
    def c_abrir(self, args):
        celular = _opcion(args, "--celular", es_bandera=True)
        oscuro = _opcion(args, "--oscuro", es_bandera=True)
        humano = _opcion(args, "--humano", es_bandera=True)
        como = _opcion(args, "--como")
        if not args:
            raise Error("Uso: abrir NOMBRE [--celular] [--oscuro] [--humano] [--como OTRA]")
        nombre = args[0]
        if nombre in self.pestanas:
            self.actual = nombre
            return f"Vuelvo a la pestaña {nombre}. {self._info()}"
        if celular:
            opciones = dict(self.pw.devices["iPhone 13"])
            opciones.pop("default_browser_type", None)
        else:
            opciones = {"viewport": {"width": 1366, "height": 768}, "device_scale_factor": 1}
        opciones["color_scheme"] = "dark" if oscuro else "light"
        opciones["locale"] = "es-UY"
        opciones["timezone_id"] = "America/Montevideo"
        if como:
            if como not in self.pestanas:
                raise Error(f"No hay una pestaña «{como}» de la que copiar la sesión.")
            opciones["storage_state"] = self.pestanas[como]["ctx"].storage_state()
        ctx = self.browser.new_context(**opciones)
        tema = "dark" if oscuro else "light"
        ctx.add_init_script(f"try {{ if (!localStorage.getItem('theme')) localStorage.setItem('theme', '{tema}') }} catch (e) {{}}")
        page = ctx.new_page()
        registro = {"consola": [], "red": []}

        def en_consola(m):
            if m.type in ("error", "warning"):
                registro["consola"].append(f"{m.type}: {m.text[:300]}")

        def en_respuesta(r):
            if r.status >= 400:
                registro["red"].append(f"{r.status} {r.request.method} {r.url[:200]}")

        page.on("console", en_consola)
        page.on("pageerror", lambda e: registro["consola"].append(f"excepción: {str(e)[:300]}"))
        page.on("response", en_respuesta)
        page.on("requestfailed", lambda r: registro["red"].append(f"falló {r.method} {r.url[:200]} ({r.failure})"))
        self.pestanas[nombre] = {"ctx": ctx, "page": page, "celular": celular, "oscuro": oscuro,
                                 "humano": humano, **registro}
        self.actual = nombre
        que = "celular (iPhone 390x844)" if celular else "notebook (1366x768)"
        return (f"Pestaña {nombre} abierta: {que}, tema {'oscuro' if oscuro else 'claro'}"
                f"{', modo humano (solo capturas y clics por coordenadas)' if humano else ''}.")

    def c_pestanas(self, args):
        if not self.pestanas:
            return "No hay pestañas abiertas."
        filas = []
        for n, t in self.pestanas.items():
            marca = "→" if n == self.actual else " "
            filas.append(f"{marca} {n}: {t['page'].url} ({'celular' if t['celular'] else 'notebook'}, "
                         f"{'oscuro' if t['oscuro'] else 'claro'}{', humano' if t['humano'] else ''})")
        return "\n".join(filas)

    def c_cerrar(self, args):
        return "Navegador cerrado."

    # -- moverse
    def c_ir(self, args):
        if not args:
            raise Error("Uso: ir RUTA")
        t0 = time.time()
        resp = self.pag.goto(self._url(args[0]), wait_until="domcontentloaded", timeout=60000)
        self._calma(15000)
        seg = time.time() - t0
        estado = resp.status if resp else "?"
        return f"{self._info()}  ·  {estado}  ·  tardó {seg:.1f} s"

    def c_atras(self, args):
        self.pag.go_back()
        self._calma()
        return self._info()

    def c_recargar(self, args):
        self.pag.reload()
        self._calma()
        return self._info()

    def c_esperar(self, args):
        self.pag.wait_for_timeout(int(args[0]) if args else 1000)
        return self._info()

    def c_entrar(self, args):
        mundo = _opcion(args, "--mundo")
        if len(args) < 2:
            raise Error("Uso: entrar USUARIO CLAVE [--mundo NOMBRE]")
        p = self.pag
        p.goto(self._url("/login"), wait_until="domcontentloaded", timeout=60000)
        p.locator("input[name=email]").fill(args[0])
        p.locator("input[name=password]").fill(args[1])
        p.locator("form button[type=submit]").first.click()
        try:
            p.wait_for_url(lambda u: "/login" not in u, timeout=45000)
        except Exception:
            self._calma(3000)
            avisos = p.locator("[data-sonner-toast]").all_inner_texts()
            raise Error(f"No pude entrar: sigo en {p.url}. Avisos en pantalla: {avisos or 'ninguno'}")
        self._calma(15000)
        salida = f"Adentro. {self._info()}"
        if "/mundos" in p.url and mundo:
            self._clic_texto(mundo, 1, False)
            self._calma(15000)
            salida += f"\nElegí el mundo «{mundo}». {self._info()}"
        elif "/mundos" in p.url:
            salida += "\nTe pide elegir mundo: `click \"Tienda Inglesa\"` (o el que toque)."
        return salida

    # -- mirar
    def c_ver(self, args):
        completa = _opcion(args, "--completa", es_bandera=True)
        nombre = args[0] if args else "captura"
        self.n_captura += 1
        seguro = "".join(c if c.isalnum() or c in "-_" else "-" for c in nombre)[:60]
        ruta = CAPTURAS / f"{self.n_captura:03d}-{self.actual}-{seguro}.png"
        self.pag.screenshot(path=str(ruta), full_page=completa, scale="css", animations="disabled")
        vp = self.pag.viewport_size or {}
        return (f"{ruta}\n{self._info()}  ·  pantalla {vp.get('width')}x{vp.get('height')}"
                " (las coordenadas de la captura son las de click-xy)")

    def c_texto(self, args):
        t = self.pag.inner_text("body")
        lineas = [l.strip() for l in t.splitlines() if l.strip()]
        texto = "\n".join(lineas)
        return f"{self._info()}\n---\n{texto[:8000]}" + ("\n…(cortado)" if len(texto) > 8000 else "")

    def c_elementos(self, args):
        from chequeos import ELEMENTOS_JS
        items = self.pag.evaluate(ELEMENTOS_JS)
        filas = [self._info(), "---"]
        for it in items:
            avisos = []
            if it["chico"]:
                avisos.append(f"chico {it['w']}x{it['h']}")
            if it["soloIcono"]:
                avisos.append("solo ícono: una persona no ve qué dice")
            filas.append(f"{it['rol']:<9} «{it['nombre'][:60]}» en ({it['x']},{it['y']})"
                         + (f"  ⚠ {', '.join(avisos)}" if avisos else ""))
        return "\n".join(filas) if items else f"{self._info()}\nNo veo nada para tocar."

    def c_medidas(self, args):
        from chequeos import MEDIDAS_JS, contar_en_texto
        celular = self.pestanas[self.actual]["celular"]
        m = self.pag.evaluate(MEDIDAS_JS, celular)
        return f"{self._info()}\n" + contar_en_texto(m, celular)

    def c_errores(self, args):
        t = self.pestanas[self.actual]
        consola, red = t["consola"][:], t["red"][:]
        t["consola"].clear()
        t["red"].clear()
        if not consola and not red:
            return "Sin errores desde la última vez."
        return "\n".join(["Consola:"] + [f"  {c}" for c in consola[-30:]] +
                         ["Pedidos fallidos:"] + [f"  {r}" for r in red[-30:]])

    def c_js(self, args):
        if not args:
            raise Error("Uso: js CODIGO")
        r = self.pag.evaluate(args[0])
        return json.dumps(r, ensure_ascii=False, default=str)[:4000]

    # -- tocar
    def _candidatos(self, texto: str, exacto: bool):
        p = self.pag
        roles = ["button", "link", "tab", "menuitem", "option", "checkbox", "radio", "switch", "combobox"]
        for rol in roles:
            yield f"{rol}", p.get_by_role(rol, name=texto, exact=exacto)
        yield "campo", p.get_by_label(texto, exact=exacto)
        yield "texto", p.get_by_text(texto, exact=exacto)
        yield "título", p.get_by_title(texto, exact=exacto)

    def _clic_texto(self, texto: str, n: int, exacto: bool) -> str:
        vistos = []
        for tipo, loc in self._candidatos(texto, exacto):
            try:
                cuantos = loc.count()
            except Exception:
                continue
            for i in range(cuantos):
                el = loc.nth(i)
                try:
                    if el.is_visible():
                        vistos.append((tipo, el))
                except Exception:
                    pass
            if len(vistos) >= n:
                break
        if len(vistos) < n:
            raise Error(f"No veo nada que diga «{texto}» en la pantalla"
                        + (f" (vi {len(vistos)}, pediste el {n}º)" if vistos else "")
                        + ". Si una persona tampoco lo encontraría, anotalo como hallazgo. "
                          "Probá `texto`, `elementos` o `ver`.")
        tipo, el = vistos[n - 1]
        try:
            nombre = (el.inner_text(timeout=1000) or "").strip().replace("\n", " ")[:60]
        except Exception:
            nombre = texto
        el.scroll_into_view_if_needed(timeout=5000)
        if self.pestanas[self.actual]["celular"]:
            el.tap(timeout=10000)
        else:
            el.click(timeout=10000)
        self._calma()
        return f"Toqué {tipo} «{nombre or texto}». {self._info()}"

    def c_click(self, args):
        n = int(_opcion(args, "--n", "1"))
        exacto = _opcion(args, "--exacto", es_bandera=True)
        if not args:
            raise Error("Uso: click TEXTO [--n N] [--exacto]")
        return self._clic_texto(args[0], n, exacto)

    def c_click_xy(self, args):
        if len(args) < 2:
            raise Error("Uso: click-xy X Y")
        x, y = float(args[0]), float(args[1])
        if self.pestanas[self.actual]["celular"]:
            self.pag.touchscreen.tap(x, y)
        else:
            self.pag.mouse.click(x, y)
        self._calma()
        return f"Clic en ({x:.0f},{y:.0f}). {self._info()}"

    def c_escribir(self, args):
        if len(args) < 2:
            raise Error("Uso: escribir CAMPO TEXTO")
        campo, texto = args[0], args[1]
        p = self.pag
        for loc in (p.get_by_label(campo), p.get_by_placeholder(campo), p.get_by_role("textbox", name=campo),
                    p.get_by_role("combobox", name=campo), p.get_by_role("spinbutton", name=campo)):
            try:
                for i in range(loc.count()):
                    el = loc.nth(i)
                    if el.is_visible() and el.is_editable():
                        el.fill(texto)
                        return f"Escribí en «{campo}». {self._info()}"
            except Exception:
                continue
        raise Error(f"No veo un campo «{campo}» (ni por su etiqueta ni por su texto de ejemplo). "
                    "Si no tiene etiqueta visible, una persona tampoco sabe qué va ahí: anotalo.")

    def c_teclear(self, args):
        self.pag.keyboard.type(" ".join(args), delay=15)
        return self._info()

    def c_tecla(self, args):
        if not args:
            raise Error("Uso: tecla TECLA")
        self.pag.keyboard.press(args[0])
        self._calma(4000)
        return self._info()

    def c_elegir(self, args):
        if len(args) < 2:
            raise Error("Uso: elegir CAMPO OPCION")
        self.pag.get_by_label(args[0]).select_option(label=args[1])
        self._calma(4000)
        return f"Elegí «{args[1]}» en «{args[0]}». {self._info()}"

    def c_subir(self, args):
        campo = _opcion(args, "--campo")
        if not args:
            raise Error("Uso: subir ARCHIVO [ARCHIVO...] [--campo TEXTO]")
        p = self.pag
        loc = p.get_by_label(campo) if campo else p.locator("input[type=file]").first
        loc.set_input_files([str(pathlib.Path(a).resolve()) for a in args])
        self._calma()
        return f"Adjunté {len(args)} archivo(s). {self._info()}"

    def c_pasar(self, args):
        if not args:
            raise Error("Uso: pasar TEXTO")
        self.pag.get_by_text(args[0]).first.hover()
        self.pag.wait_for_timeout(600)
        return self._info()

    def c_rueda(self, args):
        hacia = args[0] if args else "abajo"
        px = int(args[1]) if len(args) > 1 else 600
        dx, dy = {"abajo": (0, px), "arriba": (0, -px), "derecha": (px, 0), "izquierda": (-px, 0)}.get(hacia, (0, px))
        vp = self.pag.viewport_size or {"width": 800, "height": 600}
        self.pag.mouse.move(vp["width"] / 2, vp["height"] / 2)
        self.pag.mouse.wheel(dx, dy)
        self.pag.wait_for_timeout(500)
        return self._info()

    def c_arrastrar(self, args):
        if len(args) < 4:
            raise Error("Uso: arrastrar X1 Y1 X2 Y2")
        x1, y1, x2, y2 = (float(a) for a in args[:4])
        m = self.pag.mouse
        m.move(x1, y1)
        m.down()
        self.pag.wait_for_timeout(500)  # el tablero arrastra con el dedo a los 0,45 s
        for i in range(1, 11):
            m.move(x1 + (x2 - x1) * i / 10, y1 + (y2 - y1) * i / 10)
            self.pag.wait_for_timeout(40)
        m.up()
        self._calma()
        return f"Arrastré de ({x1:.0f},{y1:.0f}) a ({x2:.0f},{y2:.0f}). {self._info()}"


if __name__ == "__main__":
    main()

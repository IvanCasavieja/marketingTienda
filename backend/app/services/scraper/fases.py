"""
fases.py — Orquestador de scraping sin CLI.

Entrada única: run_full() — raspa las 4 fuentes completas y deja
los productos en la SQLite intermedia (store.DB_PATH).
Desde ahí, scraper_sync._sync_to_postgres() vuelca a PostgreSQL.
"""

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

from . import store
from .adapters import extraer, ProductRecord

_PKG_DIR  = Path(__file__).parent
_DATA_DIR = Path(os.environ.get("SCRAPER_DATA_DIR", "/tmp/scraper"))
_DATA_DIR.mkdir(parents=True, exist_ok=True)

CATEGORIAS_GDU_JSON = _PKG_DIR / "categorias_gdu.json"
PROGRESO_GDU        = _DATA_DIR / "progreso_gdu.json"
PROGRESO_TATA       = _DATA_DIR / "progreso_tata.json"
PROGRESO_FARMASHOP  = _DATA_DIR / "progreso_farmashop.json"
PROGRESO_TI         = _DATA_DIR / "progreso_ti.json"

DOMINIOS_GDU = {
    "Disco":  "https://www.disco.com.uy",
    "Devoto": "https://www.devoto.com.uy",
    "Geant":  "https://www.geant.com.uy",
}

TATA_FASE_1 = [
    ["frescos"], ["bebidas"], ["perfumeria"], ["textil"],
    ["limpieza"], ["congelados"],
]
TATA_FASE_2 = [
    ["bebes"], ["ferreteria"], ["mascotas"], ["tecnologia"],
    ["almacen", "desayuno"], ["almacen", "golosinas-y-chocolates"],
    ["almacen", "aceites-y-aderezos"], ["almacen", "snacks"],
    ["almacen", "conservas"], ["almacen", "pastas-y-salsas"],
    ["almacen", "arroz-harina-y-legumbres"], ["almacen", "panificados"],
    ["almacen", "sopas-caldos-y-pure"], ["almacen", "aceitunas-y-encurtidos"],
    ["almacen", "cigarros"], ["almacen", "pascuas"],
]
TATA_FASE_3 = [
    ["hogar-y-bazar"], ["jugueteria-y-libreria"],
    ["electrodomesticos-y-aires-ac-"], ["electronica-audio-y-video"],
    ["belleza-y-cuidado-personal"], ["deportes-y-fitness"],
    ["pequenos-electrodomesticos"], ["herramientas"], ["hogar-muebles-y-jardin"],
]

TATA_TODAS_CONOCIDAS: set = set()
for _f in [TATA_FASE_1, TATA_FASE_2, TATA_FASE_3]:
    for _c in _f:
        TATA_TODAS_CONOCIDAS.add("/".join(_c))
TATA_FASES_CONOCIDAS = {1: TATA_FASE_1, 2: TATA_FASE_2, 3: TATA_FASE_3}

TERMINOS_DESCUBRIMIENTO = [
    "heladera","lavarropas","microondas","television",
    "remera","pantalon","zapatilla","campera",
    "tablet","notebook","impresora",
    "pelota","juguete","bicicleta",
    "vitamina","crema","shampoo",
    "sarten","olla","plato","colchon",
]

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def cargar_progreso(path: Path) -> dict:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"completados": [], "total_guardados": 0}


def guardar_progreso(path: Path, prog: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(prog, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# GDU — Disco / Devoto / Géant (Blazor Server)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def slugs_gdu_unicos() -> tuple:
    with open(CATEGORIAS_GDU_JSON, encoding="utf-8") as f:
        mapeo = json.load(f)
    vistos: set = set()
    result = []
    for slugs in mapeo.values():
        for s in slugs:
            if s not in vistos:
                vistos.add(s)
                result.append(s)
    return tuple(result)


def slugs_por_fase_gdu() -> dict:
    todos = list(slugs_gdu_unicos())
    n     = len(todos)
    size  = (n + 3) // 4
    return {i + 1: todos[i * size:(i + 1) * size] for i in range(4)}


def link_a_url_producto(base: str, link: str) -> str | None:
    if not link.startswith("/product/"):
        return None
    sin_prefix = link.replace("/product/", "/", 1)
    partes = sin_prefix.rsplit("/", 1)
    if len(partes) != 2 or not partes[1].isdigit():
        return None
    return base + partes[0] + "-" + partes[1] + "/p"


def scroll_categoria(page, url: str, max_pasos: int = 60,
                     espera_ms: int = 700, paso_px: int = 400) -> set:
    page.goto(url, timeout=30000)
    page.wait_for_timeout(4000)
    vistos = set(re.findall(r'href="(/product/[^"]+)"', page.content()))
    sin_cambios = 0
    for _ in range(max_pasos):
        page.mouse.wheel(0, paso_px)
        page.wait_for_timeout(espera_ms)
        nuevos = set(re.findall(r'href="(/product/[^"]+)"', page.content()))
        sin_cambios = 0 if len(nuevos) != len(vistos) else sin_cambios + 1
        vistos = nuevos
        if sin_cambios >= 6:
            break
    return vistos


def extraer_lote_gdu(urls: list, workers: int = 4) -> tuple:
    records = []
    errores = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(extraer, url): url for url in urls}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                rec = fut.result()
                records.append(rec)
                if rec.error:
                    errores += 1
            except Exception as e:
                errores += 1
                log.warning("GDU extract error: %s", e)
            if i % 100 == 0:
                log.info("GDU: %d/%d extraidos", i, len(urls))
    guardados = store.guardar_bulk(records)
    return guardados, errores


def run_gdu_fase(fase: int):
    from playwright.sync_api import sync_playwright

    fases  = slugs_por_fase_gdu()
    slugs  = fases.get(fase)
    if not slugs:
        log.error("GDU: fase %d no existe", fase)
        return

    prog        = cargar_progreso(PROGRESO_GDU)
    completados = set(prog["completados"])
    todas       = [(slug, tienda, base) for slug in slugs
                   for tienda, base in DOMINIOS_GDU.items()]
    pendientes  = [(s, t, b) for s, t, b in todas if f"{t}::{s}" not in completados]

    log.info("GDU Fase %d: %d combinaciones, %d pendientes", fase, len(todas), len(pendientes))
    if not pendientes:
        log.info("GDU Fase %d: ya completada", fase)
        return

    fase_guardados = fase_errores = 0
    pendientes_por_tienda: dict = {}
    for slug, tienda, base in pendientes:
        pendientes_por_tienda.setdefault(tienda, []).append((slug, base))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        for tienda, items in pendientes_por_tienda.items():
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            try:
                for slug, base in items:
                    url = f"{base}/{slug}"
                    log.info("GDU [%s] %s", tienda, slug)
                    try:
                        links = scroll_categoria(page, url)
                        if links:
                            urls = [link_a_url_producto(base, lk) for lk in links]
                            urls = [u for u in urls if u]
                            g, e = extraer_lote_gdu(urls)
                            fase_guardados += g
                            fase_errores   += e
                            log.info("GDU [%s] %s: g=%d e=%d", tienda, slug, g, e)
                        prog["completados"].append(f"{tienda}::{slug}")
                        guardar_progreso(PROGRESO_GDU, prog)
                    except Exception as ex:
                        log.warning("GDU [%s] %s ERROR: %s", tienda, slug, str(ex)[:100])
            finally:
                page.close()
        browser.close()

    prog["total_guardados"] = prog.get("total_guardados", 0) + fase_guardados
    guardar_progreso(PROGRESO_GDU, prog)
    log.info("GDU Fase %d terminada: guardados=%d errores=%d", fase, fase_guardados, fase_errores)


# ---------------------------------------------------------------------------
# Ta-Ta — GraphQL API
# ---------------------------------------------------------------------------

def _guardar_productos_tata(resultado: dict, prog: dict) -> int:
    guardados = 0
    for slug, info in resultado.items():
        if "error" in info:
            log.warning("Tata %s ERROR: %s", slug, info["error"])
            continue
        prods = info.get("productos", [])
        records = [
            ProductRecord(
                tienda="Ta-Ta", url=pr["url"], nombre=pr["nombre"],
                precio=float(pr["precio"]) if pr["precio"] is not None else None,
                precio_lista=float(pr["precio_lista"]) if pr.get("precio_lista") is not None else None,
                sku=str(pr["sku"]) if pr["sku"] else None,
                barcode=str(pr["barcode"]) if pr.get("barcode") else None,
                marca=pr.get("marca"), categoria=slug,
            )
            for pr in prods
        ]
        guardados += store.guardar_bulk(records)
        prog["completados"].append(slug)
        guardar_progreso(PROGRESO_TATA, prog)
        log.info("Tata %s: %d productos", slug, len(prods))
    return guardados


def run_tata_fase(fase: int):
    if fase in (1, 2, 3):
        _run_tata_fase_conocida(fase)
    elif fase == 4:
        _run_tata_fase4_descubrimiento()
    else:
        log.error("Tata: fase %d no existe (hay 4)", fase)


def _run_tata_fase_conocida(fase: int):
    from .tata_graphql import bajar_varias

    categorias  = TATA_FASES_CONOCIDAS[fase]
    prog        = cargar_progreso(PROGRESO_TATA)
    completados = set(prog["completados"])
    pendientes  = [c for c in categorias if "/".join(c) not in completados]

    log.info("Tata Fase %d: %d categorias, %d pendientes", fase, len(categorias), len(pendientes))
    if not pendientes:
        log.info("Tata Fase %d: ya completada", fase)
        return

    resultado = bajar_varias(pendientes)
    guardados = _guardar_productos_tata(resultado, prog)
    prog["total_guardados"] = prog.get("total_guardados", 0) + guardados
    guardar_progreso(PROGRESO_TATA, prog)
    log.info("Tata Fase %d terminada: %d productos", fase, guardados)


def _run_tata_fase4_descubrimiento():
    import urllib.parse
    from .tata_graphql import bajar_categoria
    from playwright.sync_api import sync_playwright

    log.info("Tata Fase 4: descubrimiento dinámico")
    prog        = cargar_progreso(PROGRESO_TATA)
    completados = set(prog["completados"])
    BASE        = "https://www.tata.com.uy"

    def search_url(term):
        v = {"first": 1, "after": "0", "sort": "score_desc", "term": term,
             "selectedFacets": [
                 {"key": "channel", "value": '{"salesChannel":"4","regionId":""}'},
                 {"key": "locale",  "value": "es-uy"},
             ]}
        return f"{BASE}/api/graphql?operationName=ProductGalleryQuery&variables={urllib.parse.quote(json.dumps(v))}"

    nuevas_cats: dict = {}

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = b.new_page()
        page.goto(BASE, timeout=30000)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        page.wait_for_timeout(2000)

        for term in TERMINOS_DESCUBRIMIENTO:
            try:
                raw = page.evaluate(
                    "async (u) => (await fetch(u, {headers:{'content-type':'application/json'}})).text()",
                    search_url(term),
                )
                d = json.loads(raw)
                s = (d.get("data") or {}).get("search") or {}
                for f in s.get("facets", []):
                    if f.get("key") == "category-1":
                        for val in f.get("values", []):
                            cat = val["value"]
                            if cat not in TATA_TODAS_CONOCIDAS and cat not in completados:
                                nuevas_cats[cat] = val.get("quantity", 0)
                time.sleep(0.2)
            except Exception:
                pass
        page.close()

        guardados_total = 0
        for slug in list(nuevas_cats.keys()):
            if slug in completados:
                continue
            pg = b.new_page()
            try:
                pg.goto(BASE, timeout=30000)
                try:
                    pg.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass
                pg.wait_for_timeout(1500)
                prods, total = bajar_categoria(pg, [slug])
                records = [
                    ProductRecord(
                        tienda="Ta-Ta", url=pr["url"], nombre=pr["nombre"],
                        precio=float(pr["precio"]) if pr["precio"] is not None else None,
                        precio_lista=float(pr["precio_lista"]) if pr.get("precio_lista") is not None else None,
                        sku=str(pr["sku"]) if pr["sku"] else None,
                        barcode=str(pr["barcode"]) if pr.get("barcode") else None,
                        marca=pr.get("marca"), categoria=slug,
                    )
                    for pr in prods
                ]
                guardados_total += store.guardar_bulk(records)
                prog["completados"].append(slug)
                guardar_progreso(PROGRESO_TATA, prog)
                log.info("Tata [fase4] %s: %d/%d", slug, len(prods), total)
            except Exception as e:
                log.warning("Tata [fase4] %s ERROR: %s", slug, str(e)[:80])
            finally:
                pg.close()
        b.close()

    prog["total_guardados"] = prog.get("total_guardados", 0) + guardados_total
    guardar_progreso(PROGRESO_TATA, prog)
    log.info("Tata Fase 4 terminada: %d productos", guardados_total)


# ---------------------------------------------------------------------------
# Farmashop — Magento 2.4 GraphQL
# ---------------------------------------------------------------------------

def _guardar_productos_farmashop(resultado: dict, prog: dict) -> int:
    guardados = 0
    for nombre_cat, info in resultado.items():
        if "error" in info:
            log.warning("Farmashop %s ERROR: %s", nombre_cat, info["error"])
            continue
        prods = info.get("productos", [])
        records = [
            ProductRecord(
                tienda="Farmashop", url=pr["url"], nombre=pr["nombre"],
                precio=pr["precio"], precio_lista=pr.get("precio_lista"),
                sku=pr.get("sku"), barcode=None,
                marca=pr.get("marca"), categoria=pr.get("categoria"),
            )
            for pr in prods
        ]
        guardados += store.guardar_bulk(records)
        prog["completados"].append(nombre_cat)
        guardar_progreso(PROGRESO_FARMASHOP, prog)
        log.info("Farmashop %s: %d productos", nombre_cat, len(prods))
    return guardados


def run_farmashop_fase(fase: int):
    from .farmashop_graphql import bajar_varias, FARMASHOP_FASES

    cats = FARMASHOP_FASES.get(fase)
    if not cats:
        log.error("Farmashop: fase %d no existe", fase)
        return

    prog        = cargar_progreso(PROGRESO_FARMASHOP)
    completados = set(prog["completados"])
    pendientes  = [c for c in cats if c not in completados]

    log.info("Farmashop Fase %d: %d cats, %d pendientes", fase, len(cats), len(pendientes))
    if not pendientes:
        log.info("Farmashop Fase %d: ya completada", fase)
        return

    resultado = bajar_varias(pendientes)
    guardados = _guardar_productos_farmashop(resultado, prog)
    prog["total_guardados"] = prog.get("total_guardados", 0) + guardados
    guardar_progreso(PROGRESO_FARMASHOP, prog)
    log.info("Farmashop Fase %d terminada: %d productos", fase, guardados)


# ---------------------------------------------------------------------------
# Tienda Inglesa — HTML server-rendered (Hanoi/iMasDev)
# ---------------------------------------------------------------------------

def _guardar_productos_ti(resultado: dict, prog: dict) -> int:
    guardados = 0
    for slug, info in resultado.items():
        if "error" in info:
            log.warning("TI %s ERROR: %s", slug, info["error"])
            continue
        prods = info.get("productos", [])
        records = [
            ProductRecord(
                tienda="Tienda Inglesa", url=pr["url"], nombre=pr["nombre"],
                precio=float(pr["precio"]) if pr["precio"] is not None else None,
                precio_lista=float(pr["precio_lista"]) if pr.get("precio_lista") is not None else None,
                sku=str(pr["sku"]) if pr.get("sku") else None,
                barcode=None, marca=None, categoria=slug,
            )
            for pr in prods
        ]
        guardados += store.guardar_bulk(records)
        prog["completados"].append(slug)
        guardar_progreso(PROGRESO_TI, prog)
        log.info("TI %s: %d productos", slug, len(prods))
    return guardados


def run_ti_fase(fase: int):
    from .tienda_inglesa import bajar_varias, TI_FASES

    cats = TI_FASES.get(fase)
    if not cats:
        log.error("TI: fase %d no existe", fase)
        return

    prog        = cargar_progreso(PROGRESO_TI)
    completados = set(prog["completados"])
    pendientes  = [c for c in cats if c not in completados]

    log.info("TI Fase %d: %d cats, %d pendientes", fase, len(cats), len(pendientes))
    if not pendientes:
        log.info("TI Fase %d: ya completada", fase)
        return

    resultado = bajar_varias(pendientes)
    guardados = _guardar_productos_ti(resultado, prog)
    prog["total_guardados"] = prog.get("total_guardados", 0) + guardados
    guardar_progreso(PROGRESO_TI, prog)
    log.info("TI Fase %d terminada: %d productos", fase, guardados)


# ---------------------------------------------------------------------------
# Full scan
# ---------------------------------------------------------------------------

def run_full():
    """Raspa Tata, Farmashop y GDU. Tienda Inglesa deshabilitada (170k productos, cobertura GDU aún baja)."""
    log.info("=== FULL SCAN INICIADO ===")

    # Limpiar SQLite para empezar fresco
    store.limpiar()

    for fase in (1, 2, 3, 4):
        run_tata_fase(fase)
    for fase in (1, 2, 3, 4):
        run_farmashop_fase(fase)
    for fase in (1, 2, 3, 4):
        run_gdu_fase(fase)

    totales = store.contar()
    total   = sum(totales.values())
    log.info("=== FULL SCAN COMPLETADO — %d productos ===", total)
    for t, n in sorted(totales.items()):
        log.info("  %s: %d", t, n)
    return total

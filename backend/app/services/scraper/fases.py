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
from functools import lru_cache
from pathlib import Path

from . import store
from .adapters import ProductRecord

_PKG_DIR  = Path(__file__).parent
_DATA_DIR = Path(os.environ.get("SCRAPER_DATA_DIR", "/tmp/scraper"))
_DATA_DIR.mkdir(parents=True, exist_ok=True)

CATEGORIAS_GDU_JSON = _PKG_DIR / "categorias_gdu.json"
PROGRESO_GDU        = _DATA_DIR / "progreso_gdu.json"
PROGRESO_GDU_REST   = _DATA_DIR / "progreso_gdu_rest.json"
PROGRESO_TATA       = _DATA_DIR / "progreso_tata.json"
PROGRESO_FARMASHOP  = _DATA_DIR / "progreso_farmashop.json"
PROGRESO_TI         = _DATA_DIR / "progreso_ti.json"
PROGRESO_BOTIGA     = _DATA_DIR / "progreso_botiga.json"
PROGRESO_PIGALLE    = _DATA_DIR / "progreso_pigalle.json"
PROGRESO_ELDORADO   = _DATA_DIR / "progreso_eldorado.json"

DOMINIOS_GDU = {
    "Disco":  "https://www.disco.com.uy",
    "Devoto": "https://www.devoto.com.uy",
    "Geant":  "https://www.geant.com.uy",
}

TATA_TODAS_CATS: list[list] = [
    ["frescos"], ["bebidas"], ["perfumeria"], ["textil"],
    ["limpieza"], ["congelados"],
    ["bebes"], ["ferreteria"], ["mascotas"], ["tecnologia"],
    ["almacen", "desayuno"], ["almacen", "golosinas-y-chocolates"],
    ["almacen", "aceites-y-aderezos"], ["almacen", "snacks"],
    ["almacen", "conservas"], ["almacen", "pastas-y-salsas"],
    ["almacen", "arroz-harina-y-legumbres"], ["almacen", "panificados"],
    ["almacen", "sopas-caldos-y-pure"], ["almacen", "aceitunas-y-encurtidos"],
    ["almacen", "cigarros"], ["almacen", "pascuas"],
    ["hogar-y-bazar"], ["jugueteria-y-libreria"],
    ["electrodomesticos-y-aires-ac-"], ["electronica-audio-y-video"],
    ["belleza-y-cuidado-personal"], ["deportes-y-fitness"],
    ["pequenos-electrodomesticos"], ["herramientas"], ["hogar-muebles-y-jardin"],
]

TATA_TODAS_CONOCIDAS: set = {"/".join(c) for c in TATA_TODAS_CATS}

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
    for k, v in mapeo.items():
        if k.startswith("_"):   # ignorar claves de metadatos (_nota, etc.)
            continue
        slugs = v if isinstance(v, list) else [v]
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


_JS_EXTRAER_CARDS = """
() => {
    const items = document.querySelectorAll('.product-item');
    return Array.from(items).map(item => {
        const linkEl = item.querySelector('h3 a') || item.querySelector('figure a');
        const href = linkEl ? linkEl.getAttribute('href') : null;
        if (!href || !href.startsWith('/product/')) return null;

        const h3El   = item.querySelector('h3 a');
        const imgEl  = item.querySelector('figure img');
        const nombre = (h3El  ? h3El.textContent.trim()          : null) ||
                       (imgEl ? imgEl.getAttribute('alt')         : null);

        const dp = item.querySelector('.desc-prices');
        let precio_str = null, precio_lista_str = null;
        if (dp) {
            const valEl = dp.querySelector('.val');
            if (valEl) precio_str = valEl.textContent.trim();
            const oldEl = dp.querySelector('.price-old');
            if (oldEl) precio_lista_str = oldEl.textContent.replace(/[^0-9,.]/g, '');
        }
        const brandEl = item.querySelector('.prod-cats a');
        return { href, nombre, precio_str, precio_lista_str,
                 marca: brandEl ? brandEl.textContent.trim() : null };
    }).filter(Boolean);
}
"""


def _parse_precio(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return float(s.replace(".", "").replace(",", "."))
    except (ValueError, AttributeError):
        return None


def scroll_categoria_con_datos(page, url: str, tienda: str, base_url: str,
                                max_pasos: int = 300, espera_ms: int = 900,
                                paso_px: int = 800, sin_cambios_max: int = 30) -> list:
    """Scroll GDU category page y extrae datos de cada product card inline.
    No hace requests adicionales por producto — todo viene del DOM del listado.
    Retorna lista de ProductRecord listos para guardar.

    sin_cambios_max=30 (27s de tolerancia) cubre:
    - Categorías con inicio tardío (ej: ferreteria necesita ~15 pasos antes del 1er batch)
    - 3 sesiones Blazor en paralelo (servidor 2x más lento bajo carga concurrente)
    max_pasos=300 garantiza completar categorías grandes (~1500 productos = ~75 batches × 2 pasos)
    """
    resp = page.goto(url, timeout=30000)
    if resp and resp.status >= 400:
        log.warning("GDU: %s HTTP %d — saltando", url, resp.status)
        return []
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    # Espera fija post-carga: le da tiempo al componente Blazor de virtual scroll
    # para inicializarse antes de empezar el loop. Sin esto, bajo carga paralela
    # el scroll puede empezar antes de que el componente esté montado.
    page.wait_for_timeout(2500)

    categoria_slug = url.replace(base_url + "/", "")
    acumulados: dict[str, dict] = {}   # href -> card data

    def _extraer():
        try:
            for card in page.evaluate(_JS_EXTRAER_CARDS):
                href = card.get("href")
                if href and href not in acumulados:
                    acumulados[href] = card
        except Exception:
            pass

    _extraer()
    vistos = set(acumulados.keys())
    sin_cambios = 0

    for _ in range(max_pasos):
        page.mouse.wheel(0, paso_px)
        page.wait_for_timeout(espera_ms)
        _extraer()
        nuevos = set(acumulados.keys())
        sin_cambios = 0 if nuevos != vistos else sin_cambios + 1
        vistos = nuevos
        if sin_cambios >= sin_cambios_max:
            break

    records = []
    for href, card in acumulados.items():
        url_prod = link_a_url_producto(base_url, href)
        if not url_prod:
            continue
        records.append(ProductRecord(
            tienda=tienda,
            url=url_prod,
            nombre=card.get("nombre"),
            precio=_parse_precio(card.get("precio_str")),
            precio_lista=_parse_precio(card.get("precio_lista_str")),
            marca=card.get("marca"),
            categoria=categoria_slug,
        ))
    return records


def run_gdu_fase(fase: int):
    import threading
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

    pendientes_por_tienda: dict = {}
    for slug, tienda, base in pendientes:
        pendientes_por_tienda.setdefault(tienda, []).append((slug, base))

    prog_lock   = threading.Lock()
    resultados  = {}  # tienda → (guardados, errores)

    def scroll_tienda(tienda: str, items: list):
        g_total = 0
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            for slug, base in items:
                url = f"{base}/{slug}"
                log.info("GDU [%s] %s", tienda, slug)
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                try:
                    records = scroll_categoria_con_datos(page, url, tienda, base)
                    g = store.guardar_bulk(records) if records else 0
                    g_total += g
                    log.info("GDU [%s] %s: %d productos", tienda, slug, g)
                    with prog_lock:
                        prog["completados"].append(f"{tienda}::{slug}")
                        guardar_progreso(PROGRESO_GDU, prog)
                except Exception as ex:
                    log.warning("GDU [%s] %s ERROR: %s", tienda, slug, str(ex)[:150])
                finally:
                    page.close()
            browser.close()
        resultados[tienda] = (g_total, 0)

    threads = [
        threading.Thread(target=scroll_tienda, args=(tienda, items), name=f"gdu-{tienda}", daemon=True)
        for tienda, items in pendientes_por_tienda.items()
    ]
    log.info("GDU Fase %d: corriendo %d tiendas en paralelo", fase, len(threads))
    for i, t in enumerate(threads):
        t.start()
        if i < len(threads) - 1:
            time.sleep(15)  # stagger: evita que 3 browsers golpeen el servidor al mismo tiempo
    for t in threads:
        t.join()

    total_g = sum(g for g, _ in resultados.values())
    total_e = sum(e for _, e in resultados.values())
    prog["total_guardados"] = prog.get("total_guardados", 0) + total_g
    guardar_progreso(PROGRESO_GDU, prog)
    log.info("GDU Fase %d terminada: guardados=%d errores=%d", fase, total_g, total_e)


# ---------------------------------------------------------------------------
# GDU REST — Disco / Devoto / Géant vía microservicios Azure (sin Playwright)
# ---------------------------------------------------------------------------

def run_gdu_rest_fase(fase: int) -> None:
    """
    Raspa GDU (Disco/Devoto/Géant) via REST API para un rango de páginas.

    Un ProductRecord por (producto × sucursal). La URL lleva ?sc=<branch_id>
    para que el sitio muestre el precio de esa sucursal.

    Fases: 4 rangos de ~132 páginas sobre las ~527 del catálogo completo.
    """
    from .gdu_rest import scan_fase, GDU_REST_PHASES

    rango = GDU_REST_PHASES.get(fase)
    if not rango:
        log.error("GDU REST: fase %d no existe (hay 4)", fase)
        return

    page_from, page_to = rango
    prog = cargar_progreso(PROGRESO_GDU_REST)

    if fase in prog.get("fases_completadas", []):
        log.info("GDU REST: fase %d ya completada", fase)
        return

    log.info("GDU REST: fase %d — páginas %s–%s", fase, page_from, page_to or "fin")

    records = scan_fase(page_from, page_to, cache_dir=_DATA_DIR)
    guardados = store.guardar_bulk(records)

    fases_ok = prog.get("fases_completadas", [])
    fases_ok.append(fase)
    prog["fases_completadas"]  = fases_ok
    prog["total_guardados"]    = prog.get("total_guardados", 0) + guardados
    guardar_progreso(PROGRESO_GDU_REST, prog)
    log.info("GDU REST: fase %d completada — %d registros guardados", fase, guardados)


# ---------------------------------------------------------------------------
# Ta-Ta — GraphQL API
# ---------------------------------------------------------------------------

def _guardar_productos_tata(resultado: dict, prog: dict,
                            sucursal: dict | None = None) -> int:
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
                sucursal_id=pr.get("sucursal_id"),
                sucursal_nombre=pr.get("sucursal_nombre"),
            )
            for pr in prods
        ]
        guardados += store.guardar_bulk(records)
        log.info("Tata [%s] %s: %d productos",
                 sucursal["nombre"] if sucursal else "–", slug, len(prods))
    return guardados


def run_tata_fase(fase: int):
    """
    Raspa Ta-Ta con requests — las 15 sucursales en paralelo en una sola llamada.
    El parámetro `fase` se ignora (se mantiene por compatibilidad con run_scan.py).
    Solo corre en la primera llamada; las restantes detectan que ya está completo.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from .tata_graphql import SUCURSALES, bajar_sucursal

    prog        = cargar_progreso(PROGRESO_TATA)
    completados = set(prog.get("completados_suc", []))
    pendientes  = [s for s in SUCURSALES if s["seller_id"] not in completados]

    if not pendientes:
        log.info("Tata: todas las sucursales ya completadas (fase %d ignorada)", fase)
        return

    log.info("Tata: %d sucursales en paralelo", len(pendientes))

    prog_lock       = threading.Lock()
    guardados_total = 0

    def _procesar_sucursal(suc: dict) -> int:
        log.info("Tata [%s]: scraping %d categorías", suc["nombre"], len(TATA_TODAS_CATS))
        resultado = bajar_sucursal(suc, TATA_TODAS_CATS)
        guardados = _guardar_productos_tata(resultado, {}, sucursal=suc)
        with prog_lock:
            prog.setdefault("completados_suc", []).append(suc["seller_id"])
            prog["total_guardados"] = prog.get("total_guardados", 0) + guardados
            guardar_progreso(PROGRESO_TATA, prog)
        log.info("Tata [%s]: %d productos guardados", suc["nombre"], guardados)
        return guardados

    with ThreadPoolExecutor(max_workers=len(pendientes)) as ex:
        futures = {ex.submit(_procesar_sucursal, suc): suc for suc in pendientes}
        for f in as_completed(futures):
            try:
                guardados_total += f.result()
            except Exception as exc:
                suc = futures[f]
                log.error("Tata [%s]: error fatal — %s", suc["nombre"], exc, exc_info=True)

    log.info("Tata: %d sucursales completadas — %d productos totales", len(pendientes), guardados_total)



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
# Botiga — Magento 2.4 GraphQL (mismo backend que Farmashop, distinto store-view)
# ---------------------------------------------------------------------------

def _guardar_productos_botiga(resultado: dict, prog: dict) -> int:
    from .botiga_graphql import validar_urls

    # Juntar todos los productos de la fase para validar URLs en un solo batch
    todos_prods = []
    cats_ok = []
    for nombre_cat, info in resultado.items():
        if "error" in info:
            log.warning("Botiga %s ERROR: %s", nombre_cat, info["error"])
            continue
        todos_prods.extend(info.get("productos", []))
        cats_ok.append(nombre_cat)

    if not todos_prods:
        return 0

    # Validar URLs — filtra 404s y reporta conteo
    prods_validos, n_404 = validar_urls(todos_prods)
    if n_404:
        prog["urls_404"] = prog.get("urls_404", 0) + n_404
        guardar_progreso(PROGRESO_BOTIGA, prog)

    # Agrupar de vuelta por categoría para guardar
    validos_set = {p["url"] for p in prods_validos}
    guardados = 0
    for nombre_cat in cats_ok:
        prods = [p for p in resultado[nombre_cat].get("productos", []) if p["url"] in validos_set]
        records = [
            ProductRecord(
                tienda="Botiga", url=pr["url"], nombre=pr["nombre"],
                precio=pr["precio"], precio_lista=pr.get("precio_lista"),
                sku=pr.get("sku"), barcode=None,
                marca=pr.get("marca"), categoria=pr.get("categoria"),
            )
            for pr in prods
        ]
        guardados += store.guardar_bulk(records)
        prog["completados"].append(nombre_cat)
        guardar_progreso(PROGRESO_BOTIGA, prog)
        log.info("Botiga %s: %d productos (válidos)", nombre_cat, len(prods))

    log.info("Botiga fase: %d guardados, %d URLs 404 filtradas", guardados, n_404)
    return guardados


def run_botiga_fase(fase: int):
    from .botiga_graphql import bajar_varias, BOTIGA_FASES

    cats = BOTIGA_FASES.get(fase)
    if not cats:
        log.error("Botiga: fase %d no existe", fase)
        return

    prog        = cargar_progreso(PROGRESO_BOTIGA)
    completados = set(prog["completados"])
    pendientes  = [c for c in cats if c not in completados]

    log.info("Botiga Fase %d: %d cats, %d pendientes", fase, len(cats), len(pendientes))
    if not pendientes:
        log.info("Botiga Fase %d: ya completada", fase)
        return

    resultado = bajar_varias(pendientes)
    guardados = _guardar_productos_botiga(resultado, prog)
    prog["total_guardados"] = prog.get("total_guardados", 0) + guardados
    guardar_progreso(PROGRESO_BOTIGA, prog)
    log.info("Botiga Fase %d terminada: %d productos", fase, guardados)


# ---------------------------------------------------------------------------
# Pigalle — Magento 2.4 HTML (GraphQL roto server-side)
# ---------------------------------------------------------------------------

def _guardar_productos_pigalle(resultado: dict, prog: dict) -> int:
    guardados = 0
    for nombre_cat, info in resultado.items():
        if "error" in info:
            log.warning("Pigalle %s ERROR: %s", nombre_cat, info["error"])
            continue
        prods = info.get("productos", [])
        records = [
            ProductRecord(
                tienda="Pigalle", url=pr["url"], nombre=pr["nombre"],
                precio=pr["precio"], precio_lista=pr.get("precio_lista"),
                sku=None, barcode=None,
                marca=None, categoria=pr.get("categoria"),
            )
            for pr in prods
        ]
        guardados += store.guardar_bulk(records)
        prog["completados"].append(nombre_cat)
        guardar_progreso(PROGRESO_PIGALLE, prog)
        log.info("Pigalle %s: %d productos", nombre_cat, len(prods))
    return guardados


def run_pigalle_fase(fase: int):
    from .pigalle_html import bajar_varias, PIGALLE_FASES

    cats = PIGALLE_FASES.get(fase)
    if not cats:
        log.error("Pigalle: fase %d no existe", fase)
        return

    prog        = cargar_progreso(PROGRESO_PIGALLE)
    completados = set(prog["completados"])
    pendientes  = [c for c in cats if c not in completados]

    log.info("Pigalle Fase %d: %d cats, %d pendientes", fase, len(cats), len(pendientes))
    if not pendientes:
        log.info("Pigalle Fase %d: ya completada", fase)
        return

    resultado = bajar_varias(pendientes)
    guardados = _guardar_productos_pigalle(resultado, prog)
    prog["total_guardados"] = prog.get("total_guardados", 0) + guardados
    guardar_progreso(PROGRESO_PIGALLE, prog)
    log.info("Pigalle Fase %d terminada: %d productos", fase, guardados)


# ---------------------------------------------------------------------------
# El Dorado — VTEX IO Catalog System REST (sin autenticación)
# ---------------------------------------------------------------------------

_ELDORADO_PHASES_CACHE: dict | None = None


def _get_eldorado_phases() -> dict:
    """Descarga el árbol de categorías una sola vez y lo cachea en memoria."""
    global _ELDORADO_PHASES_CACHE
    if _ELDORADO_PHASES_CACHE is None:
        from .eldorado_rest import build_phases
        _ELDORADO_PHASES_CACHE = build_phases(4)
    return _ELDORADO_PHASES_CACHE


def run_eldorado_fase(fase: int) -> None:
    """
    Raspa El Dorado vía VTEX IO Intelligent Search con regionId por sucursal.
    17 tiendas en Uruguay divididas en 4 fases de 4-5 sucursales c/u.
    Una fila por (producto × sucursal) — precios varían por departamento.
    """
    from .eldorado_rest import scan_fase

    prog = cargar_progreso(PROGRESO_ELDORADO)

    if fase in prog.get("fases_completadas", []):
        log.info("ElDorado: fase %d ya completada", fase)
        return

    fases = _get_eldorado_phases()
    records   = scan_fase(fase, fases)
    guardados = store.guardar_bulk(records)

    fases_ok = prog.get("fases_completadas", [])
    fases_ok.append(fase)
    prog["fases_completadas"] = fases_ok
    prog["total_guardados"]   = prog.get("total_guardados", 0) + guardados
    guardar_progreso(PROGRESO_ELDORADO, prog)
    log.info("ElDorado: fase %d completada — %d registros guardados", fase, guardados)


# ---------------------------------------------------------------------------
# Full scan
# ---------------------------------------------------------------------------

def run_full():
    """Raspa Tata, Farmashop, GDU REST, Botiga, Pigalle y El Dorado."""
    log.info("=== FULL SCAN INICIADO ===")

    store.limpiar()
    for _prog in (PROGRESO_GDU, PROGRESO_TATA, PROGRESO_FARMASHOP, PROGRESO_TI,
                  PROGRESO_BOTIGA, PROGRESO_PIGALLE, PROGRESO_ELDORADO):
        if _prog.exists():
            _prog.unlink()

    for fase in (1, 2, 3, 4):
        run_tata_fase(fase)
    for fase in (1, 2, 3, 4):
        run_farmashop_fase(fase)
    for fase in (1, 2, 3, 4):
        run_gdu_fase(fase)
    for fase in (1, 2, 3, 4):
        run_botiga_fase(fase)
    for fase in (1, 2, 3, 4):
        run_pigalle_fase(fase)
    for fase in (1, 2, 3, 4):
        run_eldorado_fase(fase)

    totales = store.contar()
    total   = sum(totales.values())
    log.info("=== FULL SCAN COMPLETADO — %d productos ===", total)
    for t, n in sorted(totales.items()):
        log.info("  %s: %d", t, n)
    return total


def run_gdu_only() -> int:
    """Raspa solo GDU (Geant, Disco, Devoto) y deja los productos en SQLite.
    No toca Tata ni Farmashop. El sync posterior hace upsert por URL,
    actualizando solo registros GDU sin duplicar ni borrar los de otras tiendas."""
    log.info("=== GDU SCAN INICIADO ===")

    store.limpiar()
    if PROGRESO_GDU.exists():
        PROGRESO_GDU.unlink()

    for fase in (1, 2, 3, 4):
        run_gdu_fase(fase)

    totales = store.contar()
    total   = sum(totales.values())
    log.info("=== GDU SCAN COMPLETADO — %d productos ===", total)
    for t, n in sorted(totales.items()):
        log.info("  %s: %d", t, n)
    return total

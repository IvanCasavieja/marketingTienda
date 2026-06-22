"""
pigalle_html.py — scraper de Pigalle (www.pigalle.com.uy) via Playwright + BeautifulSoup.

El GraphQL de Pigalle está roto server-side. Las páginas de categoría están protegidas
por Cloudflare, por lo que se requiere un browser real (Playwright/Chromium).
Magento 2 Luma: 26 productos por página, paginación ?p=N.
Precio en atributo data-price-amount (valor en UYU entero).
"""

import time
import random
import logging
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_BASE_URL = "https://www.pigalle.com.uy"

# Categorías navegables de Pigalle
CATEGORIAS = [
    "fragancias",
    "maquillaje",
    "cuidado-de-la-piel",
    "salud",
    "cuidado-personal",
    "cuidado-capilar",
    "bebe-y-mama",
    "limpieza-y-hogar",
    "incontinencia-adulto",
    "cuidado-oral",
]

PIGALLE_FASE_1 = ["fragancias", "maquillaje", "cuidado-de-la-piel"]
PIGALLE_FASE_2 = ["salud", "cuidado-personal", "cuidado-capilar"]
PIGALLE_FASE_3 = ["bebe-y-mama", "limpieza-y-hogar"]
PIGALLE_FASE_4 = ["incontinencia-adulto", "cuidado-oral"]

PIGALLE_FASES = {
    1: PIGALLE_FASE_1,
    2: PIGALLE_FASE_2,
    3: PIGALLE_FASE_3,
    4: PIGALLE_FASE_4,
}


def _extraer_items(soup: BeautifulSoup, categoria: str) -> list:
    productos = []
    for li in soup.select("li.product-item"):
        link = li.select_one("a.product-item-link")
        if not link:
            continue

        nombre = link.get_text(strip=True) or None
        url    = link.get("href") or ""
        if not url:
            continue

        final_el   = li.select_one('[data-price-type="finalPrice"]')
        regular_el = li.select_one('[data-price-type="regularPrice"]')

        precio       = None
        precio_lista = None
        if final_el and final_el.get("data-price-amount"):
            try:
                precio = float(final_el["data-price-amount"])
            except (ValueError, TypeError):
                pass
        if regular_el and regular_el.get("data-price-amount"):
            try:
                val = float(regular_el["data-price-amount"])
                if val != precio:
                    precio_lista = val
            except (ValueError, TypeError):
                pass

        productos.append({
            "tienda":       "Pigalle",
            "nombre":       nombre,
            "precio":       precio,
            "precio_lista": precio_lista,
            "sku":          None,
            "barcode":      None,
            "marca":        None,
            "categoria":    categoria,
            "url":          url,
        })
    return productos


def _esperar_productos(page) -> bool:
    """Espera hasta que los items de producto estén presentes en el DOM."""
    try:
        page.wait_for_selector("li.product-item", timeout=15000)
        return True
    except Exception:
        return False


def bajar_categoria(categoria: str, page=None) -> tuple:
    """Descarga todos los productos de una categoría.
    Si se provee un page de Playwright ya abierto, lo reutiliza (más eficiente).
    Devuelve (lista_productos, total_declarado).
    """
    if page is not None:
        return _bajar_con_page(categoria, page)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            result = _bajar_con_page(categoria, pg)
        finally:
            pg.close()
            browser.close()
    return result


def _bajar_con_page(categoria: str, page) -> tuple:
    productos = []

    # Página 1 (sin parámetro para evitar redirect o cache diferente)
    url_p1 = f"{_BASE_URL}/{categoria}"
    try:
        page.goto(url_p1, timeout=30000)
    except Exception as e:
        log.warning("Pigalle [%s] goto failed: %s", categoria, str(e)[:80])
        return [], 0

    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass

    if not _esperar_productos(page):
        log.warning("Pigalle [%s]: sin productos en página 1", categoria)
        return [], 0

    soup  = BeautifulSoup(page.content(), "html.parser")
    items = _extraer_items(soup, categoria)
    productos.extend(items)

    pagina = 2
    while True:
        next_btn = soup.select_one("li.pages-item-next a")
        if not next_btn:
            break

        time.sleep(random.uniform(1.0, 2.0))
        url_pn = f"{_BASE_URL}/{categoria}?p={pagina}"
        try:
            page.goto(url_pn, timeout=30000)
        except Exception as e:
            log.warning("Pigalle [%s] p%d goto failed: %s", categoria, pagina, str(e)[:80])
            break

        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        if not _esperar_productos(page):
            break

        soup  = BeautifulSoup(page.content(), "html.parser")
        items = _extraer_items(soup, categoria)
        if not items:
            break

        productos.extend(items)
        pagina += 1

    return productos, len(productos)


def bajar_varias(categorias: list) -> dict:
    """Baja todas las categorías con un único browser Playwright (más eficiente)."""
    from playwright.sync_api import sync_playwright

    resultado = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            for cat in categorias:
                try:
                    prods, total = _bajar_con_page(cat, page)
                    log.info("Pigalle %s: %d productos", cat, len(prods))
                    print(f"  Pigalle {cat}: {len(prods)} productos", flush=True)
                    resultado[cat] = {"productos": prods, "total_declarado": total}
                except Exception as e:
                    log.warning("Pigalle %s ERROR: %s", cat, str(e)[:80])
                    print(f"  Pigalle {cat}: ERROR {str(e)[:80]}", flush=True)
                    resultado[cat] = {"error": str(e)}
                time.sleep(random.uniform(2.0, 3.5))
        finally:
            page.close()
            browser.close()

    return resultado

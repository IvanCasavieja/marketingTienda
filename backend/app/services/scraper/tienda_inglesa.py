"""
tienda_inglesa.py — Scraper de Tienda Inglesa (plataforma Hanoi/iMasDev).

Extrae productos de las 14 categorías top-level via Playwright.
HTML server-rendered: span.ProductPrice = precio actual,
span.wTxtProductPriceBefore = precio de lista (cuando hay descuento).
Paginación: /supermercado/categoria/{slug}/busqueda?0,0,*:*,{id},0,0,,,false,,,{page},1
60 items/página.
"""

import re
import time
from typing import Optional

BASE_URL = "https://www.tiendainglesa.com.uy"
ITEMS_POR_PAGINA = 60

CATEGORIAS_TI = [
    ("almacen",             78),
    ("bebes",              529),
    ("bebidas",           1001),
    ("congelados",         181),
    ("deportes-y-fitness", 4677),
    ("electro-y-tecnologia", 302),
    ("ferreteria",         379),
    ("frescos",           1894),
    ("hogar-y-tiempo-libre", 1005),
    ("jugueteria",         618),
    ("limpieza",          1895),
    ("papeleria",         4131),
    ("perfumeria",         569),
    ("textiles",          1008),
]

# 4 fases de 3-4 categorías cada una
TI_FASE_1 = ["almacen", "frescos", "bebidas", "congelados"]
TI_FASE_2 = ["limpieza", "perfumeria", "bebes", "textiles"]
TI_FASE_3 = ["hogar-y-tiempo-libre", "deportes-y-fitness", "ferreteria", "papeleria"]
TI_FASE_4 = ["electro-y-tecnologia", "jugueteria"]

TI_FASES = {1: TI_FASE_1, 2: TI_FASE_2, 3: TI_FASE_3, 4: TI_FASE_4}

_CAT_MAP = {slug: cat_id for slug, cat_id in CATEGORIAS_TI}


def _pagina_url(slug: str, cat_id: int, pagina: int) -> str:
    return (
        f"{BASE_URL}/supermercado/categoria/{slug}"
        f"/busqueda?0,0,*%3A*,{cat_id},0,0,,,false,,,,{pagina}"
    )


def _extraer_productos_js(page) -> list:
    """Extrae todos los productos de la página actual vía JS evaluate."""
    return page.evaluate("""() => {
        const results = [];
        const sections = document.querySelectorAll('.card-product-section');
        for (const sec of sections) {
            const nameEl = sec.querySelector('.card-product-name');
            const link = sec.querySelector('a[href*=".producto"]');
            const priceEl = sec.querySelector('span.ProductPrice');
            const listEl = sec.querySelector('span.wTxtProductPriceBefore');

            const href = link ? link.getAttribute('href') : null;
            if (!href || !nameEl) continue;

            // Extract numeric product ID from URL (?12345,,cat)
            const idMatch = href.match(/[?](\\d+)/);

            // Parse price: "$ 199" → 199.0
            function parsePrice(el) {
                if (!el) return null;
                const m = el.innerText.replace(/[$.]/g, '').replace(',', '.').trim().match(/[0-9]+/);
                return m ? parseFloat(m[0]) : null;
            }

            results.push({
                nombre: nameEl.innerText.trim(),
                href: href,
                sku: idMatch ? idMatch[1] : null,
                precio: parsePrice(priceEl),
                precio_lista: parsePrice(listEl),
            });
        }
        return results;
    }""")


def _contar_paginas(page) -> int:
    """Detecta el número de páginas desde los links de paginación."""
    return page.evaluate("""() => {
        const links = [...document.querySelectorAll('a[href*="busqueda"]')];
        let max = 1;
        for (const a of links) {
            const m = a.href.match(/,(\\d+)$/);
            if (m) max = Math.max(max, parseInt(m[1]));
        }
        return max;
    }""")


def bajar_categoria(page, slug: str, cat_id: Optional[int] = None) -> tuple:
    """
    Descarga todos los productos de una categoría.
    Retorna (lista_de_productos, total).
    """
    if cat_id is None:
        cat_id = _CAT_MAP.get(slug)
    if cat_id is None:
        return [], 0

    todos = []
    max_paginas = None

    for pag in range(1, 300):
        url = _pagina_url(slug, cat_id, pag)
        for intento in range(3):
            try:
                page.goto(url, timeout=30000)
                page.wait_for_load_state("networkidle", timeout=12000)
                break
            except Exception as e:
                if intento == 2:
                    print(f"    [TI] {slug} p{pag} error tras 3 intentos: {e}", flush=True)
                    return todos, len(todos)
                time.sleep(2)

        if max_paginas is None:
            max_paginas = _contar_paginas(page)

        productos_pag = _extraer_productos_js(page)
        if not productos_pag:
            break

        for pr in productos_pag:
            # Build clean URL: base + href, strip campaign params
            href_clean = re.sub(r',,\d+(&.*)?$', '', pr["href"])
            pr["url"] = BASE_URL + href_clean
            pr["categoria"] = slug
        todos.extend(productos_pag)

        print(f"    [TI] {slug} p{pag}/{max_paginas}: {len(productos_pag)} prods (total: {len(todos)})", flush=True)

        if pag >= max_paginas:
            break
        time.sleep(0.5)

    return todos, len(todos)


def bajar_varias(slugs: list, browser=None) -> dict:
    """
    Descarga múltiples categorías con un solo browser.
    Retorna dict: slug → {"productos": [...], "total": N} | {"error": "..."}
    """
    from playwright.sync_api import sync_playwright

    resultado = {}
    _own_browser = browser is None

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]) if _own_browser else browser
        pg = b.new_page(viewport={"width": 1280, "height": 900})
        # Load homepage first to set cookies/session
        try:
            pg.goto(BASE_URL, timeout=20000)
            pg.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        pg.wait_for_timeout(1500)

        for slug in slugs:
            cat_id = _CAT_MAP.get(slug)
            if cat_id is None:
                resultado[slug] = {"error": f"slug desconocido: {slug}"}
                continue
            try:
                productos, total = bajar_categoria(pg, slug, cat_id)
                resultado[slug] = {"productos": productos, "total": total}
                print(f"  [TI] {slug}: {total} productos", flush=True)
            except Exception as e:
                resultado[slug] = {"error": str(e)}
                print(f"  [TI] {slug}: ERROR {e}", flush=True)

        pg.close()
        if _own_browser:
            b.close()

    return resultado

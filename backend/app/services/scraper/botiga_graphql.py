"""
botiga_graphql.py — scraper de Botiga (botiga.farmashop.com.uy) via Magento 2.4 GraphQL.

Botiga es un store-view separado del mismo backend Magento que Farmashop.
Comparte los mismos category_id pero expone un catálogo diferente.
URL de producto: https://botiga.farmashop.com.uy/{url_key}.html
"""

import logging
import time
import random
import requests

log = logging.getLogger(__name__)

_ENDPOINT = "https://botiga.farmashop.com.uy/graphql"

_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Origin": "https://botiga.farmashop.com.uy",
    "Referer": "https://botiga.farmashop.com.uy/",
}

_QUERY = """
query ProductsByCategory($categoryId: String!, $pageSize: Int!, $currentPage: Int!) {
  products(
    filter: { category_id: { eq: $categoryId } }
    pageSize: $pageSize
    currentPage: $currentPage
  ) {
    total_count
    items {
      name
      sku
      url_key
      price_range {
        minimum_price {
          final_price   { value }
          regular_price { value }
        }
      }
    }
  }
}
"""

# Mismos category_id que Farmashop — comparten el mismo backend Magento.
# Botiga expone un subconjunto de productos diferente por visibilidad de store-view.
CATEGORIAS = {
    "perfumes":               "39835",
    "maquillaje":             "4944",
    "manos":                  "4946",
    "cuidado-personal":       "4941",
    "salud":                  "4939",
    "bebes":                  "4942",
    "limpieza":               "49291",
    "hogar":                  "4940",
    "libreria":               "40276",
    "alimentos":              "5062",
    "deportes":               "38554",
    "jugueteria":             "41311",
    "indumentaria":           "42909",
    "creando":                "25416",
    "marcas-exclusivas":      "4468",
    "productos-profesionales": "42741",
}

BOTIGA_FASE_1 = ["perfumes", "maquillaje", "manos", "cuidado-personal"]
BOTIGA_FASE_2 = ["salud", "bebes", "limpieza", "hogar"]
BOTIGA_FASE_3 = ["libreria", "alimentos", "deportes", "jugueteria"]
BOTIGA_FASE_4 = ["indumentaria", "creando", "marcas-exclusivas", "productos-profesionales"]

BOTIGA_FASES = {
    1: BOTIGA_FASE_1,
    2: BOTIGA_FASE_2,
    3: BOTIGA_FASE_3,
    4: BOTIGA_FASE_4,
}

_BASE_URL = "https://botiga.farmashop.com.uy"


def _parse_item(item: dict, nombre_cat: str) -> dict:
    precio_range = item.get("price_range") or {}
    min_price    = precio_range.get("minimum_price") or {}
    final        = (min_price.get("final_price")   or {}).get("value")
    regular      = (min_price.get("regular_price") or {}).get("value")
    url_key      = item.get("url_key") or ""
    return {
        "tienda":       "Botiga",
        "nombre":       item.get("name"),
        "precio":       float(final)   if final   is not None else None,
        "precio_lista": float(regular) if regular is not None and regular != final else None,
        "sku":          item.get("sku"),
        "barcode":      None,
        "marca":        None,
        "categoria":    nombre_cat,
        "url":          f"{_BASE_URL}/{url_key}.html",
    }


def bajar_categoria(nombre_cat: str, page_size: int = 48) -> tuple:
    """Descarga todos los productos de una categoría.
    Devuelve (lista_productos, total_declarado).
    """
    cat_id    = CATEGORIAS[nombre_cat]
    productos = []
    total     = None
    page      = 1

    while True:
        payload = {
            "query": _QUERY,
            "variables": {
                "categoryId": cat_id,
                "pageSize":   page_size,
                "currentPage": page,
            },
        }
        resp = None
        for intento in range(3):
            try:
                r = requests.post(_ENDPOINT, json=payload, headers=_HEADERS, timeout=20)
                r.raise_for_status()
                resp = r.json()
                break
            except Exception:
                if intento < 2:
                    time.sleep(random.uniform(1.0, 2.5))

        if resp is None:
            break

        prods_data = (resp.get("data") or {}).get("products") or {}
        if total is None:
            total = prods_data.get("total_count", 0) or 0

        items = prods_data.get("items") or []
        if not items:
            break

        for item in items:
            productos.append(_parse_item(item, nombre_cat))

        if len(productos) >= total:
            break

        page += 1
        time.sleep(random.uniform(0.3, 0.8))

    return productos, total or 0


def validar_urls(productos: list, max_workers: int = 30, timeout: int = 10) -> tuple:
    """Verifica cada URL única con HEAD request en paralelo.
    Retorna (productos_validos, n_404) filtrando los que devuelvan 404.
    Errores de red / timeouts se conservan (no son 404 confirmados).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Deduplicar por URL para no hacer el mismo check dos veces
    url_status: dict[str, int] = {}
    urls_unicas = list({p["url"] for p in productos})

    _check_headers = {**_HEADERS, "Accept": "text/html,application/xhtml+xml,*/*"}

    def _check(url: str) -> tuple[str, int]:
        try:
            r = requests.head(url, headers=_check_headers, timeout=timeout, allow_redirects=True)
            return url, r.status_code
        except Exception:
            return url, 0  # error de red → conservar

    log.info("Botiga validar_urls: %d URLs únicas con %d workers", len(urls_unicas), max_workers)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_check, u): u for u in urls_unicas}
        done = 0
        for fut in as_completed(futures):
            url, status = fut.result()
            url_status[url] = status
            done += 1
            if done % 500 == 0:
                log.info("Botiga validar_urls: %d/%d verificadas", done, len(urls_unicas))

    invalidos_404 = [u for u, s in url_status.items() if s == 404]
    invalidos_set = set(invalidos_404)
    n_404 = len(invalidos_404)

    if n_404:
        log.warning("Botiga validar_urls: %d URLs con 404 (filtradas)", n_404)
        print(f"  [validacion] {n_404} URLs con 404 filtradas de {len(urls_unicas)} únicas", flush=True)

    validos = [p for p in productos if p["url"] not in invalidos_set]
    return validos, n_404


def bajar_varias(nombres_cats: list, max_workers: int = 4) -> dict:
    """Baja varias categorías en paralelo via ThreadPoolExecutor."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _bajar(nombre):
        if nombre not in CATEGORIAS:
            return nombre, {"error": f"Categoría desconocida: {nombre}"}
        try:
            prods, total = bajar_categoria(nombre)
            print(f"  {nombre}: {len(prods)}/{total}", flush=True)
            return nombre, {"productos": prods, "total_declarado": total}
        except Exception as e:
            print(f"  {nombre}: ERROR {str(e)[:80]}", flush=True)
            return nombre, {"error": str(e)}

    resultado = {}
    workers = min(max_workers, len(nombres_cats))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for nombre, data in (f.result() for f in as_completed(ex.submit(_bajar, n) for n in nombres_cats)):
            resultado[nombre] = data
    return resultado

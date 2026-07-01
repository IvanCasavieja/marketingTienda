"""
live_search.py — búsqueda en vivo de UN producto en todas las cadenas, sin
pasar por la base de datos. Golpea las mismas APIs que el scraper masivo,
pero filtradas por término y en todas las sucursales en paralelo.

Reusa los parsers de cada módulo (_parse_node, _parse_product_is, _parse_prices)
para no duplicar lógica de normalización — solo cambia CÓMO se piden los datos
(filtrado por término en vez de paginar el catálogo completo).

Cadenas con búsqueda por keyword real:
  - Ta-Ta:      GraphQL "term"        — 15 sucursales en paralelo.
  - El Dorado:  VTEX IS "query"       — 17 sucursales en paralelo.
  - GDU:        REST "Name" (param no documentado, descubierto por prueba) —
                catálogo filtrado + precios de TODAS las sucursales en una sola
                tanda de llamadas (la API de precios ya devuelve todas las
                sucursales por producto, no hace falta iterar una por una).
  - FarmaShop:  Magento 2 GraphQL — precio único, sin sucursales.
  - Botiga:     Magento 2 GraphQL (mismo servidor que FarmaShop, store_view 22).
"""

import json
import logging
import os
import re
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path

import requests as _requests
from rapidfuzz import fuzz as _fuzz

from . import eldorado_rest as eldorado
from . import gdu_rest as gdu
from . import tata_graphql as tata
from .adapters import ProductRecord

log = logging.getLogger(__name__)

_DATA_DIR = Path(os.environ.get("SCRAPER_DATA_DIR", "/tmp/scraper"))

_GDU_MAX_PAGES = 20  # tope de seguridad: 20 páginas x 100 = 2000 productos por término
_MIN_SCORE     = 55.0  # threshold mínimo de relevancia (0-100)


def _es_codigo(term: str) -> bool:
    """True si el término es puramente numérico — barcode EAN o SKU interno."""
    return term.strip().isdigit()


def score_match(nombre: str, term: str) -> float:
    """Relevancia 0–100 entre búsqueda y nombre de producto.

    Combina token_set_ratio (insensible al orden de palabras, útil cuando distintos
    supers nombran el mismo producto diferente) con cobertura de tokens (% de las
    palabras del término que aparecen en el nombre). Un resultado necesita ≥55 para
    no ser descartado.
    """
    n = (nombre or "").lower().strip()
    t = (term  or "").lower().strip()
    if not n or not t:
        return 0.0
    if t in n:
        return 100.0
    tsr = _fuzz.token_set_ratio(t, n)
    palabras = [w for w in t.split() if len(w) >= 3]
    if not palabras:
        return float(tsr)
    cobertura = sum(
        1 for p in palabras
        if _fuzz.partial_ratio(p, n) >= 80
    ) / len(palabras)
    return round(tsr * 0.55 + cobertura * 100 * 0.45, 1)


# ── Ta-Ta ─────────────────────────────────────────────────────────────────────

def _tata_search_url(term: str, region_id: str, first: int = 20) -> str:
    facets = [
        {"key": "channel", "value": f'{{"salesChannel":"4","regionId":"{region_id}"}}'},
        {"key": "locale", "value": "es-uy"},
    ]
    variables = {
        "first": first, "after": "0", "sort": "score_desc",
        "term": term, "selectedFacets": facets,
    }
    qs = urllib.parse.quote(json.dumps(variables))
    return f"https://www.tata.com.uy/api/graphql?operationName=ProductsQuery&variables={qs}"


def buscar_tata(term: str) -> list[ProductRecord]:
    records: list[ProductRecord] = []
    lock = threading.Lock()

    def _una(sucursal: dict):
        url = _tata_search_url(term, sucursal["region_id"])
        data = tata._fetch(url, retries=1, timeout=5, fast_fail=True)
        if data is None:
            return
        search = (data.get("data") or {}).get("search") or {}
        edges = (search.get("products") or {}).get("edges") or []
        parsed = []
        for e in edges:
            d = tata._parse_node(e["node"], sucursal)
            score = 100.0 if _es_codigo(term) else score_match(d["nombre"], term)
            if score < _MIN_SCORE:
                continue
            parsed.append(ProductRecord(
                tienda=d["tienda"],
                nombre=d["nombre"],
                precio=d["precio"],
                precio_lista=d["precio_lista"],
                sku=d["sku"],
                barcode=d["barcode"],
                marca=d["marca"],
                categoria=None,
                url=d["url"],
                sucursal_id=d["sucursal_id"],
                sucursal_nombre=d["sucursal_nombre"],
                relevancia=score,
            ))
        with lock:
            records.extend(parsed)

    with ThreadPoolExecutor(max_workers=len(tata.SUCURSALES)) as ex:
        list(ex.map(_una, tata.SUCURSALES))

    return records


# ── El Dorado ─────────────────────────────────────────────────────────────────

def buscar_eldorado(term: str) -> list[ProductRecord]:
    records: list[ProductRecord] = []
    lock = threading.Lock()

    def _una(sucursal: dict):
        try:
            r = eldorado._get(eldorado._IS_URL, {
                "query":                term,
                "count":                20,
                "locale":               "es-UY",
                "from":                 0,
                "to":                   19,
                "regionId":             sucursal["region_id"],
                "hideUnavailableItems": "false",
            }, timeout=5, fast_fail=True)
            data = r.json()
        except Exception as exc:
            log.warning("ElDorado live: %s falló — %s", sucursal["nombre"], exc)
            return
        parsed = []
        for raw in data.get("products") or []:
            rec = eldorado._parse_product_is(raw, sucursal)
            if rec is None:
                continue
            score = 100.0 if _es_codigo(term) else score_match(rec.nombre, term)
            if score < _MIN_SCORE:
                continue
            parsed.append(replace(rec, relevancia=score))
        with lock:
            records.extend(parsed)

    with ThreadPoolExecutor(max_workers=len(eldorado.SUCURSALES)) as ex:
        list(ex.map(_una, eldorado.SUCURSALES))

    return records


# ── GDU (Disco / Devoto / Géant) ───────────────────────────────────────────────

def buscar_gdu(term: str, cache_dir: Path = _DATA_DIR) -> list[ProductRecord]:
    jwt         = gdu._get_jwt(cache_dir)
    session     = gdu._build_session(jwt)
    branch_meta = gdu._load_branch_meta()

    product_ids: list[str]             = []
    names:       dict[str, str]        = {}
    barcodes:    dict[str, str | None] = {}
    categorias:  dict[str, str | None] = {}
    seen_ids:    set[str]              = set()

    def _registrar_item(item: dict) -> None:
        pid = item["id"]
        if pid in seen_ids:
            return
        seen_ids.add(pid)
        desc = item.get("description", {})
        name = desc.get("name", pid)
        barcodes_list = item.get("barcodes") or []
        barcode = barcodes_list[0].get("barcode") if barcodes_list else None
        categoria = None
        for df in item.get("dynamicFields") or []:
            if df.get("fieldName") == "FILTER|Categoría":
                categoria = df.get("fieldValue")
                break
        product_ids.append(pid)
        names[pid]      = name
        barcodes[pid]   = barcode
        categorias[pid] = categoria

    def _buscar_param(param_name: str, param_value: str) -> None:
        page, total_pages = 1, None
        while True:
            try:
                r = gdu._llamar(
                    session, "GET",
                    f"{gdu._BASE_PRODS}/api/accounts/{gdu._ACCOUNT}/products",
                    params={"Page": page, "ItemsPerPage": gdu._PAGE_SIZE, "IsActive": True, param_name: param_value},
                )
                data = r.json()
            except Exception as exc:
                log.warning("GDU live: error buscando %s='%s' pág %d — %s", param_name, param_value, page, exc)
                break
            if total_pages is None:
                total_pages = min(data.get("totalPageCount", 1), _GDU_MAX_PAGES)
            for item in data.get("items", []):
                _registrar_item(item)
            if page >= total_pages:
                break
            page += 1

    term_clean = term.strip()
    if _es_codigo(term_clean):
        # Término numérico: podría ser un product ID de GDU (ej: "110025")
        # El endpoint SSE ya resolvió barcode → nombre antes de llegar aquí,
        # así que lo más probable es que sea un ID interno de GDU.
        try:
            r = gdu._llamar(
                session, "GET",
                f"{gdu._BASE_PRODS}/api/accounts/{gdu._ACCOUNT}/products/{term_clean}",
            )
            _registrar_item(r.json())
        except Exception:
            pass
        if not product_ids:
            _buscar_param("Name", term_clean)
    else:
        # Búsqueda por nombre: OR de cada palabra significativa
        palabras = [w for w in term_clean.split() if w.isalpha() and len(w) >= 3] or [term_clean]
        for palabra in palabras:
            _buscar_param("Name", palabra)

    # Filtrar por relevancia ANTES del batch de precios — cada llamada de precios
    # cuesta una request a la API de GDU; descartar irrelevantes aquí ahorra tiempo.
    if not _es_codigo(term_clean):
        product_ids = [
            pid for pid in product_ids
            if score_match(names.get(pid, ""), term_clean) >= _MIN_SCORE
        ]

    api_records: list[ProductRecord] = []
    for i in range(0, len(product_ids), gdu._PRICE_BATCH):
        batch = product_ids[i:i + gdu._PRICE_BATCH]
        price_records = gdu._get_prices_batch(session, batch)
        gdu._parse_prices(price_records, names, barcodes, categorias, branch_meta, api_records)

    # Asignar score de relevancia a cada record (nombres vienen del catálogo, ya disponibles)
    scored: list[ProductRecord] = []
    for r in api_records:
        s = 100.0 if _es_codigo(term_clean) else score_match(r.nombre or "", term_clean)
        scored.append(replace(r, relevancia=s))
    api_records = scored

    # Precio real al consumidor desde HTML del website (Blazor Server, server-rendered).
    # La API Azure devuelve precios internos/costo para productos frescos de rotisería.
    # Fetch desde Devoto (una sola cadena por SKU) — el precio es el mismo para todas.
    _MAX_HTML = 40

    sku_url_map: dict[str, str] = {}
    for r in api_records:
        if r.sku and r.sku not in sku_url_map and r.tienda == "Devoto":
            sku_url_map[r.sku] = r.url
            if len(sku_url_map) >= _MAX_HTML:
                break
    for r in api_records:
        if r.sku and r.sku not in sku_url_map:
            sku_url_map[r.sku] = r.url
            if len(sku_url_map) >= _MAX_HTML:
                break

    html_prices: dict[str, float] = {}
    if sku_url_map:
        def _fetch_one(item: tuple[str, str]) -> tuple[str, float | None]:
            sku, url = item
            m = re.search(r"/product/p/(\d+)", url)
            if not m:
                return sku, None
            return sku, gdu._fetch_html_precio("Devoto", m.group(1))

        with ThreadPoolExecutor(max_workers=8) as ex:
            for sku, price in ex.map(_fetch_one, sku_url_map.items()):
                if price is not None:
                    html_prices[sku] = price

    if not html_prices:
        return api_records

    records: list[ProductRecord] = []
    for r in api_records:
        if r.sku:
            html_p = html_prices.get(r.sku)
            if html_p is not None and html_p != r.precio:
                r = replace(
                    r,
                    precio=html_p,
                    precio_lista=r.precio if r.precio and r.precio < html_p else r.precio_lista,
                )
        records.append(r)
    return records


# ── FarmaShop / Botiga (Magento 2 GraphQL) ────────────────────────────────────

_MAGENTO_QUERY = """
query Search($search: String!, $pageSize: Int!, $currentPage: Int!) {
  products(search: $search, pageSize: $pageSize, currentPage: $currentPage) {
    total_count
    items {
      name
      sku
      price_range {
        minimum_price {
          final_price   { value }
          regular_price { value }
        }
      }
      url_key
    }
  }
}
"""

_MAGENTO_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
_MAGENTO_PAGE_SIZE = 50
_MAGENTO_MAX       = 300


def _buscar_magento(term: str, base_url: str, tienda_nombre: str) -> list[ProductRecord]:
    records: list[ProductRecord] = []
    current_page = 1

    while len(records) < _MAGENTO_MAX:
        payload = {
            "query": _MAGENTO_QUERY,
            "variables": {"search": term, "pageSize": _MAGENTO_PAGE_SIZE, "currentPage": current_page},
        }
        try:
            r = _requests.post(
                f"{base_url}/graphql",
                json=payload,
                headers=_MAGENTO_HEADERS,
                timeout=8,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            log.warning("magento %s: error en página %d — %s", tienda_nombre, current_page, exc)
            break

        products = (data.get("data") or {}).get("products") or {}
        total    = products.get("total_count", 0)
        items    = products.get("items") or []
        if not items:
            break

        for item in items:
            nombre_item = item.get("name") or ""
            score = score_match(nombre_item, term)
            if score < _MIN_SCORE:
                continue

            mp          = (item.get("price_range") or {}).get("minimum_price") or {}
            final_price = (mp.get("final_price") or {}).get("value")
            reg_price   = (mp.get("regular_price") or {}).get("value")
            if not final_price:
                continue

            url_key     = item.get("url_key") or ""
            url         = f"{base_url}/{url_key}" if url_key else base_url

            records.append(ProductRecord(
                tienda          = tienda_nombre,
                nombre          = nombre_item,
                precio          = final_price,
                precio_lista    = reg_price if reg_price and reg_price > (final_price or 0) else None,
                sku             = item.get("sku"),
                barcode         = None,
                marca           = None,
                categoria       = None,
                url             = url,
                sucursal_id     = None,
                sucursal_nombre = None,
                relevancia      = score,
            ))

        if len(records) >= total:
            break
        current_page += 1

    return records


def buscar_farmashop(term: str) -> list[ProductRecord]:
    return _buscar_magento(term, "https://tienda.farmashop.com.uy", "FarmaShop")


def buscar_botiga(term: str) -> list[ProductRecord]:
    return _buscar_magento(term, "https://botiga.farmashop.com.uy", "Botiga")


# ── Orquestador ───────────────────────────────────────────────────────────────

def buscar_todas(term: str, cache_dir: Path = _DATA_DIR) -> dict[str, list[ProductRecord]]:
    """Busca `term` en Ta-Ta, El Dorado, GDU, FarmaShop y Botiga en paralelo.
    Devuelve {cadena: [ProductRecord, ...]}. Si una cadena falla, devuelve lista
    vacía para esa cadena y continúa con las demás (nunca lanza excepción)."""
    futs: dict[str, "Future"] = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {
            "Ta-Ta":     ex.submit(buscar_tata, term),
            "ElDorado":  ex.submit(buscar_eldorado, term),
            "GDU":       ex.submit(buscar_gdu, term, cache_dir),
            "FarmaShop": ex.submit(buscar_farmashop, term),
            "Botiga":    ex.submit(buscar_botiga, term),
        }
        resultados: dict[str, list[ProductRecord]] = {}
        for cadena, fut in futs.items():
            try:
                resultados[cadena] = fut.result()
                log.info("live_search: %s — %d registros para '%s'", cadena, len(resultados[cadena]), term)
            except Exception as exc:
                log.error("live_search: %s falló — %s", cadena, exc, exc_info=True)
                resultados[cadena] = []

    return resultados


def buscar_todas_streaming(term: str, cache_dir: Path = _DATA_DIR):
    """Generador síncrono que hace yield de (cadena, records) en orden de llegada.
    La cadena más rápida aparece primero — ideal para streaming SSE."""
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {
            ex.submit(buscar_tata,      term):            "Ta-Ta",
            ex.submit(buscar_eldorado,  term):            "ElDorado",
            ex.submit(buscar_gdu,       term, cache_dir): "GDU",
            ex.submit(buscar_farmashop, term):            "FarmaShop",
            ex.submit(buscar_botiga,    term):            "Botiga",
        }
        for fut in as_completed(futs):
            cadena = futs[fut]
            try:
                records = fut.result()
                log.info("live_search streaming: %s — %d registros para '%s'", cadena, len(records), term)
                yield cadena, records, None
            except Exception as exc:
                log.error("live_search streaming: %s falló — %s", cadena, exc, exc_info=True)
                yield cadena, [], str(exc)

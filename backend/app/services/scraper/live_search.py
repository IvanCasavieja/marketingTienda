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

import html
import json
import logging
import os
import re
import threading
import time
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

    Nota: cuando el término mezcla una marca con una palabra de categoría genérica
    que no aparece literalmente en el nombre del producto (ej. "celular samsung" vs.
    "Samsung Galaxy A57 5G", que no dice "celular"), este puntaje no alcanza para
    distinguir eso de un falso positivo real de otra categoría (ej. "Auriculares
    Samsung Galaxy Buds") — ambos dan el mismo score porque a los dos les "falta"
    la misma palabra. Exigir que todas las palabras estén presentes literalmente
    rechaza los dos casos por igual (probado y descartado); arreglarlo bien
    requeriría cruzar contra la categoría real del producto, que no todos los
    adapters exponen.
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

    # Deduplicar por (product_id, cadena, precio): sin deduplicar aparecerían ~50
    # filas idénticas de Devoto todas al mismo precio. Conservar la sucursal con
    # ID numérico más bajo (la más "estándar") como representante de cada precio.
    # El precio en el website depende de la sucursal seleccionada en la sesión del
    # usuario, no del ?sc= en la URL — lo que mostramos aquí es la variación real
    # de precios que existe entre sucursales de la misma cadena.
    dedup: dict[tuple, ProductRecord] = {}
    for r in api_records:
        key = (r.sku, r.tienda, r.precio)
        existing = dedup.get(key)
        if existing is None:
            dedup[key] = r
        else:
            # Preferir la sucursal con ID numérico menor (tienda más estándar)
            try:
                if int(r.sucursal_id or "9999") < int(existing.sucursal_id or "9999"):
                    dedup[key] = r
            except (ValueError, TypeError):
                pass
    # Limpiar URL: quitar ?sc= porque el precio en el website depende de la sesión
    # del usuario (sucursal seleccionada), no del parámetro URL. Un link con ?sc=119
    # muestra el mismo precio que sin él si la sesión del usuario tiene otra tienda.
    # La URL limpia abre el producto correctamente; el precio de la sesión es el real.
    api_records = [
        replace(r, url=r.url.split("?")[0] if r.url else r.url)
        for r in dedup.values()
    ]

    # Asignar score de relevancia a cada record (nombres vienen del catálogo, ya disponibles)
    scored: list[ProductRecord] = []
    for r in api_records:
        s = 100.0 if _es_codigo(term_clean) else score_match(r.nombre or "", term_clean)
        scored.append(replace(r, relevancia=s))
    api_records = scored

    return api_records


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

_FARMASHOP_BASE = "https://tienda.farmashop.com.uy"
_BOTIGA_BASE    = "https://botiga.farmashop.com.uy"
_MAGENTO_VERIFY_WORKERS = 8

# Headers para requests GET simples (WooCommerce/Shopify/DIMM/Fama) — sin
# Content-Type: algunos WAF (Wordfence en WooCommerce) bloquean con 403 un GET
# que trae Content-Type: application/json, por parecer tráfico no-browser.
_UA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def _resolver_url_magento(
    url_key: str,
    base_primario: str, tienda_primaria: str,
    base_alternativo: str, tienda_alternativa: str,
) -> tuple[str, str]:
    """
    FarmaShop y Botiga comparten el mismo backend Magento (mismo store_code
    "default" en /graphql, catálogo idéntico) pero cada producto solo resuelve
    como página real en UNO de los dos dominios — no hay ninguna señal en la
    respuesta de GraphQL para saber cuál (categories vuelve vacío siempre).
    Se verifica en vivo con un HEAD corto y, si el dominio primario da 404,
    se asume que vive en el alternativo (sin verificarlo también, para no
    duplicar la latencia — es mejor esfuerzo, no garantía).

    Devuelve (url, tienda_real) — tienda_real distingue de la cadena bajo la
    que el producto quedó listado cuando el link termina apuntando a la otra.
    """
    candidato = f"{base_primario}/{url_key}.html"
    try:
        r = _requests.head(candidato, headers=_UA_HEADERS, timeout=4, allow_redirects=True)
        if r.status_code == 200:
            return candidato, tienda_primaria
    except Exception:
        pass
    return f"{base_alternativo}/{url_key}.html", tienda_alternativa


def _buscar_magento(
    term: str,
    base_url: str, tienda_nombre: str,
    base_alternativo: str, tienda_alternativa: str,
) -> list[ProductRecord]:
    records: list[ProductRecord] = []
    url_keys: list[str] = []
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
            nombre_item = html.unescape(item.get("name") or "")
            score = score_match(nombre_item, term)
            if score < _MIN_SCORE:
                continue

            mp          = (item.get("price_range") or {}).get("minimum_price") or {}
            final_price = (mp.get("final_price") or {}).get("value")
            reg_price   = (mp.get("regular_price") or {}).get("value")
            if not final_price:
                continue

            records.append(ProductRecord(
                tienda          = tienda_nombre,
                nombre          = nombre_item,
                precio          = final_price,
                precio_lista    = reg_price if reg_price and reg_price > (final_price or 0) else None,
                sku             = item.get("sku"),
                barcode         = None,
                marca           = None,
                categoria       = None,
                url             = base_url,  # placeholder — se resuelve en paralelo más abajo
                sucursal_id     = None,
                sucursal_nombre = None,
                relevancia      = score,
            ))
            url_keys.append(item.get("url_key") or "")

        if len(records) >= total:
            break
        current_page += 1

    if not records:
        return records

    # Resolver URLs en paralelo — cada HEAD es independiente y con timeout corto,
    # así que un lote de N productos no cuesta N veces la latencia de a uno.
    with ThreadPoolExecutor(max_workers=_MAGENTO_VERIFY_WORKERS) as ex:
        resueltos = list(ex.map(
            lambda uk: _resolver_url_magento(uk, base_url, tienda_nombre, base_alternativo, tienda_alternativa)
                       if uk else (base_url, tienda_nombre),
            url_keys,
        ))
    records = [
        replace(rec, url=url, tienda_real=(tienda_real if tienda_real != rec.tienda else None))
        for rec, (url, tienda_real) in zip(records, resueltos)
    ]

    return records


def buscar_farmashop(term: str) -> list[ProductRecord]:
    return _buscar_magento(term, _FARMASHOP_BASE, "FarmaShop", _BOTIGA_BASE, "Botiga")


def buscar_botiga(term: str) -> list[ProductRecord]:
    return _buscar_magento(term, _BOTIGA_BASE, "Botiga", _FARMASHOP_BASE, "FarmaShop")


# ── Utilidades de precio en formato uruguayo (miles con punto, decimales con coma) ──

def _parse_precio_uy(raw: str) -> float | None:
    """Convierte '1.149,00' o '1.158' a float. Sin separador de miles también funciona."""
    if not raw:
        return None
    limpio = raw.strip().replace(".", "").replace(",", ".")
    try:
        return float(limpio)
    except ValueError:
        return None


# ── WooCommerce genérico (Black Dog / Electrohogar) ────────────────────────────

def _buscar_woocommerce(term: str, base_url: str, tienda_nombre: str) -> list[ProductRecord]:
    records: list[ProductRecord] = []
    try:
        # Sin headers custom a propósito: el WAF (Wordfence) de estos sitios devuelve
        # 403 ante un UA de Chrome sin el resto de headers típicos de un browser real
        # (Accept, Sec-Ch-Ua, etc.), pero deja pasar el UA default de requests.
        r = _requests.get(
            f"{base_url}/wp-json/wc/store/products",
            params={"search": term, "per_page": 30},
            timeout=8,
        )
        r.raise_for_status()
        items = r.json()
    except Exception as exc:
        log.warning("woocommerce %s: error buscando '%s' — %s", tienda_nombre, term, exc)
        return records

    for item in items or []:
        nombre_item = html.unescape(item.get("name") or "")
        score = score_match(nombre_item, term)
        if score < _MIN_SCORE:
            continue

        prices = item.get("prices") or {}
        raw_price   = prices.get("price")
        raw_regular = prices.get("regular_price")
        if not raw_price:
            continue
        minor = prices.get("currency_minor_unit", 2)
        precio       = float(raw_price) / (10 ** minor)
        precio_lista = float(raw_regular) / (10 ** minor) if raw_regular and raw_regular != raw_price else None

        records.append(ProductRecord(
            tienda          = tienda_nombre,
            nombre          = nombre_item,
            precio          = precio,
            precio_lista    = precio_lista,
            sku             = item.get("sku") or None,
            barcode         = None,
            marca           = None,
            categoria       = None,
            url             = item.get("permalink") or base_url,
            sucursal_id     = None,
            sucursal_nombre = None,
            relevancia      = score,
            moneda          = prices.get("currency_code") or "USD",
        ))

    return records


def buscar_blackdog(term: str) -> list[ProductRecord]:
    return _buscar_woocommerce(term, "https://www.bde.com.uy", "BlackDog")


def buscar_electrohogar(term: str) -> list[ProductRecord]:
    return _buscar_woocommerce(term, "https://electrohogar.uy", "Electrohogar")


# ── Shopify (Cover Company) ─────────────────────────────────────────────────────

def buscar_covercompany(term: str) -> list[ProductRecord]:
    base_url = "https://covercompany.com.uy"
    records: list[ProductRecord] = []
    try:
        r = _requests.get(
            f"{base_url}/search/suggest.json",
            params={"q": term, "resources[type]": "product", "resources[limit]": 10},
            headers=_UA_HEADERS,
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        log.warning("CoverCompany: error buscando '%s' — %s", term, exc)
        return records

    products = ((data.get("resources") or {}).get("results") or {}).get("products") or []
    for item in products:
        nombre_item = item.get("title") or ""
        score = score_match(nombre_item, term)
        if score < _MIN_SCORE:
            continue

        raw_precio = item.get("price")
        raw_lista  = item.get("compare_at_price_max")
        if not raw_precio:
            continue
        precio       = float(raw_precio)
        precio_lista = float(raw_lista) if raw_lista and float(raw_lista) > precio else None

        url_path = (item.get("url") or "").split("?")[0]

        records.append(ProductRecord(
            tienda          = "CoverCompany",
            nombre          = nombre_item,
            precio          = precio,
            precio_lista    = precio_lista,
            sku             = str(item["id"]) if item.get("id") else None,
            barcode         = None,
            marca           = item.get("vendor") or None,
            categoria       = item.get("type") or None,
            url             = f"{base_url}{url_path}" if url_path else base_url,
            sucursal_id     = None,
            sucursal_nombre = None,
            relevancia      = score,
            moneda          = "UYU",
        ))

    return records


# ── DIMM / Stienda (typeahead "buscador-sugerencias") ──────────────────────────
# Mismo backend custom (CDN f.fcdn.app) para ambas tiendas. Endpoint encontrado
# en el bundle JS minificado (Twitter Typeahead + Bloodhound) — no aparece en el
# HTML ni en ningún sitemap de búsqueda.

_MONTO_RE   = re.compile(r'class="monto">([\d.,]+)<')
_MONEDA_RE  = re.compile(r'class="sim">([A-Z$]+)<')


def _buscar_dimm_stienda(term: str, base_url: str, tienda_nombre: str) -> list[ProductRecord]:
    records: list[ProductRecord] = []
    try:
        r = _requests.get(
            f"{base_url}/ajax",
            params={"service": "buscador-sugerencias", "q": term},
            headers=_UA_HEADERS,
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        log.warning("%s: error buscando '%s' — %s", tienda_nombre, term, exc)
        return records

    for item in data.get("datos") or []:
        if item.get("t") != "a":  # "c" = categoría, "all" = resumen — solo interesan productos
            continue

        nombre_item = item.get("nom") or ""
        score = score_match(nombre_item, term)
        if score < _MIN_SCORE:
            continue

        precio_match = _MONTO_RE.search(item.get("prV") or "")
        if not precio_match:
            continue
        precio = _parse_precio_uy(precio_match.group(1))
        if precio is None:
            continue

        lista_match  = _MONTO_RE.search(item.get("prL") or "")
        precio_lista = _parse_precio_uy(lista_match.group(1)) if lista_match else None
        if precio_lista == precio:
            precio_lista = None

        moneda_match = _MONEDA_RE.search(item.get("prV") or "")
        moneda = moneda_match.group(1) if moneda_match else "USD"
        moneda = "UYU" if moneda == "$" else moneda

        records.append(ProductRecord(
            tienda          = tienda_nombre,
            nombre          = nombre_item,
            precio          = precio,
            precio_lista    = precio_lista,
            sku             = None,
            barcode         = None,
            marca           = None,
            categoria       = None,
            url             = item.get("url") or base_url,
            sucursal_id     = None,
            sucursal_nombre = None,
            relevancia      = score,
            moneda          = moneda,
        ))

    return records


def buscar_dimm(term: str) -> list[ProductRecord]:
    return _buscar_dimm_stienda(term, "https://www.dimm.com.uy", "DIMM")


def buscar_stienda(term: str) -> list[ProductRecord]:
    return _buscar_dimm_stienda(term, "https://stienda.uy", "Stienda")


# ── Fama (buscador dinámico) ────────────────────────────────────────────────────
# Endpoint encontrado en un <script> inline que arma la URL para el plugin
# EasyAutocomplete — tampoco aparece en HTML plano ni en sitemap.
# Catálogo con precios mixtos: algunos productos en USD, otros en pesos ($).

def buscar_fama(term: str) -> list[ProductRecord]:
    base_url = "https://www.fama.com.uy"
    records: list[ProductRecord] = []
    try:
        r = _requests.get(
            f"{base_url}/productos/scripts/buscador_dinamico_productos.php",
            params={"p": 0, "idc": 0, "q": term},
            headers=_UA_HEADERS,
            timeout=8,
        )
        r.raise_for_status()
        items = r.json()
    except Exception as exc:
        log.warning("Fama: error buscando '%s' — %s", term, exc)
        return records

    for item in items or []:
        if not item.get("tiene_precio"):
            continue

        nombre_item = item.get("text") or ""
        score = score_match(nombre_item, term)
        if score < _MIN_SCORE:
            continue

        precio_raw = (item.get("precio") or "").strip()
        partes = precio_raw.split(maxsplit=1)
        if len(partes) != 2:
            continue
        moneda = "UYU" if partes[0] == "$" else partes[0]
        precio = _parse_precio_uy(partes[1])
        if precio is None:
            continue

        url = item.get("url") or ""
        if url and not url.startswith("http"):
            url = f"{base_url}{url}"

        records.append(ProductRecord(
            tienda          = "Fama",
            nombre          = nombre_item,
            precio          = precio,
            precio_lista    = None,
            sku             = str(item["id"]) if item.get("id") else None,
            barcode         = None,
            marca           = None,
            categoria       = None,
            url             = url or base_url,
            sucursal_id     = None,
            sucursal_nombre = None,
            relevancia      = score,
            moneda          = moneda,
        ))

    return records


# ── LOi (API pública documentada — /api/v1/products.json) ─────────────────────
# A diferencia del resto de este archivo, LOi publica su propia API con límites
# de uso documentados (/developer-ai.txt, /llms-full.txt): 60 req/min para
# búsqueda, y piden identificarse con un User-Agent descriptivo en vez de
# simular un navegador. Por eso esta cadena NO reusa _UA_HEADERS (que finge ser
# Chrome) y tiene su propio limitador de velocidad — puesto a propósito, no
# heredado del resto del archivo (que no tiene ninguno).

_LOI_USER_AGENT   = "PrecioCompetitivoBot/1.0 (uso interno, solo lectura de precios publicos)"
_LOI_MIN_INTERVAL = 1.1  # seg entre pedidos — bien por debajo del límite de 60/min documentado
_loi_lock         = threading.Lock()
_loi_last_call    = 0.0


def _loi_throttle() -> None:
    global _loi_last_call
    with _loi_lock:
        ahora = time.monotonic()
        espera = _loi_last_call + _LOI_MIN_INTERVAL - ahora
        if espera > 0:
            time.sleep(espera)
        _loi_last_call = time.monotonic()


def buscar_loi(term: str) -> list[ProductRecord]:
    if _es_codigo(term):
        return []  # la API pública de LOi no documenta búsqueda por barcode/SKU

    _loi_throttle()
    records: list[ProductRecord] = []
    try:
        r = _requests.get(
            "https://loi.com.uy/api/v1/products.json",
            params={"q": term, "per_page": 24},
            headers={"User-Agent": _LOI_USER_AGENT, "Accept": "application/json"},
            timeout=8,
        )
        if r.status_code == 429:
            log.warning("LOi: rate-limited (429) buscando '%s'", term)
            return records
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        log.warning("LOi: error buscando '%s' — %s", term, exc)
        return records

    for item in data.get("products") or []:
        nombre_item = item.get("title") or ""
        score = score_match(nombre_item, term)
        if score < _MIN_SCORE:
            continue

        precio_info = item.get("price") or {}
        precio = precio_info.get("amount")
        if precio is None:
            continue
        precio_lista = precio_info.get("original_amount")
        if precio_lista is not None and precio_lista <= precio:
            precio_lista = None

        marca_info      = item.get("brand") or {}
        categoria_info   = item.get("category") or {}

        records.append(ProductRecord(
            tienda          = "LOi",
            nombre          = nombre_item,
            precio          = float(precio),
            precio_lista    = float(precio_lista) if precio_lista is not None else None,
            sku             = item.get("sku") or (str(item["id"]) if item.get("id") else None),
            barcode         = None,
            marca           = marca_info.get("name") or None,
            categoria       = categoria_info.get("name") or None,
            url             = item.get("url") or "https://loi.com.uy",
            sucursal_id     = None,
            sucursal_nombre = None,
            relevancia      = score,
            moneda          = precio_info.get("currency") or "UYU",
        ))

    return records


# ── Orquestador ───────────────────────────────────────────────────────────────

# LOi queda afuera de la selección por defecto: a diferencia del resto de estas
# cadenas (supermercados/farmacias/electro que compiten directo con nuestro
# rubro), LOi es un catálogo general (celulares, hogar, belleza...) sin
# relación con la mayoría de lo que se busca acá — traerlo siempre significaría
# gastar presupuesto de su rate limit documentado en búsquedas donde nunca iba
# a aparecer (ej. "coca cola"). Se busca solo si el usuario la selecciona a
# propósito desde el filtro de cadenas.
_CADENAS_DEFAULT = [
    "Ta-Ta", "ElDorado", "GDU", "FarmaShop", "Botiga", "BlackDog",
    "Electrohogar", "CoverCompany", "DIMM", "Stienda", "Fama",
]
_CADENAS_OPT_IN = ["LOi"]
_CADENAS_TODAS  = _CADENAS_DEFAULT + _CADENAS_OPT_IN


def _tareas_disponibles(term: str, cache_dir: Path) -> dict[str, tuple]:
    return {
        "Ta-Ta":         (buscar_tata,         (term,)),
        "ElDorado":      (buscar_eldorado,     (term,)),
        "GDU":           (buscar_gdu,          (term, cache_dir)),
        "FarmaShop":     (buscar_farmashop,    (term,)),
        "Botiga":        (buscar_botiga,       (term,)),
        "BlackDog":      (buscar_blackdog,     (term,)),
        "Electrohogar":  (buscar_electrohogar, (term,)),
        "CoverCompany":  (buscar_covercompany, (term,)),
        "DIMM":          (buscar_dimm,         (term,)),
        "Stienda":       (buscar_stienda,      (term,)),
        "Fama":          (buscar_fama,         (term,)),
        "LOi":           (buscar_loi,          (term,)),
    }


def buscar_todas(
    term: str,
    cache_dir: Path = _DATA_DIR,
    cadenas: list[str] | None = None,
) -> dict[str, list[ProductRecord]]:
    """Busca `term` en las cadenas seleccionadas en paralelo (todas las de
    _CADENAS_DEFAULT si `cadenas` es None — ver _CADENAS_OPT_IN).
    Devuelve {cadena: [ProductRecord, ...]}. Si una cadena falla, devuelve lista
    vacía para esa cadena y continúa con las demás (nunca lanza excepción)."""
    seleccion = set(cadenas) if cadenas is not None else set(_CADENAS_DEFAULT)
    activas = {c: t for c, t in _tareas_disponibles(term, cache_dir).items() if c in seleccion}

    resultados: dict[str, list[ProductRecord]] = {}
    with ThreadPoolExecutor(max_workers=max(len(activas), 1)) as ex:
        futs = {cadena: ex.submit(fn, *args) for cadena, (fn, args) in activas.items()}
        for cadena, fut in futs.items():
            try:
                resultados[cadena] = fut.result()
                log.info("live_search: %s — %d registros para '%s'", cadena, len(resultados[cadena]), term)
            except Exception as exc:
                log.error("live_search: %s falló — %s", cadena, exc, exc_info=True)
                resultados[cadena] = []

    return resultados


def buscar_todas_streaming(term: str, cache_dir: Path = _DATA_DIR, cadenas: list[str] | None = None):
    """Generador síncrono que hace yield de (cadena, records, error) en orden de
    llegada. La cadena más rápida aparece primero — ideal para streaming SSE.
    `cadenas` selecciona qué cadenas consultar (_CADENAS_DEFAULT si es None)."""
    seleccion = set(cadenas) if cadenas is not None else set(_CADENAS_DEFAULT)
    activas = {c: t for c, t in _tareas_disponibles(term, cache_dir).items() if c in seleccion}

    with ThreadPoolExecutor(max_workers=max(len(activas), 1)) as ex:
        futs = {ex.submit(fn, *args): cadena for cadena, (fn, args) in activas.items()}
        for fut in as_completed(futs):
            cadena = futs[fut]
            try:
                records = fut.result()
                log.info("live_search streaming: %s — %d registros para '%s'", cadena, len(records), term)
                yield cadena, records, None
            except Exception as exc:
                log.error("live_search streaming: %s falló — %s", cadena, exc, exc_info=True)
                yield cadena, [], str(exc)

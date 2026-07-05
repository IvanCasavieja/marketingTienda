"""
tata_graphql.py — cliente de la API GraphQL interna de Ta-Ta.

Usa requests directo — sin Playwright ni browser.
El WAF de Ta-Ta acepta requests con UA de Chrome sin bloqueos.

Una fila por (producto × sucursal) — 15 tiendas en Uruguay.
regionId calculable como base64("SW#" + sellerId) sin consultar API.
"""

import json
import time
import urllib.parse

import requests


# ── Sucursales ────────────────────────────────────────────────────────────────
# regionId = base64("SW#" + sellerId)

SUCURSALES = [
    {"seller_id": "tatauymontevideo",   "nombre": "Montevideo",     "region_id": "U1cjdGF0YXV5bW9udGV2aWRlbw=="},
    {"seller_id": "tatauycanelones",    "nombre": "Canelones",      "region_id": "U1cjdGF0YXV5Y2FuZWxvbmVz"},
    {"seller_id": "tatauymaldonado",    "nombre": "Maldonado",      "region_id": "U1cjdGF0YXV5bWFsZG9uYWRv"},
    {"seller_id": "tatauycolonia",      "nombre": "Colonia",        "region_id": "U1cjdGF0YXV5Y29sb25pYQ=="},
    {"seller_id": "tatauyrocha",        "nombre": "Rocha",          "region_id": "U1cjdGF0YXV5cm9jaGE="},
    {"seller_id": "tatauysalto",        "nombre": "Salto",          "region_id": "U1cjdGF0YXV5c2FsdG8="},
    {"seller_id": "tatauypaysandu",     "nombre": "Paysandú",       "region_id": "U1cjdGF0YXV5cGF5c2FuZHU="},
    {"seller_id": "tatauytacuarembo",   "nombre": "Tacuarembó",     "region_id": "U1cjdGF0YXV5dGFjdWFyZW1ibw=="},
    {"seller_id": "tatauymelo",         "nombre": "Melo",           "region_id": "U1cjdGF0YXV5bWVsbw=="},
    {"seller_id": "tatauyminas",        "nombre": "Minas",          "region_id": "U1cjdGF0YXV5bWluYXM="},
    {"seller_id": "tatauytreintaytres", "nombre": "Treinta y Tres", "region_id": "U1cjdGF0YXV5dHJlaW50YXl0cmVz"},
    {"seller_id": "tatauyrivera",       "nombre": "Rivera",         "region_id": "U1cjdGF0YXV5cml2ZXJh"},
    {"seller_id": "tatauymercedes",     "nombre": "Mercedes",       "region_id": "U1cjdGF0YXV5bWVyY2VkZXM="},
    {"seller_id": "tatauyartigas",      "nombre": "Artigas",        "region_id": "U1cjdGF0YXV5YXJ0aWdhcw=="},
    {"seller_id": "tatauytrinidad",     "nombre": "Trinidad",       "region_id": "U1cjdGF0YXV5dHJpbmlkYWQ="},
]


# ── HTTP ──────────────────────────────────────────────────────────────────────

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "es-UY,es;q=0.9",
    "Referer": "https://www.tata.com.uy/",
    "content-type": "application/json",
}

_SESSION = requests.Session()
_SESSION.headers.update(_HEADERS)
# Pool generoso: la búsqueda en vivo lanza 15 sucursales en paralelo
_SESSION.mount("https://", requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20))
_SESSION.mount("http://",  requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20))


def _fetch(url: str, retries: int = 3, timeout: int = 8, fast_fail: bool = False) -> dict | None:
    for attempt in range(retries):
        try:
            r = _SESSION.get(url, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                if fast_fail:
                    return None  # live search: fail fast instead of sleeping 30s
                time.sleep(30)
                continue
            if r.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
        except Exception:
            if attempt < retries - 1 and not fast_fail:
                time.sleep(1.5)
    return None


# ── URL builder ───────────────────────────────────────────────────────────────

def _build_url(cat_facets: list, first: int = 50, after: str = "0",
               region_id: str = "") -> str:
    facets = [{"key": f"category-{i+1}", "value": v} for i, v in enumerate(cat_facets)]
    facets.append({"key": "channel", "value": f'{{"salesChannel":"4","regionId":"{region_id}"}}'})
    facets.append({"key": "locale",  "value": "es-uy"})
    variables = {
        "first": first, "after": after, "sort": "score_desc",
        "term": "", "selectedFacets": facets,
    }
    qs = urllib.parse.quote(json.dumps(variables))
    return f"https://www.tata.com.uy/api/graphql?operationName=ProductsQuery&variables={qs}"


# ── Parser ────────────────────────────────────────────────────────────────────

def _parse_node(node: dict, sucursal: dict | None = None) -> dict:
    offers      = node.get("offers", {}) or {}
    oferta_list = offers.get("offers", [])
    o = oferta_list[0] if oferta_list else {}
    return {
        "tienda":          "Ta-Ta",
        "nombre":          node.get("name"),
        "precio":          o.get("price") or offers.get("lowPrice"),
        "precio_lista":    o.get("listPrice"),
        "sku":             node.get("sku"),
        "barcode":         node.get("gtin"),
        "marca":           (node.get("brand") or {}).get("name"),
        "url":             f"https://www.tata.com.uy/{node.get('slug')}/p",
        "sucursal_id":     sucursal["seller_id"] if sucursal else None,
        "sucursal_nombre": sucursal["nombre"]    if sucursal else None,
    }



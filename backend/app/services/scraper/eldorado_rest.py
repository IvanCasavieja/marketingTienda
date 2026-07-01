"""
eldorado_rest.py — Scraper de El Dorado via VTEX IO Intelligent Search.

Una fila por (producto × sucursal) — 17 tiendas en Uruguay.
Precios con regionId para el precio real de cada tienda (varían por departamento).

APIs:
  /api/checkout/pub/regions                  → regionId por código postal (usado
                                                para descubrir los IDs; están
                                                hardcodeados en SUCURSALES abajo)
  /_v/api/intelligent-search/product_search  → precios + catálogo con regionId

Limitación conocida: la IS API de ElDorado no soporta filtrado por categoría
ni ordenamiento (fq= y sort= devuelven HTTP 400).  El máximo accesible es
posición 0–2499 (2500 productos).  Se itera toda esa ventana por sucursal.
"""

import logging
import time
from typing import Iterator

import requests

from .adapters import ProductRecord

log = logging.getLogger(__name__)

_UA      = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0"
_BASE    = "https://www.eldorado.com.uy"
_IS_URL  = f"{_BASE}/_v/api/intelligent-search/product_search"
_IS_PAGE = 50
_IS_MAX  = 2499   # to= máximo antes de HTTP 400 (límite de la IS de ElDorado)

_HEADERS = {
    "User-Agent": _UA,
    "Accept":     "application/json",
}

# ── Tiendas con regionId (obtenidos via /api/checkout/pub/regions + CP) ───────

SUCURSALES = [
    {"id": "eldoradouy2099", "nombre": "Montevideo",         "region_id": "v2.DD35665D6A73D8DCA70480411AD8CAA4"},
    {"id": "eldoradouy770",  "nombre": "La Paz",             "region_id": "v2.304A1DEFCB2E4B29E2DD3441ABD2E0A2"},
    {"id": "eldoradouy765",  "nombre": "Ciudad de la Costa", "region_id": "v2.B2FD9AE189A8BB61E36DC1662DD8CF2B"},
    {"id": "eldoradouy761",  "nombre": "Barros Blancos",     "region_id": "v2.E621B8D5AECA52D35DE77A393A734C2E"},
    {"id": "eldoradouy950",  "nombre": "Maldonado",          "region_id": "v2.7FEF430037A06712D4072D9A8F12ACC9"},
    {"id": "eldoradouy554",  "nombre": "San Carlos",         "region_id": "v2.1F8E022C7447B730FC86F0E92464D1C6"},
    {"id": "eldoradouy550",  "nombre": "Punta del Este",     "region_id": "v2.0BB7FC0C99CF9FD34C25B753FBC5F147"},
    {"id": "eldoradouy830",  "nombre": "Rocha",              "region_id": "v2.26432E369E1543ACC1E5167AF313685C"},
    {"id": "eldoradouy880",  "nombre": "Rocha Centro",       "region_id": "v2.F17CC5856BAA58DD72193116D68902C5"},
    {"id": "eldoradouy470",  "nombre": "Colonia",            "region_id": "v2.F5930DA9396D2913B7BA36C2EE557C95"},
    {"id": "eldoradouy620",  "nombre": "Treinta y Tres",     "region_id": "v2.36FDA2809DB75E8DF80673E230CF58B2"},
    {"id": "eldoradouy2610", "nombre": "Salto",              "region_id": "v2.15205C22914B42269AA9E6CC07AE0D54"},
    {"id": "eldoradouy1710", "nombre": "Paysandú",           "region_id": "v2.8D872B090EE3E9398F8041B3F5DCEFE8"},
    {"id": "eldoradouy2310", "nombre": "Tacuarembó",         "region_id": "v2.B4841C53A78B32B3A14A567A4881821F"},
    {"id": "eldoradouy1410", "nombre": "Durazno",            "region_id": "v2.808DE92B37CB259A492482D11A9F1955"},
    {"id": "eldoradouy2410", "nombre": "Rivera",             "region_id": "v2.B564BD1B4559562BA5DD10EAAB42E0AC"},
    {"id": "eldoradouy2510", "nombre": "Florida",            "region_id": "v2.86F646CDE3A12758759620B06035858D"},
]

# 4 fases: ~4-5 sucursales por fase
ELDORADO_PHASES_BY_STORE: dict[int, list[dict]] = {
    1: SUCURSALES[0:5],    # Montevideo, La Paz, Costa, Barros Blancos, Maldonado
    2: SUCURSALES[5:9],    # San Carlos, Punta del Este, Rocha, Rocha Centro
    3: SUCURSALES[9:13],   # Colonia, Treinta y Tres, Salto, Paysandú
    4: SUCURSALES[13:17],  # Tacuarembó, Durazno, Rivera, Florida
}


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _get(url: str, params: dict) -> requests.Response:
    for attempt in range(1, 4):
        try:
            r = requests.get(url, params=params, headers=_HEADERS, timeout=8)
            if r.status_code in (200, 206):
                return r
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 30))
                log.warning("ElDorado: rate limit — esperando %ds", wait)
                time.sleep(wait)
                continue
            log.warning("ElDorado: HTTP %d intento %d/3 — %s", r.status_code, attempt, url)
        except requests.exceptions.Timeout:
            log.warning("ElDorado: timeout intento %d/3", attempt)
        except requests.exceptions.ConnectionError as e:
            log.warning("ElDorado: conexión intento %d/3 — %s", attempt, e)
        if attempt < 3:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"ElDorado: fallo definitivo tras 3 intentos — {url}")


# ── Iterador de productos via Intelligent Search ──────────────────────────────

def _iter_store_is(region_id: str) -> Iterator[dict]:
    """
    Itera los productos de una tienda via IS con su regionId.

    La IS de ElDorado no soporta filtrado por categoría (fq= → HTTP 400) ni
    ordenamiento (sort= → HTTP 400).  Se accede directamente desde la posición
    0 hasta _IS_MAX (2499).  Más allá de ese valor la API devuelve HTTP 400.
    """
    from_idx = 0

    while from_idx <= _IS_MAX:
        to_idx = min(from_idx + _IS_PAGE - 1, _IS_MAX)
        r = _get(_IS_URL, {
            "query":                "",
            "count":                _IS_PAGE,
            "locale":               "es-UY",
            "from":                 from_idx,
            "to":                   to_idx,
            "regionId":             region_id,
            "hideUnavailableItems": "false",
        })
        data     = r.json()
        products = data.get("products") or []
        if not products:
            break

        for p in products:
            yield p

        from_idx = to_idx + 1
        time.sleep(0.05)


# ── Parser de productos ───────────────────────────────────────────────────────

def _parse_product_is(raw: dict, sucursal: dict) -> ProductRecord | None:
    link_text = raw.get("linkText", "")
    if not link_text:
        return None

    items = raw.get("items") or []
    if not items:
        return None

    # Preferir primer SKU con stock; si no, usar el primero disponible
    sku_item = None
    for it in items:
        sellers = it.get("sellers") or []
        if sellers and sellers[0].get("commertialOffer", {}).get("AvailableQuantity", 0) > 0:
            sku_item = it
            break
    if sku_item is None:
        sku_item = items[0]

    offer  = (sku_item.get("sellers") or [{}])[0].get("commertialOffer", {})
    precio = offer.get("Price")
    lista  = offer.get("ListPrice")

    if precio is None:
        return None

    ref_ids = sku_item.get("referenceId") or []
    sku     = ref_ids[0].get("Value") if ref_ids else sku_item.get("itemId")
    barcode = sku_item.get("ean") or None

    cats = raw.get("categories") or []
    cat  = cats[0].strip("/").replace("/", " > ") if cats else None

    return ProductRecord(
        tienda          = "ElDorado",
        url             = f"{_BASE}/{link_text}/p",
        nombre          = raw.get("productName") or raw.get("productTitle"),
        precio          = float(precio),
        precio_lista    = float(lista) if lista and lista != precio else None,
        sku             = str(sku) if sku else None,
        barcode         = str(barcode) if barcode else None,
        marca           = raw.get("brand") or None,
        categoria       = cat,
        sucursal_id     = sucursal["id"],
        sucursal_nombre = sucursal["nombre"],
    )


# ── Scan por fase ─────────────────────────────────────────────────────────────

def scan_fase(fase: int, fases: dict[int, list[dict]]) -> list[ProductRecord]:
    """
    Raspa los productos de El Dorado para las sucursales del rango dado.
    `fases` es el resultado de `build_phases()` — dict {fase: [sucursales]}.
    Una fila por (producto × sucursal).

    Nota: la IS API de ElDorado limita el acceso a las posiciones 0-2499
    (≈2500 productos más relevantes).  El catálogo completo tiene ~9565.
    """
    sucursales = fases.get(fase, [])
    if not sucursales:
        log.warning("ElDorado: fase %d vacía", fase)
        return []

    log.info("ElDorado: fase %d — %d sucursales", fase, len(sucursales))

    records: list[ProductRecord] = []

    for suc in sucursales:
        suc_id    = suc["id"]
        suc_count = 0

        for raw in _iter_store_is(suc["region_id"]):
            rec = _parse_product_is(raw, suc)
            if rec is not None:
                records.append(rec)
                suc_count += 1

        log.info("ElDorado [%s]: %d productos", suc["nombre"], suc_count)

    log.info("ElDorado: fase %d completada — %d registros (sucursal×producto)", fase, len(records))
    return records


def build_phases(n: int = 4) -> dict[int, list[dict]]:
    """
    Retorna las fases con sus sucursales.
    Compatible con la llamada en fases.py (_get_eldorado_phases → build_phases).
    """
    return ELDORADO_PHASES_BY_STORE

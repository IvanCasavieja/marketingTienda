"""
eldorado_rest.py — Scraper REST de El Dorado (VTEX IO, catálogo público).

No requiere autenticación ni Playwright. API VTEX Catalog System pública.
Precio único nacional (sin variación por sucursal).

Itera por categorías hoja para evitar el límite de 2500 productos de VTEX
en búsquedas lineales. Filtro correcto: fq=C:/{path_de_ids}/.

~9.600 productos en ~318 categorías hoja.
URL: https://www.eldorado.com.uy/{linkText}/p
"""

import logging
import time
from typing import Generator

import requests

from .adapters import ProductRecord

log = logging.getLogger(__name__)

_UA       = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0"
_BASE     = "https://www.eldorado.com.uy"
_ENDPOINT = f"{_BASE}/api/catalog_system/pub/products/search"
_CAT_TREE = f"{_BASE}/api/catalog_system/pub/category/tree/5"
_PAGE     = 50   # máximo de VTEX por llamada

_HEADERS = {
    "User-Agent": _UA,
    "Accept":     "application/json",
}


def _llamar(url: str, params: dict) -> requests.Response:
    for attempt in range(1, 4):
        try:
            r = requests.get(url, params=params, headers=_HEADERS, timeout=30)
            if r.status_code in (200, 206):
                return r
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 30))
                log.warning("ElDorado: rate limit — esperando %ds", wait)
                time.sleep(wait)
                continue
            log.warning("ElDorado: HTTP %d intento %d/3", r.status_code, attempt)
        except requests.exceptions.Timeout:
            log.warning("ElDorado: timeout intento %d/3", attempt)
        except requests.exceptions.ConnectionError as e:
            log.warning("ElDorado: conexión intento %d/3 — %s", attempt, e)
        if attempt < 3:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"ElDorado: fallo definitivo tras 3 intentos — {url}")


def _get_leaf_categories() -> list[dict]:
    """
    Descarga el árbol VTEX y devuelve lista de categorías hoja con su path.
    Cada item: {id, name, path_fq} donde path_fq = "C:/{root_id}/.../leaf_id/"
    """
    r = _llamar(_CAT_TREE, {})
    tree = r.json()
    hojas = []

    def _recorrer(nodos: list, id_path: list[int]):
        for nodo in nodos:
            current_path = id_path + [nodo["id"]]
            hijos = nodo.get("children") or []
            if not hijos:
                fq = "C:/" + "/".join(str(i) for i in current_path) + "/"
                hojas.append({
                    "id":       nodo["id"],
                    "name":     nodo.get("name", str(nodo["id"])),
                    "path_fq":  fq,
                })
            else:
                _recorrer(hijos, current_path)

    _recorrer(tree, [])
    return hojas


def _iter_category(fq: str) -> Generator[dict, None, None]:
    """Itera todos los productos de una categoría hoja paginando de a _PAGE."""
    cursor = 0
    total  = None

    while True:
        end = cursor + _PAGE - 1
        r   = _llamar(_ENDPOINT, {"fq": fq, "_from": cursor, "_to": end})
        data = r.json()

        if total is None:
            resources = r.headers.get("resources", "")
            total = int(resources.split("/")[-1]) if "/" in resources else 0
            if total == 0:
                return

        if not data:
            break

        for item in data:
            yield item

        cursor = end + 1
        if cursor >= total:
            break


def _parse_product(raw: dict) -> ProductRecord | None:
    """Convierte un item de la API VTEX en ProductRecord."""
    link_text = raw.get("linkText", "")
    if not link_text:
        return None

    # Tomar el primer item (SKU) activo con stock; si no, el primero
    sku_item = None
    for it in raw.get("items", []):
        sellers = it.get("sellers", [])
        if sellers and sellers[0].get("commertialOffer", {}).get("AvailableQuantity", 0) > 0:
            sku_item = it
            break
    if sku_item is None:
        sku_item = raw.get("items", [{}])[0] if raw.get("items") else {}

    offer  = (sku_item.get("sellers") or [{}])[0].get("commertialOffer", {})
    precio = offer.get("Price")
    lista  = offer.get("ListPrice")

    if precio is None:
        return None

    ref_ids = sku_item.get("referenceId", [])
    sku     = ref_ids[0].get("Value") if ref_ids else sku_item.get("itemId")
    barcode = sku_item.get("ean") or None

    cats = raw.get("categories", [])
    cat  = cats[0].strip("/").replace("/", " > ") if cats else None

    return ProductRecord(
        tienda       = "ElDorado",
        url          = f"{_BASE}/{link_text}/p",
        nombre       = raw.get("productName") or raw.get("productTitle"),
        precio       = float(precio),
        precio_lista = float(lista) if lista else None,
        sku          = str(sku) if sku else None,
        barcode      = str(barcode) if barcode else None,
        marca        = raw.get("brand") or None,
        categoria    = cat,
    )


def scan_fase(fase: int, fases: dict[int, list[dict]]) -> list[ProductRecord]:
    """
    Raspa los productos de El Dorado para las categorías del rango dado.
    `fases` es el resultado de `build_phases()` — se genera una sola vez
    y se pasa a cada fase para evitar re-descargar el árbol de categorías.

    Llamado por run_eldorado_fase() en fases.py.
    """
    cats = fases.get(fase, [])
    if not cats:
        log.warning("ElDorado: fase %d vacía o inexistente", fase)
        return []

    log.info("ElDorado: fase %d — %d categorías", fase, len(cats))
    records:  list[ProductRecord] = []
    seen_ids: set[str]            = set()   # deduplicar por productId

    for cat in cats:
        cat_records = 0
        for raw in _iter_category(cat["path_fq"]):
            pid = raw.get("productId")
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            rec = _parse_product(raw)
            if rec is not None:
                records.append(rec)
                cat_records += 1
        if cat_records:
            log.debug("ElDorado [%s]: %d", cat["name"], cat_records)

    log.info("ElDorado: fase %d completada — %d productos", fase, len(records))
    return records


def build_phases(n: int = 4) -> dict[int, list[dict]]:
    """
    Descarga el árbol de categorías y lo divide en n fases aproximadamente iguales.
    Retornar {1: [cats...], 2: [cats...], ...}
    """
    hojas = _get_leaf_categories()
    log.info("ElDorado: %d categorías hoja encontradas", len(hojas))
    size  = (len(hojas) + n - 1) // n
    return {i + 1: hojas[i * size:(i + 1) * size] for i in range(n)}

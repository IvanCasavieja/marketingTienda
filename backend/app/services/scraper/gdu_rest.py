"""
gdu_rest.py — Scraper REST de GDU (Disco / Devoto / Géant).

Reemplaza el scraper Playwright de GDU. Sin navegador, sin sesión Blazor.
Usa los microservicios Azure de GDU directamente via JWT público.

Una fila por (producto × sucursal) — sin agrupar sucursales con mismo precio,
porque cada sucursal tiene su propia URL con el parámetro ?sc=<branch_id>.

URL resultante: https://www.disco.com.uy/product/p/<product_id>?sc=<branch_id>
Blazor ignora el segmento slug/categoria cuando el formato es /product/p/{id}.
El mismo product_id es válido en las tres cadenas (catálogo unificado GDU).

APIs:
  oauth.disco.com.uy                              → JWT (~15 días, sin secret)
  gdu-products.azurewebsites.net                  → catálogo paginado (100/pág)
  gdu-productsprices.azurewebsites.net            → precios (100 IDs/call)
  gdu-branchoffices.azurewebsites.net             → sucursales (sin auth)
"""

import json
import logging
import time
from pathlib import Path

import requests

from .adapters import ProductRecord

log = logging.getLogger(__name__)

# ── Endpoints ─────────────────────────────────────────────────────────────────

_UA          = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0"
_TOKEN_URL   = "https://oauth.disco.com.uy/connect/token"
_BASE_PRODS  = "https://gdu-products.azurewebsites.net"
_BASE_PRICES = "https://gdu-productsprices.azurewebsites.net"
_ACCOUNT     = "gdu"
_PAGE_SIZE   = 100   # cap real de la API (ignorada si se pasa más)
_PRICE_BATCH = 100   # cap real de la API de precios

# ── Rangos de ID por cadena ───────────────────────────────────────────────────
# [P3] Clasificar por ID numérico, no por nombre: Express/Fresh Market de Devoto
# (3102–3140) no tienen "Devoto" en el nombre y se clasificarían mal.

_RANGO_DISCO  = range(100, 200)
_RANGO_DEVOTO = range(3000, 4000)
_RANGO_GEANT  = {1501, 5201}

_BRANCH_IDS_EXCLUIR = {"CDPerimetral", "Marketplace", "SUC-01", "string", " 3026 "}

_DOMINIOS = {
    "Disco":  "https://www.disco.com.uy",
    "Devoto": "https://www.devoto.com.uy",
    "Geant":  "https://www.geant.com.uy",
}

_PKG_DIR = Path(__file__).parent

# ── Helpers ───────────────────────────────────────────────────────────────────

def _clasificar_cadena(branch_id: str) -> str:
    if not branch_id.isdigit():
        return "excluir"
    n = int(branch_id)
    if n in _RANGO_DISCO:
        return "Disco"
    if n in _RANGO_DEVOTO:
        return "Devoto"
    if n in _RANGO_GEANT:
        return "Geant"
    return "excluir"


def _construir_url(cadena: str, product_id: str, branch_id: str) -> str:
    """URL con parámetro de sucursal. /product/p/{id} funciona sin slug ni categoría."""
    base = _DOMINIOS.get(cadena, "https://www.disco.com.uy")
    return f"{base}/product/p/{product_id}?sc={branch_id}"


# ── JWT con cache en disco ────────────────────────────────────────────────────

def _get_jwt(cache_dir: Path, force_refresh: bool = False) -> str:
    """
    JWT con cache en archivo. Dura ~15 días; se renueva si faltan < 24h.
    Para integración futura: reemplazar cache_file por Redis.
    """
    cache_file = cache_dir / "gdu_jwt_cache.json"
    cache_dir.mkdir(parents=True, exist_ok=True)

    if not force_refresh and cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if time.time() < cached.get("expires_at", 0) - 86400:
                return cached["access_token"]
        except Exception:
            pass

    log.info("GDU REST: obteniendo JWT de oauth.disco.com.uy ...")
    r = requests.post(
        _TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id":  "gdu-blazor",
            "scope":      "ecom_products_api ecom_products_prices_api",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": _UA},
        timeout=8,
    )
    r.raise_for_status()
    payload     = r.json()
    token       = payload["access_token"]
    expires_in  = payload.get("expires_in", 1_296_000)  # default 15 días
    cache_file.write_text(
        json.dumps({"access_token": token, "expires_at": time.time() + expires_in}, indent=2),
        encoding="utf-8",
    )
    log.info("GDU REST: JWT obtenido (expira en %.0f días)", expires_in / 86400)
    return token


def _build_session(jwt: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {jwt}",
        "User-Agent":    _UA,
        "Accept":        "application/json",
    })
    return s


def _llamar(session: requests.Session, method: str, url: str, **kwargs) -> requests.Response:
    """HTTP con retry/backoff exponencial."""
    for attempt in range(1, 4):
        try:
            resp = session.request(method, url, timeout=8, **kwargs)
            if resp.status_code == 200:
                return resp
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 30))
                log.warning("GDU REST: rate limit — esperando %ds", wait)
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                log.warning("GDU REST: HTTP %d intento %d/3 — %s", resp.status_code, attempt, url)
            else:
                resp.raise_for_status()
        except requests.exceptions.Timeout:
            log.warning("GDU REST: timeout intento %d/3 — %s", attempt, url)
        except requests.exceptions.ConnectionError as e:
            log.warning("GDU REST: conexión intento %d/3 — %s", attempt, e)

        if attempt < 3:
            time.sleep(2 ** attempt)

    raise RuntimeError(f"GDU REST: fallo definitivo tras 3 intentos — {url}")


# ── Metadatos de sucursales ───────────────────────────────────────────────────

_CHAIN_MAP = {
    "Disco":  "Disco",
    "Devoto": "Devoto",
    "Geant":  "Geant",
    "GDU":    "excluir",  # Express/Fresh Market: sus IDs no son reconocidos en devoto.com.uy
}


def _load_branch_meta() -> dict[str, dict]:
    """
    Carga {branch_id: {nombre, cadena}} desde el JSON empaquetado.
    Usa el campo 'chain' del JSON para clasificar (Disco/Devoto/Geant/GDU).
    chain='GDU' → excluir: son Express/Fresh Market cuyo ?sc= no es reconocido
    por devoto.com.uy (el sitio muestra el store default ignorando el parámetro).
    chain='Devoto' incluye tanto Devoto clásico como Devoto Express.
    """
    json_path = _PKG_DIR / "sucursales_gdu.json"
    if not json_path.exists():
        log.warning("GDU REST: sucursales_gdu.json no encontrado en %s", _PKG_DIR)
        return {}

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    result: dict[str, dict] = {}
    for chain_key, branches in data.items():
        cadena = _CHAIN_MAP.get(chain_key, "excluir")
        if cadena == "excluir":
            continue
        for b in branches:
            bid = b["id"]
            if bid in _BRANCH_IDS_EXCLUIR:
                continue
            result[bid] = {"nombre": b.get("nombre", bid), "cadena": cadena}
    return result


# ── Consulta de precios ───────────────────────────────────────────────────────

def _get_prices_batch(session: requests.Session, product_ids: list[str]) -> list[dict]:
    """
    Precios de hasta 100 productos para TODAS las sucursales a la vez.

    [P1] Filtrar por priceListId.isdigit(): solo IDs base de sucursal.
         Descartar _YA (tarjeta fidelización), _NORMAL (lista), discouy* (web).
    [P5] Cap: 100 IDs por llamada — la API trunca silenciosamente si se pasan más.
    """
    params = [("ProductsIds", pid) for pid in product_ids[:_PRICE_BATCH]]
    r = _llamar(
        session, "GET",
        f"{_BASE_PRICES}/api/accounts/{_ACCOUNT}/products-prices/active",
        params=params,
    )
    return r.json()


def _parse_prices(
    price_records: list[dict],
    names:         dict[str, str],
    barcodes:      dict[str, str | None],
    categorias:    dict[str, str | None],
    branch_meta:   dict[str, dict],
    out:           list[ProductRecord],
) -> None:
    """
    Convierte raw price records en ProductRecord (1 por producto × sucursal).
    Modifica `out` in-place.
    """
    for rec in price_records:
        pl_id = rec.get("priceListId", "")

        # [P1] Solo IDs puramente numéricos = precio base de sucursal
        if not pl_id.isdigit():
            continue
        # [P2] Excluir IDs no comerciales
        if pl_id in _BRANCH_IDS_EXCLUIR:
            continue

        meta = branch_meta.get(pl_id)
        if not meta:
            continue

        cadena        = meta["cadena"]
        pid           = rec["productId"]
        name          = names.get(pid, pid)
        current       = rec["price"]["currentPrice"]
        normal        = rec["price"]["normalPrice"]

        # normalPrice = precio de mostrador (lo que paga cualquiera)
        # currentPrice = precio con tarjeta Hiper+ / promoción activa
        # Si normalPrice=0 y currentPrice=0 → sin precio, saltear
        # Si currentPrice < normalPrice → mostrar currentPrice con normalPrice tachado
        # Si currentPrice = 0 (sin promo) → mostrar normalPrice sin descuento
        precio_base = normal or current
        if not precio_base:
            continue

        precio_final = current if (current and current < precio_base) else precio_base
        precio_lista_val = precio_base if (current and current < precio_base) else None

        out.append(ProductRecord(
            tienda          = cadena,
            url             = _construir_url(cadena, pid, pl_id),
            nombre          = name,
            precio          = precio_final,
            precio_lista    = precio_lista_val,
            sku             = pid,
            barcode         = barcodes.get(pid),
            categoria       = categorias.get(pid),
            sucursal_id     = pl_id,
            sucursal_nombre = meta["nombre"],
        ))

"""Scrapeo TOTAL del catálogo de la competencia, para el informe semanal de pricing.

No es la búsqueda en vivo (live_search.py), que pide un término y trae lo que
matchea: acá se baja el catálogo COMPLETO de cada cadena, sin buscar nada.

Cómo se corre:
    python scripts/scrapeo_total.py                  # todo, y arma el Excel
    python scripts/scrapeo_total.py --cadenas GDU    # solo una
    python scripts/scrapeo_total.py --solo-excel     # rearma el Excel con lo ya bajado

Cada cadena escribe su JSONL en un archivo temporal y recién al terminar BIEN
reemplaza al anterior (--dir, por defecto ~/scrapeo_total): si una corrida se
corta, queda la última buena, no un archivo vaciado a medias. Con cada cadena
terminada se actualiza además resumen.json (cuántos publica la cadena y
cuántos se bajaron), que es de donde el Excel saca la hoja Cobertura.

UNA FILA = un producto a un precio en una cadena. Las sucursales que comparten
exactamente el mismo precio van juntas en una fila, con su lista y su cantidad:
no se pierde ni un precio, y evita que GDU solo (65.796 productos × 72
sucursales = 4,7 millones) no entre en Excel, que corta en 1.048.576 filas por
hoja.

Hasta dónde llega cada cadena (medido el 28/09/2026):
  GDU (Disco/Devoto/Géant)  catálogo completo, ~66.000 productos × 72 sucursales
  Ta-Ta                     PARCIAL: su API deja de devolver pasadas unas
                            páginas (~3.000 de ~9.000 por sucursal)
  El Dorado                 PARCIAL: su API corta en la posición 2.499 por
                            tienda (~4.900 juntando las 17)
  LOi                       catálogo completo, ~3.100 (troceado por categoría:
                            Algolia no deja pasar de 1.000 por consulta)
  FarmaShop                 catálogo completo, ~18.700 — sus páginas tardan
                            hasta 25 s, por eso se baja con reintentos
  Pigalle                   catálogo completo, ~7.200
  BlackDog / Electrohogar / CoverCompany   catálogo completo, precio único
Botiga queda AFUERA por defecto: su Magento devuelve exactamente el mismo
catálogo que FarmaShop y sumarla contaría todo dos veces. DIMM, Stienda, Fama,
Zona Tecno, AMV y Estación Hogar no exponen forma de listar el catálogo (sus
buscadores exigen un término): la hoja "Cobertura" del Excel lo dice
explícitamente para que nadie lea el informe como si fuera todo el mercado.
"""
import argparse
import json
import logging
import os
import sys
import time
import urllib.parse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Lock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from app.services.scraper import eldorado_rest as eldorado  # noqa: E402
from app.services.scraper import gdu_rest as gdu  # noqa: E402
from app.services.scraper import live_search as ls  # noqa: E402
from app.services.scraper import tata_graphql as tata  # noqa: E402

log = logging.getLogger("scrapeo")

COLUMNAS = [
    "cadena", "sku", "barcode", "nombre", "marca", "categoria",
    "precio", "precio_lista", "moneda",
    "sucursales", "sucursales_detalle", "url", "bajado",
]


# ── Escritura incremental ─────────────────────────────────────────────────

class Salida:
    """Un JSONL por cadena, escrito a medida que se baja.

    Escribe en un archivo temporal y recién al terminar BIEN reemplaza al
    definitivo: antes arrancaba vaciando el archivo, y si el reintento de una
    cadena fallaba a mitad de camino se perdía también lo de la semana
    anterior."""

    def __init__(self, carpeta: Path, cadena: str):
        self.ruta = carpeta / f"{cadena.replace('/', '_')}.jsonl"
        self._tmp = self.ruta.with_name(self.ruta.name + ".tmp")
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._f = self._tmp.open("w", encoding="utf-8")
        self._lock = Lock()
        self.n = 0
        # Lo completa cada bajada: cuántos productos DICE publicar la cadena.
        # Va a resumen.json, de donde el Excel arma la hoja Cobertura.
        self.total_reportado: int | None = None

    def fila(self, **kw) -> None:
        kw.setdefault("bajado", datetime.now().isoformat(timespec="seconds"))
        linea = json.dumps({c: kw.get(c) for c in COLUMNAS}, ensure_ascii=False)
        with self._lock:
            self._f.write(linea + "\n")
            self.n += 1
            if self.n % 5000 == 0:
                self._f.flush()
                log.info("  … %s filas", f"{self.n:,}")

    def cerrar(self, exito: bool = True) -> None:
        self._f.close()
        if exito and self.n > 0:
            os.replace(self._tmp, self.ruta)
        else:
            self._tmp.unlink(missing_ok=True)
            log.warning("%s: la corrida no terminó bien — queda el archivo anterior tal cual",
                        self.ruta.stem)


def _agrupar_por_precio(registros) -> list[dict]:
    """Las sucursales con el MISMO precio se juntan en una fila. `registros` son
    ProductRecord del mismo producto."""
    grupos: dict[tuple, list] = defaultdict(list)
    for r in registros:
        grupos[(r.precio, r.precio_lista, r.moneda)].append(r)
    filas = []
    for (precio, lista, moneda), rs in grupos.items():
        nombres = sorted({r.sucursal_nombre for r in rs if r.sucursal_nombre})
        uno = rs[0]
        filas.append(dict(
            cadena=uno.tienda, sku=uno.sku, barcode=uno.barcode, nombre=uno.nombre,
            marca=uno.marca, categoria=uno.categoria,
            precio=precio, precio_lista=lista, moneda=moneda,
            sucursales=len(rs), sucursales_detalle=", ".join(nombres),
            url=uno.url,
        ))
    return filas


# ── GDU (Disco / Devoto / Géant) ──────────────────────────────────────────

def bajar_gdu(salida: Salida, cache: Path, limite_paginas: int | None = None) -> None:
    jwt = gdu._get_jwt(cache)
    session = gdu._build_session(jwt)
    try:
        # en vivo: para el informe conviene la lista del día, no la empaquetada
        branch_meta = {s["id"]: {"nombre": s["nombre"], "cadena": s["cadena"]}
                       for s in gdu.descargar_sucursales()}
    except Exception as exc:
        log.warning("GDU: no pude leer las sucursales en vivo (%s), uso la lista guardada", exc)
        branch_meta = gdu._load_branch_meta()
    porcadena = Counter(m["cadena"] for m in branch_meta.values())
    log.info("GDU: %d sucursales — %s", len(branch_meta), dict(porcadena))

    def pagina(p: int) -> dict:
        r = gdu._llamar(session, "GET", f"{gdu._BASE_PRODS}/api/accounts/{gdu._ACCOUNT}/products",
                        params={"Page": p, "ItemsPerPage": gdu._PAGE_SIZE, "IsActive": True})
        return r.json()

    primera = pagina(1)
    total_paginas = primera.get("totalPageCount", 1)
    if limite_paginas:
        total_paginas = min(total_paginas, limite_paginas)
    salida.total_reportado = primera.get("totalItemCount") or None
    log.info("GDU: %s productos en %d páginas", f"{primera.get('totalItemCount', 0):,}", total_paginas)

    cotizacion = gdu._get_cotizacion_compra(cache)
    vistos: set[str] = set()

    def procesar(items: list[dict]) -> None:
        names, barcodes, cats, dolar, ids = {}, {}, {}, set(), []
        for item in items:
            pid = item["id"]
            if pid in vistos:
                continue
            vistos.add(pid)
            ids.append(pid)
            desc = item.get("description", {}) or {}
            names[pid] = desc.get("name", pid)
            bl = item.get("barcodes") or []
            barcodes[pid] = bl[0].get("barcode") if bl else None
            cats[pid] = None
            for df in item.get("dynamicFields") or []:
                if df.get("fieldName") == "FILTER|Categoría":
                    cats[pid] = df.get("fieldValue")
                elif df.get("fieldName") == "FRONT_BACKEND|precioDolar" and str(df.get("fieldValue")).lower() == "true":
                    dolar.add(pid)
        if not ids:
            return
        for i in range(0, len(ids), gdu._PRICE_BATCH):
            lote = ids[i:i + gdu._PRICE_BATCH]
            try:
                crudos = gdu._get_prices_batch(session, lote)
            except Exception as exc:
                log.warning("GDU: precios fallaron para %d ids — %s", len(lote), exc)
                continue
            registros: list = []
            gdu._parse_prices(crudos, names, barcodes, cats, branch_meta, registros,
                              precio_dolar_ids=dolar, cotizacion_compra=cotizacion)
            por_producto: dict[tuple, list] = defaultdict(list)
            for r in registros:
                por_producto[(r.sku, r.tienda)].append(r)  # una fila por producto Y cadena
            for rs in por_producto.values():
                for fila in _agrupar_por_precio(rs):
                    salida.fila(**fila)

    procesar(primera.get("items") or [])
    for p in range(2, total_paginas + 1):
        try:
            procesar(pagina(p).get("items") or [])
        except Exception as exc:
            log.warning("GDU: página %d falló — %s", p, exc)
        if p % 50 == 0:
            log.info("GDU: página %d/%d, %s filas", p, total_paginas, f"{salida.n:,}")


# ── Ta-Ta ─────────────────────────────────────────────────────────────────

_TATA_PAGE = 50


def bajar_tata(salida: Salida, limite_paginas: int | None = None) -> None:
    por_producto: dict[str, list] = defaultdict(list)
    lock = Lock()
    # Lo que la API dice publicar (totalCount por sucursal): queda en el
    # resumen para que la Cobertura diga "parcial: X de Y" con el Y real.
    totales_reportados: list[int] = []

    def una_sucursal(suc: dict) -> int:
        bajados, after = 0, 0
        while True:
            url = tata._build_url([], first=_TATA_PAGE, after=str(after), region_id=suc["region_id"])
            data = tata._fetch(url, timeout=20)
            if data is None:
                break
            prods = ((data.get("data") or {}).get("search") or {}).get("products") or {}
            edges = prods.get("edges") or []
            if not edges:
                break
            for e in edges:
                d = tata._parse_node(e["node"], suc)
                if not d.get("precio"):
                    continue
                from app.services.scraper.adapters import ProductRecord
                r = ProductRecord(
                    tienda="Ta-Ta", url=d["url"], nombre=d["nombre"], precio=float(d["precio"]),
                    precio_lista=float(d["precio_lista"]) if d.get("precio_lista") and d["precio_lista"] != d["precio"] else None,
                    sku=d.get("sku"), barcode=d.get("barcode"), marca=d.get("marca"),
                    sucursal_id=d.get("sucursal_id"), sucursal_nombre=d.get("sucursal_nombre"),
                )
                with lock:
                    por_producto[str(r.sku)].append(r)
                bajados += 1
            after += _TATA_PAGE
            total = (prods.get("pageInfo") or {}).get("totalCount")
            if total:
                with lock:
                    totales_reportados.append(int(total))
            if total and after >= total:
                break
            if limite_paginas and after >= limite_paginas * _TATA_PAGE:
                break
            time.sleep(0.05)
        log.info("Ta-Ta: %s — %d productos", suc["nombre"], bajados)
        return bajados

    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(una_sucursal, tata.SUCURSALES))

    salida.total_reportado = max(totales_reportados) if totales_reportados else None
    for rs in por_producto.values():
        for fila in _agrupar_por_precio(rs):
            salida.fila(**fila)


# ── El Dorado ─────────────────────────────────────────────────────────────

def bajar_eldorado(salida: Salida, limite_paginas: int | None = None) -> None:
    por_producto: dict[str, list] = defaultdict(list)
    lock = Lock()

    def una_sucursal(suc: dict) -> None:
        n, desde = 0, 0
        tope = min(eldorado._IS_MAX, limite_paginas * eldorado._IS_PAGE) if limite_paginas else eldorado._IS_MAX
        while desde <= tope:
            hasta = min(desde + eldorado._IS_PAGE - 1, tope)
            try:
                r = eldorado._get(eldorado._IS_URL, {
                    "query": "", "count": hasta - desde + 1, "locale": "es-UY",
                    "from": desde, "to": hasta, "regionId": suc["region_id"],
                    "hideUnavailableItems": "false",
                }, timeout=15)
            except Exception as exc:
                log.warning("ElDorado %s: %s", suc["nombre"], exc)
                break
            productos = (r.json() or {}).get("products") or []
            if not productos:
                break
            for p in productos:
                rec = eldorado._parse_product_is(p, suc)
                if rec:
                    with lock:
                        por_producto[str(rec.sku)].append(rec)
                    n += 1
            desde = hasta + 1
            time.sleep(0.05)
        log.info("ElDorado: %s — %d productos", suc["nombre"], n)

    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(una_sucursal, eldorado.SUCURSALES))

    for rs in por_producto.values():
        for fila in _agrupar_por_precio(rs):
            salida.fila(**fila)


# ── LOi (Algolia) ─────────────────────────────────────────────────────────
# Algolia no deja pasar de 1.000 resultados por consulta ("you can only fetch the
# 1000 hits for this query"), y el catálogo son 3.091: se trocea por categoría,
# que es el facet que el propio buscador del sitio ya usa.

def _loi_consulta(params: str, query: str = "") -> dict:
    # _loi_post trae la key vigente y, si LOi la rotó, la relee del sitio y
    # reintenta solo (pasó el 28/09/2026: 403 con la key de la semana anterior).
    r = ls._loi_post(
        {"requests": [{"indexName": ls._LOI_ALGOLIA_INDEX, "query": query, "params": params}]},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["results"][0]


def bajar_loi(salida: Salida) -> None:
    base_filtro = "facetFilters=%5B%22product_enabled%3A1%22%5D"
    cabecera = _loi_consulta(f"hitsPerPage=1&{base_filtro}&facets=%5B%22category%22%5D&maxValuesPerFacet=1000")
    categorias = sorted((cabecera.get("facets") or {}).get("category", {}).keys())
    salida.total_reportado = cabecera.get("nbHits") or None
    log.info("LOi: %s productos en %d categorías", f"{cabecera.get('nbHits', 0):,}", len(categorias))

    vistos: set[str] = set()

    def guardar(hits: list[dict]) -> None:
        for h in hits:
            pid = str(h.get("product_sku") or h.get("product_id") or h.get("objectID"))
            if pid in vistos:
                continue
            vistos.add(pid)
            precio = h.get("product_price_int")
            if precio is None:
                continue
            lista = h.get("market_price_int")
            salida.fila(
                cadena="LOi", sku=pid, barcode=None, nombre=h.get("product_name"),
                marca=h.get("fabricante_name") or h.get("producer_name"),
                categoria=h.get("category"), precio=float(precio),
                precio_lista=float(lista) if lista and lista > precio else None,
                moneda=h.get("currency") or "UYU", sucursales=1, sucursales_detalle="",
                url=h.get("product_url") or "https://loi.com.uy",
            )

    for cat in categorias:
        filtro = urllib.parse.quote(json.dumps([["product_enabled:1"], [f"category:{cat}"]]))
        pagina = 0
        while True:
            try:
                res = _loi_consulta(f"hitsPerPage=1000&page={pagina}&facetFilters={filtro}")
            except Exception as exc:
                log.warning("LOi: categoría %s pág %d — %s", cat, pagina, exc)
                break
            hits = res.get("hits") or []
            guardar(hits)
            if pagina + 1 >= (res.get("nbPages") or 1) or not hits:
                break
            pagina += 1
            time.sleep(0.1)
    log.info("LOi: %s productos distintos", f"{len(vistos):,}")


# ── FarmaShop / Botiga (Magento 2) ────────────────────────────────────────

# products(search:"") devuelve 0 en este Magento: la busqueda vacia no lista nada.
# Filtrando por la categoria raiz (category_id=2, "Base") sí sale el catalogo
# entero -- 18.424 productos, medido el 21/09/2026.
_MAGENTO_CATALOGO = """
query Catalogo($pageSize: Int!, $currentPage: Int!) {
  products(filter: {category_id: {eq: "2"}}, pageSize: $pageSize, currentPage: $currentPage) {
    total_count
    items {
      name
      sku
      url_key
      price_range { minimum_price { final_price { value } regular_price { value } } }
    }
  }
}
"""
_MAGENTO_PAGINA = 100


def _magento_pagina(cadena: str, base: str, pagina: int, intentos: int = 3) -> dict | None:
    """Una página del catálogo, con reintentos.

    FarmaShop tarda entre 10 y 25 segundos por página: con el timeout de 20 s
    de antes, una página lenta cortaba la cadena entera a la mitad (pasó el
    21/09 y el 28/09, siempre alrededor de la página 131, dejando 13.000 de
    18.700). Timeout largo, tres intentos con espera, y si ni así sale se
    devuelve None para que la página se saltee sin frenar el resto."""
    payload = {"query": _MAGENTO_CATALOGO,
               "variables": {"pageSize": _MAGENTO_PAGINA, "currentPage": pagina}}
    for intento in range(1, intentos + 1):
        try:
            r = requests.post(f"{base}/graphql", json=payload, headers=ls._MAGENTO_HEADERS, timeout=45)
            r.raise_for_status()
            return (r.json().get("data") or {}).get("products") or {}
        except Exception as exc:
            log.warning("%s: página %d, intento %d/%d — %s", cadena, pagina, intento, intentos, exc)
            if intento < intentos:
                time.sleep(3 * intento)
    return None


def bajar_magento(salida: Salida, cadena: str, base: str, limite_paginas: int | None = None) -> None:
    primera = _magento_pagina(cadena, base, 1)
    if primera is None:
        raise RuntimeError(f"{cadena}: no contestó ni la primera página")
    total = primera.get("total_count") or 0
    salida.total_reportado = total or None
    # Se recorre por CANTIDAD de páginas, no hasta la primera página corta:
    # Pigalle devuelve 99 items en una página del medio (la 22), y el corte de
    # antes ("menos de 100 = se terminó") dejaba 2.200 de 7.200 productos.
    paginas = max(1, -(-total // _MAGENTO_PAGINA)) if total else 1
    if limite_paginas:
        paginas = min(paginas, limite_paginas)
    log.info("%s: %s productos en %d páginas", cadena, f"{total:,}", paginas)

    vistos: set = set()
    fallidas: list[int] = []

    def procesar(data: dict) -> None:
        for it in data.get("items") or []:
            sku = it.get("sku")
            if sku in vistos:
                # El catálogo se reordena mientras se pagina y algún producto
                # se repite entre páginas (580 repetidos el 28/09): una vez.
                continue
            vistos.add(sku)
            precios = ((it.get("price_range") or {}).get("minimum_price") or {})
            final = (precios.get("final_price") or {}).get("value")
            regular = (precios.get("regular_price") or {}).get("value")
            if not final:
                continue
            salida.fila(
                cadena=cadena, sku=sku, barcode=None, nombre=it.get("name"),
                marca=None, categoria=None, precio=float(final),
                precio_lista=float(regular) if regular and regular > final else None,
                moneda="UYU", sucursales=1, sucursales_detalle="",
                url=f"{base}/{it.get('url_key')}.html" if it.get("url_key") else base,
            )

    procesar(primera)
    for pagina in range(2, paginas + 1):
        data = _magento_pagina(cadena, base, pagina)
        if data is None:
            fallidas.append(pagina)
            continue
        procesar(data)
        time.sleep(0.05)

    # Una vuelta más por lo que falló: suele ser el sitio lento, no roto.
    for pagina in list(fallidas):
        data = _magento_pagina(cadena, base, pagina)
        if data is not None:
            procesar(data)
            fallidas.remove(pagina)
    if fallidas:
        log.warning("%s: %d páginas no salieron ni reintentando: %s",
                    cadena, len(fallidas), fallidas[:10])
    log.info("%s: %s con precio, de %s publicados", cadena, f"{salida.n:,}", f"{total:,}")


# ── WooCommerce (BlackDog, Electrohogar) ──────────────────────────────────
# La Store API de WooCommerce lista el catalogo sin autenticacion. Los precios
# vienen como enteros en la unidad minima: currency_minor_unit dice cuantos
# decimales tiene. BlackDog publica en dolares (currency_code USD).

_UA_JSON = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0",
            "Accept": "application/json"}


def _woo_precio(valor, minor: int):
    if valor in (None, ""):
        return None
    try:
        return round(int(valor) / (10 ** minor), 2)
    except (TypeError, ValueError):
        return None


def bajar_woocommerce(salida: Salida, cadena: str, base: str, limite_paginas: int | None = None) -> None:
    pagina = 1
    while True:
        try:
            r = requests.get(f"{base}/wp-json/wc/store/v1/products",
                             params={"per_page": 100, "page": pagina}, headers=_UA_JSON, timeout=25)
            r.raise_for_status()
            items = r.json()
        except Exception as exc:
            log.warning("%s: página %d — %s", cadena, pagina, exc)
            break
        if not isinstance(items, list) or not items:
            break
        if pagina == 1:
            log.info("%s: %s productos", cadena, r.headers.get("X-WP-Total", "?"))
        for it in items:
            precios = it.get("prices") or {}
            minor = precios.get("currency_minor_unit", 2)
            precio = _woo_precio(precios.get("price"), minor)
            if precio is None:
                continue
            regular = _woo_precio(precios.get("regular_price"), minor)
            marcas = [b.get("name") for b in (it.get("brands") or []) if b.get("name")]
            cats = [c.get("name") for c in (it.get("categories") or []) if c.get("name")]
            salida.fila(
                cadena=cadena, sku=it.get("sku") or str(it.get("id")), barcode=None,
                nombre=it.get("name"), marca=", ".join(marcas) or None,
                categoria=" > ".join(cats) or None, precio=precio,
                precio_lista=regular if regular and regular > precio else None,
                moneda=precios.get("currency_code") or "UYU",
                sucursales=1, sucursales_detalle="", url=it.get("permalink") or base,
            )
        if len(items) < 100:
            break
        pagina += 1
        if limite_paginas and pagina > limite_paginas:
            break
        time.sleep(0.1)


# ── Shopify (CoverCompany) ────────────────────────────────────────────────
# /products.json es el feed publico de cualquier tienda Shopify. Una fila por
# VARIANTE: cada una tiene su SKU y su precio.

def bajar_shopify(salida: Salida, cadena: str, base: str, limite_paginas: int | None = None) -> None:
    pagina = 1
    total = 0
    while True:
        try:
            r = requests.get(f"{base}/products.json", params={"limit": 250, "page": pagina},
                             headers=_UA_JSON, timeout=25)
            r.raise_for_status()
            productos = (r.json() or {}).get("products") or []
        except Exception as exc:
            log.warning("%s: página %d — %s", cadena, pagina, exc)
            break
        if not productos:
            break
        for prod in productos:
            for v in prod.get("variants") or []:
                try:
                    precio = float(v.get("price"))
                except (TypeError, ValueError):
                    continue
                try:
                    lista = float(v.get("compare_at_price")) if v.get("compare_at_price") else None
                except (TypeError, ValueError):
                    lista = None
                titulo = prod.get("title") or ""
                if v.get("title") and v["title"].lower() != "default title":
                    titulo = f"{titulo} - {v['title']}"
                salida.fila(
                    cadena=cadena, sku=v.get("sku") or str(v.get("id")), barcode=None,
                    nombre=titulo, marca=prod.get("vendor"), categoria=prod.get("product_type"),
                    precio=precio, precio_lista=lista if lista and lista > precio else None,
                    moneda="UYU", sucursales=1, sucursales_detalle="",
                    url=f"{base}/products/{prod.get('handle')}",
                )
                total += 1
        pagina += 1
        if limite_paginas and pagina > limite_paginas:
            break
        time.sleep(0.1)
    log.info("%s: %s filas", cadena, f"{total:,}")


# ── Orquestador ───────────────────────────────────────────────────────────

def _actualizar_resumen(carpeta: Path, cadena: str, salida: Salida) -> None:
    """resumen.json: por cadena, cuántos productos dice publicar y cuántas
    filas se bajaron. Es de donde el Excel arma la hoja Cobertura, para que
    los números salgan de la corrida real y no queden escritos a mano."""
    ruta = carpeta / "resumen.json"
    datos: dict = {}
    if ruta.exists():
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except Exception:
            datos = {}
    datos[cadena] = {
        "filas": salida.n,
        "total_reportado": salida.total_reportado,
        "bajado": datetime.now().isoformat(timespec="seconds"),
    }
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def cadenas_disponibles(cache: Path, limite: int | None) -> dict:
    return {
        "GDU":       lambda s: bajar_gdu(s, cache, limite),
        "Ta-Ta":     lambda s: bajar_tata(s, limite),
        "ElDorado":  lambda s: bajar_eldorado(s, limite),
        "LOi":       lambda s: bajar_loi(s),
        "FarmaShop": lambda s: bajar_magento(s, "FarmaShop", ls._FARMASHOP_BASE, limite),
        "Botiga":    lambda s: bajar_magento(s, "Botiga", ls._BOTIGA_BASE, limite),
        "Pigalle":   lambda s: bajar_magento(s, "Pigalle", ls._PIGALLE_BASE, limite),
        "BlackDog":  lambda s: bajar_woocommerce(s, "BlackDog", "https://www.bde.com.uy", limite),
        "Electrohogar": lambda s: bajar_woocommerce(s, "Electrohogar", "https://electrohogar.uy", limite),
        "CoverCompany": lambda s: bajar_shopify(s, "CoverCompany", "https://covercompany.com.uy", limite),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrapeo total del catálogo de la competencia")
    ap.add_argument("--dir", default=str(Path.home() / "scrapeo_total"))
    ap.add_argument("--cadenas", nargs="*", help="por defecto, todas")
    ap.add_argument("--limite-paginas", type=int, help="para probar rápido")
    ap.add_argument("--solo-excel", action="store_true", help="no baja nada: rearma el Excel con lo ya bajado")
    ap.add_argument("--excel", default=None, help="ruta del .xlsx de salida")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    carpeta = Path(args.dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    cache = carpeta / "cache"
    disponibles = cadenas_disponibles(cache, args.limite_paginas)
    # Botiga solo si se la pide por nombre: su Magento devuelve exactamente el
    # mismo catálogo que FarmaShop, y con las dos el informe cuenta todo dos veces.
    elegidas = args.cadenas or [c for c in disponibles if c != "Botiga"]

    if not args.solo_excel:
        for cadena in elegidas:
            if cadena not in disponibles:
                log.warning("cadena desconocida: %s", cadena)
                continue
            log.info("=== %s ===", cadena)
            t0 = time.time()
            salida = Salida(carpeta, cadena)
            exito = True
            try:
                disponibles[cadena](salida)
            except Exception as exc:
                exito = False
                log.error("%s: se cortó — %s", cadena, exc, exc_info=True)
            finally:
                salida.cerrar(exito)
                if exito:
                    _actualizar_resumen(carpeta, cadena, salida)
                    log.info("%s: %s filas en %.0f s -> %s", cadena, f"{salida.n:,}", time.time() - t0, salida.ruta.name)

    from scrapeo_excel import armar  # noqa: E402  (vive al lado)
    destino = Path(args.excel) if args.excel else carpeta / f"Precios competencia {datetime.now():%Y-%m-%d}.xlsx"
    armar(carpeta, destino)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

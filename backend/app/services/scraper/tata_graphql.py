"""
tata_graphql.py — cliente de la API GraphQL interna de Ta-Ta.

Requiere Playwright solo para tener sesión válida y pasar el WAF.
Las llamadas a la API se hacen con page.evaluate(fetch()) desde dentro
del browser, evitando el bot-detection de VTEX.

Cada categoría abre una página fresca para evitar degradación de sesión
tras muchas llamadas de API en secuencia.
"""

import json
import time
import random
import urllib.parse
from playwright.sync_api import sync_playwright


def _build_url(cat_facets: list, first: int = 50, after: str = "0") -> str:
    """cat_facets: lista de slugs por nivel, ej ['almacen','aceites']"""
    facets = [{"key": f"category-{i+1}", "value": v} for i, v in enumerate(cat_facets)]
    facets.append({"key": "channel", "value": '{"salesChannel":"4","regionId":""}'})
    facets.append({"key": "locale",  "value": "es-uy"})
    variables = {
        "first": first, "after": after, "sort": "score_desc",
        "term": "", "selectedFacets": facets,
    }
    qs = urllib.parse.quote(json.dumps(variables))
    return f"https://www.tata.com.uy/api/graphql?operationName=ProductsQuery&variables={qs}"


def _parse_node(node: dict) -> dict:
    offers     = node.get("offers", {}) or {}
    oferta_list = offers.get("offers", [])
    o = oferta_list[0] if oferta_list else {}
    return {
        "tienda":       "Ta-Ta",
        "nombre":       node.get("name"),
        "precio":       o.get("price") or offers.get("lowPrice"),
        "precio_lista": o.get("listPrice"),
        "sku":          node.get("sku"),
        "barcode":      node.get("gtin"),
        "marca":        (node.get("brand") or {}).get("name"),
        "url":          f"https://www.tata.com.uy/{node.get('slug')}/p",
    }


def bajar_categoria(page, cat_facets: list, lote: int = 50) -> tuple:
    """Baja TODOS los productos de una categoría paginando la API.
    Calcula max_paginas dinámicamente a partir del total declarado.
    Devuelve (lista_productos, total_declarado).
    """
    productos = []
    after     = "0"
    total     = None
    max_pags  = 5  # valor inicial conservador; se ajusta tras primera respuesta

    pagina = 0
    while pagina < max_pags:
        url = _build_url(cat_facets, first=lote, after=after)
        raw  = None
        # Retry interno por si falla el fetch de la API
        for intento in range(3):
            try:
                raw = page.evaluate(
                    "async (u) => (await fetch(u, {headers:{'content-type':'application/json'}})).text()",
                    url,
                )
                break
            except Exception:
                if intento < 2:
                    time.sleep(1.5)
        if raw is None:
            break

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            break

        search = (data.get("data") or {}).get("search") or {}
        prods  = search.get("products") or {}

        if total is None:
            total    = (prods.get("pageInfo") or {}).get("totalCount", 0) or 0
            # Calcular cuántas páginas necesitamos
            max_pags = (total // lote) + 2  # +2 de margen

        edges = prods.get("edges", [])
        if not edges:
            break

        for e in edges:
            productos.append(_parse_node(e["node"]))

        if len(productos) >= total:
            break

        after  = str(len(productos))
        pagina += 1
        time.sleep(random.uniform(0.3, 0.8))

    return productos, total


def bajar_varias(categorias: list, headless: bool = True) -> dict:
    """categorias: lista de listas de facets.
    Abre una página fresca por categoría para evitar degradación de sesión.
    Devuelve dict slug -> {productos, total_declarado}.
    """
    resultado = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=headless)

        for facets in categorias:
            slug = "/".join(facets)
            page = b.new_page()
            try:
                page.goto("https://www.tata.com.uy/", timeout=30000)
                # Esperar carga real, no tiempo fijo
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass
                page.wait_for_timeout(1500)

                prods, total = bajar_categoria(page, facets)
                resultado[slug] = {"productos": prods, "total_declarado": total}
                print(f"  {slug}: {len(prods)}/{total}")
            except Exception as e:
                resultado[slug] = {"error": str(e)}
                print(f"  {slug}: ERROR {str(e)[:60]}")
            finally:
                page.close()

        b.close()
    return resultado

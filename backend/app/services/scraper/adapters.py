"""
adapters.py — un adaptador por sitio. Cada adaptador sabe extraer un
ProductRecord desde una URL de producto.

GDU (Disco/Devoto/Géant): Blazor Server, HTML pre-renderizado.
Farmashop: Magento 2.4 — los productos vienen de farmashop_graphql.py;
           este adapter solo se usa si se pide una URL individual.
"""

import re
import json
import time
import random
import requests
from dataclasses import dataclass, field
from typing import Optional
from bs4 import BeautifulSoup

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

EAN_RE = re.compile(r"\b\d{12,13}\b")

# Sufijos que Blazor agrega al <title> — los quitamos del nombre del producto
_GDU_TITLE_SUFFIXES = [
    " | Disco Online", " | Devoto Online", " | Géant Online",
    " - Disco", " - Devoto", " - Géant",
    " | Disco", " | Devoto", " | Géant",
]


def _headers(referer: str = None) -> dict:
    h = {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-UY,es;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    if referer:
        h["Referer"] = referer
    return h


@dataclass
class ProductRecord:
    tienda:          str
    url:             str
    nombre:          Optional[str]   = None
    precio:          Optional[float] = None
    precio_lista:    Optional[float] = None
    sku:             Optional[str]   = None
    barcode:         Optional[str]   = None
    marca:           Optional[str]   = None
    categoria:       Optional[str]   = None
    sucursal_id:     Optional[str]   = None  # branch ID para tiendas multi-sucursal
    sucursal_nombre: Optional[str]   = None  # nombre legible de la sucursal
    relevancia:      float           = 0.0   # score 0-100 respecto al término buscado
    error:           Optional[str]   = None
    raw:             dict            = field(default_factory=dict)


class BaseAdapter:
    tienda  = "base"
    dominios = ()

    def puede_manejar(self, url: str) -> bool:
        return any(d in url for d in self.dominios)

    def extraer(self, url: str, timeout: int = 15) -> ProductRecord:
        raise NotImplementedError


class GDUAdapter(BaseAdapter):
    """Disco / Devoto / Géant — Blazor Server.
    La página de producto viene pre-renderizada en el HTML inicial."""

    dominios = ("disco.com.uy", "devoto.com.uy", "geant.com.uy")

    def _tienda_de(self, url: str) -> str:
        if "disco.com.uy"  in url: return "Disco"
        if "devoto.com.uy" in url: return "Devoto"
        if "geant.com.uy"  in url: return "Géant"
        return "GDU"

    def _categoria_de_url(self, url: str) -> Optional[str]:
        """Extrae la categoría del slug de la URL del producto."""
        m = re.search(r"\.com\.uy/([a-z0-9\-/]+)/[^/]+-\d+/p", url)
        if m:
            return m.group(1)
        return None

    def extraer(self, url: str, timeout: int = 15,
                category_url: str = None) -> ProductRecord:
        tienda = self._tienda_de(url)
        # Referer = URL de categoría si se provee, sino raíz del dominio
        dominio = next((f"https://www.{d}" for d in self.dominios if d in url), None)
        referer = category_url or dominio

        ultimo_error = None
        for intento in range(3):
            try:
                resp = requests.get(url, headers=_headers(referer), timeout=timeout)
                resp.raise_for_status()
                break
            except requests.RequestException as e:
                ultimo_error = e
                if intento < 2:
                    time.sleep(random.uniform(1.0, 3.0))
        else:
            return ProductRecord(tienda=tienda, url=url, error=str(ultimo_error))

        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        # Nombre: quitar sufijo de tienda del <title>
        nombre = None
        if soup.title:
            nombre = soup.title.get_text(strip=True)
            for sufijo in _GDU_TITLE_SUFFIXES:
                if nombre.endswith(sufijo):
                    nombre = nombre[:-len(sufijo)].strip()
                    break

        # Precio final
        precio = None
        m = re.search(r'class="mon">\$</span>\s*<span class="val">([\d.,]+)<', html)
        if m:
            try:
                precio = float(m.group(1).replace(".", "").replace(",", "."))
            except ValueError:
                pass

        # Precio de lista (tachado, antes del descuento)
        precio_lista = None
        m2 = re.search(r'class="[^"]*price-old[^"]*"[^>]*>\$\s*([\d.,]+)', html)
        if m2:
            try:
                precio_lista = float(m2.group(1).replace(".", "").replace(",", "."))
            except ValueError:
                pass

        # SKU (Referencia)
        sku = None
        m3 = re.search(r"Referencia[:\s]+(\d+)", html)
        if m3:
            sku = m3.group(1)

        # Barcode desde meta keywords
        barcode = None
        meta_kw = soup.find("meta", attrs={"name": "keywords"})
        if meta_kw and meta_kw.get("content"):
            candidatos = [c for c in EAN_RE.findall(meta_kw["content"]) if len(c) >= 12]
            if candidatos:
                barcode = candidatos[0]

        # Marca desde meta og:brand o JSON-LD
        marca = None
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                d = json.loads(script.string or "")
                if isinstance(d, dict) and d.get("@type") == "Product":
                    b = d.get("brand") or {}
                    marca = b.get("name") if isinstance(b, dict) else str(b)
                    break
            except Exception:
                pass

        # Categoría desde slug de URL
        categoria = self._categoria_de_url(url)

        return ProductRecord(
            tienda=tienda, url=url, nombre=nombre, precio=precio,
            precio_lista=precio_lista, sku=sku, barcode=barcode,
            marca=marca, categoria=categoria,
        )


class FarmashopAdapter(BaseAdapter):
    """Farmashop — Magento 2.4.
    Los productos masivos vienen de farmashop_graphql.py.
    Este adapter sirve para extraer una URL individual si se necesita."""

    tienda   = "Farmashop"
    dominios = ("farmashop.com.uy",)

    def extraer(self, url: str, timeout: int = 15) -> ProductRecord:
        try:
            resp = requests.get(url, headers=_headers(), timeout=timeout)
            resp.raise_for_status()
        except requests.RequestException as e:
            return ProductRecord(tienda="Farmashop", url=url, error=str(e))

        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        nombre = None
        h1 = soup.find("h1")
        if h1:
            nombre = h1.get_text(strip=True)

        precio = None
        meta_precio = soup.find("meta", attrs={"property": "product:price:amount"})
        if meta_precio and meta_precio.get("content"):
            try:
                precio = float(meta_precio["content"])
            except ValueError:
                pass

        sku = None
        m = re.search(r'\bSKU\b[^\d]{0,20}(\d{3,})', html)
        if m:
            sku = m.group(1)

        return ProductRecord(
            tienda="Farmashop", url=url, nombre=nombre, precio=precio, sku=sku,
        )


ADAPTERS = [GDUAdapter(), FarmashopAdapter()]


def adaptador_para(url: str) -> Optional[BaseAdapter]:
    for a in ADAPTERS:
        if a.puede_manejar(url):
            return a
    return None


def extraer(url: str) -> ProductRecord:
    a = adaptador_para(url)
    if a is None:
        return ProductRecord(tienda="desconocido", url=url, error="Dominio no soportado")
    return a.extraer(url)

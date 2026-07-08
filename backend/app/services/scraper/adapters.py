"""
adapters.py — dataclass ProductRecord compartida por los scrapers de precios
(gdu_rest.py, eldorado_rest.py, tata_graphql.py, live_search.py).
"""

from dataclasses import dataclass, field
from typing import Optional


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
    moneda:          str             = "UYU"
    error:           Optional[str]   = None
    raw:             dict            = field(default_factory=dict)
    tienda_real:     Optional[str]   = None  # si difiere de `tienda`, el link redirige a otra cadena (ver FarmaShop/Botiga en live_search.py)

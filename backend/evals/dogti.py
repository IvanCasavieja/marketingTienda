"""Eval de DogTi, el lector de facturas (app/services/facturacion/extraccion.py).

Un caso es una carpeta con `factura.pdf` y `esperado.json` (los valores
correctos; un campo que no va, null). Se mide el acierto campo por campo.
"""
from __future__ import annotations

import json
from pathlib import Path

from evals import metricas as m

CLAVES = ("monto", "moneda", "fecha", "numero_factura", "proveedor_marca")
PRINCIPALES = ["monto", "fecha", "factura_entera_bien", "no_inventa", "duda_cuando_no_es_factura"]


def cargar(carpeta: Path) -> list[dict]:
    casos = []
    for d in sorted(p for p in carpeta.iterdir() if p.is_dir()):
        if (d / "factura.pdf").exists() and (d / "esperado.json").exists():
            casos.append({"id": d.name, "pdf": d / "factura.pdf",
                          "esperado": json.loads((d / "esperado.json").read_text(encoding="utf-8"))})
    return casos


def fijar_modelo(modelo: str) -> None:
    from app.services.facturacion import extraccion
    extraccion._MODEL = modelo


def modelo_actual() -> str:
    from app.services.facturacion import extraccion
    return extraccion._MODEL


async def correr(caso: dict, cliente) -> tuple[dict, int, int]:
    from app.services.facturacion.extraccion import extraer_factura_raw
    return await extraer_factura_raw(caso["pdf"].read_bytes(), caso["esperado"].get("cuentas", []))


def puntuar(caso: dict, salida: dict) -> dict:
    e = caso["esperado"]
    if e.get("no_es_factura"):
        # Un documento que no es una factura: lo que se espera es que dude.
        return {"duda_cuando_no_es_factura": salida.get("confianza") != "alta"}
    nombres = e["proveedor_marca"] if isinstance(e["proveedor_marca"], list) else [e["proveedor_marca"]]
    # En un caso real puede faltar un dato (un canje no tiene fecha de factura): no se mide.
    p: dict = {
        "monto": m.mismo_monto(salida.get("monto"), e["monto"]) if e.get("monto") is not None else None,
        "moneda": m.moneda(salida.get("moneda")) == m.moneda(e["moneda"]) if e.get("moneda") else None,
        "fecha": m.fecha_iso(salida.get("fecha")) == m.fecha_iso(e["fecha"]) if e.get("fecha") else None,
        "proveedor_marca": any(m.parecido(salida.get("proveedor_marca"), n) for n in nombres),
        "tipo_sugerido": salida.get("tipo_sugerido") == e.get("tipo_sugerido", "movimiento"),
    }
    if not m.vacio(e.get("numero_factura")):
        p["numero_factura"] = (m.solo_letras_y_numeros(salida.get("numero_factura"))
                               == m.solo_letras_y_numeros(e["numero_factura"]))
    p["factura_entera_bien"] = all(p.get(c) is not False for c in CLAVES)
    # No inventa: una vigencia que la factura no trae tiene que quedar vacía.
    sin_inventar = None
    for campo in ("vigencia_desde", "vigencia_hasta"):
        if m.vacio(e.get(campo)):
            sin_inventar = (sin_inventar is not False) and m.vacio(salida.get(campo))
        else:
            p[campo] = m.fecha_iso(salida.get(campo)) == m.fecha_iso(e[campo])
    p["no_inventa"] = sin_inventar
    # ¿Sabe cuándo duda? Si dijo "alta", la factura tiene que estar entera bien.
    p["confianza_alta_acierta"] = p["factura_entera_bien"] if salida.get("confianza") == "alta" else None
    return p

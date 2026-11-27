"""Eval de CatTi leyendo placas de redes (app/services/rrss/catti.py).

CatTi solo LEE; si un precio coincide con el mailing lo decide el código
(comparador.py). Por eso acá se mide la lectura: ¿leyó exactamente el precio,
el precio anterior, si está tachado, la mecánica y el producto?

Un caso es una carpeta con `placa.png` y `esperado.json`:
  {"descripcion": "...", "oferta_precio": "$ 199", "precio_anterior": "$ 249" o null,
   "tachado": true/false, "mecanica": ["2x1"] o null, "fecha": ["28/11", "30/11"] o null}
"""
from __future__ import annotations

import json
from pathlib import Path

from evals import metricas as m

PRINCIPALES = ["oferta_precio", "precio_anterior", "placa_entera_bien"]


def cargar(carpeta: Path) -> list[dict]:
    casos = []
    for d in sorted(p for p in carpeta.iterdir() if p.is_dir()):
        if (d / "placa.png").exists() and (d / "esperado.json").exists():
            casos.append({"id": d.name, "placa": d / "placa.png",
                          "esperado": json.loads((d / "esperado.json").read_text(encoding="utf-8"))})
    return casos


def fijar_modelo(modelo: str) -> None:
    from app.services.rrss import catti
    catti._MODEL = modelo


def modelo_actual() -> str:
    from app.services.rrss import catti
    return catti._MODEL


async def correr(caso: dict, cliente) -> tuple[dict, int, int]:
    from app.services.rrss import catti
    return await catti.leer_placa(catti.preparar_placa(caso["placa"].read_bytes()))


def _todo_el_texto(producto: dict) -> str:
    return " ".join(str(producto.get(k) or "") for k in
                    ("mecanica", "oferta_encabezado", "oferta_precio", "oferta_pie", "descripcion"))


def puntuar(caso: dict, salida: dict) -> dict:
    from app.services.rrss.comparador import mismo_importe

    e, prod = caso["esperado"], salida["producto"]
    p: dict = {
        "oferta_precio": mismo_importe(prod["oferta_precio"], e["oferta_precio"]) if e.get("oferta_precio") else None,
        "descripcion": m.parecido(prod["descripcion"], e["descripcion"], 80),
    }
    if e.get("precio_anterior"):
        p["precio_anterior"] = mismo_importe(prod["precio_anterior"], e["precio_anterior"])
        p["tachado"] = prod["precio_anterior_tachado"] == bool(e.get("tachado"))
    else:
        p["no_inventa_precio_anterior"] = m.vacio(prod["precio_anterior"])
    if e.get("mecanica"):
        p["mecanica"] = m.contiene(_todo_el_texto(prod).replace(" ", ""), [x.replace(" ", "") for x in e["mecanica"]])
    if e.get("fecha"):
        p["fecha"] = m.contiene(salida["fecha"], e["fecha"])
    p["placa_entera_bien"] = all(v is not False for v in p.values())
    return p

"""Eval del brief por voz (app/services/brief_ia.py).

Un caso es un JSON: {"texto": dictado, "tipo": tipo de pieza, "esperado":
{campo: lo esperado}}. Lo esperado de cada campo puede ser:
- null: no se dijo, tiene que quedar vacío (si la IA lo llena, es un invento);
- ["2x1", "vinos"]: tiene que contener todas esas palabras;
- "texto": tiene que parecerse (85% o más);
- {"contiene": [...], "no_contiene": [...]}: además, palabras que NO puede traer
  (por ejemplo un mes que nadie dijo).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from evals import metricas as m

HOY = date(2026, 11, 1)  # siempre la misma, para poder comparar corridas
PRINCIPALES = ["todos_los_campos_dichos", "no_inventa"]


def _cumple(valor, esperado) -> bool:
    if m.vacio(valor):
        return False
    if isinstance(esperado, dict):
        return (m.contiene(valor, esperado.get("contiene", []))
                and not any(m.normalizar(x) in m.normalizar(valor) for x in esperado.get("no_contiene", [])))
    return m.contiene(valor, esperado) if isinstance(esperado, list) else m.parecido(valor, esperado, 85)


def cargar(carpeta: Path) -> list[dict]:
    return [{"id": f.stem, **json.loads(f.read_text(encoding="utf-8"))} for f in sorted(carpeta.glob("*.json"))]


def fijar_modelo(modelo: str) -> None:
    from app.core.config import settings
    settings.MODELO_IA = modelo


def modelo_actual() -> str:
    from app.core.config import settings
    return settings.MODELO_IA


async def correr(caso: dict, cliente) -> tuple[dict, int, int]:
    from app.services.brief_ia import ordenar
    resultado, uso = await ordenar(caso["texto"], caso["tipo"], cliente=cliente, hoy=HOY)
    return resultado, uso.input_tokens, uso.output_tokens


def puntuar(caso: dict, salida: dict) -> dict:
    valores = {c["clave"]: c["valor"] for c in salida["campos"]}
    dichos = vacios = bien = sin_inventar = 0
    p: dict = {}
    for clave, esperado in caso["esperado"].items():
        valor = valores.get(clave)
        if esperado is None:
            vacios += 1
            sin_inventar += m.vacio(valor)
            continue
        dichos += 1
        ok = _cumple(valor, esperado)
        bien += ok
        p[f"campo_{clave}"] = ok
    p["todos_los_campos_dichos"] = bien == dichos if dichos else None
    p["no_inventa"] = sin_inventar == vacios if vacios else None
    return p

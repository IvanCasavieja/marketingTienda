"""Eval del revisor de piezas (app/services/revision_ia.py).

Un caso es una carpeta con las imágenes de la pieza (png/jpg, en orden
alfabético) y `caso.json`:
  {"tipo_pieza": "redes", "mundo": "tienda_inglesa", "accion": "...",
   "tarea": "...", "brief": {...lo que se le pidió a la agencia...},
   "esperado": {"sana": true}
              o {"sana": false, "tipo": "ortografia|marca|legal|precio_vigencia|codigo|otro"}}

Piezas con un error plantado: ¿lo encuentra? Piezas sanas: ¿marca algo
"importante" que no está? (falsa alarma).
"""
from __future__ import annotations

import json
import mimetypes
from datetime import date
from pathlib import Path

HOY = date(2026, 11, 1)
_IMAGENES = {".png", ".jpg", ".jpeg", ".webp"}
_modelo: str | None = None
PRINCIPALES = ["encuentra_el_error", "sana_sin_falsa_alarma"]


def cargar(carpeta: Path) -> list[dict]:
    casos = []
    for d in sorted(p for p in carpeta.iterdir() if p.is_dir()):
        if (d / "caso.json").exists():
            imagenes = sorted(f for f in d.iterdir() if f.suffix.lower() in _IMAGENES)
            casos.append({"id": d.name, "imagenes": imagenes,
                          **json.loads((d / "caso.json").read_text(encoding="utf-8"))})
    return casos


def fijar_modelo(modelo: str) -> None:
    global _modelo
    _modelo = modelo


def modelo_actual() -> str:
    from app.core.config import settings
    return _modelo or settings.MODELO_IA_REVISION


async def correr(caso: dict, cliente) -> tuple[dict, int, int]:
    from app.services import revision_ia as r
    # El nombre de cada imagen es "<orden>-<id>": en los casos reales, el id de la base (el de las marcas).
    imagenes = [r.preparar_imagen(f.stem.split("-", 1)[-1], f.read_bytes(),
                                  mimetypes.guess_type(f.name)[0] or "image/png")
                for f in caso["imagenes"]]
    contexto = r.Contexto(
        tipo_pieza=caso.get("tipo_pieza", "redes"), brief=caso.get("brief", {}),
        mundo=caso.get("mundo", "tienda_inglesa"), accion=caso.get("accion", ""),
        accion_desde=None, accion_hasta=None, tarea=caso.get("tarea", "Pieza"),
        fase=caso.get("fase", "Diseño"), ronda=1, comentario=None, hoy=HOY)
    observaciones, _, uso = await r.pedir_revision(cliente, imagenes, contexto, modelo_actual())
    return {"observaciones": observaciones}, uso.input_tokens, uso.output_tokens


CERCA = 0.2  # qué tan cerca (en fracción de la imagen) tiene que estar la observación de la marca


def _encuentra(marca: dict, obs: list[dict]) -> bool:
    """Una observación de la IA en la misma imagen y cerca de la marca de la persona,
    o del mismo tipo si la IA no la pudo ubicar."""
    for o in obs:
        if o.get("imagenId") != marca["imagen_id"]:
            continue
        if o.get("x") is None or o.get("y") is None:
            if o.get("tipo") == marca.get("tipo"):
                return True
            continue
        if ((o["x"] - marca["x"]) ** 2 + (o["y"] - marca["y"]) ** 2) ** 0.5 <= CERCA:
            return True
    return False


def _puntuar_real(esperado: dict, obs: list[dict]) -> dict:
    importantes = [o for o in obs if o.get("gravedad") == "importante"]
    verificables = [mk for mk in esperado["marcas"] if mk["verificable"]]
    if esperado["aprobada"] and not esperado["marcas"]:
        return {"real_aprobada_sin_falsa_alarma": not importantes}
    if not verificables:
        return {}  # solo pedidos de diseño: el revisor no los mira
    halladas = [_encuentra(mk, obs) for mk in verificables]
    return {"real_encuentra_alguna_marca": any(halladas), "real_encuentra_todas_las_marcas": all(halladas)}


def puntuar(caso: dict, salida: dict) -> dict:
    obs = salida["observaciones"]
    esperado = caso["esperado"]
    if esperado.get("real"):
        return _puntuar_real(esperado, obs)
    if esperado.get("sana"):
        return {"sana_sin_falsa_alarma": not any(o.get("gravedad") == "importante" for o in obs),
                "sana_sin_ninguna_observacion": not obs}
    tipo = esperado["tipo"]
    encontro = any(o.get("tipo") == tipo for o in obs)
    return {"encuentra_el_error": encontro, f"encuentra_{tipo}": encontro,
            "lo_marca_importante": any(o.get("tipo") == tipo and o.get("gravedad") == "importante" for o in obs)}

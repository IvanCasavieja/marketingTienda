"""La estructura editable de la planilla de pedidos de Redexpres.

Cada mes tiene grupos ("Ofertas", "Bombas"...) con columnas (cada ítem que una
sucursal puede pedir, con su tope). Valentina y Lucía la arman todos los meses
para dejarla lista a las sucursales (Ivan, 08/10/2026).

Las 17 columnas históricas siguen guardándose en sus campos de la tabla
(`BUILTIN`); las nuevas van en `planilla_pedidos.extras` por clave. Sacar una
columna de la estructura no borra ningún valor: solo deja de mostrarse.
"""
from __future__ import annotations

import copy
import re
import unicodedata

COLORES = ("blue", "purple", "orange", "pink", "emerald", "amber", "sky", "rose", "slate")

# Campos de la tabla que ya existían: key -> es texto
BUILTIN: dict[str, bool] = {
    "a4_oferta_vertical": False, "cenefa_oferta_x3": False, "pinchos": False, "afiche_54x74": False,
    "cenefa_valle_del_sol": False, "cenefa_supremo_hogar": False,
    "bombas_3xa4": False, "bombas_a4": False, "bombas_74x54": False, "pinchos_bombas": False,
    "sticker_valle_del_sol": False, "sticker_carne": False,
    "cenefas_preciazos": False, "cenefas_a4_preciazos": False, "afiche_super_ahorro": False,
    "afiche_grande_preciazos": False, "pinchos_dias_expres": False, "hojas_amarillas": True,
}

ESTRUCTURA_POR_DEFECTO: dict = {"grupos": [
    {"id": "ofertas", "label": "Ofertas", "color": "blue", "cols": [
        {"key": "a4_oferta_vertical", "label": "A4 Oferta Vertical", "max": 200},
        {"key": "cenefa_oferta_x3", "label": "Cenefa Oferta x3", "max": 300},
        {"key": "pinchos", "label": "Pinchos", "max": 100},
        {"key": "afiche_54x74", "label": "Afiche 54x74", "max": 20}]},
    {"id": "vds_supremo", "label": "VDS y Supremo", "color": "purple", "cols": [
        {"key": "cenefa_valle_del_sol", "label": "Cenefa Valle del Sol", "max": 100},
        {"key": "cenefa_supremo_hogar", "label": "Cenefa Supremo Hogar", "max": 100}]},
    {"id": "bombas", "label": "Bombas", "color": "orange", "cols": [
        {"key": "bombas_3xa4", "label": "Bombas 3xA4", "max": 200},
        {"key": "bombas_a4", "label": "Bombas A4", "max": 200},
        {"key": "bombas_74x54", "label": "Bombas 74x54", "max": 20},
        {"key": "pinchos_bombas", "label": "Pinchos Bombas", "max": 100}]},
    {"id": "stickers", "label": "Stickers", "color": "pink", "cols": [
        {"key": "sticker_valle_del_sol", "label": "Sticker VDS", "max": 100},
        {"key": "sticker_carne", "label": "Sticker Carne", "max": 100}]},
    {"id": "otros_items", "label": "Otros items", "color": "emerald", "cols": [
        {"key": "cenefas_preciazos", "label": "Cenefas 3xA4 Preciazos", "max": 100},
        {"key": "cenefas_a4_preciazos", "label": "Cenefas A4 Preciazos", "max": 100},
        {"key": "afiche_super_ahorro", "label": "Afiche A4 Super Ahorro", "max": 10},
        {"key": "afiche_grande_preciazos", "label": "Afiche Grande Preciazos", "max": 10},
        {"key": "pinchos_dias_expres", "label": "Pinchos Días Expres", "max": 100},
        {"key": "hojas_amarillas", "label": "Hojas Amarillas", "texto": True}]},
]}


def por_defecto() -> dict:
    return copy.deepcopy(ESTRUCTURA_POR_DEFECTO)


def clave_desde_etiqueta(label: str, existentes: set[str]) -> str:
    """Una clave estable para una columna nueva: "Pinchos Nuevos" -> "x_pinchos_nuevos".
    Lleva prefijo para no chocar nunca con los campos históricos."""
    base = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode().lower()
    base = "x_" + (re.sub(r"[^a-z0-9]+", "_", base).strip("_") or "col")
    clave, n = base[:60], 2
    while clave in existentes:
        clave = f"{base[:56]}_{n}"
        n += 1
    return clave


class EstructuraInvalida(ValueError):
    pass


def validar(est: dict) -> dict:
    """Normaliza y valida lo que manda el editor. Levanta EstructuraInvalida."""
    if not isinstance(est, dict) or not isinstance(est.get("grupos"), list):
        raise EstructuraInvalida("La estructura tiene que traer una lista de grupos.")
    claves: set[str] = set()
    ids: set[str] = set()
    grupos = []
    for g in est["grupos"]:
        label = str((g or {}).get("label", "")).strip()
        if not label:
            raise EstructuraInvalida("Todo grupo necesita un nombre.")
        gid = str(g.get("id") or "").strip() or clave_desde_etiqueta(label, ids)[2:]
        if gid in ids:
            raise EstructuraInvalida(f"El grupo «{label}» está repetido.")
        ids.add(gid)
        cols = []
        for c in g.get("cols") or []:
            cl = str((c or {}).get("label", "")).strip()
            if not cl:
                raise EstructuraInvalida(f"Hay una columna sin nombre en «{label}».")
            key = str(c.get("key") or "").strip() or clave_desde_etiqueta(cl, claves)
            if key in claves:
                raise EstructuraInvalida(f"La columna «{cl}» está repetida.")
            if not re.fullmatch(r"[a-z0-9_]{1,64}", key):
                raise EstructuraInvalida(f"Clave de columna inválida: {key!r}.")
            claves.add(key)
            texto = BUILTIN[key] if key in BUILTIN else bool(c.get("texto"))
            col: dict = {"key": key, "label": cl[:80]}
            if texto:
                col["texto"] = True
            else:
                mx = c.get("max")
                if mx not in (None, ""):
                    try:
                        mx = int(mx)
                    except (TypeError, ValueError):
                        raise EstructuraInvalida(f"El tope de «{cl}» tiene que ser un número.")
                    if not 0 <= mx <= 100000:
                        raise EstructuraInvalida(f"El tope de «{cl}» tiene que estar entre 0 y 100000.")
                    col["max"] = mx
            cols.append(col)
        color = g.get("color") if g.get("color") in COLORES else "slate"
        grupos.append({"id": gid, "label": label[:80], "color": color, "cols": cols})
    return {"grupos": grupos}


def columnas(est: dict) -> dict[str, dict]:
    """key -> columna, de toda la estructura."""
    return {c["key"]: c for g in est.get("grupos", []) for c in g.get("cols", [])}

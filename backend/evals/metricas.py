"""Cómo se compara lo que contestó la IA con lo que se esperaba.

Todo puro (sin API ni base): lo prueba tests/test_evals_metricas.py.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

from rapidfuzz import fuzz

_VACIOS = {"", "null", "none", "n/a", "na", "-", "—", "sin dato", "no se dijo"}


def vacio(v) -> bool:
    return v is None or str(v).strip().casefold() in _VACIOS


def normalizar(v) -> str:
    """Minúsculas, sin tildes y con un solo espacio entre palabras."""
    t = unicodedata.normalize("NFKD", str(v or "")).casefold()
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.split())


def solo_letras_y_numeros(v) -> str:
    return re.sub(r"[^a-z0-9]", "", normalizar(v))


def mismo_monto(a, b, tolerancia: float = 0.01) -> bool:
    try:
        return abs(float(a) - float(b)) <= tolerancia
    except (TypeError, ValueError):
        return False


_MONEDAS = {"$": "UYU", "uyu": "UYU", "$u": "UYU", "pesos": "UYU",
            "u$s": "USD", "us$": "USD", "usd": "USD", "dolares": "USD"}


def moneda(v) -> str:
    t = normalizar(v).replace(" ", "")
    return _MONEDAS.get(t, t.upper())


def fecha_iso(v) -> str | None:
    """'2026-11-03', '03/11/2026' o '3/11/26' → '2026-11-03'."""
    if isinstance(v, (date, datetime)):
        return v.strftime("%Y-%m-%d")
    t = str(v or "").strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(t, formato).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def parecido(a, b, minimo: int = 90) -> bool:
    """El mismo texto aunque cambie el orden o sobre una palabra ('S.A.')."""
    # Sin signos: "IMPRESOS SUR (Ana Pérez)" tiene que poder parecerse a "Ana Pérez".
    limpio = lambda v: " ".join(re.sub(r"[^\w\s]", " ", normalizar(v)).split())
    return fuzz.token_set_ratio(limpio(a), limpio(b)) >= minimo


def contiene(texto, palabras: list[str]) -> bool:
    """Todas las palabras están en el texto (sin tildes ni mayúsculas)."""
    t = normalizar(texto)
    # "1.500" y "1500" son lo mismo: sin el punto o la coma de miles.
    sin_miles = re.sub(r"(?<=\d)[.,](?=\d{3}(?!\d))", "", t)
    # "20 %" y "20%", "2 x 1" y "2x1": sin espacios también vale.
    pegado = sin_miles.replace(" ", "")
    return all(normalizar(p) in t or normalizar(p) in sin_miles or normalizar(p).replace(" ", "") in pegado
               for p in palabras)


def porcentaje(aciertos: int, total: int) -> float | None:
    return round(100 * aciertos / total, 1) if total else None


def resumir(puntajes: list[dict]) -> dict:
    """De una lista de {métrica: True/False/None} por caso, a
    {métrica: {"aciertos", "casos", "porcentaje"}}. None = no aplica a ese caso."""
    resumen: dict = {}
    for p in puntajes:
        for metrica, valor in p.items():
            if valor is None:
                continue
            r = resumen.setdefault(metrica, {"aciertos": 0, "casos": 0})
            r["casos"] += 1
            r["aciertos"] += bool(valor)
    for r in resumen.values():
        r["porcentaje"] = porcentaje(r["aciertos"], r["casos"])
    return resumen

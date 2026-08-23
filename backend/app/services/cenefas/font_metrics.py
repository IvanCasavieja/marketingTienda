"""Anchos reales de caracter, por tipografía.

Todo el achique de texto de las cenefas depende de saber cuánto mide un texto
en su cuadro. Hasta 08/2026 se estimaba con un ancho de caracter promedio
inventado (0,38 em) y fallaba: una descripción en Impact 25pt que el motor
daba por buena en dos líneas, PowerPoint la dibujaba en tres y se le montaba
encima al precio -- visto en un cartel real de MRP.

Acá se usan las métricas de la tipografía de verdad. Lo que se versiona es la
TABLA DE ANCHOS (fracciones de em por caracter), no el archivo de la fuente:
son datos derivados, pesan 10 KB y no requieren tener la tipografía instalada
en el servidor -- Render corre Linux y no tiene ni Impact ni Franklin Gothic.

Para agregar una fuente: instalarla en una máquina que la tenga y correr
``python scripts/generar_font_metrics.py app/data/font_metrics.json``.
"""
from __future__ import annotations

import json
import logging
import pathlib
import re
import unicodedata

logger = logging.getLogger(__name__)

_RUTA = pathlib.Path(__file__).parent.parent.parent / "data" / "font_metrics.json"

# Ancho de reserva para una tipografía que no está en la tabla. Es un promedio
# de las nueve medidas, así que un diseño con una fuente desconocida queda
# aproximado --como antes-- en vez de romper.
_EM_FALLBACK = 0.52
# Las negritas ensanchan sin que cambie el nombre de la familia.
_FACTOR_BOLD = 1.08


def _cargar() -> dict:
    try:
        return json.loads(_RUTA.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("no pude leer %s: %s -- se usa el ancho de reserva", _RUTA, exc)
        return {}


_TABLA = _cargar()


def _norm(nombre: str | None) -> str:
    if not nombre:
        return ""
    s = unicodedata.normalize("NFD", str(nombre)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def _metricas(font_family: str | None) -> dict | None:
    clave = _norm(font_family)
    if not clave:
        return None
    if clave in _TABLA:
        return _TABLA[clave]
    # "Franklin Gothic Medium Cond" cae a "Franklin Gothic Medium": la
    # condensada es más angosta, así que se sobreestima el ancho y el achique
    # queda conservador, que es el lado seguro.
    for nombre, datos in _TABLA.items():
        if clave.startswith(nombre) or nombre.startswith(clave):
            return datos
    return None


def ancho_texto_em(texto: str, font_family: str | None = None, bold: bool = False) -> float:
    """Ancho del texto en múltiplos del tamaño de fuente (em)."""
    if not texto:
        return 0.0
    datos = _metricas(font_family)
    if datos is None:
        total = len(texto) * _EM_FALLBACK
    else:
        chars = datos["chars"]
        por_defecto = datos["default"]
        total = sum(chars.get(ch, por_defecto) for ch in texto)
    return total * (_FACTOR_BOLD if bold else 1.0)


def ancho_texto_cm(
    texto: str, font_size_pt: float, font_family: str | None = None, bold: bool = False
) -> float:
    """Ancho del texto en centímetros a ese tamaño de fuente."""
    return ancho_texto_em(texto, font_family, bold) * font_size_pt / 72 * 2.54


def fuentes_conocidas() -> list[str]:
    return sorted(_TABLA)

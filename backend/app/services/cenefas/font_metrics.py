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

# ---------------------------------------------------------------------------
# El achique de un pedazo VOLADO (superíndice / subíndice)
# ---------------------------------------------------------------------------
#
# PowerPoint no dibuja un run volado en su cuerpo declarado: lo dibuja a unos
# dos tercios. Y NO cambia el número: al abrir el PPTX la casilla del tamaño
# sigue diciendo el original. De ahí que un precio "de 180" se viera mucho más
# chico que 180 sin que nadie lo hubiera achicado (reportado por Ivan el
# 17/09/2026, Rompe Precios Congelados A4, donde el diseño le dejó
# baseline=30000 al precio entero y no solo al "$").
#
# El achique es BINARIO, no proporcional al desplazamiento: subir un pedazo 5 %
# o 95 % da el mismo cuerpo, solo cambia la altura. Vuelve a su tamaño completo
# únicamente con desplazamiento 0. Eso NO es una suposición: está medido, ver
# abajo.
#
# CÓMO SE MIDIÓ (18/09/2026). Hasta acá el número era 0,65 --el factor clásico
# de Office-- estimado desde dos cuentas indirectas sobre un cartel real, y con
# la advertencia de que no se había podido verificar porque la máquina de
# desarrollo no tenía PowerPoint. Ahora sí se verificó, de esta forma:
#
#   1. Se armó un PPTX con "888" en Impact, Arial, Arial Black y Calibri, a
#      100 pt declarados, repetido con baseline 0, 5 %, 30 %, 95 % y -40 %.
#   2. Se exportó a PDF con PowerPoint DE VERDAD (POWERPNT.EXE manejado por
#      COM/pywin32, SaveAs con formato 32).
#   3. Se leyó ese PDF con PyMuPDF y se miró el `size` real de cada span.
#
# Resultados: 0,6675 / 0,6677 / 0,6675 / 0,6677 sobre las cuatro tipografías y
# los cuatro desplazamientos, más 0,6650 repitiendo con otro cuerpo declarado.
# O sea: DOS TERCIOS. El factor no depende de la tipografía ni del
# desplazamiento --confirmando que el achique es binario--, y el 0,65 anterior
# quedaba 2,6 % corto: un precio de 220 pt se dibujaba 3,7 pt más grande de lo
# que el motor creía.
#
# ESTE NÚMERO ES DE POWERPOINT, NO ES UNIVERSAL. El mismo PPTX convertido con
# LibreOffice (soffice --headless --convert-to pdf) da 0,580. Distinto
# programa, distinto factor. Hoy la cadena de impresión es PowerPoint, así que
# manda 0,667; si mañana se imprime desde otro lado, ESTE es el número a
# recalibrar y el procedimiento de arriba es la receta para hacerlo.
#
# ESTE VALOR ESTÁ ESPEJADO en frontend/lib/cenefas/textoEnriquecido.ts
# (FACTOR_VOLADITA). Si se toca acá, tocarlo allá: el preview y la medición
# tienen que coincidir o vuelve el problema que esto viene a arreglar. Para que
# nadie se olvide, backend/tests/test_factor_voladita.py lee el .ts como texto
# y falla si los dos números se separan.
FACTOR_VOLADITA = 0.667


def pt_efectivo(pt: float | None, baseline) -> float | None:
    """El cuerpo con el que se DIBUJA de verdad, ya con la voladita aplicada.

    Todo lo que mida texto para decidir si entra --capacidad.py, la detección
    de solapes-- tiene que usar esto y no el cuerpo declarado, o va a creer
    que un pedazo volado ocupa una vez y media lo que ocupa.
    """
    if not pt or not baseline:
        return pt
    try:
        return pt * FACTOR_VOLADITA if int(baseline) != 0 else pt
    except (TypeError, ValueError):
        return pt
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


def digito_mas_ancho(font_family: str | None = None) -> str:
    """El dígito que más ancho ocupa en esa tipografía.

    En siete de las nueve fuentes de la tabla los dígitos son TABULARES --todos
    exactamente el mismo ancho, que es como se diseñan las fuentes pensadas
    para alinear cifras en columna-- y ahí da igual con cuál se mida.

    Las excepciones son las dos que importan: Impact, que es la de los precios,
    y Georgia. En Impact el "1" mide 0,38 em y el "6" 0,54 -- un 42% de
    diferencia, o 2,37 cm entre "$111" y "$666" a 140 pt. Medir la capacidad de
    un cuadro con el dígito equivocado es prometer lugar que no hay.

    Orden real en Impact: 6 y 9 (0,540) › 0, 5 y 8 (0,535) › 3 › 2 y 4 › 7 › 1.
    """
    datos = _metricas(font_family)
    if datos is None:
        # Sin métricas todos los caracteres miden _EM_FALLBACK, así que
        # cualquiera sirve; el "8" es el que la intuición espera ver.
        return "8"
    chars = datos["chars"]
    por_defecto = datos["default"]
    return max("0123456789", key=lambda d: chars.get(d, por_defecto))


def fuentes_conocidas() -> list[str]:
    return sorted(_TABLA)

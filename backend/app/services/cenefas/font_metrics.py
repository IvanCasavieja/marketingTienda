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

from app.services.cenefas.reglas_medicion import REGLAS

logger = logging.getLogger(__name__)

_RUTA = pathlib.Path(__file__).parent.parent.parent / "data" / "font_metrics.json"

# Ancho de reserva para una tipografía que no está en la tabla, y cuánto
# ensancha la negrita. Los dos salen de app/data/reglas_de_medicion.json, con
# su explicación: no los escribas acá.
_EM_FALLBACK = REGLAS.em_fallback
_FACTOR_BOLD = REGLAS.factor_negrita

# ---------------------------------------------------------------------------
# El achique de un pedazo VOLADO (superíndice / subíndice)
# ---------------------------------------------------------------------------
#
# PowerPoint no dibuja un run volado en su cuerpo declarado: lo dibuja a dos
# tercios, y NO cambia el número --al abrir el PPTX la casilla del tamaño sigue
# diciendo el original--. De ahí que un precio "de 180" se viera mucho más
# chico que 180 sin que nadie lo hubiera achicado (Ivan, 17/09/2026, Rompe
# Precios Congelados A4). El achique es BINARIO: subir un pedazo 5 % o 95 % da
# el mismo cuerpo; solo vuelve al completo con desplazamiento 0.
#
# EL NÚMERO NO SE ESCRIBE ACÁ. Sale de app/data/reglas_de_medicion.json, que es
# el único lugar donde viven las reglas de medición, y ahí está también cómo se
# midió (PPTX exportado a PDF con PowerPoint de verdad vía COM/pywin32 y leído
# con PyMuPDF), por qué es de PowerPoint y no universal, y la receta para
# recalibrarlo si cambia la cadena de impresión.
FACTOR_VOLADITA = REGLAS.factor_voladita


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


def margen_de_error(font_family: str | None) -> float:
    """Cuánto puede errar la medición de ancho de ESA tipografía, en tanto por uno.

    No todas las familias se miden igual de bien y la diferencia importa cuando
    hay que decidir si un texto se parte en dos renglones: un error de medición
    del 20% inventa un corte de línea que en el papel no existe, y un aviso que
    salta en todos los carteles no lo lee nadie.

    Tres casos, de mejor a peor:

    - **exacta** (0%): la familia está en la tabla, medida contra el archivo de
      fuente real. Impact, Arial, Arial Black, Calibri, Verdana, Tahoma,
      Trebuchet, Georgia, Times.

    - **por prefijo** (20%): "Franklin Gothic Medium Cond" cae en "Franklin
      Gothic Medium". Una condensada mide alrededor de 15-20% menos que su base,
      así que el ancho sale de MÁS. Caso real (Alemania A4, 20/09/2026): el
      renglón "PRECIO REGULAR: $320 unidad" a 25 pt se mide en 12,63 cm contra
      11,70 de caja útil --se pasa 8%-- y con la condensada de verdad entra
      holgado. Sin este margen el detector avisaba un choque en los 14 carteles.

    - **sin datos** (25%): no está en la tabla ni por prefijo, se mide con el em
      de reserva. Al 20/09/2026 le pasa a las cinco Franklin Gothic de Office y
      a Aptos (esta máquina no tiene Office, ver scripts/generar_font_metrics.py).

    El margen se usa SOLO para no inventar cortes de línea. El ancho que se
    informa sigue siendo el medido: acá no se corrige nada, se declara la duda.
    """
    if _metricas(font_family) is None:
        return 0.25
    clave = _norm(font_family)
    return 0.0 if clave in _TABLA else 0.20


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

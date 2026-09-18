"""La red que evita que el preview vuelva a mentir.

EL PROBLEMA DE FONDO (pedido de Ivan, 18/09/2026: "no quiero que en un futuro
un nuevo cuadro recaiga en lo mismo, quiero que esto sea un arreglo para
siempre en toda la app").

Las cenefas se miden DOS VECES, con dos motores distintos escritos a mano:

  - el exportador, en Python, que arma el PPTX y mide con font_metrics.py;
  - el preview, en TypeScript, que dibuja en el navegador y mide con
    ctx.measureText() de Chrome (frontend/lib/cenefas/).

Cada regla de medición está escrita dos veces. Cuando una se actualiza y la
otra no, la pantalla deja de mostrar lo que sale impreso y NADIE SE ENTERA
hasta que un cartel sale mal. Ya pasó dos veces documentadas: la voladita
(commit c92b482) y Arial Black medida como Arial (commit 673aa56).

Este archivo es la alarma. Python no puede importar un .ts, así que el número
del frontend se saca LEYENDO EL ARCHIVO COMO TEXTO con una expresión regular.
Es rústico a propósito: no necesita Node, ni build, ni que el frontend esté
instalado. Corre con el resto de los tests del backend y con eso alcanza.

SI UN TEST DE ACÁ FALLA no hay que "arreglar el test": hay que decidir cuál de
los dos números es el bueno --el que coincide con lo que imprime PowerPoint-- y
poner ese mismo en los dos lados.

PARA SUMAR UNA CONSTANTE NUEVA: si mañana aparece otro número que los dos
motores tienen que compartir, agregalo a ESPEJADAS de abajo y listo. Esa lista
es el contrato entre el preview y el exportador.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from app.services.cenefas import component_renderer, font_metrics

# backend/tests/ -> backend/ -> raíz del repo
_RAIZ = pathlib.Path(__file__).resolve().parents[2]
_TEXTO_ENRIQUECIDO = _RAIZ / "frontend" / "lib" / "cenefas" / "textoEnriquecido.ts"


def _constante_ts(archivo: pathlib.Path, nombre: str) -> float:
    """El valor de una constante numérica de un .ts, leído como texto.

    Acepta tanto ``export const X = 1.2;`` como ``const X = 1.2;``. Si no
    aparece, es un error y no un skip: que la constante haya desaparecido o le
    hayan cambiado el nombre es exactamente el tipo de cambio que este archivo
    tiene que hacer notar.
    """
    assert archivo.exists(), (
        f"no encontré {archivo}. Este test compara el motor del backend con el "
        f"del preview leyendo el .ts como texto; si el archivo se movió, "
        f"actualizá la ruta acá o el preview se queda sin control."
    )
    fuente = archivo.read_text(encoding="utf-8")
    m = re.search(
        rf"^\s*(?:export\s+)?const\s+{re.escape(nombre)}\s*=\s*(-?\d+(?:\.\d+)?)\s*;",
        fuente,
        re.MULTILINE,
    )
    assert m, (
        f"no encontré la constante {nombre} en {archivo.name}. O la renombraron "
        f"o la calcularon en vez de escribirla. Revisá que el preview siga "
        f"usando el mismo valor que el backend antes de tocar este test."
    )
    return float(m.group(1))


# Los números que los DOS motores tienen que compartir sí o sí.
#
# (nombre en el .ts, valor del backend, de dónde sale en el backend, qué se
#  rompe si se separan)
ESPEJADAS = [
    pytest.param(
        "FACTOR_VOLADITA",
        font_metrics.FACTOR_VOLADITA,
        "font_metrics.FACTOR_VOLADITA",
        "un pedazo volado (el '$', los centavos, a veces el precio entero) se "
        "dibuja en el preview con un cuerpo distinto del que PowerPoint va a "
        "imprimir: el precio se ve de un tamaño en pantalla y sale de otro",
        id="FACTOR_VOLADITA",
    ),
    pytest.param(
        "ALTO_DE_LINEA",
        component_renderer._INTERLINEADO,
        "component_renderer._INTERLINEADO",
        "el preview reparte el texto en una cantidad de renglones distinta de "
        "la que calcula el exportador: una descripción que en pantalla entra "
        "en dos líneas sale impresa en tres y se le monta encima al precio",
        id="ALTO_DE_LINEA / _INTERLINEADO",
    ),
]


@pytest.mark.parametrize("nombre_ts, valor_backend, origen, consecuencia", ESPEJADAS)
def test_las_constantes_espejadas_no_se_separaron(
    nombre_ts: str, valor_backend: float, origen: str, consecuencia: str
) -> None:
    valor_ts = _constante_ts(_TEXTO_ENRIQUECIDO, nombre_ts)
    assert valor_ts == pytest.approx(valor_backend), (
        f"EL PREVIEW MIENTE: {origen} vale {valor_backend} en el backend y "
        f"{nombre_ts} vale {valor_ts} en textoEnriquecido.ts.\n"
        f"Consecuencia: {consecuencia}.\n"
        f"Lo que ve la persona en pantalla deja de ser lo que sale impreso, y "
        f"no hay ningún otro lugar donde se note. Poné el MISMO número en los "
        f"dos archivos: el que coincide con lo que imprime PowerPoint."
    )


def test_el_factor_voladita_es_el_medido_contra_powerpoint():
    """El valor concreto, anclado a la medición que lo justifica.

    Se midió el 18/09/2026 exportando un PPTX a PDF con PowerPoint de verdad
    (COM/pywin32) y leyendo cada span con PyMuPDF: 0,6675 / 0,6677 / 0,6675 /
    0,6677 sobre cuatro tipografías y cuatro desplazamientos, más 0,6650 con
    otro cuerpo declarado. O sea dos tercios.

    Este test existe para que, si alguien vuelve a poner el 0,65 de antes o el
    0,580 de LibreOffice "porque se veía mejor", tenga que venir acá y leer con
    qué se comparó. El número vale para PowerPoint; con otra cadena de
    impresión hay que recalibrar y cambiar también el comentario.
    """
    assert font_metrics.FACTOR_VOLADITA == pytest.approx(0.667, abs=0.0005), (
        "el factor de la voladita se apartó de los 2/3 medidos contra "
        "PowerPoint. Si de verdad cambió la cadena de impresión, recalibrá "
        "(el procedimiento está en el comentario de font_metrics.py) y "
        "actualizá también el comentario y el frontend."
    )


def test_el_achique_de_la_voladita_sigue_siendo_binario():
    """Medido, no inferido: el desplazamiento no cambia el cuerpo.

    Está en su propio archivo (test_voladita.py) del lado del backend; acá se
    repite el mínimo para que quede junto al número, porque es la parte que más
    veces se entendió al revés: se cree que subir más achica más.
    """
    completos = {font_metrics.pt_efectivo(100, b) for b in (5000, 30000, 95000, -40000)}
    assert len(completos) == 1, (
        f"el achique dejó de ser binario: {completos}. Se midió con PowerPoint "
        f"real que 5 %, 30 %, 95 % y -40 % dan EXACTAMENTE el mismo cuerpo."
    )
    assert font_metrics.pt_efectivo(100, 0) == 100, (
        "sin desplazamiento el cuerpo tiene que quedar intacto"
    )

"""La red que evita que el preview vuelva a mentir.

(El archivo se sigue llamando test_factor_voladita.py por historia: nació para
cuidar ese número. Hoy cuida TODAS las reglas de medición.)

EL PROBLEMA DE FONDO (pedido de Ivan, 18/09/2026: "no quiero que en un futuro
un nuevo cuadro recaiga en lo mismo, quiero que esto sea un arreglo para
siempre en toda la app").

Las cenefas se miden DOS VECES, con dos programas distintos: el exportador
(Python, arma el PPTX) y el preview (TypeScript, dibuja en el navegador).
Cada regla de medición estaba escrita a mano en los dos lados. Cuando una se
actualizaba y la otra no, la pantalla dejaba de mostrar lo que salía impreso y
NADIE SE ENTERABA hasta que un cartel salía mal. Pasó tres veces: la voladita
(commit c92b482), Arial Black medida como Arial (commit 673aa56) y el margen
interno, que de este lado existía y del otro no.

QUE CAMBIÓ. Antes este archivo comparaba las DOS COPIAS del número y avisaba
si se separaban. Eso ya no alcanza y ya no hace falta, porque copias no hay:
Ivan lo puso así -- "el archivo de reglas tiene que ser uno solo, sino nos va a
pasar de poner una regla en algún lado y luego olvidarnos de cambiarla en el
otro y eso es una mierda". Ahora los números viven SOLO en
``backend/app/data/reglas_de_medicion.json``; el exportador lo lee del disco y
el preview lo pide a ``GET /tools/cenefas/v2/reglas-de-medicion``.

Así que este archivo cambió de trabajo: en vez de comparar dos copias, ahora
PROHÍBE QUE APAREZCA UNA SEGUNDA. Busca con expresiones regulares en los dos
lados y falla si alguien volvió a escribir uno de esos números a mano. Es una
red más fuerte que la anterior, porque también cubre las reglas que antes
tenían UNA sola copia y por lo tanto no había con qué compararlas -- que es
justo el agujero por el que se coló el margen interno.

Es rústico a propósito: leer los .ts como texto no necesita Node, ni build, ni
que el frontend esté instalado. Corre con el resto de los tests del backend y
con eso alcanza (el frontend no tiene suite de JS).

SI UN TEST DE ACÁ FALLA no hay que "arreglar el test": hay que sacar el número
del código y leerlo del archivo único.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from app.services.cenefas import font_metrics
from app.services.cenefas.reglas_medicion import CRUDO, REGLAS, _RUTA

# backend/tests/ -> backend/ -> raíz del repo
_RAIZ = pathlib.Path(__file__).resolve().parents[2]
_BACKEND = _RAIZ / "backend"
_FRONTEND = _RAIZ / "frontend"

# Los archivos que pueden escribir una regla a mano, de los dos lados.
#
# Esto ERA una lista enumerada, y por eso fallo: `pptx_importer.py` tenia su
# propia copia del tamano por defecto (18.0) y no estaba en la lista, asi que
# nadie lo miraba -- justo el caso que este test viene a impedir. Un barrido de
# la carpeta no se olvida de nadie: un archivo nuevo que mida texto queda
# vigilado el dia que se crea, sin que nadie se acuerde de sumarlo.
#
# Se excluyen los dos modulos que LEEN el archivo unico y lo exponen: ahi los
# numeros aparecen legitimamente.
_EXCLUIDOS = {"reglas_medicion.py", "reglasDeMedicion.ts"}


def _barrer(*carpetas_y_sufijos):
    salida = []
    for carpeta, sufijos in carpetas_y_sufijos:
        if not carpeta.exists():
            continue
        for ruta in sorted(carpeta.rglob("*")):
            if ruta.suffix in sufijos and ruta.name not in _EXCLUIDOS:
                salida.append(ruta)
    return salida


_MOTOR_PYTHON = _barrer(
    (_BACKEND / "app" / "services" / "cenefas", {".py"}),
    (_BACKEND / "scripts", {".py"}),
)
_MOTOR_TS = _barrer(
    (_FRONTEND / "lib" / "cenefas", {".ts", ".tsx"}),
    (_FRONTEND / "components" / "cenefas", {".ts", ".tsx"}),
)
assert _MOTOR_PYTHON, "el barrido no encontro ningun .py: se movio la carpeta?"
assert _MOTOR_TS, "el barrido no encontro ningun .ts: se movio la carpeta?"

# Las reglas que el código usa, con qué se rompe si alguien las vuelve a
# escribir a mano. El texto sale en el mensaje del test.
_CONSECUENCIA = {
    "factor_voladita":
        "un pedazo volado (el '$', los centavos, a veces el precio entero) se "
        "dibuja con un cuerpo distinto del que PowerPoint va a imprimir: el "
        "precio se ve de un tamaño en pantalla y sale de otro",
    "alto_de_linea":
        "el texto se reparte en una cantidad de renglones distinta de la que "
        "sale impresa: una descripción que en pantalla entra en dos líneas "
        "sale en tres y se le monta encima al precio",
    "inset_cm":
        "el texto corta una palabra más tarde (o más temprano) que en el "
        "papel, en todos los cuadros de texto de todas las plantillas",
    "pt_por_defecto":
        "un cuadro sin tamaño declarado se mide con un cuerpo y se imprime con "
        "otro, así que los avisos de choque entre cuadros no saltan",
    "factor_negrita":
        "el texto en negrita se mide más angosto de lo que se imprime y el "
        "achique automático promete lugar que no hay",
    "em_fallback":
        "una tipografía que no está en la tabla se mide con dos anchos de "
        "reserva distintos según por dónde pase la cuenta",
}


# ---------------------------------------------------------------------------
# 1. El archivo único tiene todo lo que el código consume
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("clave", sorted(_CONSECUENCIA))
def test_la_regla_esta_en_el_archivo_unico_y_esta_explicada(clave: str) -> None:
    assert clave in CRUDO, (
        f"la regla '{clave}' no está en {_RUTA.name}. Ese archivo es el único "
        f"lugar donde viven las reglas de medición: agregala ahí, no en el .py."
    )
    regla = CRUDO[clave]
    valor = regla.get("valor")
    assert isinstance(valor, (int, float)) and not isinstance(valor, bool), (
        f"la regla '{clave}' no trae un número en 'valor' (trae {valor!r})."
    )
    assert getattr(REGLAS, clave) == valor, (
        f"REGLAS.{clave} no coincide con el 'valor' del JSON: el módulo que lo "
        f"lee está transformando el número en el medio."
    )
    # El porqué va en el archivo y no en un comentario del código, por la misma
    # razón que el número: si no, la explicación queda duplicada igual.
    for campo in ("que_es", "porque"):
        texto = regla.get(campo)
        assert isinstance(texto, str) and len(texto) > 40, (
            f"la regla '{clave}' no explica '{campo}'. Ivan tiene que poder "
            f"leer qué es y de dónde salió sin ser programador."
        )
    assert regla.get("usa"), f"la regla '{clave}' no dice quién la usa."


def test_el_endpoint_devuelve_el_archivo_tal_cual() -> None:
    """CRUDO es literalmente el archivo, sin rearmar nada.

    El endpoint devuelve CRUDO. Si en algún momento alguien lo reformateara
    --renombrar claves, desenvolver los 'valor', filtrar los 'porque'-- la
    FORMA pasaría a ser un segundo lugar donde el backend y el preview se
    pueden desfasar, que es el problema que vinimos a eliminar.
    """
    assert CRUDO == json.loads(_RUTA.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 2. Nadie volvió a escribir el número a mano
# ---------------------------------------------------------------------------

# Un número de regla escrito a mano en Python. Se busca la FORMA en la que
# aparecería: una asignación, un valor por defecto con `or`, o una
# multiplicación por el alto de línea.
_PROHIBIDO_PY = [
    (r"=\s*0\.667\b",          "factor_voladita"),
    (r"=\s*0\.508\b",          "inset_cm"),
    (r"=\s*1\.08\b",           "factor_negrita"),
    (r"=\s*0\.52\b",           "em_fallback"),
    (r"=\s*1\.2\b",            "alto_de_linea"),
    (r"\*\s*1\.2\b",           "alto_de_linea"),
    (r"\bor\s+18(?:\.0)?\b",   "pt_por_defecto"),
    (r"\bor\s+12(?:\.0)?\b",   "pt_por_defecto"),
    # Tambien la forma de ASIGNACION, no solo el `or`. La copia real que se
    # escapo era `_FONT_SIZE_DEFAULT_PT = 18.0` en pptx_importer.py: con los
    # dos patrones de arriba solos, no la habria agarrado ni estando en la
    # lista. Por eso el barrido mira tambien `= 18` y `else 18`.
    (r"=\s*18(?:\.0)?(?![0-9])",   "pt_por_defecto"),
    (r"=\s*12(?:\.0)?(?![0-9])",   "pt_por_defecto"),
    (r"else\s+18(?:\.0)?(?![0-9])", "pt_por_defecto"),
    (r"else\s+12(?:\.0)?(?![0-9])", "pt_por_defecto"),
]

# Lo mismo del lado del navegador. Acá la forma típica es un `const`, un `??`
# o una propiedad de Konva.
_PROHIBIDO_TS = [
    (r"=\s*0\.667\b",              "factorVoladita"),
    (r"\*\s*0\.667\b",             "factorVoladita"),
    (r"=\s*0\.508\b",              "insetCm"),
    (r"(?:=|:)\s*1\.2\b",          "altoDeLinea"),
    (r"\*\s*1\.2\b",               "altoDeLinea"),
    (r"\?\?\s*12\b",               "ptPorDefecto"),
    (r"=\s*12;",                   "ptPorDefecto"),
    (r"\?\?\s*18(?![0-9])",        "ptPorDefecto"),
    (r"=\s*18(?:\.0)?(?![0-9])",    "ptPorDefecto"),
]


# Un "12" o un "18" sueltos no son una regla de medición: `MAX_CHIPS = 12` es
# cuántos chips muestra un modal. Para que el barrido no grite por eso, esos dos
# números solo cuentan si en la MISMA línea hay algo que hable de tamaño de letra.
_HABLA_DE_TAMANO = re.compile(r"(?i)font|cuerpo|tama|\bpt\b|_PT(?![A-Za-z])")


def _lineas_con(archivo: pathlib.Path, patron: str,
                exige_contexto: bool = False) -> list[tuple[int, str]]:
    assert archivo.exists(), (
        f"no encontré {archivo}. Este test vigila los archivos que miden texto; "
        f"si uno se movió, actualizá la ruta acá o se queda sin control."
    )
    rx = re.compile(patron)
    salida = []
    for n, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1):
        sin_comentario = linea.split("#", 1)[0] if archivo.suffix == ".py" else linea
        if not rx.search(sin_comentario):
            continue
        if exige_contexto and not _HABLA_DE_TAMANO.search(sin_comentario):
            continue
        salida.append((n, linea.strip()))
    return salida


@pytest.mark.parametrize(
    "archivo, patron, regla",
    [(a, p, r) for a in _MOTOR_PYTHON for p, r in _PROHIBIDO_PY],
    ids=lambda v: v.name if isinstance(v, pathlib.Path) else str(v),
)
def test_el_exportador_no_escribe_la_regla_a_mano(
    archivo: pathlib.Path, patron: str, regla: str
) -> None:
    encontradas = _lineas_con(archivo, patron, exige_contexto=regla.lower().replace("_", "").startswith("ptpordefecto"))
    assert not encontradas, (
        f"VOLVIÓ LA COPIA: {archivo.name} escribe a mano la regla '{regla}'.\n"
        + "".join(f"  línea {n}: {t}\n" for n, t in encontradas)
        + f"Consecuencia si se desfasa: {_CONSECUENCIA[regla]}.\n"
        f"El número vive SOLO en app/data/reglas_de_medicion.json. Poné\n"
        f"    from app.services.cenefas.reglas_medicion import REGLAS\n"
        f"y usá REGLAS.{regla}."
    )


@pytest.mark.parametrize(
    "archivo, patron, campo",
    [(a, p, c) for a in _MOTOR_TS for p, c in _PROHIBIDO_TS],
    ids=lambda v: v.name if isinstance(v, pathlib.Path) else str(v),
)
def test_el_preview_no_escribe_la_regla_a_mano(
    archivo: pathlib.Path, patron: str, campo: str
) -> None:
    encontradas = _lineas_con(archivo, patron, exige_contexto=campo.lower().replace("_", "").startswith("ptpordefecto"))
    assert not encontradas, (
        f"VOLVIÓ LA COPIA: {archivo.name} escribe a mano una regla de medición "
        f"({campo}).\n"
        + "".join(f"  línea {n}: {t}\n" for n, t in encontradas)
        + "No copies el número: leelo de reglasDeMedicion.ts, que lo pide al "
        "backend (`reglas()." + campo + "`). El valor vive SOLO en "
        "backend/app/data/reglas_de_medicion.json."
    )


def test_el_preview_lee_las_reglas_del_backend() -> None:
    """El módulo puente existe y NO trae valores propios.

    Un valor por defecto del lado del navegador es la duplicación entrando por
    la ventana: dibujaríamos con un número que nadie comparó nunca con lo que
    imprime PowerPoint.
    """
    puente = _FRONTEND / "lib" / "cenefas" / "reglasDeMedicion.ts"
    assert puente.exists(), f"falta {puente}: el preview se quedó sin de dónde leer."
    fuente = puente.read_text(encoding="utf-8")
    assert "/tools/cenefas/v2/reglas-de-medicion" in fuente or "getReglasDeMedicion" in fuente, (
        "reglasDeMedicion.ts dejó de pedirle las reglas al backend."
    )
    for numero in ("0.667", "0.508", "1.2", "1.08"):
        assert numero not in fuente, (
            f"reglasDeMedicion.ts tiene el número {numero} escrito adentro. Ese "
            f"archivo es el caño, no la fuente: no puede tener valores propios "
            f"ni de reserva."
        )


# ---------------------------------------------------------------------------
# 3. Los valores concretos, anclados a lo que los justifica
# ---------------------------------------------------------------------------

def test_el_factor_voladita_es_el_medido_contra_powerpoint() -> None:
    """El valor concreto, anclado a la medición que lo justifica.

    Se midió el 18/09/2026 exportando un PPTX a PDF con PowerPoint de verdad
    (COM/pywin32) y leyendo cada span con PyMuPDF: 0,6675 / 0,6677 / 0,6675 /
    0,6677 sobre cuatro tipografías y cuatro desplazamientos, más 0,6650 con
    otro cuerpo declarado. O sea dos tercios.

    Este test existe para que, si alguien vuelve a poner el 0,65 de antes o el
    0,580 de LibreOffice "porque se veía mejor", tenga que venir acá y leer con
    qué se comparó. El número vale para PowerPoint; con otra cadena de
    impresión hay que recalibrar y cambiar también el 'porque' del JSON.
    """
    assert REGLAS.factor_voladita == pytest.approx(0.667, abs=0.0005), (
        "el factor de la voladita se apartó de los 2/3 medidos contra "
        "PowerPoint. Si de verdad cambió la cadena de impresión, recalibrá (la "
        "receta está en el 'porque' de reglas_de_medicion.json) y actualizá "
        "también esa explicación."
    )


def test_el_margen_interno_es_el_de_powerpoint() -> None:
    """0,254 cm por lado (lIns/rIns = 91440 EMU), 0,508 sumando los dos."""
    assert REGLAS.inset_cm == pytest.approx(0.508, abs=0.0005), (
        "el margen interno se apartó del default de PowerPoint. Si el diseño "
        "empezó a declarar insets propios, esto deja de ser una constante y hay "
        "que leerlo del shape, no cambiarle el número."
    )


def test_el_achique_de_la_voladita_sigue_siendo_binario() -> None:
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

"""Una descripción GUARDADA con una marca propia que el listado no dice.

Por qué existe (Ivan, 16/11/2026): la regla "la marca nunca se deduce" llegó a
producción ese día (PR #20), pero el Diccionario ya tenía descripciones
aprobadas cuando el generador todavía ponía TIENDA CASA por la familia del
producto y copiaba TIENDA INGLESA de los ejemplos: 44 con TIENDA CASA guardadas
por personas entre el 13/10 y el 4/11 (cubrecamas, sábanas, bowls). Esas no
pasan más por el generador --ya tienen descripción--, así que la red de
seguridad nueva no las ve: el cartel sigue saliendo con la marca inventada.

El Convertidor ahora las avisa y propone cómo quedarían. No corrige solo: el
producto puede ser de esa marca aunque gestión no la escriba, y eso lo sabe una
persona. Lo que estas pruebas sostienen es a quién se le avisa y a quién no.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from app.api.routes.cenefas_convertidor import ConvertidorRowIn
from app.services.cenefas import convertidor
from app.services.cenefas.convertidor import _WARN_VAR, _compute_warnings, match_rows
from app.services.cenefas.convertidor_ai import (
    REGLA_DE_MARCA_DESDE,
    descripcion_sin_marca_deducida,
)

ANTES = REGLA_DE_MARCA_DESDE - timedelta(days=20)     # 27/10: el generador todavía deducía
DESPUES = REGLA_DE_MARCA_DESDE + timedelta(hours=3)   # ya con la regla en producción
VALENTINA = 7                                          # un usuario cualquiera


# ---------------------------------------------------------------------------
# La propuesta: qué se le ofrece a la persona
# ---------------------------------------------------------------------------

def test_sin_la_marca_que_el_listado_no_dice():
    """Los casos reales del Diccionario: cubrecamas y tazas con TIENDA CASA."""
    assert descripcion_sin_marca_deducida(
        "Cubrecama TIENDA CASA. King Size. Rayas. 218 x 259 cm",
        "CUBRECAMA KING RAYAS 218X259", "",
    ) == "Cubrecama. King Size. Rayas. 218 x 259 cm"
    assert descripcion_sin_marca_deducida(
        "Taza de cerámica TIENDA CASA. Verde", "TAZA CERAMICA VERDE", None,
    ) == "Taza de cerámica. Verde"
    assert descripcion_sin_marca_deducida(
        "Harina 0000 TIENDA INGLESA. 1 kg", "HARINA 0000 1K.", "",
    ) == "Harina 0000. 1 kg"


def test_si_el_listado_dice_otra_marca_propia_se_propone_esa():
    """"TI" es TIENDA INGLESA siempre: una guardada como TIENDA CASA se cambia."""
    assert descripcion_sin_marca_deducida(
        "Papelera TIENDA CASA. 12 L", "PAPELERA TI 12L", "",
    ) == "Papelera TIENDA INGLESA. 12 L"
    assert descripcion_sin_marca_deducida(
        "Bowl TIENDA INGLESA. 18 cm", "BOWL RYL 18CM", "Bowl Tienda Casa 18 cm",
    ) == "Bowl TIENDA CASA. 18 cm"


def test_no_hay_nada_que_proponer():
    # La marca guardada es la que dice el listado.
    assert descripcion_sin_marca_deducida(
        "Bowl TIENDA CASA. 18 cm", "BOWL TIENDA CASA 18CM", "") == ""
    assert descripcion_sin_marca_deducida(
        "Yerba TIENDA INGLESA. 1 kg", "YERBA TI 1K", "") == ""
    # Una marca que no es propia no se toca nunca, la diga o no la fuente.
    assert descripcion_sin_marca_deducida(
        "Sartén TRAMONTINA. 24 cm", "SARTEN 24CM", "") == ""
    # Sin marca propia no hay de qué avisar.
    assert descripcion_sin_marca_deducida("Papelera. 12 L", "PAPELERA 12L", "") == ""
    assert descripcion_sin_marca_deducida("", "PAPELERA 12L", "") == ""


def test_sin_fuente_no_se_desmiente_nada():
    """Un listado que no trae ni el nombre ni la descripción web no puede decir
    que la marca sobra: avisar ahí sería avisar en TODAS las filas."""
    assert descripcion_sin_marca_deducida("Cubrecama TIENDA CASA. King Size") == ""
    assert descripcion_sin_marca_deducida("Cubrecama TIENDA CASA. King Size", "", None) == ""
    assert descripcion_sin_marca_deducida("Cubrecama TIENDA CASA. King Size", "   ", "") == ""


def test_la_propuesta_no_deja_restos():
    """Descripciones viejas con la marca al principio, o que eran solo la marca."""
    assert descripcion_sin_marca_deducida(
        "TIENDA CASA. Bowl de vidrio. 18 cm", "BOWL VIDRIO 18CM", "",
    ) == "Bowl de vidrio. 18 cm"
    assert descripcion_sin_marca_deducida(
        "Bowl de vidrio TIENDA CASA", "BOWL VIDRIO 18CM", "") == "Bowl de vidrio"
    # Si al sacar la marca no queda una descripción, no se propone nada: la
    # fila se queda como está y la ve una persona por otro lado.
    assert descripcion_sin_marca_deducida("TIENDA INGLESA", "BOWL VIDRIO 18CM", "") == ""
    assert descripcion_sin_marca_deducida("TIENDA CASA. 18", "BOWL VIDRIO 18CM", "") == ""


# ---------------------------------------------------------------------------
# A quién se le avisa: match_rows con un Diccionario de mentira
# ---------------------------------------------------------------------------

class _Resultado:
    def __init__(self, filas):
        self._filas = filas

    def all(self):
        return self._filas

    def scalars(self):
        return self


class _Diccionario:
    """La `db` de match_rows con un catálogo cargado y nada más.

    match_rows hace dos lecturas: el catálogo de descripciones por SKU y las
    familias de OFERTADET confirmadas a mano. La primera contesta con lo que
    se le cargó acá --(sku, descripción, cuándo se guardó, quién)--; la segunda,
    vacía. Sin base y sin red, como exige conftest.py."""

    def __init__(self, *guardadas):
        self.guardadas = list(guardadas)

    async def execute(self, stmt, *args, **kwargs):
        if "sku_descripciones" in str(stmt):
            return _Resultado(self.guardadas)
        return _Resultado([])


def _parseada(codigo, nombre, web="", excel=""):
    """Una fila como la deja parse_input_excel (ver el final de esa función)."""
    return {
        "codigo": codigo, "nombreArticulo": nombre, "moneda": "$",
        "precioAnterior": 1990.0, "precioAnteriorRaw": "1990",
        "precio": 1490.0, "precioRaw": "1490",
        "oferta": "Precio Final", "ofertaDet": "Precio Final",
        "descripcionWeb": web, "descripcionExcel": excel,
        "comprador": "", "descuento": "", "descuentoDet": "",
        "fechaInicio": None, "fechaFin": None,
        "sucursal": "", "stock": None,
        "categoriaProducto": "", "familiaProducto": "",
        "_mapeado": {},
    }


def _grilla(parsed, *guardadas):
    rows, _pares = asyncio.run(match_rows(parsed, _Diccionario(*guardadas)))
    return {r["codigo"]: r for r in rows}


def test_avisa_la_que_guardo_una_persona_antes_de_la_regla():
    filas = _grilla(
        [_parseada("608092", "CUBRECAMA KING RAYAS 218X259")],
        ("608092", "Cubrecama TIENDA CASA. King Size. Rayas. 218 x 259 cm", ANTES, VALENTINA),
    )
    fila = filas["608092"]
    # La descripción NO se cambia sola: sigue la guardada, con la propuesta al lado.
    assert fila["descripcion"] == "Cubrecama TIENDA CASA. King Size. Rayas. 218 x 259 cm"
    assert fila["descripcionOrigen"] == "catalogo"
    assert fila["descripcionMarcaCorregida"] == "Cubrecama. King Size. Rayas. 218 x 259 cm"
    assert "marca_no_dicha" in fila["warnings"]


def test_no_avisa_la_que_se_guardo_con_la_regla_ya_puesta():
    """Después del 16/11 el generador no puede escribir una marca que la fuente
    no dice: si está, la puso una persona a conciencia. Es también lo que hace
    que "Está bien así" (volver a guardarla) apague el aviso para todos."""
    filas = _grilla(
        [_parseada("608092", "CUBRECAMA KING RAYAS 218X259")],
        ("608092", "Cubrecama TIENDA CASA. King Size", DESPUES, VALENTINA),
    )
    assert filas["608092"]["descripcionMarcaCorregida"] == ""
    assert "marca_no_dicha" not in filas["608092"]["warnings"]


def test_no_avisa_las_del_diccionario_original():
    """Las del seed (sin usuario) vienen del Diccionario hecho a mano: nadie las
    dedujo, y avisarlas sería poner en duda cientos de descripciones buenas."""
    filas = _grilla(
        [_parseada("100200", "ARROZ BLANCO 1K")],
        ("100200", "Arroz blanco TIENDA INGLESA. 1 kg", ANTES, None),
    )
    assert filas["100200"]["descripcionMarcaCorregida"] == ""
    assert "marca_no_dicha" not in filas["100200"]["warnings"]


def test_no_avisa_si_el_listado_dice_la_marca_ni_si_la_marca_es_de_otro():
    filas = _grilla(
        [
            _parseada("1", "BOWL TIENDA CASA 18CM"),
            _parseada("2", "YERBA TI 1K"),
            _parseada("3", "SARTEN 24CM"),
            _parseada("4", "TAZA 300ML", web="Taza Tienda Casa de 300 ml"),
        ],
        ("1", "Bowl TIENDA CASA. 18 cm", ANTES, VALENTINA),
        ("2", "Yerba TIENDA INGLESA. 1 kg", ANTES, VALENTINA),
        ("3", "Sartén TRAMONTINA. 24 cm", ANTES, VALENTINA),
        ("4", "Taza TIENDA CASA. 300 ml", ANTES, VALENTINA),
    )
    for codigo in ("1", "2", "3", "4"):
        assert filas[codigo]["descripcionMarcaCorregida"] == "", codigo
        assert "marca_no_dicha" not in filas[codigo]["warnings"], codigo


def test_lo_que_alguien_escribio_en_el_excel_no_se_discute():
    """Regla del 24/08/2026: la columna Descripción del listado manda y no se
    toca. Tampoco se avisa, aunque el Diccionario tenga otra guardada."""
    filas = _grilla(
        [_parseada("608092", "CUBRECAMA KING RAYAS", excel="Cubrecama TIENDA CASA. King")],
        ("608092", "Cubrecama TIENDA CASA. King Size", ANTES, VALENTINA),
    )
    assert filas["608092"]["descripcionOrigen"] == "excel"
    assert filas["608092"]["descripcionMarcaCorregida"] == ""
    assert "marca_no_dicha" not in filas["608092"]["warnings"]


def test_una_fecha_sin_zona_se_lee_como_utc():
    """Si el driver devolviera la fecha sin zona, comparar reventaría el import
    entero por un aviso: se toma como UTC."""
    sin_zona = datetime(2026, 10, 27, 12, 0)
    filas = _grilla(
        [_parseada("608092", "CUBRECAMA KING RAYAS")],
        ("608092", "Cubrecama TIENDA CASA. King Size", sin_zona, VALENTINA),
    )
    assert filas["608092"]["descripcionMarcaCorregida"] == "Cubrecama. King Size"


def test_la_regla_arranca_despues_del_merge_del_pr_20():
    """El PR #20 se mergeó el 16/11/2026 a las 14:18 UTC. Lo guardado antes de
    eso es lo sospechoso; el margen cubre el despliegue."""
    merge = datetime(2026, 11, 16, 14, 17, 53, tzinfo=timezone.utc)
    assert merge < REGLA_DE_MARCA_DESDE <= merge + timedelta(hours=2)


# ---------------------------------------------------------------------------
# El Excel que se descarga: marca la celda solo si nadie lo resolvió
# ---------------------------------------------------------------------------

def _fila_de_la_grilla(descripcion, propuesta):
    return {
        "descripcion": descripcion, "descripcionMarcaCorregida": propuesta,
        "nombreArticulo": "CUBRECAMA KING RAYAS", "descripcionWeb": "",
        "precioRaw": "1490", "precioAnteriorRaw": "1990", "ofertaDet": "Precio Final",
    }


def test_el_aviso_se_recalcula_con_la_descripcion_de_ahora():
    pendiente = _fila_de_la_grilla("Cubrecama TIENDA CASA. King Size", "Cubrecama. King Size")
    assert "marca_no_dicha" in _compute_warnings(pendiente)

    # "Quitar la marca": la descripción ya es la propuesta.
    corregida = _fila_de_la_grilla("Cubrecama. King Size", "Cubrecama. King Size")
    assert "marca_no_dicha" not in _compute_warnings(corregida)

    # "Está bien así": la grilla vacía la propuesta y la marca se queda.
    dejada = _fila_de_la_grilla("Cubrecama TIENDA CASA. King Size", "")
    assert "marca_no_dicha" not in _compute_warnings(dejada)

    # La persona la reescribió a mano sin la marca, con la propuesta vieja colgada.
    a_mano = _fila_de_la_grilla("Cubrecama rayado. King", "Cubrecama. King Size")
    assert "marca_no_dicha" not in _compute_warnings(a_mano)


def test_el_aviso_pinta_la_columna_de_la_descripcion_y_la_propuesta_vuelve_de_la_grilla():
    assert _WARN_VAR["marca_no_dicha"] == "descripcion"
    # Si ConvertidorRowIn no declara el campo, pydantic lo descarta en silencio
    # (extra="ignore") y el Excel dejaría de marcar la celda sin que nada falle.
    vuelta = ConvertidorRowIn(row_id=1, descripcionMarcaCorregida="Cubrecama. King Size")
    assert vuelta.model_dump()["descripcionMarcaCorregida"] == "Cubrecama. King Size"
    assert convertidor.descripcion_sin_marca_deducida is descripcion_sin_marca_deducida

"""Fija el comportamiento del parseo de precios y del vocabulario de variables.

Cada test de este archivo corresponde a un bug real ya arreglado o a una
decisión explícita documentada en el código. Si uno falla, no es "un test
viejo": es que se rompió algo que ya rompió antes en producción.
"""
from app.services.cenefas.data_engine import normalize_decimal, split_price
from app.services.cenefas.formatters import fmt_price
from app.services.cenefas.pptx_importer import _LEGACY_PLACEHOLDERS, _detect_placeholder
from app.services.cenefas.variables import (
    ALIAS_CORTOS,
    CANONICAL_SET,
    CANONICAL_VARS,
    ORDEN_EXPORT,
    es_alcohol,
    resolve,
)


# ---------------------------------------------------------------------------
# split_price — el camino de ida y vuelta del Convertidor
# ---------------------------------------------------------------------------

def test_miles_con_punto_no_es_decimal():
    # Bug real: "1.299" (formato uruguayo escrito por el propio Convertidor)
    # se releía como 1,299 y el cartel salía "$1".
    assert split_price("1.299") == ("1.299", "")
    assert split_price("1.234.567") == ("1.234.567", "")


def test_simbolo_de_moneda_se_descarta_del_valor():
    # El símbolo viaja aparte (unidadMoneda) — un "$" pegado al número no
    # puede romper el parseo ni duplicarse.
    assert split_price("$1.290") == ("1.290", "")
    assert split_price("$ 1.290") == ("1.290", "")
    assert split_price("$1.290,50") == ("1.290", ",50")


def test_decimales_se_separan_con_coma_adelante():
    assert split_price(1234.5) == ("1.234", ",50")
    assert split_price("1.234,50") == ("1.234", ",50")
    # Redondo: sin ",00" que el diseño no contempla.
    assert split_price(899) == ("899", "")
    assert split_price("1234.00") == ("1.234", "")


def test_mecanica_pasa_tal_cual():
    # "2x1" NO es un precio: en un M x N el literal ocupa el cuadro grande.
    assert split_price("2x1") == ("2x1", "")
    assert split_price("SOLO X 25") == ("SOLO X 25", "")


def test_precio_con_unidad_de_venta_pegada():
    # Bug real: "31,2 unidad" no se partía y el cuadro de decimales quedaba
    # vacío en vez de mostrar ",20".
    assert split_price("39 unidad") == ("39", "")
    assert split_price("31,2 unidad") == ("31", ",20")
    assert split_price("74,5 la unidad") == ("74", ",50")


def test_redondeo_no_trunca():
    # Bug real: un precio salido de una fórmula de Excel que cae apenas
    # debajo del entero (510.999...) se imprimía $510 en un cartel que tenía
    # que decir $511 — la parte entera se tomaba por truncamiento.
    assert fmt_price(510.9999999999999) == "511"
    assert fmt_price(510.30) == "510,30"


def test_normalize_decimal():
    # Excel guarda "0,50" como el float 0.5 — sin este caso salía ",05".
    assert normalize_decimal(0.5) == ",50"
    assert normalize_decimal("50") == ",50"
    assert normalize_decimal(",50") == ",50"
    assert normalize_decimal("0") == ""
    assert normalize_decimal("") == ""


# ---------------------------------------------------------------------------
# Vocabulario canónico
# ---------------------------------------------------------------------------

def test_las_32_variables():
    assert len(CANONICAL_VARS) == 32
    assert set(ORDEN_EXPORT) == CANONICAL_SET
    assert "unidadMoneda" in CANONICAL_VARS


def test_resolve_normaliza_nombres():
    assert resolve("PRECIOREGULAR") == "precioRegular"
    assert resolve("precio_regular") == "precioRegular"
    assert resolve("Precio Regular") == "precioRegular"
    # ñ/tildes colapsan: "ano" y "año" son la misma variable.
    assert resolve("ano") == "año"
    assert resolve("unidadMoneda") == "unidadMoneda"
    # una columna ajena no matchea nada (no hay alias acá)
    assert resolve("OFERTA") is None
    assert resolve("columna inventada") is None


# ---------------------------------------------------------------------------
# Alias cortos — el segundo nombre de cada variable
# ---------------------------------------------------------------------------
#
# La regla es que el alias y el nombre largo son LA MISMA variable en todos
# los caminos de entrada: encabezado de Excel y placeholder del PPTX. Lo que
# se fija acá es la paridad, no el contenido de la tabla.

def test_cada_variable_tiene_exactamente_un_alias():
    assert set(ALIAS_CORTOS.values()) == CANONICAL_SET
    assert len(ALIAS_CORTOS) == len(CANONICAL_VARS) == 32
    # Un alias no puede llamarse igual que una variable: sería ambiguo.
    assert not (set(ALIAS_CORTOS) & CANONICAL_SET)


def test_alias_resuelve_igual_que_el_nombre_largo():
    # Camino del encabezado de Excel (data_engine usa resolve()).
    for alias, largo in ALIAS_CORTOS.items():
        assert resolve(alias) == largo
        # Mayúsculas y espacios alrededor, igual que tolera el nombre largo.
        assert resolve(alias.upper()) == largo
        assert resolve(f"  {alias}  ") == largo


def test_placeholder_con_alias_resuelve_igual_que_el_largo():
    # Camino del placeholder del PPTX: la terna (variable, tipo, transform)
    # tiene que ser idéntica escriba uno u otro nombre.
    for alias, largo in ALIAS_CORTOS.items():
        esperado = _detect_placeholder(f"<<{largo}>>")
        for escrito in (alias, alias.upper(), alias.capitalize()):
            assert _detect_placeholder(f"<<{escrito}>>") == esperado, escrito


def test_alias_terminado_en_digito_acepta_sufijo_de_banda():
    # Bug real (08/09/2026): el regex <<(\w+?)(\d*)>> le entrega los dígitos
    # finales al sufijo, así que <<o11>> ("ofertaUno" en la banda 1) llegaba
    # partido en "o" + "11" y no resolvía, mientras que <<ofertaUno1>> sí.
    #
    # No era un cuadro vacío y nada más: _detect_slot_bands saca la cantidad
    # de slots del GCD de los conteos por variable, y tres nombres inventados
    # ("o11", "o12", "o13") lo bajaban a 1 — la plantilla entera quedaba como
    # un solo slot y se apagaba la vinculación entre bandas.
    for alias, largo in ALIAS_CORTOS.items():
        for slot in ("1", "2", "3"):
            assert (
                _detect_placeholder(f"<<{alias}{slot}>>")
                == _detect_placeholder(f"<<{largo}{slot}>>")
            ), f"<<{alias}{slot}>>"


def test_los_alias_no_pisan_los_placeholders_viejos():
    # Los alias se prueban ANTES que la tabla de compatibilidad, así que uno
    # de una o dos letras podría robarse un placeholder de una PPT vieja.
    for clave, destino in _LEGACY_PLACEHOLDERS.items():
        variable, _tipo, _transform = _detect_placeholder(f"<<{clave}>>")
        assert variable == ("" if destino is None else destino), clave


# ---------------------------------------------------------------------------
# Detección de alcohol — la leyenda es obligatoria por ley
# ---------------------------------------------------------------------------

def test_alcohol_por_nombre():
    # Incidente real: una Stella Artois salió sin la leyenda porque el export
    # no traía columna CATEGORIA.
    assert es_alcohol("", "CERVEZA STELLA ARTOIS 330ML")
    assert es_alcohol("BEBIDAS CON ALCOHOL", "")
    assert es_alcohol("", "Vinos TRAVERSA. Todas las variedades")


def test_alcohol_no_salta_por_palabras_parecidas():
    # "gin" dentro de "Ginger ale" y "ron" dentro de "Ronda" eran falsos
    # positivos reales — el borde de palabra va de los dos lados.
    assert not es_alcohol("", "Ginger ale PAOLA 1.5L")
    assert not es_alcohol("", "Ronda de quesos LA CABAÑA")


def test_alcohol_vaso_de_cerveza_es_exceso_aceptado():
    # Decisión vigente (documentada en variables.py): errar por exceso agrega
    # una leyenda que sobra; errar por defecto es una infracción. Un VASO de
    # cerveza dispara la leyenda. Si algún día se decide excluir cristalería,
    # este test se invierte a propósito — no lo "arregles" sin esa decisión.
    assert es_alcohol("", "VASO DE CERVEZA VIDRIO 580ML")


def test_campos_de_entrada_en_camel_case():
    # Regla de la plataforma (Ivan, 2026-08-29): todo el vocabulario visible
    # va en camelCase — incluidos los 12 campos de entrada del Convertidor
    # que se ofrecen en el panel de Tinín. Un guion bajo acá es una clave
    # interna filtrándose a la pantalla de nuevo.
    from app.services.cenefas.convertidor import _INPUT_ALIASES
    from app.services.cenefas.convertidor_ai import _CAMPOS_SUGERIBLES
    assert all("_" not in campo for campo in _CAMPOS_SUGERIBLES), sorted(_CAMPOS_SUGERIBLES)
    assert all("_" not in campo for campo in _INPUT_ALIASES.values()), sorted(set(_INPUT_ALIASES.values()))
    assert set(_CAMPOS_SUGERIBLES) <= set(_INPUT_ALIASES.values())


def test_parseo_de_precio_del_convertidor_no_inventa():
    # Bug real (2026-08-29): "Comprando 2 $129 unidad" en la celda de precio
    # se parseaba a 2.0 en silencio y salio impreso $2. Ahora: o la celda es
    # un precio de punta a punta, o es None y la fila queda roja.
    from app.services.cenefas.convertidor import _parse_price_or_none as pp
    assert pp("Comprando 2 $129 unidad") is None
    assert pp("2X148") is None
    assert pp("2da unidad al 50%") is None
    # lo que SI es un precio se tolera igual que siempre
    assert pp("148 unidad") == 148.0
    assert pp("$119") == 119.0
    assert pp("U$S 45") == 45.0
    assert pp("119,50") == 119.5
    assert pp("1.299") == 1299.0
    assert pp(148) == 148.0
    assert pp("") is None

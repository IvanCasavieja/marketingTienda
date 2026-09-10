"""Fija con qué texto el unificador reconoce un producto.

El caso real (Ivan, 09/09/2026): "pasé un Excel y las unificaciones no
funcionaron". El listado era `LISTADO OFERTAS_ ESPECIAL RP CONGELADOS_`, un
export de Mailing de 57 filas que trae DESCRIPCION y DESCRIPCIONWEB y NO trae
NOMBREARTICULO.

El filtro de entrada del unificador exigía `nombreArticulo`, así que las 57
filas quedaban afuera, `procesables` daba 0, y la función devolvía
`{"grupos": [], "error": False}` al instante -- sin llamar a la IA. Para quien
mira el modal eso es idéntico a "ya revisé todo y no hay nada para unificar".

Medido contra el listado real: 0 grupos con la columna ausente, 7 grupos
(helados CRUFI 1L y 2L, empanadas SARUBBI, mini chipá CELISANO, CRUFIMAX,
canelones LA ESPECIALISTA, hamburguesas SCHNECK) usando la descripción como
respaldo.
"""
from app.services.cenefas.convertidor_ai import (
    _build_unify_prompt,
    _clave_agrupado,
    nombre_para_agrupar,
)

SIN_NOMBRE_ERP = {
    "row_id": 0, "codigo": "68448",
    "nombreArticulo": "",
    "descripcion": "Helado CRUFI Vainilla 1 L",
}
CON_NOMBRE_ERP = {
    "row_id": 1, "codigo": "70980",
    "nombreArticulo": "HELADO CRUFI FRUTILLA 1L",
    "descripcion": "Helado CRUFI Frutilla 1 L",
}
VACIA = {"row_id": 2, "codigo": "9", "nombreArticulo": "", "descripcion": ""}


def test_el_nombre_de_gestion_manda_cuando_esta():
    assert nombre_para_agrupar(CON_NOMBRE_ERP) == "HELADO CRUFI FRUTILLA 1L"


def test_la_descripcion_es_el_respaldo():
    # Sin esto, un export de Mailing entero sale del unificador con 0 grupos.
    assert nombre_para_agrupar(SIN_NOMBRE_ERP) == "Helado CRUFI Vainilla 1 L"


def test_una_fila_sin_ningun_texto_sigue_quedando_afuera():
    # No es lo mismo que el bug: acá de verdad no hay con qué reconocer nada,
    # y mandársela a Tinín es pedirle que invente.
    assert nombre_para_agrupar(VACIA) == ""


def test_el_filtro_de_entrada_acepta_las_filas_sin_nombre_erp():
    filas = [SIN_NOMBRE_ERP, CON_NOMBRE_ERP, VACIA]
    procesables = [f for f in filas if nombre_para_agrupar(f)]
    assert [f["codigo"] for f in procesables] == ["68448", "70980"]


def test_el_orden_por_marca_tambien_usa_el_respaldo():
    """`_clave_agrupado` ordena por marca antes de partir en tandas, y es lo
    que mantiene juntas a las variantes de una misma línea. Leyendo un nombre
    vacío la marca salía siempre "" y el orden se derrumbaba a alfabético."""
    marca, nombre = _clave_agrupado(SIN_NOMBRE_ERP)
    assert marca == "CRUFI"
    assert nombre == "helado crufi vainilla 1 l"


def test_el_prompt_no_le_muestra_un_nombre_vacio():
    """Aunque el filtro dejara pasar la fila, el prompt armaba
    'nombre ERP: ""' y Tinín no tenía con qué agrupar."""
    prompt = _build_unify_prompt([SIN_NOMBRE_ERP, CON_NOMBRE_ERP])
    assert 'nombre ERP: ""' not in prompt
    assert 'nombre ERP: "Helado CRUFI Vainilla 1 L"' in prompt

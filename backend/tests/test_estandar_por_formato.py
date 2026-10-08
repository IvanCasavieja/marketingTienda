"""El estándar por formato de las cenefas TI, inyectado como reglas fijas.

Ivan, 08/10/2026: "los formatos deberían compartir los mismos tamaños...
quiero que estos escalones sean para absolutamente todas las cenefas, reglas
preestablecidas en los bloques de cada variable, dentro de la plataforma".
Ver estandar_por_formato.py y app/data/escalones_por_formato.json.
"""
import pathlib
import re

from app.services.cenefas.component_renderer import preparar_componentes
from app.services.cenefas.estandar_por_formato import (
    CLAVE_ESTANDAR, cargar_estandar, formato_de, reglas_del_estandar,
)
from app.services.cenefas.reglas_fijas import CLAVE_BLOQUEADA, asegurar_reglas_fijas

_PANEL = (pathlib.Path(__file__).resolve().parents[2]
          / "frontend" / "components" / "cenefas" / "editor" / "RulesPanel.tsx")


def _plantilla(formato="a4", mundo="marca_propia", con_category=True):
    d = {
        "version": "2.0", "name": "x", "master_format": formato, "formats": [formato],
        "hoja": {"ancho_cm": 21.0, "alto_cm": 29.7, "formato_declarado": formato},
        "components": [
            {"id": "desc", "type": "text", "variable": "descripcion",
             "base_bounds": {"x": 1, "y": 1, "width": 17.7, "height": 6.7}, "style": {"font_size": 70.0}},
            {"id": "precio", "type": "text", "base_bounds": {"x": 1, "y": 10, "width": 17.7, "height": 10},
             "style": {"font_size": 120.0}, "segments": [
                 {"type": "variable", "value": "unidadMoneda", "style": {"font_size": 120.0, "baseline": 30000}},
                 {"type": "variable", "value": "precioOferta", "style": {"font_size": 228.0}}]},
            {"id": "cod", "type": "text", "base_bounds": {"x": 1, "y": 0.5, "width": 6.6, "height": 0.9},
             "style": {"font_size": 16.0}, "segments": [
                 {"type": "static", "value": "COD.: "}, {"type": "variable", "value": "codigo"}]},
            {"id": "legal", "type": "text", "static_value": "Descuento aplicado en caja",
             "base_bounds": {"x": 1, "y": 28, "width": 10, "height": 0.5}, "style": {"font_size": 8.0}},
        ],
        "rules": [{"id": "mia", "name": "de una persona", "target_component_id": "legal",
                   "condition": {"field": "codigo", "operator": "is_empty"}, "action": {"type": "hide"}}],
    }
    if con_category:
        d["category"] = mundo
    return d


def _por_accion(reglas):
    return {r["id"]: r for r in reglas}


# ------------------------------------------------------------------ el JSON


def test_el_json_es_coherente():
    e = cargar_estandar()
    assert set(e["formatos"]) == {"a4", "3xa4", "a5", "6xa4"}
    assert "marca_propia" in e["mundos"] and "marcas_exclusivas" in e["mundos"]
    for fmt, b in e["formatos"].items():
        esc = b["descripcion"]["escalera"]
        assert [u for u, _ in esc] == sorted({u for u, _ in esc}), f"{fmt}: umbrales de descripción desordenados"
        assert all(esc[i][1] > esc[i + 1][1] for i in range(len(esc) - 1)), f"{fmt}: la escalera de descripción no baja"
        assert all(pt < b["descripcion"]["base_pt"] for _, pt in esc), f"{fmt}: un escalón no es menor que la base"
        grupos = {(g["moneda"], g["con_decimal"]) for g in b["precioOferta"]["escaleras"]}
        assert len(grupos) == len(b["precioOferta"]["escaleras"]), f"{fmt}: grupo de precio repetido"
        for g in b["precioOferta"]["escaleras"]:
            escp = g["escalera"]
            assert all(escp[i][1] > escp[i + 1][1] for i in range(len(escp) - 1)), f"{fmt} {g['moneda']}: el precio no baja"
            assert all(pt < b["precioOferta"]["base_pt"] for _, pt in escp)
        anchos = b["codigo"]["anchos_cm"]
        assert all(anchos[i][1] < anchos[i + 1][1] for i in range(len(anchos) - 1)), f"{fmt}: el ancho del código no crece"


# --------------------------------------------------------------- a quién le toca


def test_le_toca_a_los_mundos_ti_y_a_nadie_mas():
    assert reglas_del_estandar(_plantilla(mundo="marca_propia"))
    assert reglas_del_estandar(_plantilla(mundo="marcas_exclusivas"))
    assert reglas_del_estandar(_plantilla(mundo="redexpres")) == []
    assert reglas_del_estandar(_plantilla(mundo="alemania")) == []
    assert reglas_del_estandar(_plantilla(con_category=False)) == []
    # La categoría explícita manda sobre la guardada.
    assert reglas_del_estandar(_plantilla(mundo="redexpres"), categoria="marca_propia")
    assert reglas_del_estandar(_plantilla(mundo="marca_propia"), categoria="redexpres") == []


def test_un_formato_sin_estandar_no_recibe_nada():
    d = _plantilla(formato="rollo")
    assert formato_de(d) == "rollo"
    assert reglas_del_estandar(d) == []


def test_el_formato_sale_de_la_hoja_y_si_no_del_master_format():
    d = _plantilla("3xa4")
    assert formato_de(d) == "3xa4"
    del d["hoja"]
    assert formato_de(d) == "3xa4"
    del d["master_format"]
    assert formato_de(d) == "3xa4"


# ------------------------------------------------------------- qué reglas arma


def test_arma_base_y_escalera_de_la_descripcion():
    e = cargar_estandar()["formatos"]["a4"]
    reglas = [r for r in reglas_del_estandar(_plantilla()) if r["target_component_id"] == "desc"]
    assert reglas[0]["condition"] == {"field": "descripcion", "operator": "is_not_empty"}
    assert reglas[0]["action"] == {"type": "set_font_size", "value": e["descripcion"]["base_pt"]}
    escalones = [(r["condition"]["value"], r["action"]["value"]) for r in reglas[1:]]
    assert escalones == [(u, pt) for u, pt in e["descripcion"]["escalera"]]
    assert all(r[CLAVE_BLOQUEADA] and r[CLAVE_ESTANDAR] == "a4" for r in reglas)


def test_el_precio_lleva_base_y_una_escalera_por_moneda_con_condicion_compuesta():
    e = cargar_estandar()["formatos"]["a4"]
    reglas = [r for r in reglas_del_estandar(_plantilla()) if r["target_component_id"] == "precio"]
    assert reglas[0]["condition"] == {"field": "precioOferta", "operator": "is_not_empty"}
    assert reglas[0]["action"]["value"] == e["precioOferta"]["base_pt"]
    compuestas = reglas[1:]
    assert all(r["condition"]["operator"] == "and" for r in compuestas)
    grupos = {(r["condition"]["conditions"][0]["value"], r["condition"]["conditions"][1]["operator"] == "is_not_empty") for r in compuestas}
    assert grupos == {(g["moneda"], g["con_decimal"]) for g in e["precioOferta"]["escaleras"] if g["escalera"]}
    assert all(r["condition"]["conditions"][1]["field"] == "decimalPrecioOferta" for r in compuestas)


def test_el_codigo_recibe_anchos_y_ningun_cuerpo():
    e = cargar_estandar()["formatos"]["a4"]
    reglas = [r for r in reglas_del_estandar(_plantilla()) if r["target_component_id"] == "cod"]
    assert reglas and all(r["action"]["type"] == "set_width" for r in reglas)
    assert [(r["condition"]["value"], r["action"]["value"]) for r in reglas] == [tuple(x) for x in e["codigo"]["anchos_cm"]]


def test_un_cuadro_fijo_no_recibe_nada():
    assert not [r for r in reglas_del_estandar(_plantilla()) if r["target_component_id"] == "legal"]


def test_ids_deterministas():
    a = reglas_del_estandar(_plantilla()); b = reglas_del_estandar(_plantilla())
    assert [r["id"] for r in a] == [r["id"] for r in b]
    assert len({r["id"] for r in a}) == len(a)


# ---------------------------------------------------- por asegurar_reglas_fijas


def test_asegurar_reglas_fijas_las_pone_y_conserva_las_de_las_personas():
    salida = asegurar_reglas_fijas(_plantilla())
    fijas = [r for r in salida["rules"] if r.get(CLAVE_BLOQUEADA)]
    assert fijas and all(r.get(CLAVE_ESTANDAR) == "a4" for r in fijas)
    assert [r["id"] for r in salida["rules"] if not r.get(CLAVE_BLOQUEADA)] == ["mia"]


def test_aplicarlo_dos_veces_no_duplica_y_reemplaza_lo_viejo():
    una = asegurar_reglas_fijas(_plantilla())
    dos = asegurar_reglas_fijas(una)
    assert [r["id"] for r in dos["rules"]] == [r["id"] for r in una["rules"]]
    # Una fija de una versión anterior (otro id) se descarta.
    vieja = {**una, "rules": una["rules"] + [{"id": "fosil", "target_component_id": "desc", CLAVE_BLOQUEADA: True,
                                               "condition": {"field": "descripcion", "operator": "is_not_empty"},
                                               "action": {"type": "set_font_size", "value": 5}}]}
    assert "fosil" not in [r["id"] for r in asegurar_reglas_fijas(vieja)["rules"]]


def test_la_categoria_explicita_de_la_ruta_manda():
    d = _plantilla(con_category=False)
    assert not [r for r in asegurar_reglas_fijas(d)["rules"] if r.get(CLAVE_ESTANDAR)]
    assert [r for r in asegurar_reglas_fijas(d, categoria="marca_propia")["rules"] if r.get(CLAVE_ESTANDAR)]


def test_un_mundo_ajeno_queda_como_estaba():
    d = _plantilla(mundo="alemania")
    assert asegurar_reglas_fijas(d)["rules"] == d["rules"]


# ------------------------------------------------------------- lo que imprime


def test_el_estandar_decide_el_cuerpo_al_preparar():
    e = cargar_estandar()["formatos"]["a4"]
    d = asegurar_reglas_fijas(_plantilla())
    corta = {"codigo": "123", "descripcion": "Queso", "precioOferta": "99", "unidadMoneda": "$"}
    larga = {"codigo": "123 - 456 - 789", "descripcion": "x" * 60, "precioOferta": "1.566", "unidadMoneda": "U$S"}
    p_corta = {c["id"]: c for c in preparar_componentes(d["components"], d["rules"], corta)}
    p_larga = {c["id"]: c for c in preparar_componentes(d["components"], d["rules"], larga)}
    # La base manda aunque el diseño traiga otro cuerpo (70 -> 50).
    assert p_corta["desc"]["style"]["font_size"] == e["descripcion"]["base_pt"]
    assert p_larga["desc"]["style"]["font_size"] == [pt for u, pt in e["descripcion"]["escalera"] if 60 > u][-1]
    # El precio: base en la corta; el escalón de U$S de más de 4 caracteres en la larga.
    assert p_corta["precio"]["segments"][1]["style"]["font_size"] == e["precioOferta"]["base_pt"]
    grupo = next(g for g in e["precioOferta"]["escaleras"] if g["moneda"] == "U$S" and not g["con_decimal"])
    esperado = ([pt for u, pt in grupo["escalera"] if 5 > u] or [e["precioOferta"]["base_pt"]])[-1]
    assert p_larga["precio"]["segments"][1]["style"]["font_size"] == esperado
    # Y el símbolo volado acompaña en proporción.
    assert p_larga["precio"]["segments"][0]["style"]["font_size"] < p_corta["precio"]["segments"][0]["style"]["font_size"]
    # El código: ancho de diseño con un código, el escalón de 3 con el grupo.
    assert p_corta["cod"]["base_bounds"]["width"] == 6.6
    assert p_larga["cod"]["base_bounds"]["width"] == [cm for u, cm in e["codigo"]["anchos_cm"] if 15 > u][-1]


# --------------------------------------------------------------- el panel


def test_el_panel_lee_las_condiciones_compuestas():
    fuente = _PANEL.read_text(encoding="utf-8")
    assert "function resumenDeCondicion" in fuente
    bloque = re.search(r"export function resumenDeCondicion.*?\n}", fuente, re.S).group(0)
    assert 'cond.operator === "and"' in bloque and '" y "' in bloque, (
        "el chip del panel tiene que leer las condiciones compuestas del estándar (unidadMoneda y precioOferta)")

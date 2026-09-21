"""Las sucursales de GDU que ve la búsqueda de precios (gdu_rest).

Existe por un caso real: el 21/09/2026 la lista empaquetada tenía 72 sucursales
cuando GDU ya tenía 100 activas. Las 28 que faltaban eran Devoto Express y Fresh
Market -- tiendas de verdad, con precio propio -- y no aparecían en NINGUNA
búsqueda de precios. Si alguien vuelve a mandarlas a "excluir", esto se cae.
"""
from app.services.scraper import gdu_rest as gdu


def test_la_lista_no_puede_encogerse_en_silencio():
    meta = gdu._load_branch_meta()
    assert len(meta) >= 95, f"solo {len(meta)} sucursales: ¿se quedó vieja sucursales_gdu.json?"


def test_estan_las_express_y_fresh_market():
    """Las que faltaban. No dicen 'Devoto' en el nombre, por eso se clasifican
    por el rango del ID."""
    meta = gdu._load_branch_meta()
    for branch_id, nombre in (("3102", "Express Rivera"), ("3121", "Express Canelones"),
                              ("3108", "Fresh Market Parada 1"), ("3140", "Express Av. Italia")):
        assert branch_id in meta, f"falta la sucursal {branch_id} ({nombre})"
        assert meta[branch_id]["cadena"] == "Devoto"


def test_las_tres_cadenas_tienen_sus_sucursales():
    meta = gdu._load_branch_meta()
    por_cadena: dict[str, int] = {}
    for m in meta.values():
        por_cadena[m["cadena"]] = por_cadena.get(m["cadena"], 0) + 1
    assert set(por_cadena) == {"Disco", "Devoto", "Geant"}
    assert por_cadena["Devoto"] >= 60
    assert por_cadena["Disco"] >= 30
    # Géant tiene solo dos locales en el país: Nuevocentro y Parque Roosevelt.
    assert por_cadena["Geant"] == 2


def test_clasificar_por_rango_de_id_y_si_no_por_nombre():
    # el rango manda: las Express no dicen "Devoto" en el nombre
    assert gdu.clasificar_sucursal("3102", "Express Rivera") == "Devoto"
    assert gdu.clasificar_sucursal("199", "Disco 199") == "Disco"
    assert gdu.clasificar_sucursal("1501", "Géant Nuevocentro") == "Geant"
    # fuera de todo rango, decide el nombre
    assert gdu.clasificar_sucursal("6001", "Devoto Lagomar") == "Devoto"
    assert gdu.clasificar_sucursal("2601", "Disco Fresh Market La Cabaña") == "Disco"
    # lo que no es una tienda queda afuera
    for basura in ("CDPerimetral", "Marketplace", "string", "SUC-01", "2606"):
        assert gdu.clasificar_sucursal(basura, basura) == "excluir"
    assert gdu.clasificar_sucursal("9999", "Local 9999") == "excluir"


def test_cada_sucursal_arma_su_link_con_su_propio_sc():
    meta = gdu._load_branch_meta()
    assert gdu._construir_url("Devoto", "241345", "3121").endswith("/product/p/241345?sc=3121")
    assert gdu._construir_url("Disco", "241345", "199").startswith("https://www.disco.com.uy")
    assert gdu._construir_url("Geant", "241345", "1501").startswith("https://www.geant.com.uy")
    assert len({b for b in meta}) == len(meta)  # sin ids repetidos

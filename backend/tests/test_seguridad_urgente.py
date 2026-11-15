"""Arreglos de la auditoría de seguridad del 15/11/2026 que no necesitan base.

Lo que sí la necesita (crear usuarios, bloqueo, tope de recuperación) se probó
contra la base local de prueba; está descripto en el PR.
"""
import pytest
from pydantic import ValidationError

from app.api.routes.auth import _CREDENCIALES_INVALIDAS, hash_de_token
from app.api.routes.watchlist import AgregarItemRequest
from app.core.rate_limit import ip_de_la_cadena


# --- La IP real detrás del proxy ---------------------------------------------

def test_sin_configurar_se_toma_el_primero_como_siempre():
    assert ip_de_la_cadena("1.1.1.1, 10.0.0.1", 0) == "1.1.1.1"


def test_con_un_proxy_de_confianza_se_toma_el_ultimo_y_no_se_puede_falsear():
    """El primer eslabón lo escribe quien pide; el último, nuestro proxy."""
    assert ip_de_la_cadena("6.6.6.6, 200.1.2.3", 1) == "200.1.2.3"
    assert ip_de_la_cadena("6.6.6.6, 7.7.7.7, 200.1.2.3", 1) == "200.1.2.3"


def test_con_dos_proxies_se_cuenta_desde_el_final():
    assert ip_de_la_cadena("6.6.6.6, 200.1.2.3, 10.0.0.1", 2) == "200.1.2.3"


def test_cadena_mas_corta_que_los_saltos_o_vacia():
    assert ip_de_la_cadena("200.1.2.3", 2) == "200.1.2.3"
    assert ip_de_la_cadena("", 1) is None
    assert ip_de_la_cadena(None, 1) is None
    assert ip_de_la_cadena(" , ", 1) is None


# --- Recuperar la contraseña ----------------------------------------------------

def test_en_la_base_va_el_hash_del_link_y_no_el_link():
    token = "abc_DEF-123"
    h = hash_de_token(token)
    assert len(h) == 64 and h != token
    assert hash_de_token(token) == h  # el mismo link da el mismo hash
    assert hash_de_token(token + "x") != h


# --- Login ------------------------------------------------------------------------

def test_el_mensaje_no_dice_si_la_cuenta_existe_o_esta_bloqueada():
    assert "se bloquea" in _CREDENCIALES_INVALIDAS  # avisa del bloqueo en general…
    assert "Cuenta bloqueada" not in _CREDENCIALES_INVALIDAS  # …sin confirmar nada de una cuenta


# --- Links de las listas de precios -------------------------------------------------

def _item(url):
    return AgregarItemRequest(tienda="t", nombre="n", termino_busqueda="b", url=url, precio=1.0, moneda="UYU")


@pytest.mark.parametrize("url", ["javascript:alert(1)", " JavaScript:alert(1)", "data:text/html,x", "//evil.com", "ftp://x"])
def test_un_link_que_no_es_web_no_entra(url):
    with pytest.raises(ValidationError):
        _item(url)


@pytest.mark.parametrize("url", ["https://www.tata.com.uy/p/1", "http://x.uy", "HTTPS://X.UY", ""])
def test_los_links_web_y_el_vacio_entran(url):
    assert _item(url).url == url.strip()

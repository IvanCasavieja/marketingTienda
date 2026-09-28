"""La key de Algolia de LOi se relee del sitio cuando rota.

El 28/09/2026 LOi rotó su search key y el buscador en vivo quedó sin
resultados de LOi (403). Ahora la key vigente se lee del HTML del sitio
(input oculto `algolia_key`) y ante un 403 se reintenta con esa. Acá se fija
el parseo, que es la parte que no necesita red.
"""
from app.services.scraper.live_search import _LOI_ALGOLIA_API_KEY, _extraer_algolia_key

_HTML = '''
<input id="algolia_id" type="hidden" value="90I0MRELM2" />
<input id="algolia_key" type="hidden" value="d85010fc1b48ca21fcbb3bb8d5771014" />
'''


def test_saca_la_key_del_input_oculto():
    assert _extraer_algolia_key(_HTML) == "d85010fc1b48ca21fcbb3bb8d5771014"


def test_sin_el_input_devuelve_none():
    assert _extraer_algolia_key("<html><body>nada</body></html>") is None
    assert _extraer_algolia_key("") is None


def test_no_confunde_el_id_de_la_app_con_la_key():
    assert _extraer_algolia_key('<input id="algolia_id" type="hidden" value="90I0MRELM2" />') is None


def test_la_key_de_arranque_es_la_del_sitio_del_28_09():
    # Si alguien la vuelve a cambiar a mano, que se note en un test.
    assert _LOI_ALGOLIA_API_KEY == "d85010fc1b48ca21fcbb3bb8d5771014"

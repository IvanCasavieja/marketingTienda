"""El límite de pedidos se cuenta por persona, no por el proxy.

El 23/09/2026, con más gente usando la plataforma a la vez, empezaron a salir
429 en cualquier endpoint y el navegador los mostraba como errores de CORS (la
respuesta de rechazo no lleva los headers). La causa: la clave del limitador
era `get_remote_address`, que detrás del proxy de Render devuelve la IP del
proxy — o sea, una sola para todo el mundo. Con 200 por minuto compartidos, un
par de personas trabajando juntas dejaban afuera a las demás.
"""
from app.core.rate_limit import ip_de_quien_pide, limiter


class _Pedido:
    """Lo mínimo que mira la función: los headers y el cliente."""
    def __init__(self, headers: dict, host: str | None = "10.0.0.7"):
        self.headers = headers
        self.client = type("C", (), {"host": host})() if host else None


def test_usa_la_ip_del_cliente_y_no_la_del_proxy():
    pedido = _Pedido({"X-Forwarded-For": "190.64.1.5, 10.0.0.7"})
    assert ip_de_quien_pide(pedido) == "190.64.1.5"


def test_dos_personas_detras_del_mismo_proxy_no_comparten_el_balde():
    una = _Pedido({"X-Forwarded-For": "190.64.1.5, 10.0.0.7"})
    otra = _Pedido({"X-Forwarded-For": "190.64.9.9, 10.0.0.7"})
    assert ip_de_quien_pide(una) != ip_de_quien_pide(otra)


def test_sin_el_header_cae_a_la_ip_directa():
    # En una PC, sin proxy adelante, el header no existe.
    assert ip_de_quien_pide(_Pedido({})) == "10.0.0.7"


def test_un_header_vacio_no_deja_la_clave_en_blanco():
    # Una clave vacía volvería a juntar a todo el mundo en el mismo balde.
    assert ip_de_quien_pide(_Pedido({"X-Forwarded-For": "  "})) == "10.0.0.7"


def test_espacios_alrededor_de_la_ip_no_cuentan():
    a = ip_de_quien_pide(_Pedido({"X-Forwarded-For": " 190.64.1.5 , 10.0.0.7"}))
    b = ip_de_quien_pide(_Pedido({"X-Forwarded-For": "190.64.1.5,10.0.0.7"}))
    assert a == b == "190.64.1.5"


def test_el_limitador_quedo_armado_con_esa_clave():
    # Si alguien vuelve a poner get_remote_address, esto lo marca.
    assert limiter._key_func is ip_de_quien_pide

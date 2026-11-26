"""Don Tino no ofrece los tipos de cenefa de Tienda Inglesa que borró la 0094
(26/11/2026). Su texto fijo decía «Mundos: Redexpres, Rompe Precios, Parrilla
y Vinos…» como si estuvieran, y mandaba a un botón «Nuevo mundo» que en la
pantalla se llama «Nuevo tipo de cenefa»."""


def test_don_tino_sabe_que_los_tipos_de_tienda_inglesa_se_borraron():
    from app.api.routes import chat

    texto = chat._SYSTEM_PROMPT
    assert "**Mundos**: Redexpres, Rompe Precios" not in texto
    assert '"Nuevo mundo"' not in texto
    assert '"Nuevo tipo de cenefa"' in texto
    assert "se borraron el 26/11/2026" in texto

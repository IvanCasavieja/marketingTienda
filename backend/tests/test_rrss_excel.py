"""El Excel de correcciones para el diseñador (rrss/excel.py y rrss/correccion.py).

Los casos de las instrucciones son los de la campaña real del 17 al 20 de
setiembre de 2026, sobre la que Ivan aprobó el formato.
"""
import base64
import io

import pytest
from openpyxl import load_workbook
from PIL import Image

from app.services.rrss import correccion as c
from app.services.rrss import excel


# ---------------------------------------------------------------- instrucciones

@pytest.mark.parametrize("placa, mailing, esperado", [
    ("Carré de cerdo. Kg", "Carré de cerdo. kg", "Va en minúscula: «kg»"),
    ("Cerveza STELLA ARTOIS. Lata 710 ml.", "Cerveza STELLA ARTOIS. Lata 710 ml", "Sobra el punto: sacalo"),
    ("$171 unidad", "$171", "Sobra «unidad»: sacalo"),
    ("$340", "$340 unidad", "Falta «unidad»: agregalo"),
    ("Arvejas TIENDA INGLESA. 300g", "Arvejas TIENDA INGLESA. 300 g", "Falta el espacio: «300 g»"),
    ("Jarra eléctrica INHAUS negra 1.7L", "Jarra eléctrica INHAUS negra. 1.7 L", "Falta el punto y el espacio: agregalo"),
    ("Cerveza STELLA ARTOIS. Lata 710ml.", "Cerveza STELLA ARTOIS. Lata 710 ml", "Sacá el punto y agregá el espacio"),
    ("Vino BRISAS DEL ESTE. Tinto Tannat, Blanco Sauvignon Blanc 750 ml",
     "Vino BRISAS DEL ESTE Tinto Tannat, Blanco Sauvignon Blanc. 750 ml",
     "El punto va después de «Blanc», no de «ESTE»"),
])
def test_instrucciones_de_la_campana_real(placa, mailing, esperado):
    assert c.instruccion("diferente", placa, mailing) == esperado


def test_la_instruccion_no_baja_a_minuscula_lo_que_va_en_mayuscula():
    """str.capitalize() baja todo el resto: decía «colonia» va en mayúscula,
    justo lo contrario de lo que hay que hacer."""
    frase = c.instruccion("diferente", "Queso colonia IL CAPITANO. 100g", "Queso Colonia IL CAPITANO. 100 g")
    assert frase == "Falta el espacio: «100 g», y «Colonia» va en mayúscula"


def test_faltante_y_sobrante_se_dicen_igual_que_en_el_resto():
    assert c.instruccion("falta_en_placa", "", "unidad") == "Falta «unidad»: agregalo"
    assert c.instruccion("sobra_en_placa", "unidad", "") == "Sobra «unidad»: sacalo"


def test_si_cambia_mucho_se_da_el_texto_final():
    assert c.instruccion("diferente", "Pollo entero", "Muslo 1/4 GRANJA TRES ARROYOS. Kg") == \
        "Escribilo así: «Muslo 1/4 GRANJA TRES ARROYOS. Kg»"


# ---------------------------------------------------------------- resaltado por palabra

def _marcado(seg):
    return "".join(f"[{t}]" if d else t for t, d in seg)


def test_un_espacio_que_falta_se_ve_como_palabra_entera():
    p, m = c.diferenciar_palabras("Arvejas TIENDA INGLESA. 300g", "Arvejas TIENDA INGLESA. 300 g")
    assert _marcado(p) == "Arvejas TIENDA INGLESA. [300g]"
    assert _marcado(m) == "Arvejas TIENDA INGLESA. [300 g]"


def test_un_punto_que_se_corrio_marca_los_dos_lugares():
    p, m = c.diferenciar_palabras("DEL ESTE. Tinto Blanc 750", "DEL ESTE Tinto Blanc. 750")
    assert _marcado(p) == "DEL [ESTE.] Tinto [Blanc] 750"
    assert _marcado(m) == "DEL [ESTE] Tinto [Blanc.] 750"


def test_textos_iguales_no_marcan_nada():
    p, m = c.diferenciar_palabras("Bola de lomo. Kg", "Bola de lomo. Kg")
    assert not any(d for _, d in p + m)


# ---------------------------------------------------------------- nombres cortos

def test_etiquetas_sacan_el_prefijo_comun_sin_comerse_un_digito():
    nombres = [f"TI-Los Rompes del Finde-RRSS 17-20_{n}.jpg" for n in ("10", "10 copia", "11", "12")]
    assert list(c.etiquetas(nombres).values()) == ["10", "10 copia", "11", "12"]
    # todos empiezan con "1": el corte va en el separador, no se lleva el 1
    nombres = [f"campaña_{n}.png" for n in ("10", "11", "12")]
    assert list(c.etiquetas(nombres).values()) == ["10", "11", "12"]


def test_etiquetas_sin_prefijo_comun_o_una_sola_placa():
    assert c.etiquetas(["verano.jpg", "invierno.jpg"]) == {"verano.jpg": "verano", "invierno.jpg": "invierno"}
    assert c.etiquetas(["TI-RRSS_10 copia.jpg"]) == {"TI-RRSS_10 copia.jpg": "TI-RRSS_10 copia"}


# ---------------------------------------------------------------- el Excel

def _jpg(color, tam=(90, 90)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", tam, color).save(buf, format="JPEG")
    return buf.getvalue()


def _uri(color) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(_jpg(color, (60, 40))).decode()


def _fila(campo, estado, placa, mailing):
    return {"campo": campo, "estado": estado, "placa": placa, "mailing": mailing, "severidad": "error"}


def _placa(nombre, formato, estado, indice, filas, orden, vista=True, lectura=True):
    return {
        "nombre_archivo": f"TI-RRSS 17-20_{nombre}.jpg", "formato": formato, "estado": estado, "orden": orden,
        "match": {"indice": indice, "puntaje": 100} if indice is not None else None,
        "filas": filas, "error": None,
        "lectura": {"producto": {"descripcion": "algo"}} if lectura else None,
        "vista": _jpg((30, 60, 150), (90, 90) if formato == "1:1" else (90, 160)) if vista else None,
    }


KG = _fila("descripcion", "diferente", "Carré de cerdo. Kg", "Carré de cerdo. kg")
PUNTO = _fila("descripcion", "diferente", "Lata 710 ml.", "Lata 710 ml")
PUNTO_Y_ESPACIO = _fila("descripcion", "diferente", "Lata 710ml.", "Lata 710 ml")

VALIDACION = {
    "mailing": {
        "fecha": "DEL JUEVES 17 AL DOMINGO 20 DE SETIEMBRE",
        "productos": [
            {"descripcion": "Carré de cerdo. kg", "recorte": _uri((200, 40, 40))},
            {"descripcion": "Cerveza STELLA ARTOIS. Lata 710 ml", "recorte": _uri((200, 200, 40))},
            {"descripcion": "Bola de lomo. Kg", "recorte": None},
        ],
    },
    "imagenes": [
        _placa("13", "1:1", "diferencias", 0, [KG], 1),
        _placa("14", "4:5", "diferencias", 0, [KG], 2),
        _placa("15", "9:16", "diferencias", 0, [KG], 3),
        _placa("16", "1:1", "diferencias", 1, [PUNTO], 4),
        _placa("17", "4:5", "diferencias", 1, [PUNTO_Y_ESPACIO], 5),
        _placa("18", "9:16", "diferencias", 1, [PUNTO], 6),
        _placa("10", "1:1", "ok", 2, [], 7),
    ],
}


def _abrir(validacion):
    return load_workbook(io.BytesIO(excel.construir(validacion)), rich_text=True)


def _bloques(ws):
    """Las filas de la columna A que arrancan un bloque (celdas combinadas o sueltas)."""
    return [f for f in range(4, ws.max_row + 1) if ws[f"A{f}"].value]


def test_un_bloque_por_arreglo_no_por_placa():
    ws = _abrir(VALIDACION)["Correcciones"]
    # 6 placas con error -> 3 arreglos: el carré (3 placas), la Stella 16+18 y la Stella 17 sola
    assert len(_bloques(ws)) == 3
    assert "3 arreglos" not in str(ws["A2"].value)  # el texto dice "cosas para corregir"
    assert "3 cosas para corregir, en 6 de las 7 placas" in str(ws["A2"].value)


def test_las_placas_que_estan_bien_no_salen():
    ws = _abrir(VALIDACION)["Correcciones"]
    textos = " ".join(str(ws[f"A{f}"].value) for f in _bloques(ws))
    assert "Bola de lomo" not in textos


def test_la_adaptacion_distinta_de_sus_hermanas_lo_avisa():
    ws = _abrir(VALIDACION)["Correcciones"]
    avisos = [str(ws[f"A{f}"].value) for f in _bloques(ws)]
    assert sum("distinta de sus otras adaptaciones" in a for a in avisos) == 1


def test_lo_que_cambia_va_resaltado_y_la_instruccion_al_costado():
    ws = _abrir(VALIDACION)["Correcciones"]
    fila = _bloques(ws)[0]
    dice, tiene = ws[f"D{fila}"].value, ws[f"E{fila}"].value
    resaltado = lambda rico: [t.text for t in rico if not isinstance(t, str) and t.font.b]  # noqa: E731
    assert resaltado(dice) == ["Kg"] and resaltado(tiene) == ["kg"]
    assert ws[f"F{fila}"].value == "Va en minúscula: «kg»"


def test_lleva_la_hoja_con_todas_las_placas():
    wb = _abrir(VALIDACION)
    assert wb.sheetnames == ["Correcciones", "Todas las placas"]
    ws = wb["Todas las placas"]
    assert ws.max_row - 2 == len(VALIDACION["imagenes"])  # una fila por placa, también las que están bien
    assert [ws[f"A{f}"].value for f in range(3, 6)] == ["13", "14", "15"]


def test_las_imagenes_van_adentro():
    ws = _abrir(VALIDACION)["Correcciones"]
    # por bloque: la tira de placas + el recorte del mailing
    assert len(ws._images) == 6


def test_todas_bien_no_hay_excel():
    todas_bien = {**VALIDACION, "imagenes": [VALIDACION["imagenes"][-1]]}
    with pytest.raises(excel.NadaParaCorregir):
        excel.construir(todas_bien)


def test_una_placa_que_no_se_pudo_leer_no_rompe_el_excel():
    rota = {**_placa("20", "", "error", None, [], 1, vista=False, lectura=False), "error": "No pude abrir el archivo"}
    ws = _abrir({**VALIDACION, "imagenes": [rota]})["Correcciones"]
    assert ws["C4"].value == "No se pudo leer"


def test_una_placa_sin_producto_en_el_mailing_va_sola():
    a = _placa("21", "1:1", "sin_match", None, [], 1)
    b = _placa("22", "1:1", "sin_match", None, [], 2)
    ws = _abrir({**VALIDACION, "imagenes": [a, b]})["Correcciones"]
    assert len(_bloques(ws)) == 2  # no se juntan: no hay nada que diga que son el mismo producto
    assert ws["B4"].value == "No está en el mailing"


def test_anda_en_un_servidor_sin_fuentes(monkeypatch):
    """Render es Linux sin fuentes instaladas: el pie de las miniaturas tiene que
    salir igual, con la fuente que trae Pillow."""
    monkeypatch.setattr(excel, "_FUENTES", ("/no/existe.ttf",))
    monkeypatch.setattr(excel, "_FUENTES_NEGRITA", ("/no/existe-bold.ttf",))
    ws = _abrir(VALIDACION)["Correcciones"]
    assert len(ws._images) == 6

"""Cada producto destacado sale en TRES adaptaciones.

Pedido de Ivan (23/09/2026): "cada placa debe tener 3 adaptaciones, si tiene
menos está mal, si tiene más hay que marcarlo como advertencia". Es una regla
fija y vive con las otras en app/data/rrss_reglas.json.

Lo que fija este archivo: menos de tres es ERROR, más de tres es AVISO, tres
no dice nada; y que el hallazgo del lote se escriba sobre las filas de cada
placa del grupo, que es donde la pantalla y el Excel lo muestran.
"""
from app.services.rrss import reglas
from app.services.rrss.comparador import (
    aplicar_avisos_del_lote, chequeos_del_lote, estado_de_la_placa, _fila,
)

PRODUCTOS = [{"descripcion": "Suprema de pollo AVESUR. Kg"}]


def _placa(id_: int, formato: str, idx: int = 0) -> dict:
    return {
        "id": id_, "nombre_archivo": f"placa_{id_}.jpg", "formato": formato, "match_indice": idx,
        "lectura": {"producto": {"descripcion": "Suprema de pollo AVESUR. Kg"}, "cta": ""},
    }


def _avisos_de_cantidad(chequeos: dict) -> list[dict]:
    return [a for g in chequeos["grupos"] for a in g["avisos"]
            if a["tipo"] in ("faltan_adaptaciones", "sobran_adaptaciones")]


def test_la_regla_vive_en_el_json_y_son_tres():
    assert reglas.ADAPTACIONES == 3


def test_tres_adaptaciones_no_dicen_nada():
    ch = chequeos_del_lote([_placa(1, "1:1"), _placa(2, "4:5"), _placa(3, "9:16")], PRODUCTOS)
    assert _avisos_de_cantidad(ch) == []


def test_dos_adaptaciones_es_un_error():
    ch = chequeos_del_lote([_placa(1, "1:1"), _placa(2, "4:5")], PRODUCTOS)
    [a] = _avisos_de_cantidad(ch)
    assert a["tipo"] == "faltan_adaptaciones"
    assert a["severidad"] == "error"
    assert "2 adaptaciones" in a["texto"] and "3" in a["texto"]
    assert a["imagenes"] == [1, 2]


def test_una_sola_adaptacion_habla_en_singular():
    ch = chequeos_del_lote([_placa(1, "1:1")], PRODUCTOS)
    [a] = _avisos_de_cantidad(ch)
    assert "1 adaptación " in a["texto"] and "faltan 2" in a["texto"]


def test_cuatro_adaptaciones_es_una_advertencia():
    ch = chequeos_del_lote([_placa(1, "1:1"), _placa(2, "4:5"), _placa(3, "9:16"), _placa(4, "1:1")], PRODUCTOS)
    [a] = _avisos_de_cantidad(ch)
    assert a["tipo"] == "sobran_adaptaciones"
    assert a["severidad"] == "aviso"
    assert "4 adaptaciones" in a["texto"]


def test_los_otros_avisos_del_grupo_quedan_como_advertencia():
    # Cuatro placas, una repetida: el aviso de "repetida" sigue existiendo y es aviso.
    ch = chequeos_del_lote([_placa(1, "1:1"), _placa(2, "4:5"), _placa(3, "9:16"), _placa(4, "1:1")], PRODUCTOS)
    repetida = next(a for g in ch["grupos"] for a in g["avisos"] if a["tipo"] == "repetida")
    assert repetida["severidad"] == "aviso"


def test_se_cuenta_por_producto_no_por_lote():
    # Dos productos: uno completo, uno con dos. Solo el segundo se marca.
    productos = PRODUCTOS + [{"descripcion": "Chorizo TIENDA INGLESA. Kg"}]
    placas = [_placa(1, "1:1", 0), _placa(2, "4:5", 0), _placa(3, "9:16", 0),
              _placa(4, "1:1", 1), _placa(5, "4:5", 1)]
    ch = chequeos_del_lote(placas, productos)
    avisos = _avisos_de_cantidad(ch)
    assert len(avisos) == 1 and avisos[0]["imagenes"] == [4, 5]


# ---------------------------------------------------------------------------
# El hallazgo del lote se escribe en cada placa
# ---------------------------------------------------------------------------

def _fila_ok():
    return _fila("descripcion", "Descripción", "producto", "x", "x", "ok", None)


def test_faltan_adaptaciones_baja_a_la_placa_como_error():
    filas = aplicar_avisos_del_lote([_fila_ok()], [
        {"tipo": "faltan_adaptaciones", "severidad": "error", "texto": "Tiene 2 adaptaciones y tienen que ser 3", "imagenes": [1, 2]},
    ])
    fila = next(f for f in filas if f["campo"] == "adaptaciones")
    assert fila["severidad"] == "error"
    assert fila["estado"] == "distinto"
    assert fila["placa"] == "Tiene 2 adaptaciones y tienen que ser 3"
    assert estado_de_la_placa(filas, idx=0) == "diferencias"


def test_sobran_adaptaciones_baja_como_aviso():
    filas = aplicar_avisos_del_lote([_fila_ok()], [
        {"tipo": "sobran_adaptaciones", "severidad": "aviso", "texto": "Tiene 4", "imagenes": [1]},
    ])
    fila = next(f for f in filas if f["campo"] == "adaptaciones")
    assert fila["severidad"] == "aviso"
    assert estado_de_la_placa(filas, idx=0) == "avisos"


def test_los_otros_avisos_del_lote_no_bajan_a_la_placa():
    # "falta_formato" y "repetida" ya tienen su lugar en el resumen.
    filas = aplicar_avisos_del_lote([_fila_ok()], [
        {"tipo": "falta_formato", "severidad": "aviso", "texto": "Le falta la 9:16", "imagenes": []},
        {"tipo": "repetida", "severidad": "aviso", "texto": "Hay 2 en 1:1", "imagenes": [1, 2]},
    ])
    assert not any(f["campo"] == "adaptaciones" for f in filas)


def test_cerrar_dos_veces_no_duplica():
    aviso = {"tipo": "faltan_adaptaciones", "severidad": "error", "texto": "Tiene 2", "imagenes": [1]}
    una = aplicar_avisos_del_lote([_fila_ok()], [aviso])
    dos = aplicar_avisos_del_lote(una, [aviso])
    assert sum(1 for f in dos if f["campo"] == "adaptaciones") == 1


def test_sin_avisos_las_filas_quedan_como_estaban():
    fila = _fila_ok()
    assert aplicar_avisos_del_lote([fila], []) == [fila]

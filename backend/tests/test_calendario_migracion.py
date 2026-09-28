"""La 0057 copia el calendario de `calendario_meses` a una fila por barra.

Lo que se fija acá es que no se pierda ni se cambie nada: cada barra guardada
sale con su id, su nombre, su color y sus piezas; los días pasan a fechas del
mes al que pertenecían; y los headers derivados (los que bajan de Retail Media
o de una acción) no se copian, porque se recalculan.

Se corrió además contra la copia real de producción del 28/09/2026: 164 barras
y 2 piezas, las mismas antes y después.
"""
import importlib.util
import os
from datetime import date

_RUTA = os.path.join(os.path.dirname(__file__), "..", "migrations", "versions", "0057_calendario_por_barra.py")
_spec = importlib.util.spec_from_file_location("migracion_0057", _RUTA)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
convertir_meses = _mod.convertir_meses


def _barra(id_, nombre, desde, hasta, **extra):
    return {"id": id_, "nombre": nombre, "desde": desde, "hasta": hasta, "color": "#FFF2CC", **extra}


def _mes(comercial=(), retail=(), header=None, posiciones=None):
    return {
        "comercial": list(comercial),
        "retail": list(retail),
        "header": header or [{"id": f"pos-{i}", "nombre": f"Posición {i}", "filas": [[]]} for i in range(1, 11)],
        "posicionesRM": posiciones or [4, 5, 6],
    }


def test_cada_barra_sale_una_vez_con_su_id_y_su_nombre():
    meses = {
        "2026-09": _mes(comercial=[{"nombre": "MEGA EVENTO", "filas": [
            [_barra("br-1", "Fiesta de Italia", 9, 23), _barra("br-2", "MRP", 1, 6)],
            [_barra("br-3", "Otra", 2, 4)],
        ]}]),
    }
    barras, piezas, _ = convertir_meses(meses)
    assert sorted((b["id"], b["nombre"]) for b in barras) == [
        ("br-1", "Fiesta de Italia"), ("br-2", "MRP"), ("br-3", "Otra"),
    ]
    assert piezas == []


def test_los_dias_pasan_a_fechas_de_su_mes_y_el_renglon_se_conserva():
    meses = {"2026-10": _mes(comercial=[{"nombre": "Sin mailing", "filas": [[], [_barra("br-1", "Halloween", 27, 31)]]}])}
    barras, _, _ = convertir_meses(meses)
    assert barras[0]["desde"] == date(2026, 10, 27)
    assert barras[0]["hasta"] == date(2026, 10, 31)
    assert barras[0]["carril"] == 1
    assert barras[0]["banda"] == "Sin mailing"
    assert barras[0]["seccion"] == "comercial"


def test_un_31_en_un_mes_de_30_queda_en_el_30():
    meses = {"2026-11": _mes(retail=[{"nombre": "CARRUSEL", "grupo": "eComm", "filas": [[_barra("br-1", "X", 20, 31)]]}])}
    barras, _, _ = convertir_meses(meses)
    assert barras[0]["hasta"] == date(2026, 11, 30)


def test_las_piezas_viajan_con_su_estado_y_su_fecha():
    pieza_envio = {"id": "pz-1", "area": "email", "formato": "Mailing digital", "estado": "aprobado", "desde": 12, "hasta": 12, "hora": "10:00"}
    pieza_header = {"id": "pz-2", "area": "web-home", "formato": "Header", "estado": "pendiente"}
    meses = {"2026-10": _mes(comercial=[{"nombre": "MEGA EVENTO", "filas": [
        [_barra("br-1", "Fiesta", 9, 23, piezas=[pieza_envio, pieza_header])],
    ]}])}
    _, piezas, _ = convertir_meses(meses)
    assert [p["id"] for p in piezas] == ["pz-1", "pz-2"]
    assert piezas[0]["estado"] == "aprobado"
    assert piezas[0]["desde"] == date(2026, 10, 12)
    assert piezas[0]["hora"] == "10:00"
    assert piezas[1]["desde"] is None
    assert [p["orden"] for p in piezas] == [0, 1]
    assert all(p["barra_id"] == "br-1" for p in piezas)


def test_los_headers_derivados_no_se_copian_pero_los_manuales_si():
    header = [{"id": f"pos-{i}", "nombre": f"Posición {i}", "filas": [[]]} for i in range(1, 11)]
    header[0]["filas"][0] = [_barra("ac-br-1", "Fiesta", 9, 23, origen={"tipo": "accion", "accionId": "br-1"})]
    header[3]["filas"][0] = [_barra("rm-br-9", "Conaprole", 1, 2, origen={"tipo": "retail", "bandaId": "b", "filaIdx": 0})]
    header[6]["filas"][0] = [_barra("br-m", "A mano", 3, 5, origen={"tipo": "manual"})]
    barras, _, _ = convertir_meses({"2026-10": _mes(header=header)})
    assert [(b["id"], b["seccion"], b["banda"]) for b in barras] == [("br-m", "header", "pos-7")]


def test_las_posiciones_de_rm_de_cada_mes():
    _, _, posiciones = convertir_meses({
        "2026-09": _mes(posiciones=[4, 5, 6]),
        "2026-10": _mes(posiciones=[1, 2, 3]),
        "2026-11": {},
    })
    assert posiciones == {"2026-09": [4, 5, 6], "2026-10": [1, 2, 3], "2026-11": [4, 5, 6]}


def test_un_id_repetido_entre_meses_no_pisa_al_otro():
    meses = {
        "2026-09": _mes(comercial=[{"nombre": "A", "filas": [[_barra("br-1", "Setiembre", 1, 2)]]}]),
        "2026-10": _mes(comercial=[{"nombre": "A", "filas": [[_barra("br-1", "Octubre", 1, 2)]]}]),
    }
    barras, _, _ = convertir_meses(meses)
    assert len(barras) == 2
    assert len({b["id"] for b in barras}) == 2
    assert {b["nombre"] for b in barras} == {"Setiembre", "Octubre"}


def test_una_barra_al_reves_no_se_pierde():
    barras, _, _ = convertir_meses({"2026-10": _mes(comercial=[{"nombre": "A", "filas": [[_barra("br-1", "X", 9, 3)]]}])})
    assert (barras[0]["desde"], barras[0]["hasta"]) == (date(2026, 10, 3), date(2026, 10, 9))


def test_un_mes_vacio_no_da_barras():
    barras, piezas, posiciones = convertir_meses({"2027-01": {}})
    assert barras == [] and piezas == []
    assert posiciones == {"2027-01": [4, 5, 6]}

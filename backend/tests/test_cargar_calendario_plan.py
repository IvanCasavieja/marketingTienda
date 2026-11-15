"""El cargador del calendario desde el Excel: qué decide antes de escribir.

`scripts/cargar_calendario_desde_excel.py` se corre a mano y escribe en el
calendario por la misma API que la pantalla. Hasta acá no tenía pruebas. Lo
que se fija es el plan que arma, con barras hechas a mano (sin el Excel y sin
la red), y en especial lo que cambió el 12/11/2026:

  - el renglón 'TIENDA FARMA' ya no se carga en Tienda Inglesa: Tienda Farma
    tiene su propio mundo;
  - la categoría de una acción (su banda) ahora se cambia en la pantalla. A una
    acción recategorizada el cargador no la encontraba en la banda del Excel y
    la creaba otra vez: ahora la reconoce en la otra banda y la deja ahí;
  - dice a qué mundo le habla;
  - y lo que ya hacía con las barras que sí están en su banda sigue igual.
"""
import importlib.util
import os
import re
import sys
import warnings

import pytest

# El script importa estas tres cosas al cargarse. Donde falten, estas pruebas
# se saltean en vez de fallar.
for _dependencia in ("openpyxl", "rapidfuzz", "httpx"):
    pytest.importorskip(_dependencia)

_RUTA = os.path.join(os.path.dirname(__file__), "..", "scripts", "cargar_calendario_desde_excel.py")
_spec = importlib.util.spec_from_file_location("cargar_calendario_desde_excel", _RUTA)
_mod = importlib.util.module_from_spec(_spec)
# El script apaga todas las advertencias al cargarse (es de correr a mano).
# Adentro de este `with`, eso no le llega al resto de la corrida de pytest.
with warnings.catch_warnings():
    _spec.loader.exec_module(_mod)
armar_plan = _mod.armar_plan
quitar_retiradas = _mod.quitar_retiradas

_MES = "2026-08"


def _plataforma(id_, banda, nombre, desde, hasta, carril=0, color="#FFF2CC", mes=_MES):
    """Una barra como la devuelve GET /calendario/datos, con los días de un mes."""
    return {
        "id": id_, "mundo": "tienda_inglesa", "seccion": "comercial", "banda": banda, "carril": carril,
        "nombre": nombre, "color": color, "desde": f"{mes}-{desde:02d}", "hasta": f"{mes}-{hasta:02d}",
        "piezas": [], "avisos": [], "tareas": [],
    }


def _excel(banda, nombre, desde, hasta, carril=0, color="#FFF2CC", mes=_MES):
    """Una barra como la arma `leer_excel` de una celda combinada."""
    return {
        "banda": banda, "carril": carril, "nombre": nombre, "color": color,
        "desde": f"{mes}-{desde:02d}", "hasta": f"{mes}-{hasta:02d}",
    }


# ---------------------------------------------------------------------------
# El renglón retirado
# ---------------------------------------------------------------------------

def test_tienda_farma_ya_no_se_carga_este_escrita_como_este():
    excel = {
        "2026-08": [
            _excel("TIENDA FARMA", "Semana de la piel", 3, 9),
            _excel("FARMA", "Dermocosmética", 3, 9),
            _excel("MEGA EVENTO", "Día del Niño", 10, 16),
            _excel("tienda  farma ", "Vuelta a clases", 20, 25),
        ],
        "2026-09": [_excel("Tienda Farma", "Primavera", 21, 30, mes="2026-09")],
    }
    sacadas = quitar_retiradas(excel)
    # 'FARMA' a secas se queda: no es seguro que sea lo mismo.
    assert [(b["banda"], b["nombre"]) for b in excel["2026-08"]] == [
        ("FARMA", "Dermocosmética"), ("MEGA EVENTO", "Día del Niño"),
    ]
    assert excel["2026-09"] == []
    # Una sola cuenta por renglón, esté escrito como esté.
    assert dict(sacadas) == {"TIENDA FARMA": 3}


def test_si_no_hay_nada_de_un_renglon_retirado_no_saca_nada():
    excel = {_MES: [_excel("FARMA", "Dermocosmética", 3, 9), _excel("MEGA EVENTO", "Día del Niño", 10, 16)]}
    assert not quitar_retiradas(excel)
    assert len(excel[_MES]) == 2


def test_lo_que_quedo_en_tienda_farma_no_se_toca_ni_se_toma_por_pareja_de_nada():
    # Las barras viejas de ese renglón se dejan como están: ni se las da por
    # una acción del Excel "recategorizada", ni se les corren las fechas.
    plataforma = [
        _plataforma("br-tf-1", "TIENDA FARMA", "Semana de la piel", 3, 9),
        _plataforma("br-tf-2", "TIENDA FARMA", "Vuelta a clases", 20, 25),
    ]
    excel = {_MES: [
        _excel("FARMA", "Semana de la piel", 3, 9),      # mismo nombre y mismas fechas
        _excel("FARMA", "Vuelta a clases", 21, 26),      # mismo nombre y fechas que se tocan
    ]}
    plan = armar_plan(excel, plataforma)
    assert [(b["banda"], b["nombre"]) for b in plan["crear"]] == [
        ("FARMA", "Semana de la piel"), ("FARMA", "Vuelta a clases"),
    ]
    assert plan["cambiar"] == [] and plan["recategorizadas"] == []
    assert [s["id"] for s in plan["solo_plataforma"]] == ["br-tf-1", "br-tf-2"]


# ---------------------------------------------------------------------------
# Lo de siempre: las barras que están en su banda
# ---------------------------------------------------------------------------

def test_una_barra_del_excel_que_no_esta_en_la_plataforma_se_crea():
    plan = armar_plan({_MES: [_excel("MEGA EVENTO", "Día del Niño", 10, 16)]}, [])
    assert plan["crear"] == [{
        "mes": "2026-08", "id": "br-xl-2026-08-11e9f9256c", "seccion": "comercial",
        "banda": "MEGA EVENTO", "carril": 0, "nombre": "Día del Niño", "color": "#FFF2CC",
        "desde": "2026-08-10", "hasta": "2026-08-16",
    }]
    assert plan["cambiar"] == [] and plan["iguales"] == 0 and plan["recategorizadas"] == []
    assert plan["bandas_nuevas"] == ["MEGA EVENTO"]


def test_el_id_de_una_barra_nueva_es_siempre_el_mismo():
    # Es lo que hace que correrlo dos veces no duplique: a un id repetido el
    # servidor contesta "ya existía". Por eso está escrito acá y no calculado:
    # tiene que ser el mismo también en otra corrida y en otra máquina.
    ids = {
        armar_plan({_MES: [_excel("MEGA EVENTO", "Día del Niño", 10, 16)]}, [])["crear"][0]["id"]
        for _ in range(2)
    }
    assert ids == {"br-xl-2026-08-11e9f9256c"}
    # Y es un id que el servidor acepta (`_ID` en app/api/routes/calendario.py).
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", ids.pop())


def test_una_barra_que_ya_esta_igual_en_su_banda_no_planea_nada():
    plataforma = [_plataforma("br-1", "MEGA EVENTO", "Día del Niño", 10, 16)]
    # Las mayúsculas y los espacios de más no la hacen otra.
    plan = armar_plan({_MES: [_excel("Mega  Evento", "día del niño", 10, 16)]}, plataforma)
    assert plan["iguales"] == 1
    assert plan["crear"] == [] and plan["cambiar"] == []
    assert plan["recategorizadas"] == [] and plan["solo_plataforma"] == []


def test_el_mismo_nombre_con_otras_fechas_en_su_banda_sigue_siendo_un_cambio_de_fechas():
    plataforma = [_plataforma("br-1", "MEGA EVENTO", "Día del Niño", 10, 16)]
    plan = armar_plan({_MES: [_excel("MEGA EVENTO", "Día del Niño", 12, 18)]}, plataforma)
    assert [(c["id"], c["cambios"], c["motivo"]) for c in plan["cambiar"]] == [
        ("br-1", {"desde": "2026-08-12", "hasta": "2026-08-18"}, "mismo nombre, otras fechas"),
    ]
    assert plan["crear"] == [] and plan["recategorizadas"] == []


def test_una_renombrada_en_el_excel_se_sigue_renombrando():
    plataforma = [_plataforma("br-1", "MEGA EVENTO", "Día del Niño", 10, 16)]
    plan = armar_plan({_MES: [_excel("MEGA EVENTO", "Día del Niño - juguetes", 10, 16)]}, plataforma)
    assert [(c["id"], c["cambios"], c["motivo"]) for c in plan["cambiar"]] == [
        ("br-1", {"nombre": "Día del Niño - juguetes"}, "renombrada en el Excel"),
    ]
    assert plan["crear"] == [] and plan["recategorizadas"] == []


def test_la_que_esta_en_su_banda_es_la_pareja_aunque_haya_otra_igual_en_otra_banda():
    plataforma = [
        _plataforma("br-suya", "MEGA EVENTO", "Ciberlunes", 2, 4),
        _plataforma("br-otra", "Especiales", "Ciberlunes", 2, 4),
    ]
    plan = armar_plan({_MES: [_excel("MEGA EVENTO", "Ciberlunes", 2, 4)]}, plataforma)
    assert plan["iguales"] == 1 and plan["recategorizadas"] == []
    assert [s["id"] for s in plan["solo_plataforma"]] == ["br-otra"]


# ---------------------------------------------------------------------------
# La acción a la que le cambiaron la categoría en la pantalla
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("donde_quedo", ["Especiales", "Sin categoría"])
def test_una_accion_recategorizada_en_la_pantalla_no_se_crea_de_nuevo(donde_quedo):
    # En el Excel sigue en 'Sin mailing'; en la pantalla alguien la pasó a otra
    # categoría (y de paso le cambió el color). Se respeta tal cual está.
    plataforma = [_plataforma("br-1", donde_quedo, "Día del Niño", 10, 16, color="#DDEBF7")]
    plan = armar_plan({_MES: [_excel("Sin mailing", "Día del Niño", 10, 16)]}, plataforma)
    assert plan["crear"] == [] and plan["cambiar"] == []
    assert plan["iguales"] == 1
    assert plan["recategorizadas"] == [{
        "id": "br-1", "mes": "2026-08", "nombre": "Día del Niño",
        "banda_excel": "Sin mailing", "banda_plataforma": donde_quedo,
    }]
    assert plan["solo_plataforma"] == []


def test_recategorizada_y_con_otras_fechas_en_el_excel_solo_se_le_corren_las_fechas():
    plataforma = [
        _plataforma("br-1", "Especiales", "Día del Niño", 10, 16, carril=0),
        # Ocupa el carril 0 de Especiales justo donde caen las fechas nuevas.
        _plataforma("br-2", "Especiales", "Liquidación de invierno", 17, 23, carril=0),
    ]
    excel = {_MES: [
        _excel("Sin mailing", "Día del Niño", 12, 18),
        _excel("Especiales", "Liquidación de invierno", 17, 23),
    ]}
    plan = armar_plan(excel, plataforma)
    assert plan["crear"] == []
    assert [(c["id"], c["motivo"]) for c in plan["cambiar"]] == [
        ("br-1", "recategorizada en la plataforma: se actualizan las fechas"),
    ]
    cambios = plan["cambiar"][0]["cambios"]
    # Se queda en Especiales: la banda no viaja. Y el carril se busca ahí, donde
    # el 0 está ocupado. En 'Sin mailing', la banda del Excel, el 0 está libre:
    # si se buscara ahí, el carril no cambiaría.
    assert "banda" not in cambios
    assert cambios == {"desde": "2026-08-12", "hasta": "2026-08-18", "carril": 1}
    assert [(r["id"], r["banda_excel"], r["banda_plataforma"]) for r in plan["recategorizadas"]] == [
        ("br-1", "Sin mailing", "Especiales"),
    ]
    assert plan["solo_plataforma"] == []


def test_el_mismo_nombre_y_las_mismas_fechas_en_otra_banda_ganan_a_un_nombre_parecido_en_la_suya():
    plataforma = [
        _plataforma("br-parecida", "Sin mailing", "Día del Niño - juguetes", 9, 15),
        _plataforma("br-movida", "Especiales", "Día del Niño", 10, 16),
    ]
    plan = armar_plan({_MES: [_excel("Sin mailing", "Día del Niño", 10, 16)]}, plataforma)
    # Antes se daba a la parecida por "renombrada en el Excel" y se la pisaba.
    assert plan["cambiar"] == [] and plan["crear"] == []
    assert [r["id"] for r in plan["recategorizadas"]] == ["br-movida"]
    assert [s["id"] for s in plan["solo_plataforma"]] == ["br-parecida"]


def test_una_parecida_no_le_roba_la_pareja_a_la_recategorizada_venga_en_el_orden_que_venga():
    plataforma = [_plataforma("br-1", "Especiales", "Día del Niño", 10, 16)]
    excel = {_MES: [
        # Viene primero en el Excel, está en la banda de la de la plataforma y se le parece...
        _excel("Especiales", "Día del Niño - juguetes", 11, 17),
        # ...pero la de la plataforma es esta otra: mismo nombre y mismas fechas.
        _excel("Sin mailing", "Día del Niño", 10, 16),
    ]}
    plan = armar_plan(excel, plataforma)
    assert [r["id"] for r in plan["recategorizadas"]] == ["br-1"]
    assert plan["cambiar"] == []
    assert [(b["banda"], b["nombre"]) for b in plan["crear"]] == [("Especiales", "Día del Niño - juguetes")]


def test_la_misma_accion_en_dos_renglones_del_excel_son_dos_barras():
    # 'Ciberlunes' está en MEGA EVENTO y en Mailing GRAL, con las mismas fechas.
    # La de la plataforma ya es la pareja de una: la otra se crea, no se la da
    # por recategorizada.
    plataforma = [_plataforma("br-1", "MEGA EVENTO", "Ciberlunes", 2, 4)]
    excel = {_MES: [_excel("Mailing GRAL", "Ciberlunes", 2, 4), _excel("MEGA EVENTO", "Ciberlunes", 2, 4)]}
    plan = armar_plan(excel, plataforma)
    assert plan["iguales"] == 1 and plan["recategorizadas"] == []
    assert [(b["banda"], b["nombre"]) for b in plan["crear"]] == [("Mailing GRAL", "Ciberlunes")]


# ---------------------------------------------------------------------------
# Lo que muestra y lo que manda
# ---------------------------------------------------------------------------

def test_el_plan_dice_lo_que_no_se_carga_y_lo_que_se_respeta(capsys):
    excel = {_MES: [
        _excel("TIENDA FARMA", "Semana de la piel", 3, 9),
        _excel("Sin mailing", "Día del Niño", 10, 16),
    ]}
    plataforma = [_plataforma("br-1", "Especiales", "Día del Niño", 10, 16)]
    retiradas = quitar_retiradas(excel)
    _mod.mostrar(armar_plan(excel, plataforma), excel, retiradas)
    salida = capsys.readouterr().out
    assert "renglones del Excel que no se cargan (tienen su propio mundo): {'TIENDA FARMA': 1}" in salida
    assert "recategorizadas en la plataforma (se respetan): 1" in salida
    assert "en el Excel: Sin mailing -> en la plataforma: Especiales" in salida


def test_si_no_se_saco_ningun_renglon_el_plan_no_lo_nombra(capsys):
    excel = {_MES: [_excel("MEGA EVENTO", "Día del Niño", 10, 16)]}
    _mod.mostrar(armar_plan(excel, []), excel, quitar_retiradas(excel))
    assert "no se cargan" not in capsys.readouterr().out


class _Respuesta:
    def __init__(self, cuerpo, status_code=200):
        self._cuerpo, self.status_code, self.text = cuerpo, status_code, ""

    def json(self):
        return self._cuerpo


class _ApiDeMentira:
    """Lo que `main` usa de `Api`, sin red: anota cada pedido que le hacen."""

    def __init__(self, barras):
        self.barras, self.pedidos = barras, []

    def pedir(self, metodo, path, **kw):
        self.pedidos.append((metodo, path, kw))
        if metodo == "GET":
            return _Respuesta({"rev": 1, "mundo": "tienda_inglesa", "barras": self.barras, "posicionesRM": {}})
        return _Respuesta({"id": path.rsplit("/", 1)[-1], "rev": 2}, 201 if metodo == "POST" else 200)


@pytest.fixture
def correr(monkeypatch, tmp_path):
    """Corre `main` con un Excel y una plataforma de mentira, y devuelve los
    pedidos que le hizo a la API."""
    def _correr(excel, plataforma, *argumentos):
        api = _ApiDeMentira(plataforma)
        monkeypatch.setattr(_mod, "Api", lambda: api)
        # Por si `main` cambia y deja de pasar por `Api`: sin usuario y con esta
        # dirección, la Api de verdad no llega a ningún lado. Esto no puede
        # escribir nunca en el calendario real.
        monkeypatch.delenv("MKTG_EMAIL", raising=False)
        monkeypatch.delenv("MKTG_PASSWORD", raising=False)
        monkeypatch.setattr(_mod, "API", "http://127.0.0.1:9/no-es-la-api")
        monkeypatch.setattr(_mod, "leer_excel", lambda filtro: excel)
        monkeypatch.setitem(_mod.imp.RUTAS, "comercial", tmp_path)     # "el Excel está"
        monkeypatch.setattr(_mod, "BACKUPS", tmp_path / "backups")
        monkeypatch.setattr(_mod, "PAUSA", 0)
        monkeypatch.setattr(sys, "argv", ["cargar_calendario_desde_excel.py", *argumentos])
        assert _mod.main() == 0
        return api.pedidos
    return _correr


def _una_carga():
    excel = {_MES: [
        _excel("TIENDA FARMA", "Semana de la piel", 3, 9),       # de un renglón que no se carga
        _excel("Sin mailing", "Día del Niño", 12, 18),           # recategorizada y con otras fechas
        _excel("MEGA EVENTO", "Liquidación de invierno", 20, 25),  # nueva
    ]}
    return excel, [_plataforma("br-1", "Especiales", "Día del Niño", 10, 16)]


def test_sin_aplicar_solo_lee(correr):
    pedidos = correr(*_una_carga())
    assert pedidos == [("GET", "/calendario/datos", {"params": {"mundo": "tienda_inglesa"}})]


def test_al_aplicar_lee_y_escribe_en_tienda_inglesa_y_no_manda_la_banda_de_una_recategorizada(correr):
    pedidos = correr(*_una_carga(), "--aplicar")
    # Lee antes y después, las dos veces el mundo de Tienda Inglesa.
    assert [kw for metodo, _, kw in pedidos if metodo == "GET"] == [{"params": {"mundo": "tienda_inglesa"}}] * 2
    # A la recategorizada le corre las fechas y nada más: sigue en Especiales.
    assert [(path, kw["json"]) for metodo, path, kw in pedidos if metodo == "PATCH"] == [
        ("/calendario/barras/br-1", {"desde": "2026-08-12", "hasta": "2026-08-18"}),
    ]
    # Crea solo la nueva, y dice en qué mundo. Nada de TIENDA FARMA.
    altas = [kw["json"] for metodo, _, kw in pedidos if metodo == "POST"]
    assert [(a["mundo"], a["banda"], a["nombre"]) for a in altas] == [
        ("tienda_inglesa", "MEGA EVENTO", "Liquidación de invierno"),
    ]

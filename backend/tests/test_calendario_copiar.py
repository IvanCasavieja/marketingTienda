"""Copiar una acción a otra fecha ("copiar del año pasado").

Pedido de Ivan (15/11/2026): el Ciberlunes 2026 tiene que nacer del 2025 con
todo lo que tenía. Lo que se fija acá es lo que no depende de la base: a qué
fecha va "al año que viene", cómo cambia el año del nombre, qué se resetea y
qué se corre en cada pieza, tarea y aviso, a quién se saca y qué dice el aviso.

Lo que sí necesita Postgres (la transacción, la revisión, el reintento) se
probó a mano contra una base local y en el navegador.
"""
from datetime import date, datetime, timedelta, timezone
from itertools import count

import pytest
from pydantic import ValidationError
from sqlalchemy import Date, DateTime, Integer, String, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.api.routes.calendario import (
    CopiaDeBarra, mensaje_de_asignacion, mensaje_de_tareas_copiadas,
)
from app.models.calendario import CalendarioAviso, CalendarioBarra, CalendarioPieza, CalendarioTarea
from app.services.calendario_copia import (
    DIAS_AL_ANIO_QUE_VIENE, al_anio_que_viene, copiar_avisos, copiar_la_accion, copiar_piezas,
    copiar_tareas, en_orden_de_alta, fechas_corridas, ids_de_personas, nombre_para_la_copia,
    tareas_por_responsable, valores_copiados,
)

UN_ANIO = timedelta(days=DIAS_AL_ANIO_QUE_VIENE)
AHORA = datetime(2025, 11, 20, 12, 0, tzinfo=timezone.utc)


def _ids():
    """Ids previsibles, para poder decir cuál es cuál."""
    n = count(1)
    return lambda prefijo: f"{prefijo}-nuevo-{next(n)}"


# --- La fecha ----------------------------------------------------------------

def test_al_anio_que_viene_cae_el_mismo_dia_de_la_semana():
    """52 semanas: el Ciberlunes 2025 (lunes 1/12) va al lunes 30/11/2026."""
    ciberlunes = date(2025, 12, 1)
    copia = al_anio_que_viene(ciberlunes)
    assert copia == date(2026, 11, 30)
    assert copia.weekday() == ciberlunes.weekday() == 0


def test_al_anio_que_viene_cruzando_un_bisiesto_tambien():
    assert al_anio_que_viene(date(2027, 5, 9)).weekday() == date(2027, 5, 9).weekday()
    assert al_anio_que_viene(date(2027, 5, 9)) == date(2028, 5, 7)


# --- El nombre ---------------------------------------------------------------

def test_el_anio_del_nombre_se_corre_con_la_accion():
    assert nombre_para_la_copia("Ciberlunes 2025", date(2025, 12, 1), date(2025, 12, 2), date(2026, 11, 30)) \
        == "Ciberlunes 2026"


def test_sin_anio_en_el_nombre_queda_igual():
    assert nombre_para_la_copia("Día de la Madre", date(2025, 5, 4), date(2025, 5, 11), date(2026, 5, 3)) \
        == "Día de la Madre"


def test_si_la_copia_arranca_el_mismo_anio_el_nombre_no_cambia():
    """"Si el corrimiento cambia de año": copiar Ciberlunes 2025 una semana
    más adelante sigue siendo 2025."""
    assert nombre_para_la_copia("Ciberlunes 2025", date(2025, 12, 1), date(2025, 12, 2), date(2025, 12, 8)) \
        == "Ciberlunes 2025"


def test_una_accion_que_cruza_de_anio_corre_los_dos():
    assert nombre_para_la_copia(
        "Fin de año 2025-2026", date(2025, 12, 26), date(2026, 1, 2), date(2026, 12, 25),
    ) == "Fin de año 2026-2027"


def test_un_anio_que_no_es_el_de_la_accion_no_se_toca():
    """El "Mundial 2030" de una acción de 2025 no es el año de la acción."""
    assert nombre_para_la_copia(
        "Previa Mundial 2030 · 2025", date(2025, 6, 1), date(2025, 6, 7), date(2026, 5, 31),
    ) == "Previa Mundial 2030 · 2026"


def test_cuatro_digitos_dentro_de_un_numero_mas_largo_no_son_un_anio():
    assert nombre_para_la_copia("Cupón 20250 y SKU 120251", date(2025, 3, 1), date(2025, 3, 2), date(2026, 2, 28)) \
        == "Cupón 20250 y SKU 120251"


def test_copiar_para_atras_tambien_corre_el_anio():
    assert nombre_para_la_copia("Hot Sale 2026", date(2026, 5, 11), date(2026, 5, 13), date(2025, 5, 12)) \
        == "Hot Sale 2025"


# --- La acción ---------------------------------------------------------------

def _accion(**kw) -> CalendarioBarra:
    base = dict(
        id="br-2025", mundo="tienda_express", seccion="comercial", banda="MEGA EVENTO", carril=2,
        nombre="Ciberlunes 2025", color="#fcd34d", desde=date(2025, 12, 1), hasta=date(2025, 12, 2),
        formato=None, hora=None, estado=None, creado_por_id=7, actualizado_por_id=8,
        created_at=AHORA, updated_at=AHORA,
    )
    base.update(kw)
    return CalendarioBarra(**base)


def test_la_accion_se_copia_entera_en_el_mismo_mundo():
    v = copiar_la_accion(_accion(), "br-2026", UN_ANIO, "Ciberlunes 2026", 0, 42)
    assert v == {
        "id": "br-2026", "mundo": "tienda_express", "seccion": "comercial", "banda": "MEGA EVENTO",
        "carril": 0, "nombre": "Ciberlunes 2026", "color": "#fcd34d",
        # Dura lo mismo: dos días, corridos 52 semanas.
        "desde": date(2026, 11, 30), "hasta": date(2026, 12, 1),
        "formato": None, "hora": None, "estado": None,
        # La firma es de quien copia; los timestamps los pone la base.
        "creado_por_id": 42, "actualizado_por_id": 42,
    }


def test_un_envio_suelto_lleva_su_formato_y_hora_y_vuelve_a_pendiente():
    envio = _accion(
        seccion="envio", banda="email", desde=date(2025, 5, 2), hasta=date(2025, 5, 2),
        formato="Mailing digital", hora="09:30", estado="publicado",
    )
    v = copiar_la_accion(envio, "br-n", UN_ANIO, "Mailing", 0, 1)
    assert (v["formato"], v["hora"], v["estado"]) == ("Mailing digital", "09:30", "pendiente")
    assert v["desde"] == v["hasta"] == date(2026, 5, 1)


# --- Las piezas --------------------------------------------------------------

def _pieza(**kw) -> CalendarioPieza:
    base = dict(
        id="pz-viejo", barra_id="br-2025", area="email", formato="Mailing digital", estado="publicado",
        desde=date(2025, 11, 28), hasta=date(2025, 11, 28), hora="10:00", en_sharepoint=True, orden=3,
        created_at=AHORA, updated_at=AHORA,
    )
    base.update(kw)
    return CalendarioPieza(**base)


def test_una_pieza_vuelve_a_pendiente_fuera_de_sharepoint_y_con_su_fecha_corrida():
    [v] = copiar_piezas([_pieza()], "br-2026", UN_ANIO, _ids())
    assert v == {
        "id": "pz-nuevo-1", "barra_id": "br-2026", "area": "email", "formato": "Mailing digital",
        "estado": "pendiente", "en_sharepoint": False,
        "desde": date(2026, 11, 27), "hasta": date(2026, 11, 27), "hora": "10:00", "orden": 3,
    }


def test_una_pieza_sin_fecha_propia_sigue_con_la_accion():
    [v] = copiar_piezas([_pieza(desde=None, hasta=None, hora=None)], "br-2026", UN_ANIO, _ids())
    assert v["desde"] is None and v["hasta"] is None and v["hora"] is None


def test_cada_pieza_tiene_un_id_nuevo():
    filas = copiar_piezas([_pieza(id="a"), _pieza(id="b", formato="Recordatorio")], "br-2026", UN_ANIO)
    assert len({f["id"] for f in filas}) == 2
    assert not {f["id"] for f in filas} & {"a", "b"}


# --- Las tareas --------------------------------------------------------------

def _tarea(id, parent_id=None, **kw) -> CalendarioTarea:
    base = dict(
        id=id, barra_id="br-2025", parent_id=parent_id, titulo=f"Tarea {id}", descripcion="Detalle",
        estado="hecha", asignado_a_id=None, vence=None, orden=0, creado_por_id=7, para="tienda",
        created_at=AHORA, updated_at=AHORA,
    )
    base.update(kw)
    return CalendarioTarea(**base)


def test_tareas_y_subtareas_mantienen_su_estructura_con_ids_nuevos():
    # Llegan desordenadas: la sub-subtarea antes que su madre y su abuela.
    tareas = [
        _tarea("nieta", parent_id="hija", orden=2),
        _tarea("abuela", orden=0),
        _tarea("hija", parent_id="abuela", orden=1),
        _tarea("suelta", orden=3),
    ]
    filas = copiar_tareas(tareas, "br-2026", UN_ANIO, set(), 42, _ids()).filas
    por_titulo = {f["titulo"]: f for f in filas}
    abuela, hija, nieta = (por_titulo[f"Tarea {x}"] for x in ("abuela", "hija", "nieta"))
    assert abuela["parent_id"] is None
    assert hija["parent_id"] == abuela["id"]
    assert nieta["parent_id"] == hija["id"]
    assert por_titulo["Tarea suelta"]["parent_id"] is None
    # Ninguna apunta a una tarea de la acción original.
    assert not {f["id"] for f in filas} & {"abuela", "hija", "nieta", "suelta"}
    # Cada madre se guarda antes que sus hijas.
    orden = [f["id"] for f in filas]
    assert orden.index(abuela["id"]) < orden.index(hija["id"]) < orden.index(nieta["id"])


def test_una_tarea_vuelve_a_pendiente_y_su_vencimiento_se_corre():
    [v] = copiar_tareas(
        [_tarea("t", vence=date(2025, 11, 25), asignado_a_id=5, orden=4)],
        "br-2026", UN_ANIO, {5}, 42, _ids(),
    ).filas
    assert v == {
        "id": "ta-nuevo-1", "barra_id": "br-2026", "parent_id": None, "titulo": "Tarea t",
        "descripcion": "Detalle", "estado": "pendiente", "asignado_a_id": 5,
        "vence": date(2026, 11, 24), "orden": 4,
        # Las carga quien copia: a esa persona le avisa quien termine una.
        "creado_por_id": 42,
        # Una tarea cargada a mano no viene de ninguna plantilla (0065).
        "ancla": None, "ancla_dias": None, "plantilla_id": None,
        # Quién la hace y qué tipo de pieza es (0070) se copian tal cual: la
        # copia de una tarea para la agencia sigue siendo para la agencia (y
        # al guardarla le nace su tarjeta nueva, ver copiar_barra).
        "para": "tienda", "agencia": None, "tipo": None, "opciones": None, "detalles": None,
    }


def test_una_tarea_de_plantilla_sigue_anclada_en_la_copia():
    """Las columnas de las plantillas (0065) se copian solas: la tarea de la
    copia se sigue moviendo con su acción nueva."""
    [v] = copiar_tareas(
        [_tarea("t", vence=date(2025, 10, 31), ancla="inicio", ancla_dias=-30, plantilla_id="pl-mega")],
        "br-2026", UN_ANIO, set(), 42, _ids(),
    ).filas
    assert (v["ancla"], v["ancla_dias"], v["plantilla_id"]) == ("inicio", -30, "pl-mega")
    assert v["vence"] == date(2026, 10, 30)


def test_el_responsable_que_ya_no_entra_al_mundo_se_saca():
    copia = copiar_tareas(
        [_tarea("a", asignado_a_id=5), _tarea("b", asignado_a_id=9), _tarea("c")],
        "br-2026", UN_ANIO, responsables_validos={5}, creado_por=42,
    )
    assert [f["asignado_a_id"] for f in copia.filas] == [5, None, None]
    # Solo cuenta la que TENÍA responsable y lo perdió, no la que no tenía.
    assert copia.sin_responsable == 1


def test_una_tarea_de_tienda_no_se_copia_a_nombre_de_alguien_de_una_agencia():
    """19/11/2026: quien llevaba la tarea pasó a ser de una agencia (8, de
    Diseñadores, una agencia externa). La copia de una tarea de Tienda o de
    una agencia de afuera sale sin responsable; la pieza de su agencia sigue
    a su nombre, y alguien de Tienda (5) también."""
    copia = copiar_tareas(
        [_tarea("tienda", asignado_a_id=8, orden=0),
         _tarea("pieza", asignado_a_id=8, tipo="banners", orden=1),
         _tarea("fuera", asignado_a_id=8, para="fuera", agencia="Estudio Afuera", tipo="mailing", orden=2),
         _tarea("agencia", asignado_a_id=8, para="agencia", agencia="Diseñadores", tipo="push", orden=3),
         _tarea("equipo", asignado_a_id=5, orden=4)],
        "br-2026", UN_ANIO, responsables_validos={5, 8}, creado_por=42, de_agencias={8},
    )
    assert [f["asignado_a_id"] for f in copia.filas] == [None, None, None, 8, 5]
    assert [f["para"] for f in copia.filas] == ["tienda", "tienda", "fuera", "agencia", "tienda"]
    assert copia.sin_responsable == 3


def test_una_tarea_que_cuelga_de_otra_accion_queda_suelta():
    [v] = copiar_tareas([_tarea("a", parent_id="de-otra-accion")], "br-2026", UN_ANIO, set(), 1).filas
    assert v["parent_id"] is None


def test_un_ciclo_no_cuelga_el_orden():
    tareas = [_tarea("a", parent_id="b"), _tarea("b", parent_id="a")]
    assert len(en_orden_de_alta(tareas)) == 2


# --- La copia es genérica: lo que se agregue al modelo se copia solo ---------

def _columnas(modelo) -> set[str]:
    return {a.key for a in inspect(modelo).column_attrs}


def test_la_tarea_copiada_lleva_todas_las_columnas_del_modelo_menos_los_timestamps():
    [v] = copiar_tareas([_tarea("t")], "br-2026", UN_ANIO, set(), 1).filas
    assert set(v) == _columnas(CalendarioTarea) - {"created_at", "updated_at"}


def test_la_pieza_copiada_tambien():
    [v] = copiar_piezas([_pieza()], "br-2026", UN_ANIO)
    assert set(v) == _columnas(CalendarioPieza) - {"created_at", "updated_at"}


class _OtraBase(DeclarativeBase):
    pass


class _TareaConAncla(_OtraBase):
    """Una tarea como quedaría con columnas nuevas (el "ancla" de vencimiento
    relativo que se está agregando en paralelo): no está en el modelo de hoy,
    y la copia la tiene que llevar igual."""
    __tablename__ = "tarea_con_ancla"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    barra_id: Mapped[str] = mapped_column(String)
    parent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    titulo: Mapped[str] = mapped_column(String)
    estado: Mapped[str] = mapped_column(String)
    asignado_a_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creado_por_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    orden: Mapped[int] = mapped_column(Integer)
    vence: Mapped[date | None] = mapped_column(Date, nullable=True)
    ancla: Mapped[str | None] = mapped_column(String, nullable=True)
    ancla_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    otra_fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
    tocada_el: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def test_una_columna_nueva_se_copia_sola():
    t = _TareaConAncla(
        id="t", barra_id="b", parent_id=None, titulo="Bajar la landing", estado="hecha",
        asignado_a_id=None, creado_por_id=3, orden=0, vence=date(2025, 11, 20),
        ancla="inicio", ancla_dias=-5, otra_fecha=date(2025, 1, 10), tocada_el=AHORA,
    )
    [v] = copiar_tareas([t], "br-2026", UN_ANIO, set(), 42).filas
    assert (v["ancla"], v["ancla_dias"]) == ("inicio", -5)
    # Una fecha nueva se corre como las demás; un momento (timestamp) no viaja.
    assert v["otra_fecha"] == date(2026, 1, 9)
    assert "tocada_el" not in v
    assert v["estado"] == "pendiente"


def test_una_lista_json_no_queda_compartida_con_la_original():
    aviso = CalendarioAviso(id="a", barra_id="b", dias_antes=3, destinatarios=[1, 2], creado_por_id=1)
    v = valores_copiados(aviso, UN_ANIO, {"id": "n"})
    v["destinatarios"].append(99)
    assert aviso.destinatarios == [1, 2]


def test_las_fechas_corridas_de_una_fila():
    [v] = copiar_piezas([_pieza()], "br", UN_ANIO)
    assert fechas_corridas(v, CalendarioPieza) == [date(2026, 11, 27), date(2026, 11, 27)]


# --- Los avisos --------------------------------------------------------------

def _aviso(id="av", dias=10, destinatarios=(1, 2), **kw) -> CalendarioAviso:
    return CalendarioAviso(
        id=id, barra_id="br-2025", dias_antes=dias, destinatarios=list(destinatarios),
        creado_por_id=7, created_at=AHORA, **kw,
    )


def test_un_aviso_se_copia_con_los_mismos_dias_antes():
    [v] = copiar_avisos([_aviso(dias=15)], "br-2026", UN_ANIO, {1, 2}, 42, _ids()).filas
    # `control` (0077) va vacío: Lanzar y Cierre no se copian, la copia trae los suyos.
    assert v == {
        "id": "av-nuevo-1", "barra_id": "br-2026", "dias_antes": 15, "destinatarios": [1, 2], "creado_por_id": 42,
        "control": None,
    }


def test_quien_ya_no_ve_el_mundo_sale_del_aviso():
    copia = copiar_avisos([_aviso(destinatarios=(1, 2, 3))], "br-2026", UN_ANIO, {1, 3}, 42)
    assert copia.filas[0]["destinatarios"] == [1, 3]
    assert copia.destinatarios_quitados == 1


def test_un_aviso_que_se_queda_sin_nadie_no_se_copia():
    copia = copiar_avisos(
        [_aviso("a", destinatarios=(9,)), _aviso("b", destinatarios=(1,))], "br-2026", UN_ANIO, {1}, 42,
    )
    assert [f["destinatarios"] for f in copia.filas] == [[1]]
    assert (copia.sin_nadie, copia.destinatarios_quitados) == (1, 1)


def test_los_destinatarios_se_leen_con_cuidado():
    assert ids_de_personas([3, "4", 3, None, "x", 5.0]) == [3, 4, 5]


# --- El aviso a cada responsable --------------------------------------------

def test_un_aviso_por_responsable_y_ninguno_a_quien_copia():
    filas = [
        {"id": "1", "asignado_a_id": 5}, {"id": "2", "asignado_a_id": 6}, {"id": "3", "asignado_a_id": 5},
        {"id": "4", "asignado_a_id": None}, {"id": "5", "asignado_a_id": 42},
    ]
    grupos = tareas_por_responsable(filas, quien_copia=42)
    assert {uid: [f["id"] for f in suyas] for uid, suyas in grupos.items()} == {5: ["1", "3"], 6: ["2"]}


def test_con_una_sola_tarea_es_el_aviso_de_siempre():
    assert mensaje_de_tareas_copiadas("Ana", ["Header"], "Ciberlunes 2026", date(2026, 11, 20)) \
        == mensaje_de_asignacion("Ana", "Header", "Ciberlunes 2026", date(2026, 11, 20))


def test_con_varias_dice_cuantas_cuales_y_la_primera_que_vence():
    assert mensaje_de_tareas_copiadas("Ana", ["Header", "Mailing", "Landing"], "Ciberlunes 2026", date(2026, 11, 20)) \
        == "Ana te asignó 3 tareas en Ciberlunes 2026: Header, Mailing y Landing. La primera vence el 20/11."


def test_con_muchas_nombra_tres_y_cuenta_el_resto():
    assert mensaje_de_tareas_copiadas("Ana", ["a", "b", "c", "d", "e"], "X", None) \
        == "Ana te asignó 5 tareas en X: a, b, c y 2 más."


# --- Lo que viaja ------------------------------------------------------------

def test_el_pedido_de_copia():
    p = CopiaDeBarra(id="br-abc_1", desde="2026-11-30", nombre="  Ciberlunes 2026 ")
    assert (p.desde, p.nombre, p.carril) == (date(2026, 11, 30), "Ciberlunes 2026", None)


@pytest.mark.parametrize("malo", [
    {"id": "con espacio", "desde": "2026-11-30"},
    {"id": "br-1", "desde": "0202-11-30"},
    {"id": "br-1", "desde": "2026-11-30", "nombre": "   "},
    {"id": "br-1", "desde": "2026-11-30", "carril": -1},
])
def test_un_pedido_de_copia_mal_armado_no_entra(malo):
    with pytest.raises(ValidationError):
        CopiaDeBarra(**malo)

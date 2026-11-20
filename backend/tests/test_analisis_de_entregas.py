"""El análisis de entregas (ex «Retrabajo»), sin base.

Pedido de Ivan (20/11/2026): "el retrabajo sí sirve, pero sería más un
análisis", y sumarle "cuánto tarda cada agencia y cuántas piezas se pasan de
fecha". Las rondas siguen en test_entregas_por_fases.py; lo de la base (qué
ve la agencia y qué el equipo) en test_tablero_agencia_api.py.
"""
from datetime import date, datetime, timezone

from app.services import entregas as reglas
from app.services.entregas import PiezaDelAnalisis

HOY = date(2026, 11, 16)
DESDE = datetime(2026, 10, 18, tzinfo=timezone.utc)


def _utc(m, d, h=13):
    return datetime(2026, m, d, h, tzinfo=timezone.utc)


def pieza(tid, para="agencia", agencia="Publicis", pedida=None, primera=None, aprobada=None, vence=None, le_toca=False):
    return PiezaDelAnalisis(
        tarea_id=tid, para=para, agencia=agencia, pedida_at=pedida or _utc(11, 1),
        primera_entrega_at=primera, aprobada_at=aprobada, vence=vence, le_toca_a_quien_la_hace=le_toca,
    )


def test_quien_la_hace():
    # Un tablero se escribe como en app/core/tableros.py, se haya guardado como se haya guardado.
    assert reglas.quien_la_hace("agencia", "  disenadores ") == ("agencia:disenadores", "Diseñadores")
    assert reglas.quien_la_hace("fuera", "Agencia  Océano") == ("agencia:agencia oceano", "Agencia Océano")
    # La agencia de afuera y la de la plataforma con el mismo nombre son la misma.
    assert reglas.quien_la_hace("fuera", "PUBLICIS")[0] == reglas.quien_la_hace("agencia", "Publicis")[0]
    assert reglas.quien_la_hace("tienda", "Publicis") == (reglas.EQUIPO_PROPIO, reglas.NOMBRE_DEL_EQUIPO_PROPIO)
    assert reglas.quien_la_hace("agencia", "   ")[0] == reglas.EQUIPO_PROPIO


def test_cuanto_tarda_cada_agencia_y_cuantas_se_pasan_de_fecha():
    piezas = [
        # Publicis: a tiempo (3 días, aprobada a los 5).
        pieza("p1", primera=_utc(11, 4), aprobada=_utc(11, 6), vence=date(2026, 11, 5)),
        # Publicis: entregó tarde (7 días, vencía el 5); ahora espera al equipo.
        pieza("p2", primera=_utc(11, 8), vence=date(2026, 11, 5)),
        # Publicis: sin entregar y vencida hoy.
        pieza("p3", vence=date(2026, 11, 10), le_toca=True),
        # Publicis: entregó tarde Y hoy está vencida con cambios: cuenta UNA vez.
        pieza("p8", primera=_utc(11, 9), vence=date(2026, 11, 6), le_toca=True),
        # Publicis: de antes del período. No cuenta.
        pieza("p7", pedida=_utc(9, 20), primera=_utc(10, 1), aprobada=_utc(10, 2), vence=date(2026, 10, 3)),
        # Diseñadores (guardado sin ñ): un día, sin fecha.
        pieza("p4", agencia="disenadores", pedida=_utc(11, 2), primera=_utc(11, 3)),
        # Una agencia de afuera y el equipo.
        pieza("p5", para="fuera", agencia="Agencia Océano", primera=_utc(11, 2)),
        pieza("p6", para="tienda", agencia=None, pedida=_utc(11, 10), primera=_utc(11, 12)),
        # Una pieza que espera a quien aprueba, vencida: no es de la agencia.
        pieza("p9", agencia="Another Monday", vence=date(2026, 11, 1)),
    ]
    a = reglas.analisis_por_agencia(piezas, DESDE, HOY)
    # Primero los tres tableros (en su orden), después las demás y el equipo al final.
    # Another Monday no tiene nada en el período: no aparece.
    assert [g["nombre"] for g in a["porAgencia"]] == [
        "Publicis", "Diseñadores", "Agencia Océano", reglas.NOMBRE_DEL_EQUIPO_PROPIO,
    ]
    publicis = a["porAgencia"][0]
    assert publicis == {
        "clave": "agencia:publicis", "nombre": "Publicis",
        "entregadas": 3, "diasHastaEntregar": 6.0,   # (3 + 7 + 8) / 3
        "aprobadas": 1, "diasHastaAprobar": 5.0,
        "aTiempo": 33,                                # 1 de 3 con fecha
        "entregaronTarde": 2, "vencidas": 2, "sePasaron": 3,
    }
    disenadores = a["porAgencia"][1]
    assert disenadores["diasHastaEntregar"] == 1.0 and disenadores["aTiempo"] is None and disenadores["sePasaron"] == 0
    total = a["total"]
    assert total["entregadas"] == 6 and total["aprobadas"] == 1 and total["sePasaron"] == 3
    assert total["vencidas"] == 2 and total["entregaronTarde"] == 2


def test_la_fecha_es_la_de_uruguay():
    # El 6/11 a la 01:00 UTC en Uruguay todavía es el 5: llegó a tiempo.
    a_tiempo = pieza("p1", primera=datetime(2026, 11, 6, 1, tzinfo=timezone.utc), vence=date(2026, 11, 5))
    assert reglas.analisis_por_agencia([a_tiempo], DESDE, HOY)["total"]["entregaronTarde"] == 0
    tarde = pieza("p2", primera=datetime(2026, 11, 6, 4, tzinfo=timezone.utc), vence=date(2026, 11, 5))
    assert reglas.analisis_por_agencia([tarde], DESDE, HOY)["total"]["entregaronTarde"] == 1
    # Vence hoy: todavía no se pasó.
    hoy = pieza("p3", vence=HOY, le_toca=True)
    assert reglas.analisis_por_agencia([hoy], DESDE, HOY)["total"]["vencidas"] == 0


def test_sin_piezas_no_hay_promedios():
    a = reglas.analisis_por_agencia([], DESDE, HOY)
    assert a["porAgencia"] == []
    assert a["total"] == {
        "entregadas": 0, "diasHastaEntregar": None, "aprobadas": 0, "diasHastaAprobar": None,
        "aTiempo": None, "entregaronTarde": 0, "vencidas": 0, "sePasaron": 0,
    }

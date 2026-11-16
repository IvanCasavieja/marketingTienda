"""El calendario para Outlook/Google/iPhone: el .ics y la firma del link."""
from datetime import date, datetime, timezone

from app.api.routes.calendario_ical import armar_ics, escapar, firma_del_link, plegar


def test_la_firma_cambia_con_la_persona_y_con_otro_link():
    a = firma_del_link(7, 0)
    assert a == firma_del_link(7, 0)  # el mismo link sigue andando
    assert a != firma_del_link(8, 0)  # el de otra persona no sirve
    assert a != firma_del_link(7, 1)  # "Generar otro link" invalida el anterior
    assert len(a) == 40


def test_escapar_lo_que_rompe_un_ics():
    entrada = "Promo 2x1; carne, pollo" + "\\" + "pescado" + "\n" + "fin"
    esperado = "Promo 2x1" + "\\;" + " carne" + "\\," + " pollo" + "\\\\" + "pescado" + "\\n" + "fin"
    assert escapar(entrada) == esperado


def test_las_lineas_largas_se_pliegan_sin_cortar_una_tilde():
    linea = "SUMMARY:" + "Ñandú " * 30
    plegada = plegar(linea)
    for parte in plegada.split("\r\n"):
        assert len(parte.encode("utf-8")) <= 75
    assert plegada.replace("\r\n ", "") == linea  # se vuelve a armar igual


def test_un_evento_de_todo_el_dia_termina_al_dia_siguiente():
    ics = armar_ics("Core Tienda", [{
        "uid": "accion-x@coretienda", "inicio": date(2026, 11, 28), "fin": date(2026, 11, 30),
        "titulo": "Ciberlunes", "descripcion": "Categoría: MEGA EVENTO.", "url": "https://x/calendario?accion=x",
    }], datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc))
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert "DTSTART;VALUE=DATE:20261128\r\n" in ics
    assert "DTEND;VALUE=DATE:20261201\r\n" in ics  # fin exclusivo
    assert "SUMMARY:Ciberlunes\r\n" in ics
    assert "DTSTAMP:20261115T120000Z" in ics

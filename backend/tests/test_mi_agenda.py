"""Mi agenda (app/services/agenda_externa.py): leer el link y el calendario.

Puras: sin red ni base. Lo de quién la ve está en test_tablero_agencia_api.py.
"""
import asyncio
from datetime import date

import pytest

from app.services import agenda_externa as ae
from app.services.agenda_externa import AgendaInvalida

HOY = date(2026, 11, 17)

# Como lo publica Google: zona IANA, una reunión semanal, un evento de varios
# días, uno cancelado, uno viejo (fuera de la ventana) y una excepción.
GOOGLE = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Google Inc//Google Calendar 70.9054//EN
X-WR-TIMEZONE:America/Montevideo
BEGIN:VEVENT
UID:daily-1@google.com
DTSTART;TZID=America/Montevideo:20261102T100000
DTEND;TZID=America/Montevideo:20261102T101500
RRULE:FREQ=WEEKLY;BYDAY=MO;COUNT=6
SUMMARY:Daily de marketing
LOCATION:Sala 3
END:VEVENT
BEGIN:VEVENT
UID:daily-1@google.com
RECURRENCE-ID;TZID=America/Montevideo:20261116T100000
DTSTART;TZID=America/Montevideo:20261116T110000
DTEND;TZID=America/Montevideo:20261116T111500
SUMMARY:Daily de marketing (movida)
END:VEVENT
BEGIN:VEVENT
UID:feria@google.com
DTSTART;VALUE=DATE:20261125
DTEND;VALUE=DATE:20261128
SUMMARY:Feria del libro
END:VEVENT
BEGIN:VEVENT
UID:cancelada@google.com
DTSTART:20261120T150000Z
DTEND:20261120T160000Z
STATUS:CANCELLED
SUMMARY:Reunion cancelada
END:VEVENT
BEGIN:VEVENT
UID:vieja@google.com
DTSTART:20250101T150000Z
DTEND:20250101T160000Z
SUMMARY:Reunion de hace mucho
END:VEVENT
END:VCALENDAR
"""

# Como lo publica Outlook: zona con nombre de Windows y su VTIMEZONE.
OUTLOOK = b"""BEGIN:VCALENDAR
METHOD:PUBLISH
PRODID:Microsoft Exchange Server 2010
VERSION:2.0
X-WR-CALNAME:Calendario
BEGIN:VTIMEZONE
TZID:Montevideo Standard Time
BEGIN:STANDARD
DTSTART:16010101T000000
TZOFFSETFROM:-0300
TZOFFSETTO:-0300
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:040000008200E00074C5B7101A82E008
SUMMARY:Comite de precios
DTSTART;TZID=Montevideo Standard Time:20261118T143000
DTEND;TZID=Montevideo Standard Time:20261118T153000
LOCATION:Teams
END:VEVENT
END:VCALENDAR
"""


def test_el_link_se_normaliza_y_solo_https():
    assert ae.normalizar_url("  https://calendar.google.com/x/basic.ics ") == "https://calendar.google.com/x/basic.ics"
    assert ae.normalizar_url("webcal://outlook.office365.com/owa/calendar/a/b/calendar.ics") == (
        "https://outlook.office365.com/owa/calendar/a/b/calendar.ics"
    )
    for malo in ("", "   ", None, "http://calendar.google.com/x.ics", "ftp://x/y.ics", "file:///etc/passwd",
                 "calendar.google.com/x.ics", "https://", "https://" + "a" * 2100):
        with pytest.raises(AgendaInvalida):
            ae.normalizar_url(malo)


def test_solo_direcciones_de_internet():
    assert ae.ip_publica("142.250.79.46")
    assert ae.ip_publica("2607:f8b0:4004:c07::64")
    for interna in ("127.0.0.1", "10.0.0.5", "192.168.1.10", "172.16.3.4", "169.254.169.254", "0.0.0.0",
                    "::1", "fc00::1", "fe80::1", "100.64.0.1", "224.0.0.1", "no-es-ip"):
        assert not ae.ip_publica(interna), interna


def test_no_va_a_un_servidor_interno(monkeypatch):
    async def resolver(host, puerto, type=None):  # noqa: A002 - igual que getaddrinfo
        return [(None, None, None, "", ("10.1.2.3", puerto))]

    async def prueba():
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(loop, "getaddrinfo", resolver)
        with pytest.raises(AgendaInvalida):
            await ae.exigir_host_publico("https://intranet.ejemplo/calendario.ics")
        with pytest.raises(AgendaInvalida):
            await ae.bajar("https://intranet.ejemplo/calendario.ics")

    asyncio.run(prueba())


def test_lee_google_con_repeticiones_excepciones_y_sin_cancelados():
    eventos = ae.leer_eventos(GOOGLE, HOY)
    titulos = [e["titulo"] for e in eventos]
    assert "Reunion cancelada" not in titulos
    assert "Reunion de hace mucho" not in titulos  # fuera de la ventana
    dailies = [e for e in eventos if e["uid"] == "daily-1@google.com"]
    assert len(dailies) == 6
    # 10:00 en Montevideo (UTC-3) son las 13:00 UTC.
    assert dailies[0] == {
        "uid": "daily-1@google.com", "titulo": "Daily de marketing", "inicio": "2026-11-02T13:00:00Z",
        "fin": "2026-11-02T13:15:00Z", "todoElDia": False, "lugar": "Sala 3",
    }
    movida = next(e for e in dailies if e["inicio"].startswith("2026-11-16"))
    assert movida["titulo"] == "Daily de marketing (movida)" and movida["inicio"] == "2026-11-16T14:00:00Z"
    feria = next(e for e in eventos if e["titulo"] == "Feria del libro")
    # Todo el día: fechas, con el fin sin incluir (como en el ICS).
    assert feria["todoElDia"] and feria["inicio"] == "2026-11-25" and feria["fin"] == "2026-11-28"
    assert [e["inicio"] for e in eventos] == sorted(e["inicio"] for e in eventos)


def test_lee_outlook_con_zona_de_windows():
    (evento,) = ae.leer_eventos(OUTLOOK, HOY)
    assert evento["titulo"] == "Comite de precios" and evento["lugar"] == "Teams"
    assert evento["inicio"] == "2026-11-18T17:30:00Z" and evento["fin"] == "2026-11-18T18:30:00Z"


def test_hora_sin_zona_es_de_uruguay_y_sin_fin_dura_cero():
    datos = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:flotante
DTSTART:20261119T090000
SUMMARY:  Llamar   al   proveedor
END:VEVENT
BEGIN:VEVENT
UID:con-duracion
DTSTART:20261119T120000Z
DURATION:PT45M
END:VEVENT
END:VCALENDAR
"""
    eventos = {e["uid"]: e for e in ae.leer_eventos(datos, HOY)}
    flotante, con_duracion = eventos["flotante"], eventos["con-duracion"]
    assert flotante["inicio"] == flotante["fin"] == "2026-11-19T12:00:00Z"
    assert flotante["titulo"] == "Llamar al proveedor"  # sin espacios de más
    assert con_duracion["titulo"] == "(sin título)" and con_duracion["fin"] == "2026-11-19T12:45:00Z"


def test_lo_que_no_es_un_calendario_se_avisa():
    for malo in (b"<html><body>Iniciar sesion</body></html>", b"", b"BEGIN:VEVENT\nEND:VEVENT\n"):
        with pytest.raises(AgendaInvalida):
            ae.leer_eventos(malo, HOY)


def test_tope_de_eventos(monkeypatch):
    monkeypatch.setattr(ae, "MAX_EVENTOS", 3)
    assert len(ae.leer_eventos(GOOGLE, HOY)) == 3

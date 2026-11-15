"""El mail de recuperar la contraseña (15/11/2026).

Se fija: qué dice el mail (marca Core Tienda, el link, cuánto vale), que un
nombre con HTML no rompe el mail, con qué se manda según lo configurado, y que
por SMTP sale con TLS, con login y con las dos versiones (texto y HTML).
"""
import asyncio

import pytest

from app.core.config import settings
from app.services import email_service
from app.services.email_service import (
    ASUNTO_RECUPERACION, armar_mensaje, build_reset_email, email_configurado, proveedor, send_email,
)

LINK = "https://core.example/reset-password?token=abc_123-XYZ"


# --- Qué dice -----------------------------------------------------------------

def test_el_mail_es_de_core_tienda_y_trae_el_link():
    html, texto = build_reset_email(LINK, "Ivan Casavieja")
    for parte in (html, texto):
        assert "Core Tienda" in parte
        assert LINK in parte
        assert "MKTG" not in parte
    assert html.count(f'href="{LINK}"') == 2  # el botón y el link de respaldo
    assert "Recuperá tu contraseña de Core Tienda" == ASUNTO_RECUPERACION


def test_saluda_por_el_primer_nombre():
    html, texto = build_reset_email(LINK, "Ivan Casavieja")
    assert "Hola, Ivan" in html and "Hola, Ivan:" in texto
    assert "Casavieja" not in texto


def test_sin_nombre_saluda_igual():
    html, texto = build_reset_email(LINK, None)
    assert "Hola" in html and texto.startswith("Hola:")
    html, _ = build_reset_email(LINK, "   ")
    assert "Hola, " not in html


def test_dice_cuanto_vale_el_link():
    html, texto = build_reset_email(LINK, "Ana", minutos=60)
    assert "1 hora" in html and "1 hora" in texto
    _, texto = build_reset_email(LINK, "Ana", minutos=30)
    assert "30 minutos" in texto


def test_un_nombre_con_html_no_se_mete_en_el_mail():
    html, _ = build_reset_email(LINK, '<script>alert(1)</script> "x"')
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# --- Con qué se manda --------------------------------------------------------------

@pytest.fixture
def config(monkeypatch):
    """Arranca sin nada configurado; cada test pone lo suyo."""
    for clave, valor in {
        "EMAIL_PROVIDER": "", "SMTP_HOST": "", "SMTP_PORT": 587, "SMTP_USER": "",
        "SMTP_PASSWORD": "", "SMTP_SEGURIDAD": "starttls", "SENDGRID_API_KEY": "",
        "EMAIL_FROM": "Core Tienda <DoNotReply@ejemplo.uy>",
        "RESEND_API_KEY": "",
    }.items():
        monkeypatch.setattr(settings, clave, valor)
    return monkeypatch


def test_sin_nada_configurado_no_hay_mails(config):
    assert proveedor() is None and not email_configurado()


def test_con_smtp_va_por_smtp(config):
    config.setattr(settings, "SMTP_HOST", "smtp.azurecomm.net")
    assert proveedor() == "smtp"


def test_con_sendgrid_solo_va_por_sendgrid(config):
    config.setattr(settings, "SENDGRID_API_KEY", "SG.x")
    assert proveedor() == "sendgrid"


def test_con_los_dos_gana_smtp_salvo_que_se_pida_sendgrid(config):
    config.setattr(settings, "SMTP_HOST", "smtp.azurecomm.net")
    config.setattr(settings, "SENDGRID_API_KEY", "SG.x")
    assert proveedor() == "smtp"
    config.setattr(settings, "EMAIL_PROVIDER", "SendGrid")
    assert proveedor() == "sendgrid"


def test_pedir_uno_sin_sus_datos_es_no_tener_mails(config):
    config.setattr(settings, "SENDGRID_API_KEY", "SG.x")
    config.setattr(settings, "EMAIL_PROVIDER", "smtp")
    assert proveedor() is None
    config.setattr(settings, "EMAIL_PROVIDER", "cualquiera")
    assert proveedor() is None


# --- Por SMTP --------------------------------------------------------------------

class _SmtpFalso:
    """Hace de servidor SMTP: anota lo que se le pide."""
    ultimo: "_SmtpFalso | None" = None

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.pasos, self.mensaje = host, port, [], None
        _SmtpFalso.ultimo = self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.pasos.append("quit")

    def starttls(self, context=None):
        self.pasos.append("starttls")

    def login(self, usuario, clave):
        self.pasos.append(("login", usuario, clave))

    def send_message(self, msg):
        self.pasos.append("send")
        self.mensaje = msg


def test_por_smtp_sale_con_tls_login_y_las_dos_versiones(config):
    config.setattr(settings, "SMTP_HOST", "smtp.azurecomm.net")
    config.setattr(settings, "SMTP_USER", "recurso.app.tenant")
    config.setattr(settings, "SMTP_PASSWORD", "secreto")
    config.setattr(email_service.smtplib, "SMTP", _SmtpFalso)
    html, texto = build_reset_email(LINK, "Ana")

    asyncio.run(send_email("ana@ejemplo.uy", ASUNTO_RECUPERACION, html, texto))

    s = _SmtpFalso.ultimo
    assert (s.host, s.port) == ("smtp.azurecomm.net", 587)
    assert s.pasos == ["starttls", ("login", "recurso.app.tenant", "secreto"), "send", "quit"]
    assert s.mensaje["To"] == "ana@ejemplo.uy"
    assert s.mensaje["From"] == "Core Tienda <DoNotReply@ejemplo.uy>"
    assert s.mensaje["Subject"] == ASUNTO_RECUPERACION
    tipos = [p.get_content_type() for p in s.mensaje.iter_parts()]
    assert tipos == ["text/plain", "text/html"]


def test_sin_usuario_no_hace_login_y_sin_seguridad_no_hace_tls(config):
    config.setattr(settings, "SMTP_HOST", "127.0.0.1")
    config.setattr(settings, "SMTP_PORT", 2525)
    config.setattr(settings, "SMTP_SEGURIDAD", "ninguna")
    config.setattr(email_service.smtplib, "SMTP", _SmtpFalso)
    asyncio.run(send_email("ana@ejemplo.uy", "x", "<p>x</p>", "x"))
    assert _SmtpFalso.ultimo.pasos == ["send", "quit"]


def test_ssl_usa_la_conexion_cifrada_desde_el_principio(config):
    config.setattr(settings, "SMTP_HOST", "smtp.ejemplo.uy")
    config.setattr(settings, "SMTP_PORT", 465)
    config.setattr(settings, "SMTP_SEGURIDAD", "ssl")
    config.setattr(email_service.smtplib, "SMTP_SSL", _SmtpFalso)
    config.setattr(email_service.smtplib, "SMTP", None)  # si lo usara, explotaría
    asyncio.run(send_email("ana@ejemplo.uy", "x", "<p>x</p>", "x"))
    assert _SmtpFalso.ultimo.pasos == ["send", "quit"]


def test_sin_servicio_no_se_hace_como_que_se_mando(config):
    with pytest.raises(RuntimeError):
        asyncio.run(send_email("ana@ejemplo.uy", "x", "<p>x</p>", "x"))


def test_sin_remitente_configurado_sale_de_la_casilla_con_la_que_se_entra(config):
    """Zoho (y casi todos los SMTP) rechaza un remitente distinto de la cuenta."""
    config.setattr(settings, "EMAIL_FROM", "Core Tienda <onboarding@example.com>")
    config.setattr(settings, "SMTP_USER", "coretienda@ejemplo.uy")
    assert email_service.remitente() == "Core Tienda <coretienda@ejemplo.uy>"
    config.setattr(settings, "EMAIL_FROM", "")
    assert email_service.remitente() == "Core Tienda <coretienda@ejemplo.uy>"


def test_el_remitente_configurado_manda(config):
    config.setattr(settings, "SMTP_USER", "coretienda@ejemplo.uy")
    assert email_service.remitente() == "Core Tienda <DoNotReply@ejemplo.uy>"


def test_un_usuario_smtp_que_no_es_casilla_no_se_usa_de_remitente(config):
    """El de Azure Communication Services no es una dirección de mail."""
    config.setattr(settings, "EMAIL_FROM", "")
    config.setattr(settings, "SMTP_USER", "recurso.app.tenant")
    assert email_service.remitente() == ""


def test_el_mensaje_tiene_remitente_destino_y_asunto(config):
    msg = armar_mensaje("ana@ejemplo.uy", "Asunto", "<p>hola</p>", "hola")
    assert msg["From"] == "Core Tienda <DoNotReply@ejemplo.uy>" and msg["Subject"] == "Asunto"


# --- Por Resend (la API web que usa Tuki) -----------------------------------------
# 15/11/2026: el plan gratis de Render no deja salir SMTP (Zoho se colgaba) y la
# cuenta de SendGrid se quedó sin crédito. Resend va por HTTPS y no tiene ese problema.

def test_con_clave_de_resend_va_por_resend_aunque_haya_smtp(config):
    config.setattr(settings, "RESEND_API_KEY", "re_x")
    config.setattr(settings, "SMTP_HOST", "smtppro.zoho.com")
    config.setattr(settings, "SENDGRID_API_KEY", "SG.x")
    assert proveedor() == "resend"
    config.setattr(settings, "EMAIL_PROVIDER", "smtp")
    assert proveedor() == "smtp"
    config.setattr(settings, "EMAIL_PROVIDER", "resend")
    assert proveedor() == "resend"


def test_pedir_resend_sin_clave_es_no_tener_mails(config):
    config.setattr(settings, "EMAIL_PROVIDER", "resend")
    config.setattr(settings, "SMTP_HOST", "smtppro.zoho.com")
    assert proveedor() is None


class _ClienteFalso:
    """Hace de httpx.AsyncClient: anota el pedido y contesta lo que se le diga."""
    ultimo = None
    responde = (200, '{"id": "abc"}')

    def __init__(self, timeout=None):
        _ClienteFalso.ultimo = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        self.url, self.json, self.headers = url, json, headers
        codigo, texto = _ClienteFalso.responde
        return type("R", (), {"status_code": codigo, "text": texto})()


def test_por_resend_manda_remitente_destino_y_las_dos_versiones(config):
    config.setattr(settings, "RESEND_API_KEY", "re_clave")
    config.setattr(email_service.httpx, "AsyncClient", _ClienteFalso)
    _ClienteFalso.responde = (200, '{"id": "abc"}')
    html, texto = build_reset_email(LINK, "Ana")
    asyncio.run(send_email("ana@ejemplo.uy", ASUNTO_RECUPERACION, html, texto))
    c = _ClienteFalso.ultimo
    assert c.url == "https://api.resend.com/emails"
    assert c.headers["Authorization"] == "Bearer re_clave"
    assert c.json["from"] == "Core Tienda <DoNotReply@ejemplo.uy>"
    assert c.json["to"] == ["ana@ejemplo.uy"]
    assert c.json["subject"] == ASUNTO_RECUPERACION
    assert c.json["html"] == html and c.json["text"] == texto


def test_si_resend_rechaza_no_se_hace_como_que_salio(config):
    config.setattr(settings, "RESEND_API_KEY", "re_clave")
    config.setattr(email_service.httpx, "AsyncClient", _ClienteFalso)
    _ClienteFalso.responde = (403, '{"message": "The tenovastudio.com domain is not verified"}')
    with pytest.raises(RuntimeError, match="Resend error 403"):
        asyncio.run(send_email("ana@ejemplo.uy", "x", "<p>x</p>", "x"))

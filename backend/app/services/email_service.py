"""Los mails que manda la plataforma (hoy, el de recuperar la contraseña).

Tres formas de mandarlos, según lo que esté configurado:

- **Resend** (`RESEND_API_KEY`), por su API web (HTTPS). Es lo que usa Tuki
  y lo recomendado mientras el backend esté en el plan gratis de Render: ese
  plan no deja salir conexiones SMTP (visto el 15/11/2026: Zoho por SMTP
  respondía desde una PC y desde Render se colgaba), y una API web no tiene
  ese problema. Gratis hasta 3.000 mails por mes. El remitente tiene que ser
  de un dominio verificado en Resend.
- **SMTP** (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`,
  `SMTP_SEGURIDAD`). Sirve una casilla de Zoho Mail (la que se usa desde el
  15/11/2026) y es también como se manda desde el tenant de la empresa con
  Azure Communication Services Email. Ver docs/AZURE.md, "Mails".
- **SendGrid** (`SENDGRID_API_KEY`), lo que se usaba hasta ahora.

`EMAIL_PROVIDER` fuerza uno ("resend", "smtp" o "sendgrid"); vacío, se usa
Resend si hay clave, si no SMTP si hay `SMTP_HOST`, y si no SendGrid. Sin ninguno, no hay mails: la
pantalla de "Olvidé mi contraseña" lo dice y hay que pedirle a quien
administra que genere una contraseña nueva.
"""
from __future__ import annotations

import asyncio
import html as _html
import re
import smtplib
import ssl
from email.message import EmailMessage

import httpx

from app.core.config import settings

_FROM_EMAIL_RE = re.compile(r"<(.+?)>")

NOMBRE_DE_LA_PLATAFORMA = "Core Tienda"
ASUNTO_RECUPERACION = "Recuperá tu contraseña de Core Tienda"


def proveedor() -> str | None:
    """Con qué se mandan los mails: "resend", "smtp", "sendgrid" o None si no hay nada
    configurado (o se pidió uno que no tiene sus datos)."""
    pedido = (settings.EMAIL_PROVIDER or "").strip().lower()
    hay_smtp = bool(settings.SMTP_HOST.strip())
    hay_sendgrid = bool(settings.SENDGRID_API_KEY.strip())
    hay_resend = bool(settings.RESEND_API_KEY.strip())
    if pedido == "resend":
        return "resend" if hay_resend else None
    if pedido == "smtp":
        return "smtp" if hay_smtp else None
    if pedido == "sendgrid":
        return "sendgrid" if hay_sendgrid else None
    if pedido:
        return None
    if hay_resend:
        return "resend"
    if hay_smtp:
        return "smtp"
    if hay_sendgrid:
        return "sendgrid"
    return None


def email_configurado() -> bool:
    return proveedor() is not None


def _from_email() -> str:
    """EMAIL_FROM admite 'Nombre <email>' o el email solo. SendGrid quiere el
    email separado del nombre."""
    match = _FROM_EMAIL_RE.search(settings.EMAIL_FROM)
    return match.group(1) if match else settings.EMAIL_FROM


_REMITENTE_DE_EJEMPLO = "onboarding@example.com"


def remitente() -> str:
    """Quién manda el mail. Si EMAIL_FROM no se configuró y se entra al SMTP
    con una casilla, sale de esa casilla: Zoho, Microsoft 365 y la mayoría de
    los SMTP rechazan un remitente distinto de la cuenta con la que se entra."""
    configurado = (settings.EMAIL_FROM or "").strip()
    usuario = (settings.SMTP_USER or "").strip()
    if (not configurado or _REMITENTE_DE_EJEMPLO in configurado) and "@" in usuario:
        return f"{NOMBRE_DE_LA_PLATAFORMA} <{usuario}>"
    return configurado


def remitente_con_nombre(nombre: str) -> str:
    """La misma casilla, con el nombre de quien escribe: «Sofía y Valentina ·
    Core Tienda <...>» (el informe de Clientes VIP)."""
    actual = remitente()
    match = _FROM_EMAIL_RE.search(actual)
    direccion = match.group(1) if match else actual
    return f"{nombre} · {NOMBRE_DE_LA_PLATAFORMA} <{direccion}>"


def armar_mensaje(to: str, subject: str, html: str, plain: str) -> EmailMessage:
    """El mail con las dos versiones: texto para los clientes que no muestran
    HTML y HTML para el resto."""
    msg = EmailMessage()
    msg["From"] = remitente()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")
    return msg


def _enviar_por_smtp(msg: EmailMessage) -> None:
    seguridad = (settings.SMTP_SEGURIDAD or "starttls").strip().lower()
    puerto = settings.SMTP_PORT
    if seguridad == "ssl":
        servidor: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.SMTP_HOST, puerto, timeout=15, context=ssl.create_default_context(),
        )
    else:
        servidor = smtplib.SMTP(settings.SMTP_HOST, puerto, timeout=15)
    with servidor:
        if seguridad == "starttls":
            servidor.starttls(context=ssl.create_default_context())
        if settings.SMTP_USER:
            servidor.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        servidor.send_message(msg)


async def _enviar_por_sendgrid(to: str, subject: str, html: str, plain: str) -> None:
    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": _from_email(), "name": NOMBRE_DE_LA_PLATAFORMA},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": plain},
            {"type": "text/html", "value": html},
        ],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            headers={"Authorization": f"Bearer {settings.SENDGRID_API_KEY}"},
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"SendGrid error {resp.status_code}: {resp.text}")


async def _enviar_por_resend(to: str, subject: str, html: str, plain: str, de: str | None = None) -> None:
    payload = {"from": de or remitente(), "to": [to], "subject": subject, "html": html, "text": plain}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            json=payload,
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY.strip()}", "User-Agent": "core-tienda"},
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"Resend error {resp.status_code}: {resp.text}")


async def send_email(to: str, subject: str, html: str, plain: str, de: str | None = None) -> None:
    """`de`: otro nombre para el remitente (misma casilla). Solo lo usa Resend:
    los SMTP rechazan un From distinto de la cuenta."""
    cual = proveedor()
    if cual == "resend":
        await _enviar_por_resend(to, subject, html, plain, de)
    elif cual == "smtp":
        # smtplib bloquea: va en un hilo para no frenar al resto del backend.
        await asyncio.to_thread(_enviar_por_smtp, armar_mensaje(to, subject, html, plain))
    elif cual == "sendgrid":
        await _enviar_por_sendgrid(to, subject, html, plain)
    else:
        raise RuntimeError("No hay un servicio de mail configurado")


def _primer_nombre(nombre: str | None) -> str:
    return (nombre or "").strip().split(" ")[0] if (nombre or "").strip() else ""


def build_reset_email(reset_url: str, nombre: str | None = None, minutos: int = 60) -> tuple[str, str]:
    """El mail de recuperar la contraseña: (html, texto). El HTML va con tablas
    y estilos en línea, que es lo que respetan Outlook y Gmail."""
    quien = _primer_nombre(nombre)
    saludo = f"Hola, {quien}" if quien else "Hola"
    vence = "1 hora" if minutos == 60 else f"{minutos} minutos"
    url = _html.escape(reset_url, quote=True)
    saludo_html = _html.escape(saludo)

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <meta name="color-scheme" content="light">
  <title>{ASUNTO_RECUPERACION}</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">Elegí una contraseña nueva. El link vale por {vence} y se usa una sola vez.</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;">
    <tr>
      <td align="center" style="padding:40px 16px;">
        <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="width:100%;max-width:560px;background:#ffffff;border-radius:20px;overflow:hidden;box-shadow:0 1px 3px rgba(15,23,42,0.08);">
          <tr>
            <td style="background:#4f46e5;background-image:linear-gradient(135deg,#6366f1 0%,#4338ca 100%);padding:26px 36px;">
              <table role="presentation" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="width:40px;height:40px;background:#ffffff;border-radius:12px;text-align:center;vertical-align:middle;font-size:15px;font-weight:800;color:#4f46e5;letter-spacing:-0.5px;">CT</td>
                  <td style="padding-left:12px;">
                    <div style="font-size:17px;font-weight:700;color:#ffffff;letter-spacing:-0.3px;line-height:1.2;">Core Tienda</div>
                    <div style="font-size:12px;color:#c7d2fe;line-height:1.4;">Calendario y tareas</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:36px 36px 8px;">
              <h1 style="margin:0 0 12px;font-size:23px;font-weight:700;color:#0f172a;letter-spacing:-0.4px;line-height:1.3;">{saludo_html}</h1>
              <p style="margin:0 0 28px;font-size:15px;color:#475569;line-height:1.65;">
                Pediste cambiar la contraseña de tu cuenta de Core Tienda. Tocá el botón para elegir una nueva.
              </p>
              <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 28px;">
                <tr>
                  <td style="background:#4f46e5;border-radius:12px;">
                    <a href="{url}" target="_blank"
                       style="display:inline-block;padding:14px 28px;color:#ffffff;font-size:15px;font-weight:600;text-decoration:none;letter-spacing:-0.2px;border-radius:12px;">
                      Elegir una contraseña nueva
                    </a>
                  </td>
                </tr>
              </table>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 24px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;">
                <tr>
                  <td style="padding:14px 16px;font-size:13px;color:#475569;line-height:1.6;">
                    El link vale por <strong style="color:#0f172a;">{vence}</strong> y se puede usar una sola vez.<br>
                    Si no fuiste vos, ignorá este mail: tu contraseña sigue igual.
                  </td>
                </tr>
              </table>
              <p style="margin:0 0 28px;font-size:12px;color:#94a3b8;line-height:1.55;word-break:break-all;">
                ¿El botón no anda? Copiá este link en el navegador:<br>
                <a href="{url}" target="_blank" style="color:#4f46e5;text-decoration:underline;">{url}</a>
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:18px 36px 22px;border-top:1px solid #f1f5f9;">
              <p style="margin:0;font-size:12px;color:#94a3b8;text-align:center;line-height:1.5;">
                Core Tienda &middot; Marketing de Tienda Inglesa<br>
                Es un mail automático: no hace falta responderlo.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    plain = (
        f"{saludo}:\n\n"
        "Pediste cambiar la contraseña de tu cuenta de Core Tienda.\n"
        "Entrá a este link para elegir una nueva:\n\n"
        f"{reset_url}\n\n"
        f"El link vale por {vence} y se puede usar una sola vez.\n"
        "Si no fuiste vos, ignorá este mail: tu contraseña sigue igual.\n\n"
        "Core Tienda · Marketing de Tienda Inglesa"
    )
    return html, plain

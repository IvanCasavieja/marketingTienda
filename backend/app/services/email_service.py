"""Servicio de email via SMTP — recuperación de contraseña."""
import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings


def _send_sync(to: str, subject: str, html: str, plain: str) -> None:
    from_addr = settings.SMTP_FROM_EMAIL or settings.SMTP_USER
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{from_addr}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
        server.ehlo()
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(from_addr, [to], msg.as_string())


async def send_email(to: str, subject: str, html: str, plain: str) -> None:
    await asyncio.to_thread(_send_sync, to, subject, html, plain)


def build_reset_email(reset_url: str) -> tuple[str, str]:
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td align="center" style="padding:40px 16px;">
        <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);max-width:560px;">
          <tr>
            <td style="background:#0f172a;padding:28px 36px;">
              <table cellpadding="0" cellspacing="0">
                <tr>
                  <td style="width:34px;height:34px;background:#3b82f6;border-radius:9px;text-align:center;vertical-align:middle;font-size:16px;font-weight:700;color:#ffffff;">M</td>
                  <td style="padding-left:10px;font-size:15px;font-weight:700;color:#ffffff;letter-spacing:-0.3px;">MKTG Platform</td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:36px 36px 28px;">
              <h1 style="margin:0 0 10px;font-size:22px;font-weight:700;color:#0f172a;letter-spacing:-0.4px;">Recuperá tu contraseña</h1>
              <p style="margin:0 0 28px;font-size:15px;color:#64748b;line-height:1.65;">
                Recibimos una solicitud para restablecer la contraseña de tu cuenta.<br>
                Hacé clic en el botón para crear una nueva.
              </p>
              <table cellpadding="0" cellspacing="0" style="margin:0 0 28px;">
                <tr>
                  <td style="background:#3b82f6;border-radius:10px;">
                    <a href="{reset_url}"
                       style="display:inline-block;padding:14px 28px;color:#ffffff;font-size:15px;font-weight:600;text-decoration:none;letter-spacing:-0.2px;">
                      Restablecer contraseña &rarr;
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin:0 0 10px;font-size:13px;color:#94a3b8;line-height:1.55;">
                Este link expira en <strong style="color:#64748b;">1 hora</strong>.
                Si no solicitaste este cambio, podés ignorar este email.
              </p>
              <p style="margin:0;font-size:11px;color:#cbd5e1;word-break:break-all;">
                O copiá este link en tu navegador:<br>{reset_url}
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:18px 36px;border-top:1px solid #f1f5f9;">
              <p style="margin:0;font-size:12px;color:#cbd5e1;text-align:center;">
                Marketing Intelligence Platform &middot; Email automático, no respondas a este mensaje.
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
        "Recuperá tu contraseña de MKTG Platform\n\n"
        "Accedé al siguiente link para restablecer tu contraseña:\n"
        f"{reset_url}\n\n"
        "Este link expira en 1 hora.\n"
        "Si no solicitaste este cambio, ignorá este email.\n\n"
        "Marketing Intelligence Platform"
    )
    return html, plain

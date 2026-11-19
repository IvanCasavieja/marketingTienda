"""Los avisos de la campanita, también por mail.

Pedido de Ivan (18/11/2026): "es muy bueno que los avisos lleguen por mail".
Eligió: todos los avisos, al momento (un mail por aviso) y que cada persona
los pueda apagar en "Mi perfil" (prendidos por defecto).

Cómo anda: cada aviso nuevo nace con `mail_pendiente` (lo pone el modelo, ver
app/models/notificacion.py), así no hay que tocar ninguno de los lugares que
crean avisos. Este loop pasa cada minuto, toma los pendientes y los manda con
el servicio de mail que esté configurado (app/services/email_service.py:
Resend, SMTP o SendGrid). Así guardar algo no espera al mail, y si el
proveedor falla se reintenta (hasta MAX_INTENTOS veces).

No se mandan:
- los del tablero (tarjeta nueva, entregas, cambios pedidos, aprobaciones y
  comentarios de las tarjetas): quedan solo en la campanita. Ivan, 19/11/2026:
  hay un tope de 3.000 mails por mes y el tablero solo se lo comería
  (SOLO_CAMPANITA);
- a quien apagó los mails, no tiene mail o ya no está activo (queda en la
  campanita igual);
- los avisos de hace más de MAX_ATRASO: si el servidor estuvo caído un día,
  no le llueve a la gente una tanda de avisos viejos;
- nada si no hay un servicio de mail configurado (quedan en la campanita).
"""
from __future__ import annotations

import asyncio
import html as _html
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.notificacion import Notificacion
from app.models.user import User
from app.services import email_service

logger = logging.getLogger(__name__)

SEGUNDOS_ENTRE_VUELTAS = 60
POR_VUELTA = 50
MAX_INTENTOS = 5
MAX_ATRASO = timedelta(hours=24)
# Resend deja 2 pedidos por segundo en el plan gratis.
_PAUSA_ENTRE_MAILS = 0.6
_LARGO_DEL_ASUNTO = 90

# Los avisos que NUNCA salen por mail, solo en la campanita: los del tablero
# (app/services/entregas.py, ORIGEN). Ya nacen sin mail pendiente (ver
# entregas.avisar); esto es el freno por si alguno quedara en la cola.
SOLO_CAMPANITA = frozenset({"calendario_entrega"})


def va_por_mail(origen_tipo: str | None) -> bool:
    """Si un aviso de este origen puede salir por mail. Pura."""
    return origen_tipo not in SOLO_CAMPANITA


def destino(n) -> str:
    """A dónde lleva el botón del mail: lo mismo que la campanita
    (resolverDestino en frontend/components/layout/Campanita.tsx). Pura."""
    ref = n.origen_ref or ""
    partes = ref.split(":")
    if getattr(n, "watchlist_item_id", None) is not None:
        return "/precios/listas"
    tipo = n.origen_tipo
    if tipo == "campaign_alert":
        return "/campaigns"
    if tipo in ("calendario_aviso", "calendario_tarea") and partes[0]:
        return f"/calendario?accion={partes[0]}"
    if tipo == "calendario_accion":
        return f"/calendario?accion={partes[1]}" if len(partes) > 1 and partes[1] else "/calendario"
    if tipo == "calendario_header":
        return "/calendario"
    if tipo in ("colocacion_pedido", "colocacion_devuelta"):
        return "/fotos"
    if tipo == "colocacion_completa" and partes[0]:
        return f"/calendario?accion={partes[0]}&pestana=fotos"
    if tipo == "calendario_entrega":
        return f"/entregas?tarea={partes[1]}" if len(partes) > 1 and partes[1] else "/entregas"
    return "/home"


def asunto(mensaje: str) -> str:
    """El asunto es el aviso mismo, cortado: en la bandeja se lee qué pasó
    sin abrirlo. Pura."""
    texto = " ".join((mensaje or "").split())
    if len(texto) > _LARGO_DEL_ASUNTO:
        texto = texto[: _LARGO_DEL_ASUNTO - 1].rstrip() + "…"
    return texto or "Tenés un aviso nuevo en Core Tienda"


def armar_mail(mensaje: str, nombre: str | None, url: str) -> tuple[str, str]:
    """(html, texto) del mail de un aviso. Con tablas y estilos en línea, como
    el de recuperar la contraseña: es lo que respetan Outlook y Gmail."""
    quien = (nombre or "").strip().split(" ")[0]
    saludo = f"Hola, {quien}" if quien else "Hola"
    m = _html.escape(" ".join((mensaje or "").split()))
    u = _html.escape(url, quote=True)
    perfil = _html.escape(f"{settings.FRONTEND_URL.rstrip('/')}/perfil", quote=True)
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <meta name="color-scheme" content="light">
  <title>Aviso de Core Tienda</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">{m}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="width:100%;max-width:560px;background:#ffffff;border-radius:20px;overflow:hidden;box-shadow:0 1px 3px rgba(15,23,42,0.08);">
          <tr>
            <td style="background:#4f46e5;background-image:linear-gradient(135deg,#6366f1 0%,#4338ca 100%);padding:22px 32px;">
              <table role="presentation" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="width:36px;height:36px;background:#ffffff;border-radius:10px;text-align:center;vertical-align:middle;font-size:14px;font-weight:800;color:#4f46e5;">CT</td>
                  <td style="padding-left:12px;">
                    <div style="font-size:16px;font-weight:700;color:#ffffff;line-height:1.2;">Core Tienda</div>
                    <div style="font-size:12px;color:#c7d2fe;line-height:1.4;">Tenés un aviso nuevo</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:30px 32px 6px;">
              <p style="margin:0 0 10px;font-size:15px;color:#475569;">{_html.escape(saludo)}:</p>
              <p style="margin:0 0 24px;font-size:17px;font-weight:600;color:#0f172a;line-height:1.5;">{m}</p>
              <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 26px;">
                <tr>
                  <td style="background:#4f46e5;border-radius:12px;">
                    <a href="{u}" target="_blank" style="display:inline-block;padding:13px 26px;color:#ffffff;font-size:15px;font-weight:600;text-decoration:none;border-radius:12px;">Abrir en Core Tienda</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 32px 20px;border-top:1px solid #f1f5f9;">
              <p style="margin:0;font-size:12px;color:#94a3b8;text-align:center;line-height:1.55;">
                También está en la campanita de Core Tienda.<br>
                ¿No querés estos mails? Apagalos en <a href="{perfil}" target="_blank" style="color:#4f46e5;">Mi perfil</a>.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
    texto = (
        f"{saludo}:\n\n{' '.join((mensaje or '').split())}\n\n"
        f"Abrir en Core Tienda: {url}\n\n"
        f"También está en la campanita. ¿No querés estos mails? Apagalos en Mi perfil: "
        f"{settings.FRONTEND_URL.rstrip('/')}/perfil\n"
    )
    return html, texto


def lo_quiere(usuario: User | None) -> bool:
    """Si a esta persona le sale el mail. Pura."""
    return bool(
        usuario is not None and usuario.is_active and (usuario.email or "").strip()
        and getattr(usuario, "avisos_por_mail", True)
    )


async def mandar_pendientes(db: AsyncSession, ahora: datetime | None = None, enviar=None) -> int:
    """Una vuelta: manda los avisos pendientes por mail. Devuelve cuántos
    salieron. `enviar` es para las pruebas (por defecto, el servicio de mail)."""
    enviar = enviar or email_service.send_email
    ahora = ahora or datetime.now(timezone.utc)
    ids = list((await db.execute(
        select(Notificacion.id).where(Notificacion.mail_pendiente.is_(True))
        .order_by(Notificacion.id).limit(POR_VUELTA)
    )).scalars())
    await db.commit()
    if not ids:
        return 0
    configurado = email_service.email_configurado()
    salieron = 0
    for nid in ids:
        # Se reclama antes de mandar, en una transacción cortita: dos vueltas
        # (o dos servidores) no mandan el mismo aviso, y no queda nada
        # bloqueado mientras sale el mail (marcarlo leído no espera).
        reclamado = (await db.execute(
            update(Notificacion).where(Notificacion.id == nid, Notificacion.mail_pendiente.is_(True))
            .values(mail_pendiente=False).returning(Notificacion.id)
        )).first()
        await db.commit()
        if reclamado is None:
            continue
        fila = (await db.execute(
            select(Notificacion.mensaje, Notificacion.created_at, Notificacion.origen_tipo, Notificacion.origen_ref,
                   Notificacion.watchlist_item_id, Notificacion.mail_intentos, User)
            .join(User, User.id == Notificacion.user_id).where(Notificacion.id == nid)
        )).first()
        if fila is None:
            continue
        mensaje, creado, origen_tipo, origen_ref, item, intentos, usuario = fila
        viejo = creado is not None and ahora - creado > MAX_ATRASO
        if not configurado or viejo or not va_por_mail(origen_tipo) or not lo_quiere(usuario):
            continue
        n = SimpleNamespace(origen_tipo=origen_tipo, origen_ref=origen_ref, watchlist_item_id=item)
        url = f"{settings.FRONTEND_URL.rstrip('/')}{destino(n)}"
        html, texto = armar_mail(mensaje, usuario.full_name, url)
        try:
            await enviar(usuario.email, asunto(mensaje), html, texto)
        except Exception as exc:
            intentos = (intentos or 0) + 1
            # Vuelve a quedar pendiente para la próxima vuelta, hasta MAX_INTENTOS.
            await db.execute(update(Notificacion).where(Notificacion.id == nid).values(
                mail_intentos=intentos, mail_pendiente=intentos < MAX_INTENTOS,
            ))
            await db.commit()
            logger.warning("avisos_por_mail: no salió el %s (intento %d): %s", nid, intentos, exc)
            continue
        await db.execute(update(Notificacion).where(Notificacion.id == nid).values(mail_enviado_at=ahora))
        await db.commit()
        salieron += 1
        if _PAUSA_ENTRE_MAILS:
            await asyncio.sleep(_PAUSA_ENTRE_MAILS)
    return salieron


async def run_avisos_por_mail_loop() -> None:
    """Loop perpetuo: una vuelta por minuto (arranca con el servidor desplegado)."""
    while True:
        try:
            async with AsyncSessionLocal() as db:
                n = await mandar_pendientes(db)
            if n:
                logger.info("avisos_por_mail: %d mails", n)
        except Exception as exc:
            logger.error("avisos_por_mail: error en el loop: %s", exc, exc_info=True)
        await asyncio.sleep(SEGUNDOS_ENTRE_VUELTAS)

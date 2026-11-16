from sqlalchemy import String, Boolean, DateTime, Integer, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id", ondelete="SET NULL"), nullable=True)
    # Fuente de verdad para autorización — se siembra desde role.permissions al
    # asignar un rol, pero después se puede afinar por usuario individualmente.
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    # A qué mundos entra (Tienda Inglesa, Redexpres...): claves de
    # app/core/mundos.py. El mundo es toda la plataforma vista para un negocio.
    # Un superadmin entra a todos sin estar en ninguna lista.
    mundos: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    # JWT es sin estado — sin esto, cerrar sesión o cambiar la contraseña no
    # invalida los tokens ya emitidos (access de hasta 30 min, refresh de
    # hasta 7 días), quedan vivos igual hasta que expiren solos. Cualquier
    # token emitido con iat anterior a esta fecha se rechaza en get_current_user.
    tokens_invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Bloqueo por intentos fallidos — persistido en DB (no en Redis) para que
    # no dependa de un servicio externo que puede estar caído (ver incidente
    # con el throttle basado en Redis: sin esto, el login se degradaba mal
    # cuando Redis no respondía).
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Rotación de contraseña. must_change_password se prende cuando la
    # contraseña la puso otra persona (un admin al crear el usuario o al
    # resetearla) y se apaga cuando el propio usuario la cambia — en ese
    # momento nunca fue "elegida" por el dueño de la cuenta. password_changed_at
    # es la fecha del último cambio real, usada para exigir renovación cada 20
    # días — no aplica a los logins de sucursal (LocalAsignacion), que son
    # compartidos a propósito y no tienen dueño individual.
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # El link del calendario para Outlook/Google/iPhone va firmado con esto:
    # "Generar otro link" lo sube y el anterior deja de andar. No se usa la
    # marca de tokens_invalidated_at porque la contraseña se renueva cada 20
    # días y la suscripción de Outlook se cortaría sola (migración 0064).
    calendario_link_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Cuenta externa: la agencia o un diseñador de afuera (0068). Entra igual
    # que todos (mail y contraseña hoy; el día que se entre con Microsoft, igual,
    # con este flag), pero ve el calendario solo en una ventana alrededor del
    # mes actual, solo sus tareas y nada de las herramientas internas. Qué se
    # le permite está en app/core/externos.py; la base además se niega a
    # guardar un externo con otros permisos o como superadmin (ver la 0068).
    es_externo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # La empresa de la cuenta externa ("Agencia Pampa"): entre los de la misma
    # empresa se ven los nombres; a los de otra, no.
    empresa: Mapped[str | None] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    role = relationship("Role", back_populates="users")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")

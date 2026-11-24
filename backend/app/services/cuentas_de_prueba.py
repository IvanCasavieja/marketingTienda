"""Las cuentas del Equipo nocturno en el entorno de pruebas (24/11/2026).

Pedido de Ivan: "que sean agentes autónomos, que exploren, que usen todo lo
que esté a su alcance para mejorar, que sean incluso como la agencia, que
puedan ver la visión de la agencia; deberían tener usuarios propios". Son tres
cuentas, una por cada manera de ver la plataforma:

- **Equipo nocturno** (superadmin): ve y hace todo, como el equipo de Tienda.
- **Agencia de prueba** (cuenta externa de la agencia "Agencia de prueba"): ve
  solo su tablero y sus tareas, como Publicis.
- **Local de prueba** (login de sucursal de Redexpres): ve solo "Mi pedido".

Solo existen donde `ENTORNO_DE_PRUEBAS=true`: la copia que levantan los
agentes cada noche en su nube (con scripts/cuentas_de_prueba.py) o, si algún
día lo hay, un servidor de pruebas fijo (al arrancar, ver main.py). En
producción no se crean nunca: ahí la variable no está y vale false. Las
contraseñas vienen de `CLAVE_EQUIPO_NOCTURNO`, `CLAVE_AGENCIA_DE_PRUEBA` y
`CLAVE_LOCAL_DE_PRUEBA`, nunca del repo. Una cuenta sin su contraseña no se
crea.

En cada arranque las cuentas se dejan como dice acá (permisos, agencia, local)
y con la contraseña de la variable, recién cambiada: así no vence a los 60
días, no queda bloqueada por intentos fallidos de una noche anterior y, si un
agente la cambió probando "Mi perfil", vuelve a la de siempre. Los avisos por
mail quedan apagados: son cuentas de @example.com, no hay nadie del otro lado.

Cómo se levanta: docs/equipo-nocturno/README.md, "La plataforma andando".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.alcance import POR_DEFECTO_EXTERNO
from app.core.externos import PERMISOS_DE_EXTERNOS
from app.core.mundos import MUNDO_POR_DEFECTO, MUNDOS
from app.core.security import hash_password, verify_password
from app.models.local_asignacion import LocalAsignacion
from app.models.role import ALL_PERMISSIONS, Role
from app.models.user import User

logger = logging.getLogger(__name__)

# La agencia con la que la cuenta de prueba ve el tablero. Para pedirle una
# pieza, en la tarea se elige esta agencia.
AGENCIA_DE_PRUEBA = "Agencia de prueba"


@dataclass(frozen=True)
class Cuenta:
    variable: str  # la variable de entorno con su contraseña
    email: str
    nombre: str
    tipo: str      # "superadmin" | "agencia" | "local"


CUENTAS: tuple[Cuenta, ...] = (
    Cuenta("CLAVE_EQUIPO_NOCTURNO", "equipo-nocturno@example.com", "Equipo nocturno", "superadmin"),
    Cuenta("CLAVE_AGENCIA_DE_PRUEBA", "agencia-de-prueba@example.com", "Agencia de prueba", "agencia"),
    Cuenta("CLAVE_LOCAL_DE_PRUEBA", "local-de-prueba@example.com", "Local de prueba", "local"),
)


async def _rol_admin(db: AsyncSession) -> int | None:
    rol = (await db.execute(select(Role).where(Role.name == "Admin"))).scalar_one_or_none()
    return rol.id if rol else None


def _como_tiene_que_quedar(cuenta: Cuenta, rol_admin: int | None) -> dict:
    """Los datos de la cuenta, según su tipo. Los mismos que tiene la gente de
    verdad: el equipo con todo, la agencia como la crea el panel
    (admin._crear_externo) y el local como los 60 de Redexpres."""
    if cuenta.tipo == "superadmin":
        return dict(
            role_id=rol_admin, permissions=list(ALL_PERMISSIONS), mundos=list(MUNDOS),
            is_superuser=True, es_externo=False, empresa=None, calendario_alcance="todo",
        )
    if cuenta.tipo == "agencia":
        return dict(
            role_id=None, permissions=sorted(PERMISOS_DE_EXTERNOS), mundos=[MUNDO_POR_DEFECTO],
            is_superuser=False, es_externo=True, empresa=AGENCIA_DE_PRUEBA,
            calendario_alcance=POR_DEFECTO_EXTERNO,
        )
    if cuenta.tipo == "local":
        # Los logins de sucursal tienen solo el chat de Don Tino (ver
        # PERMISOS_DE_TODOS_LOS_MUNDOS); "Mi pedido" lo da la asignación.
        return dict(
            role_id=None, permissions=["ai.don_tino"], mundos=["redexpres"],
            is_superuser=False, es_externo=False, empresa=None, calendario_alcance="todo",
        )
    raise ValueError(f"Tipo de cuenta desconocido: {cuenta.tipo}")


async def _asignar_local(db: AsyncSession, usuario: User) -> str:
    """El local de Redexpres de la cuenta de prueba: el que ya tiene o, si
    todavía no, el primero de la lista que no sea de otro login (para no
    mezclarse con un local de verdad si la base de pruebas trae alguno)."""
    from app.api.routes.redexpres import LOCALES

    suyo = (await db.execute(
        select(LocalAsignacion.local_nombre).where(LocalAsignacion.user_id == usuario.id)
    )).scalars().first()
    if suyo:
        return suyo
    ocupados = set((await db.execute(
        select(LocalAsignacion.local_nombre).where(LocalAsignacion.user_id != usuario.id)
    )).scalars())
    local = next((nombre for nombre in LOCALES if nombre not in ocupados), LOCALES[0])
    db.add(LocalAsignacion(user_id=usuario.id, local_nombre=local, tipo="redex"))
    return local


async def preparar(db: AsyncSession, claves: dict[str, str]) -> list[str]:
    """Crea o pone al día las cuentas que tienen contraseña en `claves`
    ({variable: contraseña}). No hace commit. Devuelve una línea por cuenta
    para el log, sin contraseñas."""
    ahora = datetime.now(timezone.utc)
    rol_admin = await _rol_admin(db)
    hecho: list[str] = []
    for cuenta in CUENTAS:
        clave = (claves.get(cuenta.variable) or "").strip()
        if not clave:
            hecho.append(f"{cuenta.email}: sin {cuenta.variable}, no se crea")
            continue
        usuario = (await db.execute(select(User).where(User.email == cuenta.email))).scalar_one_or_none()
        nueva = usuario is None
        if nueva:
            usuario = User(email=cuenta.email, full_name=cuenta.nombre, hashed_password=hash_password(clave))
            db.add(usuario)
        elif not verify_password(clave, usuario.hashed_password):
            usuario.hashed_password = hash_password(clave)
        for campo, valor in _como_tiene_que_quedar(cuenta, rol_admin).items():
            setattr(usuario, campo, valor)
        usuario.full_name = cuenta.nombre
        usuario.is_active = True
        usuario.must_change_password = False
        usuario.password_changed_at = ahora
        usuario.failed_login_attempts = 0
        usuario.locked_until = None
        usuario.avisos_por_mail = False
        await db.flush()
        detalle = ""
        if cuenta.tipo == "local":
            detalle = f" (local {await _asignar_local(db, usuario)})"
        hecho.append(f"{cuenta.email}: {'creada' if nueva else 'al día'}{detalle}")
    await db.flush()
    return hecho


def claves_de(settings) -> dict[str, str]:
    return {c.variable: getattr(settings, c.variable, "") for c in CUENTAS}


async def al_arrancar() -> None:
    """Lo llama el arranque del servidor, ya con la base migrada. Si no es el
    entorno de pruebas, no hace nada."""
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal

    if not settings.ENTORNO_DE_PRUEBAS:
        return
    try:
        async with AsyncSessionLocal() as db:
            for linea in await preparar(db, claves_de(settings)):
                logger.info("cuentas de prueba: %s", linea)
            await db.commit()
    except Exception as e:  # que una cuenta no tire abajo el arranque
        logger.error("cuentas de prueba: no se pudieron preparar: %s", e)

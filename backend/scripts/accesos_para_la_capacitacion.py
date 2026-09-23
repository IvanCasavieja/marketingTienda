"""Deja cada persona con el acceso que corresponde, antes de la capacitación.

Lo pidió Ivan el 23/09/2026, por grupos. Esta es la tabla, literal:

  - Rol Admin: lucia, maria belen, anita, ivan, nathie, nati, fernanda, pablo,
    macarena, mia, mariana. Son los que van al calendario.
  - Toda la plataforma: Ivan (Superadmin), lucia, fernanda, pablo, y genesis,
    que se sumó después para poder ver todo lo que se hizo.
  - Calendario + validación de RRSS + guía de uso + el Diccionario + medios:
    nathie, nati, mia, mariana (y macarena, ver ABIERTO abajo).
  - Materiales completo + facturación: belen, anita, valentina.
  - Planilla de Redexpres: las sucursales (ya la tienen por asignación) y
    valentina.
  - Materiales completo: jenniffer duran, sebastian bastarrica, jenifer
    furtado.
  - Buscador de precios: todo el resto, menos las sucursales de Redex.

Tres cosas quedaron decididas acá y hay que mirarlas:

  ABIERTO 1 — macarena está en la lista de los que van al calendario pero
  después no cayó en ningún grupo. Se la deja con el mismo acceso que nathie,
  nati, mia y mariana.
  ABIERTO 2 — `platform.admin` (entrar al panel de administración) se da solo
  a los de "toda la plataforma". El resto queda con el ROL Admin, como se
  pidió, pero sin el panel: son 10 personas y el panel edita usuarios ajenos.
  ABIERTO 3 — `ai.don_tino` va para todas las personas. Es el anfitrión que
  guía por la plataforma y consulta con los permisos de quien pregunta, así
  que no abre nada que la persona no tenga.

Uso, desde backend/:
    python scripts/accesos_para_la_capacitacion.py            # solo muestra
    python scripts/accesos_para_la_capacitacion.py --aplicar  # escribe

Siempre respalda antes de escribir (backend/backups/).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import string
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
os.environ.setdefault("APP_SECRET_KEY", "script")
os.environ.setdefault("ENCRYPTION_KEY", "Y2q_vIGd2FgQ4CqY3Fh3du3ZehOWmx4pVHPfpJC44bA=")

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.local_asignacion import LocalAsignacion  # noqa: E402
from app.models.role import ALL_PERMISSIONS, Role  # noqa: E402
from app.models.user import User  # noqa: E402

BACKUPS = BACKEND / "backups"

# ---------------------------------------------------------------------------
# Los paquetes de permisos, armados desde el menú
# ---------------------------------------------------------------------------
# Cada uno es "lo que se ve en el menú" traducido a permisos. La guía de uso
# (/ayuda) no lleva permiso: la ve cualquiera que esté logueado.

CALENDARIO   = ["calendario.view", "calendario.edit"]
RRSS         = ["rrss.view", "rrss.validate"]
DICCIONARIO  = ["cenefas.diccionario"]
MEDIOS       = ["analytics.view", "analytics.export", "connections.view", "ai.triada"]
MATERIALES   = ["cenefas.view", "cenefas.generate", "cenefas.edit", "cenefas.import",
                "cenefas.delete", "cenefas.diccionario", "ai.tinin"]
FACTURACION  = ["facturacion.view", "facturacion.upload", "facturacion.manage", "ai.dogti"]
REDEXPRES    = ["redexpres.view"]
PRECIOS      = ["precios.search", "ai.dona_tina"]
ANFITRION    = ["ai.don_tino"]
TODO         = list(ALL_PERMISSIONS.keys())

# ---------------------------------------------------------------------------
# Quién es quién. La clave es el mail, que es lo único que no se repite.
# ---------------------------------------------------------------------------

TODA_LA_PLATAFORMA = {
    "lvignotti@tiendainglesa.com.uy",   # lucia
    "fgomez@tiendainglesa.com.uy",      # fernanda
    "prego@tiendainglesa.com.uy",       # pablo
    "gerodriguez@tiendainglesa.com.uy", # genesis — "acceso a todo para que
                                        # pueda ver todo lo que hicimos"
}

CALENDARIO_Y_MEDIOS = {
    "npacheco@tiendainglesa.com.uy",    # nathie
    "nllanes@tiendainglesa.com.uy",     # nati
    "mrobaina@tiendainglesa.com.uy",    # mia
    "macastillo@tiendainglesa.com.uy",  # mariana
    "msegade@tiendainglesa.com.uy",     # macarena — ver ABIERTO 1
}

MATERIALES_Y_FACTURACION = {
    "mdelcerro@tiendainglesa.com.uy",   # maria belen
    "agalizia@tiendainglesa.com.uy",    # anita
    "vagonzalez@expres.uy",             # valentina
}

SOLO_MATERIALES = {
    "jduran@tiendainglesa.com.uy",      # jenniffer duran
    "sbastarrica@tiendainglesa.com.uy", # sebastian bastarrica
    "jfurtado@tiendainglesa.com.uy",    # jenifer furtado
}

# Valentina además carga la planilla de Redexpres.
CON_REDEXPRES = {"vagonzalez@expres.uy"}

# Rol Admin: los que van al calendario.
CON_ROL_ADMIN = TODA_LA_PLATAFORMA | CALENDARIO_Y_MEDIOS | {
    "mdelcerro@tiendainglesa.com.uy",   # maria belen
    "agalizia@tiendainglesa.com.uy",    # anita
}

# Cuentas que no son personas y no entran en el reparto.
CUENTAS_DE_SERVICIO = {
    "agente-claude@internal.marketingtienda",
    "claude-smoketest@local.test",
}

# Las que hay que crear: no existían al 23/09/2026.
A_CREAR = [
    {"email": "prego@tiendainglesa.com.uy",      "full_name": "Pablo Rego"},
    {"email": "msegade@tiendainglesa.com.uy",    "full_name": "Macarena Segade"},
    {"email": "macastillo@tiendainglesa.com.uy", "full_name": "Mariana Castillo"},
    {"email": "gerodriguez@tiendainglesa.com.uy", "full_name": "Genesis Rodriguez"},
]


def permisos_de(email: str) -> list[str]:
    """Los permisos que le tocan a una persona. El orden del catálogo se
    respeta para que dos usuarios con lo mismo se vean iguales en el panel."""
    if email in TODA_LA_PLATAFORMA:
        # Todo menos platform.super, que es el control total y queda en la
        # cuenta de Ivan: nadie más edita roles ni usuarios sin restricción.
        return [p for p in TODO if p != "platform.super"]

    acumulado: set[str] = set(ANFITRION)
    if email in CALENDARIO_Y_MEDIOS:
        acumulado.update(CALENDARIO, RRSS, DICCIONARIO, MEDIOS)
    if email in MATERIALES_Y_FACTURACION:
        acumulado.update(MATERIALES, FACTURACION)
    if email in SOLO_MATERIALES:
        # "TAMBIÉN deben tener acceso a materiales": estaban en "todo el
        # resto", así que Materiales se les suma al buscador de precios, no lo
        # reemplaza.
        acumulado.update(MATERIALES, PRECIOS)
    if email in CON_REDEXPRES:
        acumulado.update(REDEXPRES)
    if email in CON_ROL_ADMIN:
        acumulado.update(CALENDARIO)      # el rol Admin es justamente el del calendario
    if acumulado == set(ANFITRION):
        # No cayó en ningún grupo: es "todo el resto", buscador de precios.
        acumulado.update(PRECIOS)
    return [p for p in ALL_PERMISSIONS if p in acumulado]


def _password_temporal(largo: int = 16) -> str:
    chars = string.ascii_letters + string.digits
    bruto = (
        secrets.choice(string.ascii_uppercase)
        + secrets.choice(string.digits)
        + secrets.choice("!@#$")
        + "".join(secrets.choice(chars) for _ in range(largo - 3))
    )
    return "".join(secrets.SystemRandom().sample(bruto, len(bruto)))


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aplicar", action="store_true", help="Sin esto solo muestra qué cambiaría")
    args = ap.parse_args()

    async with AsyncSessionLocal() as db:
        roles = {r.name: r for r in (await db.execute(select(Role))).scalars()}
        rol_admin = roles.get("Admin")
        rol_usuario = roles.get("Usuario")
        if not rol_admin or not rol_usuario:
            raise SystemExit("Faltan los roles del sistema (Admin / Usuario).")

        con_sucursal = {
            fila[0] for fila in (await db.execute(select(LocalAsignacion.user_id))).all()
        }
        usuarios = list((await db.execute(select(User).order_by(User.id))).scalars())
        por_mail = {u.email.lower(): u for u in usuarios}

        # --- respaldo, siempre antes de tocar nada -------------------------
        BACKUPS.mkdir(exist_ok=True)
        ruta = BACKUPS / f"usuarios_antes_de_accesos_{datetime.now():%Y-%m-%d_%H%M}.json"
        ruta.write_text(json.dumps([
            {"id": u.id, "email": u.email, "full_name": u.full_name,
             "role_id": u.role_id, "permissions": u.permissions or [],
             "is_superuser": u.is_superuser, "is_active": u.is_active}
            for u in usuarios
        ], ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Respaldo: {ruta.relative_to(BACKEND)}  ({len(usuarios)} usuarios)\n")

        # --- altas ---------------------------------------------------------
        nuevas: list[tuple[str, str]] = []
        for datos in A_CREAR:
            if datos["email"].lower() in por_mail:
                print(f"  ya existe   {datos['email']}")
                continue
            clave = _password_temporal()
            print(f"  ALTA        {datos['full_name']:<24} {datos['email']}")
            nuevas.append((datos["email"], clave))
            if args.aplicar:
                nuevo = User(
                    email=datos["email"],
                    full_name=datos["full_name"],
                    hashed_password=hash_password(clave),
                    role_id=rol_admin.id,
                    permissions=permisos_de(datos["email"]),
                    is_superuser=False,
                    must_change_password=True,
                    password_changed_at=datetime.now(timezone.utc),
                )
                db.add(nuevo)
                await db.flush()
                por_mail[nuevo.email.lower()] = nuevo
                usuarios.append(nuevo)

        # --- reparto -------------------------------------------------------
        print(f"\n{'usuario':<26} {'rol':<10} {'permisos':>8}  qué cambia")
        print("-" * 96)
        cambios = 0
        for u in usuarios:
            mail = u.email.lower()
            if mail in CUENTAS_DE_SERVICIO or u.is_superuser:
                continue
            if u.id in con_sucursal:
                continue  # los logins de sucursal entran por su asignación

            quiere_rol = rol_admin if mail in CON_ROL_ADMIN else rol_usuario
            quiere_perms = permisos_de(mail)
            if mail not in TODA_LA_PLATAFORMA:
                quiere_perms = [p for p in quiere_perms if p != "platform.admin"]  # ver ABIERTO 2

            detalle = []
            if u.role_id != quiere_rol.id:
                antes = next((n for n, r in roles.items() if r.id == u.role_id), "sin rol")
                detalle.append(f"rol {antes} -> {quiere_rol.name}")
            suma = sorted(set(quiere_perms) - set(u.permissions or []))
            resta = sorted(set(u.permissions or []) - set(quiere_perms))
            if suma:
                detalle.append(f"+{len(suma)}")
            if resta:
                detalle.append(f"-{len(resta)} ({', '.join(resta[:3])}{'...' if len(resta) > 3 else ''})")
            if not detalle:
                continue

            cambios += 1
            print(f"{u.full_name[:25]:<26} {quiere_rol.name:<10} {len(quiere_perms):>8}  {'; '.join(detalle)}")
            if args.aplicar:
                u.role_id = quiere_rol.id
                u.permissions = quiere_perms

        print("-" * 96)
        print(f"{cambios} usuarios cambian.")
        if nuevas:
            print("\nContraseñas temporales (se piden cambiar en el primer ingreso):")
            for mail, clave in nuevas:
                print(f"  {mail:<40} {clave}")

        if args.aplicar:
            await db.commit()
            print("\nAplicado.")
        else:
            print("\nNo se escribió nada. Con --aplicar se guarda.")


if __name__ == "__main__":
    asyncio.run(main())

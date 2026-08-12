"""CRUD de cuentas de Facturación. "Eliminar" siempre es soft-delete
(activa=False) -- nunca se borra una fila, para no perder el nombre de
cuenta de movimientos/canjes históricos que la referencian (ver
FacturacionCuenta)."""
from sqlalchemy import select

from app.models.facturacion_cuenta import FacturacionCuenta


def cuenta_to_dict(c: FacturacionCuenta) -> dict:
    return {"id": c.id, "nombre": c.nombre, "activa": c.activa}


async def listar_cuentas(db, incluir_inactivas: bool = False) -> list[FacturacionCuenta]:
    stmt = select(FacturacionCuenta).order_by(FacturacionCuenta.nombre)
    if not incluir_inactivas:
        stmt = stmt.where(FacturacionCuenta.activa.is_(True))
    return (await db.execute(stmt)).scalars().all()


async def crear_cuenta(db, nombre: str) -> FacturacionCuenta:
    cuenta = FacturacionCuenta(nombre=nombre.strip(), activa=True)
    db.add(cuenta)
    await db.flush()
    return cuenta


def editar_cuenta(cuenta: FacturacionCuenta, nombre: str | None, activa: bool | None) -> FacturacionCuenta:
    """activa=False es el "eliminar" de la UI -- ver docstring del módulo."""
    if nombre is not None:
        cuenta.nombre = nombre.strip()
    if activa is not None:
        cuenta.activa = activa
    return cuenta

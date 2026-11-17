"""calendario.pedidos: pedir piezas y materiales es un permiso aparte

Pedido de Ivan (17/11/2026): la accion del calendario la arma quien lidera, y
"los pedidos de materiales y de piezas que los puedan hacer los que tienen
acceso al calendario. Es mas, deberia de ser un permiso especifico el poder
hacer peticiones de materiales".

Hasta hoy "Pedir una pieza" venia con `calendario.edit`, asi que no habia
forma de dejar a alguien pedir piezas sin que tambien pudiera crear, mover y
borrar acciones. Se agrega `calendario.pedidos` y se backfillea a TODO rol y
usuario que ya tenga `calendario.edit`: nadie pierde ni gana nada al aplicar
esto (mismo criterio que la 0056 con `cenefas.diccionario`). Despues se tilda
o destilda por persona desde el panel.

Las cuentas externas (0069) quedan afuera: no pueden tener este permiso
(app/core/externos.py) y no se les anota uno que no les sirve.

Revision ID: 0071
Revises: 0070
Create Date: 2026-11-17
"""
import json

from alembic import op
from sqlalchemy import text

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None

_NUEVO = "calendario.pedidos"
_ORIGEN = "calendario.edit"


def con_pedidos(permissions) -> tuple[list, bool]:
    """Agrega calendario.pedidos al lado de calendario.edit, si estaba.
    Devuelve (permisos, si cambio). Pura, para probarla sin base."""
    permisos = list(permissions or [])
    if _ORIGEN in permisos and _NUEVO not in permisos:
        permisos.insert(permisos.index(_ORIGEN) + 1, _NUEVO)
        return permisos, True
    return permisos, False


def upgrade() -> None:
    conn = op.get_bind()
    filas = [
        ("roles", conn.execute(text("SELECT id, permissions FROM roles")).fetchall()),
        ("users", conn.execute(
            text("SELECT id, permissions FROM users WHERE es_externo IS NOT TRUE")
        ).fetchall()),
    ]
    for tabla, registros in filas:
        for row_id, permissions in registros:
            permisos, cambio = con_pedidos(permissions)
            if cambio:
                conn.execute(
                    text(f"UPDATE {tabla} SET permissions = CAST(:p AS json) WHERE id = :id"),
                    {"p": json.dumps(permisos), "id": row_id},
                )


def downgrade() -> None:
    # El permiso no se quita: pudo tildarse o destildarse a mano despues de
    # aplicar esto (mismo criterio que 0035, 0055 y 0056). La version anterior
    # lo ignora.
    pass

"""borra las cenefas que no son de Redexpres y devuelve el lugar muerto (Clientes VIP)

Ivan (26/11/2026), liberando lugar en la base: «borres todas las plantillas de
cenefas que no sean de RedExpress. Las de RedExpress no las toques, pero el
resto elimina todos los submundos esos de cenefas porque no se van a usar». Y
de los 22 MB de Clientes VIP: «si eso se puede hacer [sin perder la
información] estaría genial».

1. Lo que el informe de cenefas necesita de cada tipo que se va —el nombre, si
   se cobra y la producción declarada (Parrilla y Vinos)— queda en
   `cenefa_destinos_borrados`: el informe es lo que se factura y da lo mismo
   antes y después, para cualquier período (ver services/cenefas/informe.py).
   Las corridas no se tocan: el mundo y el nombre de la plantilla viven en cada
   una (`categoria`, `template_nombre`, 0046), y su template_id pasa a NULL
   (ON DELETE SET NULL).
2. Se borran las plantillas que no son de un tipo del mundo Redexpres (en
   producción, 35 de 41; las 41 ocupaban 38,7 MB) y los tipos de cenefa que no
   son del mundo Redexpres (12 de 13). La última corrida con una plantilla de
   Tienda Inglesa fue del 16/10/2026. Las de Redexpres quedan tal cual.
3. Se compacta (VACUUM FULL) lo que quedó con lugar muerto y pesa más de 1 MB:
   las plantillas, las corridas (el SET NULL reescribe sus filas) y las tablas
   de Clientes VIP. La recarga del 26/11 de 2025 y enero-octubre 2026 dejó
   22 MB de filas reemplazadas: vip_cliente_mes pasó de 37,4 a 58,8 MB con los
   mismos datos. Desde ahora cada carga compacta sola lo que reemplaza (ver
   terminar_carga en app/api/routes/clientes_vip.py).
   - Primero espera (hasta 30 s) a que terminen las transacciones que podían
     ver lo borrado: VACUUM FULL copia lo que alguien todavía puede ver, y un
     pedido a mitad de camino al publicar dejaba la tabla del mismo tamaño.
   - Va con SKIP_LOCKED: no hace fila detrás de quien esté usando la tabla
     (mientras corre traba hasta las lecturas); si está en uso, se reintenta
     un par de veces y si no, queda para la próxima. No hay `SET
     lock_timeout`: con el pooler de Supabase en modo transacción podría ir a
     otra conexión que el VACUUM.
   - Compactar no es imprescindible: si algo falla, queda en el log y la
     migración sigue.

Irreversible: las plantillas borradas no vuelven (no hay copia en la base). El
downgrade devuelve los tipos de cenefa —vacíos, sin plantillas— desde
cenefa_destinos_borrados, para que el informe del código anterior, que los lee
de cenefa_destinos, siga dando lo mismo; y borra esa tabla.

Revision ID: 0094
Revises: 0093
Create Date: 2026-11-26
"""
import logging
import time

import sqlalchemy as sa
from alembic import op

revision = "0094"
down_revision = "0093"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

# El mundo de la plataforma que se queda con sus cenefas (app/core/mundos.py).
MUNDO_QUE_QUEDA = "redexpres"

# Lo que se compacta al final, en este orden. Por nombre fijo.
A_COMPACTAR = (
    "cenefa_templates_v2", "cenefa_jobs",
    "vip_cliente_mes", "vip_clientes", "vip_mes_dimension", "vip_detalle",
)
# Una tabla más chica no vale el rato trabada (y en una base nueva no hay nada).
MINIMO_A_COMPACTAR = 1024 * 1024
ESPERA_SEGUNDOS = 30.0
INTENTOS = 3
PAUSA_SEGUNDOS = 5.0

_COLUMNAS = ("slug, nombre, descripcion, icono, color, orden, mundo, cobrable, "
             "cenefas_previas, cenefas_previas_nota, created_at")

# Lo mismo que _NADIE_VE_LO_VIEJO en app/services/espacio.py, copiado para que
# la migración no cambie si un día cambia el servicio.
_NADIE_VE_LO_VIEJO = sa.text("""
    SELECT txid_snapshot_xmin(txid_current_snapshot()) > CAST(:xid AS bigint)
       AND NOT EXISTS (
            SELECT 1 FROM pg_stat_activity
             WHERE datname = current_database() AND pid <> pg_backend_pid()
               AND backend_type <> 'autovacuum worker' AND backend_xmin IS NOT NULL
               AND age(backend_xmin) >= age(CAST(CAST(CAST(:xid AS bigint) % 4294967296 AS text) AS xid)))
""")
_MEDIR = sa.text("SELECT pg_total_relation_size(CAST(:t AS regclass)), pg_relation_filenode(CAST(:t AS regclass))")


def guardar_y_borrar(conn) -> None:
    """Los pasos 1 y 2 del docstring, en la transacción de la migración.
    Aparte para poder probarlos (tests/test_cenefas_solo_redexpres.py)."""
    conn.execute(sa.text(f"""
        INSERT INTO cenefa_destinos_borrados ({_COLUMNAS})
        SELECT {_COLUMNAS}
          FROM cenefa_destinos
         WHERE mundo <> :queda
        ON CONFLICT (slug) DO NOTHING
    """), {"queda": MUNDO_QUE_QUEDA})
    conn.execute(sa.text("""
        DELETE FROM cenefa_templates_v2
         WHERE category IS NULL
            OR category NOT IN (SELECT slug FROM cenefa_destinos WHERE mundo = :queda)
    """), {"queda": MUNDO_QUE_QUEDA})
    conn.execute(sa.text("DELETE FROM cenefa_destinos WHERE mundo <> :queda"), {"queda": MUNDO_QUE_QUEDA})


def compactar(conn, tabla: str) -> bool:
    """VACUUM FULL de `tabla` sin hacer fila (paso 3). Devuelve si se
    compactó. Nunca levanta: un error queda en el log. `conn` tiene que estar
    en AUTOCOMMIT (VACUUM no va en una transacción)."""
    for intento in range(INTENTOS):
        if intento:
            time.sleep(PAUSA_SEGUNDOS)
        try:
            antes, archivo = conn.execute(_MEDIR, {"t": tabla}).one()
            conn.execute(sa.text(f'VACUUM (FULL, SKIP_LOCKED) "{tabla}"'))
            despues, archivo_nuevo = conn.execute(_MEDIR, {"t": tabla}).one()
        except Exception as exc:
            logger.warning("0094: no se pudo compactar %s (%s): queda para la próxima", tabla, exc)
            return False
        # VACUUM FULL siempre escribe un archivo nuevo: si es el mismo, la
        # tabla estaba en uso y no se tocó.
        if archivo_nuevo != archivo:
            logger.info("0094: %s compactada de %.1f a %.1f MB", tabla, antes / 2**20, despues / 2**20)
            return True
    logger.warning("0094: %s estuvo en uso y no se compactó: queda para la próxima", tabla)
    return False


def compactar_lo_que_vale_la_pena(conn, xid: int) -> list[str]:
    """El paso 3 entero: las tablas de A_COMPACTAR de más de 1 MB, después de
    esperar a que nadie pueda ver lo que borró la transacción `xid`. Devuelve
    las que se compactaron. Nunca levanta."""
    try:
        grandes = [t for t in A_COMPACTAR if conn.execute(_MEDIR, {"t": t}).one()[0] >= MINIMO_A_COMPACTAR]
        if not grandes:
            return []
        hasta = time.monotonic() + ESPERA_SEGUNDOS
        while not conn.execute(_NADIE_VE_LO_VIEJO, {"xid": xid}).scalar():
            if time.monotonic() >= hasta:
                logger.warning("0094: sigue abierta una transacción de antes: se compacta igual "
                               "y puede quedar lugar sin devolver")
                break
            time.sleep(0.5)
    except Exception as exc:
        logger.warning("0094: no se pudo compactar (%s): queda para la próxima", exc)
        return []
    return [t for t in grandes if compactar(conn, t)]


def upgrade() -> None:
    # Repetible: lo de antes del bloque de compactar queda confirmado al
    # entrar en él, pero la versión se anota recién al final. Si el servidor se
    # reiniciara mientras compacta, la 0094 corre de nuevo y no tiene que fallar.
    if sa.inspect(op.get_bind()).has_table("cenefa_destinos_borrados"):
        logger.info("0094: cenefa_destinos_borrados ya estaba (una vuelta anterior se cortó)")
    else:
        _crear_tabla()
    guardar_y_borrar(op.get_bind())
    xid = op.get_bind().execute(sa.text("SELECT txid_current()")).scalar()
    # Al entrar al bloque, lo de arriba queda confirmado: compactar ya no lo
    # puede deshacer.
    with op.get_context().autocommit_block():
        compactar_lo_que_vale_la_pena(op.get_bind(), xid)


def _crear_tabla() -> None:
    op.create_table(
        "cenefa_destinos_borrados",
        sa.Column("slug", sa.String(50), primary_key=True),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("descripcion", sa.String(300), nullable=False, server_default=""),
        sa.Column("icono", sa.String(40), nullable=False, server_default="Store"),
        sa.Column("color", sa.String(30), nullable=False, server_default="emerald"),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mundo", sa.String(32), nullable=False, server_default="tienda_inglesa"),
        sa.Column("cobrable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("cenefas_previas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cenefas_previas_nota", sa.String(300), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("borrado_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    # Las plantillas no vuelven. Los tipos de cenefa sí, vacíos.
    op.execute(f"""
        INSERT INTO cenefa_destinos ({_COLUMNAS})
        SELECT slug, nombre, descripcion, icono, color, orden, mundo, cobrable,
               cenefas_previas, cenefas_previas_nota, COALESCE(created_at, now())
          FROM cenefa_destinos_borrados
        ON CONFLICT (slug) DO NOTHING
    """)
    op.drop_table("cenefa_destinos_borrados")

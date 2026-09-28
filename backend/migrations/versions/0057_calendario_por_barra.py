"""el calendario pasa a una fila por barra, con fechas reales, y avisos a mano

Pedido de Ivan (28/09/2026), tres cosas que el calendario tendría que haber
hecho desde el principio:

1. **Una acción que cruza de mes es UNA acción.** Hasta acá cada mes era un
   documento y cada barra iba "del día X al Y" de su mes: algo del 25/09 al
   5/10 quedaba recortado a fin de mes y había que cargarlo dos veces.
2. **Dos personas no se pisan.** Cada cambio subía el mes entero y ganaba el
   último que guardaba. Ahora cada cambio toca solo su fila.
3. **Los avisos los configura una persona.** El aviso automático de 10 días
   se apaga: "tomarlo de manera automática genera errores y la gente le va a
   dejar de dar bolilla". Cada aviso es una fila de `calendario_avisos`.

Los datos: todo lo que había en `calendario_meses` se copia a las tablas
nuevas —las barras con su mismo id, sus piezas con su estado, y las
posiciones de Retail Media de cada mes—. Lo único que no se copia es lo que se
deriva y se vuelve a calcular: los headers que bajan de Retail Media y de las
acciones, y el `sinLugar`.

`calendario_meses` NO se toca: queda como respaldo de cómo estaba todo antes
de esto.

Revision ID: 0057
Revises: 0056
Create Date: 2026-09-28
"""
from calendar import monthrange
from datetime import date

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None

_RM_POR_DEFECTO = [4, 5, 6]


def _fecha(clave: str, dia) -> date:
    """El día `dia` del mes `clave`, acomodado a los días que tiene ese mes
    (un 31 en un mes de 30 puede venir de un import)."""
    anio, mes = (int(p) for p in clave.split("-"))
    tope = monthrange(anio, mes)[1]
    try:
        n = int(dia)
    except (TypeError, ValueError):
        n = 1
    return date(anio, mes, min(max(n, 1), tope))


def convertir_meses(meses: dict[str, dict]) -> tuple[list[dict], list[dict], dict[str, list[int]]]:
    """Pasa los meses guardados a (barras, piezas, posiciones de RM).

    Pura a propósito, para poder probarla con los datos de verdad sin una base.
    No inventa ni descarta nada: cada barra guardada sale como una fila, con su
    id, su nombre, su color y sus piezas tal cual. Los headers derivados (los
    que tienen `origen` retail o accion) no son datos: se recalculan."""
    barras: list[dict] = []
    piezas: list[dict] = []
    posiciones: dict[str, list[int]] = {}
    ids_barra: set[str] = set()
    ids_pieza: set[str] = set()

    def id_unico(propuesto, usados: set[str], respaldo: str) -> str:
        base = str(propuesto) if propuesto else respaldo
        candidato, n = base, 1
        while candidato in usados:
            n += 1
            candidato = f"{base}-{n}"
        usados.add(candidato)
        return candidato

    def agregar(clave: str, seccion: str, banda: str, carril: int, barra: dict, n: int):
        desde = _fecha(clave, barra.get("desde"))
        hasta = _fecha(clave, barra.get("hasta") if barra.get("hasta") is not None else barra.get("desde"))
        if hasta < desde:
            desde, hasta = hasta, desde
        barra_id = id_unico(barra.get("id"), ids_barra, f"mig-{clave}-{seccion}-{n}")
        barras.append({
            "id": barra_id,
            "seccion": seccion,
            "banda": banda,
            "carril": carril,
            "nombre": barra.get("nombre") or "",
            "color": barra.get("color"),
            "desde": desde,
            "hasta": hasta,
        })
        for orden, p in enumerate(barra.get("piezas") or []):
            piezas.append({
                "id": id_unico(p.get("id"), ids_pieza, f"{barra_id}-pz-{orden}"),
                "barra_id": barra_id,
                "area": p.get("area") or "",
                "formato": p.get("formato") or "",
                "estado": p.get("estado") or "pendiente",
                "desde": _fecha(clave, p["desde"]) if p.get("desde") is not None else None,
                "hasta": _fecha(clave, p["hasta"]) if p.get("hasta") is not None else None,
                "hora": p.get("hora"),
                "en_sharepoint": bool(p.get("enSharePoint")),
                "orden": orden,
            })

    for clave in sorted(meses):
        datos = meses[clave] or {}
        n = 0
        for seccion in ("comercial", "retail"):
            for banda in datos.get(seccion) or []:
                nombre_banda = banda.get("nombre") or "Sin nombre"
                for carril, fila in enumerate(banda.get("filas") or []):
                    for barra in fila or []:
                        n += 1
                        agregar(clave, seccion, nombre_banda, carril, barra, n)
        for i, banda in enumerate(datos.get("header") or []):
            posicion = banda.get("id") or f"pos-{i + 1}"
            for fila in (banda.get("filas") or [])[:1]:
                for barra in fila or []:
                    if (barra.get("origen") or {}).get("tipo") in ("retail", "accion"):
                        continue
                    n += 1
                    agregar(clave, "header", posicion, 0, barra, n)
        posiciones[clave] = list(datos.get("posicionesRM") or _RM_POR_DEFECTO)

    return barras, piezas, posiciones


def upgrade() -> None:
    op.create_table(
        "calendario_barras",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("seccion", sa.String(16), nullable=False),
        sa.Column("banda", sa.Text(), nullable=False),
        sa.Column("carril", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("color", sa.String(32), nullable=True),
        sa.Column("desde", sa.Date(), nullable=False),
        sa.Column("hasta", sa.Date(), nullable=False),
        sa.Column("creado_por_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actualizado_por_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_calendario_barras_seccion", "calendario_barras", ["seccion"])
    op.create_index("ix_calendario_barras_desde", "calendario_barras", ["desde"])
    op.create_index("ix_calendario_barras_hasta", "calendario_barras", ["hasta"])

    op.create_table(
        "calendario_piezas",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("barra_id", sa.String(64), sa.ForeignKey("calendario_barras.id", ondelete="CASCADE"), nullable=False),
        sa.Column("area", sa.String(20), nullable=False),
        sa.Column("formato", sa.String(100), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="pendiente"),
        sa.Column("desde", sa.Date(), nullable=True),
        sa.Column("hasta", sa.Date(), nullable=True),
        sa.Column("hora", sa.String(5), nullable=True),
        sa.Column("en_sharepoint", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_calendario_piezas_barra_id", "calendario_piezas", ["barra_id"])

    op.create_table(
        "calendario_avisos",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("barra_id", sa.String(64), sa.ForeignKey("calendario_barras.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dias_antes", sa.Integer(), nullable=False),
        sa.Column("destinatarios", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("creado_por_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
    )
    op.create_index("ix_calendario_avisos_barra_id", "calendario_avisos", ["barra_id"])

    op.create_table(
        "calendario_posiciones_rm",
        sa.Column("clave", sa.String(7), primary_key=True),
        sa.Column("posiciones", postgresql.JSONB(), nullable=False),
        sa.Column("actualizado_por_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
    )

    op.create_table(
        "calendario_revision",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rev", sa.BigInteger(), nullable=False, server_default="0"),
    )

    conn = op.get_bind()
    conn.execute(text("INSERT INTO calendario_revision (id, rev) VALUES (1, 1)"))

    # --- Los datos de calendario_meses, copiados --------------------------
    meses = {clave: datos for clave, datos in conn.execute(
        text("SELECT clave, datos FROM calendario_meses")
    ).fetchall()}
    barras, piezas, posiciones = convertir_meses(meses)

    t_barras = sa.table(
        "calendario_barras",
        sa.column("id"), sa.column("seccion"), sa.column("banda"), sa.column("carril"),
        sa.column("nombre"), sa.column("color"), sa.column("desde"), sa.column("hasta"),
    )
    t_piezas = sa.table(
        "calendario_piezas",
        sa.column("id"), sa.column("barra_id"), sa.column("area"), sa.column("formato"),
        sa.column("estado"), sa.column("desde"), sa.column("hasta"), sa.column("hora"),
        sa.column("en_sharepoint"), sa.column("orden"),
    )
    t_posiciones = sa.table(
        "calendario_posiciones_rm",
        sa.column("clave"), sa.column("posiciones", postgresql.JSONB()),
    )
    if barras:
        op.bulk_insert(t_barras, barras)
    if piezas:
        op.bulk_insert(t_piezas, piezas)
    if posiciones:
        op.bulk_insert(t_posiciones, [{"clave": c, "posiciones": p} for c, p in posiciones.items()])

    # Que no se haya perdido nada en el camino: si no coincide, la migración
    # falla entera y Alembic deshace todo, calendario_meses incluido intacto.
    esperadas = len(barras)
    guardadas = conn.execute(text("SELECT count(*) FROM calendario_barras")).scalar()
    if guardadas != esperadas:
        raise RuntimeError(f"calendario: se esperaban {esperadas} barras y quedaron {guardadas}")
    guardadas_p = conn.execute(text("SELECT count(*) FROM calendario_piezas")).scalar()
    if guardadas_p != len(piezas):
        raise RuntimeError(f"calendario: se esperaban {len(piezas)} piezas y quedaron {guardadas_p}")


def downgrade() -> None:
    # calendario_meses nunca se tocó, así que al bajar se vuelve a lo de antes.
    # Lo que se cargó DESPUÉS de la 0057 (barras nuevas, avisos) se pierde.
    op.drop_table("calendario_revision")
    op.drop_table("calendario_posiciones_rm")
    op.drop_index("ix_calendario_avisos_barra_id", table_name="calendario_avisos")
    op.drop_table("calendario_avisos")
    op.drop_index("ix_calendario_piezas_barra_id", table_name="calendario_piezas")
    op.drop_table("calendario_piezas")
    op.drop_index("ix_calendario_barras_hasta", table_name="calendario_barras")
    op.drop_index("ix_calendario_barras_desde", table_name="calendario_barras")
    op.drop_index("ix_calendario_barras_seccion", table_name="calendario_barras")
    op.drop_table("calendario_barras")

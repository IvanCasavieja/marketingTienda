"""una tarea = un pedido: todas en un solo nivel, con su responsable de Tienda

Ivan (24/11/2026): "las tareas y el pedido de piezas deberían ser uno,
entendés? sería simplemente tarea nueva pum poner los banners y descripción
o lo que sea que estemos pidiendo, pero tener así dividido en tarea, pedido
de piezas y luego subtareas me parece al pedo y confuso".

Hasta acá, "Nueva tarea" creaba una tarea de afuera ("Digital", con el
detalle, los archivos y el responsable de Tienda) y adentro una pieza por
cada cosa pedida ("TiendaChecks Emisión - Banners", la tarjeta de Publicis),
y además había subtareas. Desde ahora cada tarea es un pedido, en el primer
nivel. Esta migración:

1. Suma `calendario_tareas.responsable_id`: quién la lleva por Tienda cuando
   la hace una agencia (antes, la persona asignada a la tarea de afuera).
2. Aplana lo que ya existe, sin importar cuántos niveles haya:
   - Cada pieza (con tipo, para una agencia, o con su tarjeta) pasa al primer
     nivel, en el lugar de su tarea de afuera. Si no tenía detalle, se queda
     con el de afuera; si la hace una agencia y no tiene responsable, el
     responsable es la persona asignada afuera (si es del equipo); y se
     queda con los archivos de afuera (si son varias piezas, cada una con su
     copia).
   - La tarea de afuera se borra si era solo un envoltorio: no es pieza y
     tenía piezas adentro. Sus subtareas, y cualquier subtarea suelta, pasan
     al primer nivel, detrás de la tarea de la que colgaban.
   - Los avisos de la campanita que hablaban de una tarea borrada se borran
     (como en la 0085): llevarían a nada.
   - Las plantillas guardadas se aplanan igual.

Downgrade: saca la columna, pero lo aplanado NO vuelve a anidarse (ni vuelven
las tareas de afuera borradas): no es reversible.

Revision ID: 0090
Revises: 0089
Create Date: 2026-11-24
"""
from __future__ import annotations

import json
import secrets

import sqlalchemy as sa
from alembic import op

revision = "0090"
down_revision = "0089"
branch_labels = None
depends_on = None


# --- Lo puro (se prueba sin base: tests/test_una_tarea_un_pedido.py) --------

def es_pieza(t: dict, con_tarjeta: set[str] | frozenset = frozenset()) -> bool:
    """Una pieza: tiene tipo, la hace una agencia (de la plataforma o de
    afuera) o ya tiene su tarjeta (entregas)."""
    return bool(t.get("tipo")) or t.get("para") in ("agencia", "fuera") or t.get("id") in con_tarjeta


def aplanar(tareas: list[dict], con_tarjeta: set[str], externos: set[int]) -> dict:
    """Qué hacer con las tareas de UNA base para dejarlas en un solo nivel.

    `tareas`: dicts con id, barra_id, parent_id, descripcion, asignado_a_id,
    responsable_id, para, tipo y orden. `con_tarjeta`: las que tienen entregas.
    `externos`: ids de cuentas de agencias (no pueden ser responsables de
    Tienda).

    Devuelve:
    - cambios: {id: {columna: valor}} para las que quedan (parent_id a None,
      el detalle o el responsable heredados, el orden nuevo);
    - borrar: los ids de los envoltorios;
    - archivos: {id del envoltorio: [ids de las piezas que se quedan con sus
      archivos]}, en orden.
    Las acciones sin nada anidado no se tocan. Pura."""
    por_id = {t["id"]: t for t in tareas}
    hijas: dict[str | None, list[dict]] = {}
    for t in tareas:
        padre = t.get("parent_id") if t.get("parent_id") in por_id else None
        hijas.setdefault(padre, []).append(t)
    for lista in hijas.values():
        lista.sort(key=lambda t: (t.get("orden") or 0, t["id"]))

    def descendientes(tid: str) -> list[dict]:
        out, pila, vistos = [], list(hijas.get(tid, [])), {tid}
        while pila:
            h = pila.pop()
            if h["id"] in vistos:
                continue
            vistos.add(h["id"])
            out.append(h)
            pila.extend(hijas.get(h["id"], []))
        return out

    def ancestros(t: dict) -> list[dict]:
        """De la más cercana a la más lejana."""
        out, vistos, actual = [], {t["id"]}, t.get("parent_id")
        while actual in por_id and actual not in vistos:
            vistos.add(actual)
            out.append(por_id[actual])
            actual = por_id[actual].get("parent_id")
        return out

    anidadas = {t["id"] for t in tareas if t.get("parent_id") in por_id}
    if not anidadas:
        return {"cambios": {}, "borrar": [], "archivos": {}}

    borrar = [
        t["id"] for t in tareas
        if not es_pieza(t, con_tarjeta) and hijas.get(t["id"])
        and any(es_pieza(d, con_tarjeta) for d in descendientes(t["id"]))
    ]
    borrar_set = set(borrar)

    cambios: dict[str, dict] = {}
    archivos: dict[str, list[str]] = {}
    for t in tareas:
        if t["id"] in borrar_set:
            continue
        cambio: dict = {}
        if t["id"] in anidadas:
            cambio["parent_id"] = None
        if es_pieza(t, con_tarjeta):
            arriba = [a for a in ancestros(t) if not es_pieza(a, con_tarjeta)]
            if not (t.get("descripcion") or "").strip():
                detalle = next(((a.get("descripcion") or "").strip() for a in arriba if (a.get("descripcion") or "").strip()), "")
                if detalle:
                    cambio["descripcion"] = detalle
            if t.get("para") in ("agencia", "fuera") and t.get("responsable_id") is None:
                quien = next((a["asignado_a_id"] for a in arriba
                              if a.get("asignado_a_id") is not None and a["asignado_a_id"] not in externos), None)
                if quien is not None:
                    cambio["responsable_id"] = quien
            for a in arriba:
                if a["id"] in borrar_set:
                    archivos.setdefault(a["id"], []).append(t["id"])
        if cambio:
            cambios[t["id"]] = cambio

    # El orden nuevo, en las acciones que tenían algo anidado: recorriendo el
    # árbol como se veía (cada tarea y debajo lo suyo), sin los envoltorios.
    # Así cada pieza queda donde estaba su tarea de afuera.
    barras = {por_id[i]["barra_id"] for i in anidadas}
    for barra in barras:
        orden = 0
        raices = [t for t in hijas.get(None, []) if t["barra_id"] == barra]
        pila = list(reversed(raices))
        vistos: set[str] = set()
        while pila:
            t = pila.pop()
            if t["id"] in vistos:
                continue
            vistos.add(t["id"])
            if t["id"] not in borrar_set:
                if (t.get("orden") or 0) != orden:
                    cambios.setdefault(t["id"], {})["orden"] = orden
                orden += 1
            pila.extend(reversed(hijas.get(t["id"], [])))
    return {"cambios": cambios, "borrar": borrar, "archivos": archivos}


def aplanar_plantilla(tareas: list[dict]) -> list[dict]:
    """Las tareas de una plantilla guardada, en un solo nivel, con la misma
    regla que las tareas de verdad (en una plantilla había un nivel nomás).
    Pura: devuelve una lista nueva."""
    ids = {t.get("id") for t in tareas}
    hijas: dict[str, list[dict]] = {}
    for t in tareas:
        if t.get("parentId") in ids and t.get("parentId") != t.get("id"):
            hijas.setdefault(t["parentId"], []).append(t)
    raices = [t for t in tareas if not (t.get("parentId") in ids and t.get("parentId") != t.get("id"))]
    out: list[dict] = []
    for r in raices:
        suyas = hijas.get(r.get("id"), [])
        envoltorio = not es_pieza(r) and any(es_pieza(h) for h in suyas)
        if not envoltorio:
            out.append({**r, "parentId": None})
        for h in suyas:
            nueva = {**h, "parentId": None}
            if envoltorio and es_pieza(h):
                if not (h.get("descripcion") or "").strip() and (r.get("descripcion") or "").strip():
                    nueva["descripcion"] = r["descripcion"]
                if h.get("para") in ("agencia", "fuera") and nueva.get("responsable") is None and r.get("asignadoA") is not None:
                    nueva["responsable"] = r["asignadoA"]
            out.append(nueva)
    return out


# --- Lo de la base ---------------------------------------------------------------

def upgrade() -> None:
    op.add_column(
        "calendario_tareas",
        sa.Column("responsable_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_calendario_tareas_responsable_id", "calendario_tareas", ["responsable_id"])

    con = op.get_bind()
    tareas = [dict(f._mapping) for f in con.execute(sa.text(
        "SELECT id, barra_id, parent_id, descripcion, asignado_a_id, responsable_id, para, tipo, orden"
        " FROM calendario_tareas"
    ))]
    con_tarjeta = {f[0] for f in con.execute(sa.text("SELECT tarea_id FROM calendario_entregas"))}
    externos = {f[0] for f in con.execute(sa.text("SELECT id FROM users WHERE es_externo"))}
    plan = aplanar(tareas, con_tarjeta, externos)

    # 1. Las que quedan: sueltas, con lo heredado y su orden. Primero esto:
    # borrar un envoltorio se llevaría en cascada lo que todavía cuelgue de él.
    for tid, cambio in plan["cambios"].items():
        columnas = ", ".join(f"{c} = :{c}" for c in cambio)
        con.execute(sa.text(f"UPDATE calendario_tareas SET {columnas} WHERE id = :id"), {**cambio, "id": tid})

    # 2. Los archivos de cada envoltorio: a la primera pieza se le pasan, a
    # las demás se les copian.
    for envoltorio, piezas in plan["archivos"].items():
        ids = [f[0] for f in con.execute(
            sa.text("SELECT id FROM calendario_adjuntos WHERE tarea_id = :t ORDER BY created_at, id"), {"t": envoltorio},
        )]
        for adjunto in ids:
            for pieza in piezas[1:]:
                con.execute(sa.text(
                    "INSERT INTO calendario_adjuntos (id, tarea_id, nombre, tipo_mime, tamano, datos, subido_por_id, created_at)"
                    " SELECT :nuevo, :pieza, nombre, tipo_mime, tamano, datos, subido_por_id, created_at"
                    " FROM calendario_adjuntos WHERE id = :id"
                ), {"nuevo": f"ad-{secrets.token_hex(8)}", "pieza": pieza, "id": adjunto})
            con.execute(sa.text("UPDATE calendario_adjuntos SET tarea_id = :pieza WHERE id = :id"),
                        {"pieza": piezas[0], "id": adjunto})

    # 3. Los envoltorios. Ya no les cuelga nada.
    for tid in plan["borrar"]:
        con.execute(sa.text("DELETE FROM calendario_tareas WHERE id = :id"), {"id": tid})

    # 4. Los avisos que hablaban de una tarea que ya no existe.
    if plan["borrar"]:
        con.execute(sa.text(
            """DELETE FROM notificaciones n
               WHERE n.origen_tipo IN ('calendario_tarea', 'calendario_entrega')
                 AND NOT EXISTS (
                   SELECT 1 FROM calendario_tareas t WHERE t.id = split_part(n.origen_ref, ':', 2)
                 )"""
        ))

    # 5. Las plantillas guardadas.
    for pid, tareas_pl in con.execute(sa.text("SELECT id, tareas FROM calendario_plantillas")).all():
        lista = tareas_pl if isinstance(tareas_pl, list) else json.loads(tareas_pl or "[]")
        if not any(isinstance(t, dict) and t.get("parentId") for t in lista):
            continue
        nuevas = aplanar_plantilla([t for t in lista if isinstance(t, dict)])
        con.execute(sa.text("UPDATE calendario_plantillas SET tareas = CAST(:t AS JSONB) WHERE id = :id"),
                    {"t": json.dumps(nuevas, ensure_ascii=False), "id": pid})

    # Que las pantallas abiertas (de todos los mundos) se enteren.
    if plan["cambios"] or plan["borrar"]:
        rev = con.execute(sa.text("UPDATE calendario_revision SET rev = rev + 1 WHERE id = 1 RETURNING rev")).scalar()
        if rev is not None:
            con.execute(sa.text("UPDATE calendario_revision_mundo SET rev = :rev"), {"rev": rev})


def downgrade() -> None:
    # Solo la columna: lo aplanado no vuelve a anidarse (ver arriba).
    op.drop_index("ix_calendario_tareas_responsable_id", table_name="calendario_tareas")
    op.drop_column("calendario_tareas", "responsable_id")

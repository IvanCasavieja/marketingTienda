from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from app.core.deps import get_current_user, require_permission
from app.core.database import get_db
from app.models.user import User
from app.models.planilla_pedido import PlanillaPedido, RedexpresEstructura
from app.services import redexpres_estructura as est
from app.models.local_asignacion import LocalAsignacion

router = APIRouter(prefix="/redexpres", tags=["redexpres"])

LOCALES: list[str] = [
    "Nativo Florida",
    "Abast. Nativo B. Blancos (1000)",
    "Abast. Almenara (800)",
    "Abast. Ecomarket 3 (680)",
    "Abast. Del sol (780)",
    "Gatti (600)",
    "El Tio 1 (500)",
    "Frigo Yaro (400)",
    "Super 2 Hermanos (476)",
    "ALTOSUR 4 (545)",
    "SUPER 18 -1 (560)",
    "CARNETEL (500)",
    "Costa Verde (600)",
    "EXPRES 1 (480)",
    "El Morro (480)",
    "Fuentes (500)",
    "Nativo Suarez (400)",
    "MAROÑAS (366)",
    "Abast. San Ramón (393)",
    "Super Uno 1 (503)",
    "ABAST. SUPERMERCADO DONATO (380)",
    "Super Rodi (400)",
    "AVENIDA NORTE - SAN JOSE (600)",
    "ALTOSUR 1 (425)",
    "Frigo Centro (300)",
    "CARROUSELL (310)",
    "FLORESTA",
    "ARIEL 2 - MILLAN Y RAFFO (297)",
    "El Tio 2 (270)",
    "PINAMAR (290)",
    "Abast. La Cueva (300)",
    "El Tano (300)",
    "EXPRES 8 (330)",
    "Jardines (130)",
    "Abast. Hiperprecios (300)",
    "EXPRES 7 (295)",
    "Kampante (300)",
    "EXPRES 3 (250)",
    "EXPRES 6 (340)",
    "Comva (300)",
    "Abast. Santa Rosa (330)",
    "Super Uno 2 (270)",
    "AVENIDA MOLINO - SAN JOSE (200)",
    "AVENIDA SUR - SAN JOSE (300)",
    "SANTA CECILIA - SAN JOSE (225)",
    "SUPER 18 -2 (320)",
    "PAZ PLAZA - LA PAZ (300)",
    "L.A. DE HERRERA Y RAÑA (189)",
    "Prisma (228)",
    "DONATO EXPRESS (250)",
    "RED EXPRES NUEVO PARIS (245)",
    "AVENIDA CENTRO - SAN JOSE (200)",
    "ALTOSUR 6 (200)",
    "ALTOSUR 5 (230)",
    "OCHOA24 - SAN JOSE (100)",
    "ALTOSUR 2 (68)",
    "ALTOSUR 3 (90)",
    "PANDO",
    "JOY PANDO",
    "La Familia",
]

LOCALES_SET = set(LOCALES)


class PlanillaRowUpdate(BaseModel):
    # Topes por sucursal (no es un pool compartido entre locales) según la
    # lista de máximos por ítem que definió el negocio. Rechaza con 422 si
    # se supera — el frontend además clampea antes de llegar a guardar.
    a4_oferta_vertical: Optional[int] = Field(default=None, ge=0)
    cenefa_oferta_x3: Optional[int] = Field(default=None, ge=0)
    pinchos: Optional[int] = Field(default=None, ge=0)
    afiche_54x74: Optional[int] = Field(default=None, ge=0)
    cenefa_valle_del_sol: Optional[int] = Field(default=None, ge=0)
    cenefa_supremo_hogar: Optional[int] = Field(default=None, ge=0)
    bombas_3xa4: Optional[int] = Field(default=None, ge=0)
    bombas_a4: Optional[int] = Field(default=None, ge=0)
    bombas_74x54: Optional[int] = Field(default=None, ge=0)
    pinchos_bombas: Optional[int] = Field(default=None, ge=0)
    sticker_valle_del_sol: Optional[int] = Field(default=None, ge=0)
    sticker_carne: Optional[int] = Field(default=None, ge=0)
    cenefas_preciazos: Optional[int] = Field(default=None, ge=0)        # Cenefas 3xA4 Preciazos
    cenefas_a4_preciazos: Optional[int] = Field(default=None, ge=0)
    afiche_super_ahorro: Optional[int] = Field(default=None, ge=0)       # Afiche A4 Super Ahorro
    afiche_grande_preciazos: Optional[int] = Field(default=None, ge=0)
    pinchos_dias_expres: Optional[int] = Field(default=None, ge=0)
    hojas_amarillas: Optional[str] = None
    otros: Optional[str] = None
    # Columnas que agregó quien arma la planilla del mes (clave -> valor).
    extras: Optional[dict[str, Optional[int | str]]] = None


def _row_to_dict(row: PlanillaPedido, can_edit: bool) -> dict:
    return {
        "id": row.id,
        "local_nombre": row.local_nombre,
        "year": row.year,
        "month": row.month,
        "a4_oferta_vertical": row.a4_oferta_vertical,
        "cenefa_oferta_x3": row.cenefa_oferta_x3,
        "pinchos": row.pinchos,
        "afiche_54x74": row.afiche_54x74,
        "cenefa_valle_del_sol": row.cenefa_valle_del_sol,
        "cenefa_supremo_hogar": row.cenefa_supremo_hogar,
        "bombas_3xa4": row.bombas_3xa4,
        "bombas_a4": row.bombas_a4,
        "bombas_74x54": row.bombas_74x54,
        "pinchos_bombas": row.pinchos_bombas,
        "sticker_valle_del_sol": row.sticker_valle_del_sol,
        "sticker_carne": row.sticker_carne,
        "cenefas_preciazos": row.cenefas_preciazos,
        "cenefas_a4_preciazos": row.cenefas_a4_preciazos,
        "afiche_super_ahorro": row.afiche_super_ahorro,
        "afiche_grande_preciazos": row.afiche_grande_preciazos,
        "pinchos_dias_expres": row.pinchos_dias_expres,
        "hojas_amarillas": row.hojas_amarillas,
        "otros": row.otros,
        "extras": row.extras or {},
        "confirmado": row.confirmado,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "can_edit": can_edit,
    }


async def _estructura_de(db: AsyncSession, year: int, month: int) -> dict:
    fila = (await db.execute(
        select(RedexpresEstructura).where(RedexpresEstructura.year == year, RedexpresEstructura.month == month)
    )).scalar_one_or_none()
    return fila.estructura if fila else est.por_defecto()


def _es_gestor(user: User) -> bool:
    """Perfil completo de Redexpres (Ivan, 08/10/2026): ver y editar el pedido
    de CUALQUIER sucursal. Lo tienen los superusuarios y quien tenga el permiso
    redexpres.manage (Lucía y Valentina). Antes solo los superusuarios, y ellas
    dos, que no lo son, no podían tocar el pedido de ninguna sucursal."""
    return bool(user.is_superuser) or "redexpres.manage" in (user.permissions or [])


async def _get_user_locals(db: AsyncSession, user_id: int) -> set[str]:
    result = await db.execute(
        select(LocalAsignacion.local_nombre).where(LocalAsignacion.user_id == user_id)
    )
    return set(result.scalars().all())


# ── Public endpoints ──────────────────────────────────────────────────────────

@router.get("/locales")
async def get_locales(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("redexpres.view")),
):
    result = await db.execute(select(LocalAsignacion))
    asigs = result.scalars().all()
    asig_map: dict[str, list[int]] = {}
    for a in asigs:
        asig_map.setdefault(a.local_nombre, []).append(a.user_id)
    return [{"local_nombre": loc, "user_ids": asig_map.get(loc, [])} for loc in LOCALES]


@router.get("/meses")
async def get_meses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PlanillaPedido.year, PlanillaPedido.month)
        .distinct()
        .order_by(PlanillaPedido.year, PlanillaPedido.month)
    )
    return [{"year": r.year, "month": r.month} for r in result.all()]


@router.post("/meses")
async def crear_mes(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("redexpres.manage")),
):
    year = int(data.get("year", 0))
    month = int(data.get("month", 0))
    if not (1 <= month <= 12) or year < 2024:
        raise HTTPException(status_code=400, detail="year y month inválidos")

    existing = await db.execute(
        select(PlanillaPedido).where(
            PlanillaPedido.year == year, PlanillaPedido.month == month
        ).limit(1)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Este mes ya existe")

    for local in LOCALES:
        db.add(PlanillaPedido(local_nombre=local, year=year, month=month))

    # La planilla nueva arranca igual a la del mes anterior más cercano (Ivan,
    # 08/10/2026: "es la misma planilla todos los meses"); después se edita.
    tiene = (await db.execute(
        select(RedexpresEstructura.id).where(RedexpresEstructura.year == year, RedexpresEstructura.month == month)
    )).first()
    if not tiene:
        previa = (await db.execute(
            select(RedexpresEstructura)
            .where((RedexpresEstructura.year * 12 + RedexpresEstructura.month) < (year * 12 + month))
            .order_by((RedexpresEstructura.year * 12 + RedexpresEstructura.month).desc())
            .limit(1)
        )).scalar_one_or_none()
        if previa:
            db.add(RedexpresEstructura(year=year, month=month, estructura=previa.estructura, updated_by_id=current_user.id))

    await db.commit()
    return {"ok": True, "locales_created": len(LOCALES)}


@router.get("/estructura/{year}/{month}")
async def get_estructura(
    year: int,
    month: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Grupos y columnas de la planilla de ese mes. Los ven todos (las
    sucursales la necesitan para dibujar su pedido); solo la edita un gestor."""
    return {"estructura": await _estructura_de(db, year, month), "puede_editar": _es_gestor(current_user)}


@router.put("/estructura/{year}/{month}")
async def put_estructura(
    year: int,
    month: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("redexpres.manage")),
):
    """Guarda la planilla del mes: agregar, renombrar, mover o sacar grupos y
    columnas, y cambiar los topes. Sacar una columna NO borra lo que las
    sucursales ya cargaron en ella: solo deja de mostrarse."""
    if not (1 <= month <= 12) or year < 2024:
        raise HTTPException(status_code=400, detail="year y month inválidos")
    try:
        nueva = est.validar(data.get("estructura") if "estructura" in data else data)
    except est.EstructuraInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    fila = (await db.execute(
        select(RedexpresEstructura).where(RedexpresEstructura.year == year, RedexpresEstructura.month == month)
    )).scalar_one_or_none()
    if fila:
        fila.estructura = nueva
        fila.updated_by_id = current_user.id
    else:
        db.add(RedexpresEstructura(year=year, month=month, estructura=nueva, updated_by_id=current_user.id))
    await db.commit()
    return {"estructura": nueva}


@router.get("/planilla/{year}/{month}")
async def get_planilla(
    year: int,
    month: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("redexpres.view")),
):
    result = await db.execute(
        select(PlanillaPedido).where(
            PlanillaPedido.year == year,
            PlanillaPedido.month == month,
        )
    )
    rows = result.scalars().all()

    assigned = set() if _es_gestor(current_user) else await _get_user_locals(db, current_user.id)

    row_map = {r.local_nombre: r for r in rows}
    return [
        _row_to_dict(row_map[loc], _es_gestor(current_user) or loc in assigned)
        for loc in LOCALES
        if loc in row_map
    ]


@router.get("/mi-planilla/{year}/{month}")
async def get_mi_planilla(
    year: int,
    month: int,
    local: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Versión angosta de get_planilla para usuarios de sucursal — a diferencia
    de /planilla/{year}/{month} (que trae las filas de TODOS los locales y solo
    oculta el botón de editar), acá solo viajan por red la(s) fila(s) del/de
    los local(es) asignados al usuario logueado. Sin permiso redexpres.view:
    el acceso lo da directamente estar en LocalAsignacion.

    Los superadmins no tienen LocalAsignacion propia: pueden pasar ?local=X
    para inspeccionar cualquier sucursal (misma pantalla "Mi pedido", con un
    selector). Sin ese query param, ven la pantalla vacía por defecto."""
    if _es_gestor(current_user):
        if not local:
            return []
        if local not in LOCALES_SET:
            raise HTTPException(status_code=400, detail="Local no válido")
        target_locales = {local}
    else:
        assigned = await _get_user_locals(db, current_user.id)
        if not assigned:
            return []
        target_locales = assigned

    result = await db.execute(
        select(PlanillaPedido).where(
            PlanillaPedido.year == year,
            PlanillaPedido.month == month,
            PlanillaPedido.local_nombre.in_(target_locales),
        )
    )
    rows = result.scalars().all()
    return [_row_to_dict(r, True) for r in rows]


@router.patch("/planilla/{year}/{month}/{local_nombre:path}")
async def update_row(
    year: int,
    month: int,
    local_nombre: str,
    update: PlanillaRowUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _es_gestor(current_user):
        assigned = await _get_user_locals(db, current_user.id)
        if local_nombre not in assigned:
            raise HTTPException(status_code=403, detail="Sin permiso para editar este local")

    result = await db.execute(
        select(PlanillaPedido).where(
            PlanillaPedido.year == year,
            PlanillaPedido.month == month,
            PlanillaPedido.local_nombre == local_nombre,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Fila no encontrada")

    cambios = update.model_dump(exclude_unset=True)
    extras_nuevos = cambios.pop("extras", None) or {}
    cols = est.columnas(await _estructura_de(db, year, month))

    def _chequear(key: str, value):
        """El tope y el tipo salen de la planilla del mes, no de código fijo."""
        col = cols.get(key)
        if col is None:
            raise HTTPException(status_code=422, detail=f"La columna {key!r} no está en la planilla de este mes")
        if value is None:
            return None
        if col.get("texto"):
            return str(value)[:200]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise HTTPException(status_code=422, detail=f"«{col['label']}» tiene que ser un número entero desde 0")
        if col.get("max") is not None and value > col["max"]:
            raise HTTPException(status_code=422, detail=f"«{col['label']}» no puede pasar de {col['max']}")
        return value

    for field, value in cambios.items():
        if field in est.BUILTIN and value is not None:
            _chequear(field, value)
        setattr(row, field, value)
    if extras_nuevos:
        actuales = dict(row.extras or {})
        for key, value in extras_nuevos.items():
            if key in est.BUILTIN:
                raise HTTPException(status_code=422, detail=f"{key!r} es una columna fija, no va en extras")
            actuales[key] = _chequear(key, value)
        row.extras = actuales  # reasignado: el JSONB no detecta cambios internos
    row.updated_by_id = current_user.id

    await db.commit()
    await db.refresh(row)
    return _row_to_dict(row, True)


@router.post("/planilla/{year}/{month}/{local_nombre:path}/confirmar")
async def confirmar_pedido(
    year: int,
    month: int,
    local_nombre: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _es_gestor(current_user):
        assigned = await _get_user_locals(db, current_user.id)
        if local_nombre not in assigned:
            raise HTTPException(status_code=403, detail="Sin permiso para confirmar este pedido")

    result = await db.execute(
        select(PlanillaPedido).where(
            PlanillaPedido.year == year,
            PlanillaPedido.month == month,
            PlanillaPedido.local_nombre == local_nombre,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Fila no encontrada")

    row.confirmado = True
    row.confirmed_at = datetime.now(timezone.utc)
    row.updated_by_id = current_user.id

    await db.commit()
    return {"ok": True, "confirmed_at": row.confirmed_at.isoformat()}


@router.post("/planilla/{year}/{month}/{local_nombre:path}/desconfirmar")
async def desconfirmar_pedido(
    year: int,
    month: int,
    local_nombre: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("redexpres.manage")),
):
    result = await db.execute(
        select(PlanillaPedido).where(
            PlanillaPedido.year == year,
            PlanillaPedido.month == month,
            PlanillaPedido.local_nombre == local_nombre,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Fila no encontrada")

    row.confirmado = False
    row.confirmed_at = None
    await db.commit()
    return {"ok": True}


# ── Admin: asignaciones ───────────────────────────────────────────────────────

@router.get("/asignaciones")
async def get_asignaciones(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("redexpres.manage")),
):
    result = await db.execute(
        select(LocalAsignacion, User).join(User, LocalAsignacion.user_id == User.id)
    )
    return [
        {
            "id": a.id,
            "user_id": a.user_id,
            "user_email": u.email,
            "user_name": u.full_name,
            "local_nombre": a.local_nombre,
        }
        for a, u in result.all()
    ]


@router.post("/asignaciones")
async def create_asignacion(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("redexpres.manage")),
):
    user_id = data.get("user_id")
    local_nombre = data.get("local_nombre")
    if not user_id or not local_nombre:
        raise HTTPException(status_code=400, detail="user_id y local_nombre requeridos")
    if local_nombre not in LOCALES_SET:
        raise HTTPException(status_code=400, detail="Local no válido")

    existing = await db.execute(
        select(LocalAsignacion).where(
            LocalAsignacion.user_id == user_id,
            LocalAsignacion.local_nombre == local_nombre,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ya existe esta asignación")

    asig = LocalAsignacion(user_id=user_id, local_nombre=local_nombre)
    db.add(asig)
    await db.commit()
    await db.refresh(asig)
    return {"id": asig.id, "user_id": asig.user_id, "local_nombre": asig.local_nombre}


@router.delete("/asignaciones/{asig_id}")
async def delete_asignacion(
    asig_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("redexpres.manage")),
):
    result = await db.execute(select(LocalAsignacion).where(LocalAsignacion.id == asig_id))
    asig = result.scalar_one_or_none()
    if not asig:
        raise HTTPException(status_code=404, detail="No encontrada")

    await db.delete(asig)
    await db.commit()
    return {"ok": True}

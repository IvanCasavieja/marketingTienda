from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from app.core.deps import get_current_user, require_permission
from app.core.database import get_db
from app.models.user import User
from app.models.planilla_pedido import PlanillaPedido
from app.models.local_asignacion import LocalAsignacion

router = APIRouter(prefix="/redexpress", tags=["redexpress"])

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
    a4_oferta_vertical: Optional[int] = Field(default=None, ge=0, le=200)
    cenefa_oferta_x3: Optional[int] = Field(default=None, ge=0, le=300)
    pinchos: Optional[int] = Field(default=None, ge=0, le=100)
    afiche_54x74: Optional[int] = Field(default=None, ge=0, le=20)
    cenefa_valle_del_sol: Optional[int] = Field(default=None, ge=0, le=100)
    cenefa_supremo_hogar: Optional[int] = Field(default=None, ge=0, le=100)
    bombas_3xa4: Optional[int] = Field(default=None, ge=0, le=200)
    bombas_a4: Optional[int] = Field(default=None, ge=0, le=200)
    bombas_74x54: Optional[int] = Field(default=None, ge=0, le=20)
    pinchos_bombas: Optional[int] = Field(default=None, ge=0, le=100)
    sticker_valle_del_sol: Optional[int] = Field(default=None, ge=0, le=100)
    sticker_carne: Optional[int] = Field(default=None, ge=0, le=100)
    cenefas_preciazos: Optional[int] = Field(default=None, ge=0, le=100)        # Cenefas 3xA4 Preciazos
    cenefas_a4_preciazos: Optional[int] = Field(default=None, ge=0, le=100)
    afiche_super_ahorro: Optional[int] = Field(default=None, ge=0, le=10)       # Afiche A4 Super Ahorro
    afiche_grande_preciazos: Optional[int] = Field(default=None, ge=0, le=10)
    pinchos_dias_expres: Optional[int] = Field(default=None, ge=0, le=100)
    hojas_amarillas: Optional[str] = None
    otros: Optional[str] = None


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
        "confirmado": row.confirmado,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "can_edit": can_edit,
    }


async def _get_user_locals(db: AsyncSession, user_id: int) -> set[str]:
    result = await db.execute(
        select(LocalAsignacion.local_nombre).where(LocalAsignacion.user_id == user_id)
    )
    return set(result.scalars().all())


# ── Public endpoints ──────────────────────────────────────────────────────────

@router.get("/locales")
async def get_locales(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("redexpress.view")),
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
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Solo superadmins pueden crear meses")

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

    await db.commit()
    return {"ok": True, "locales_created": len(LOCALES)}


@router.get("/planilla/{year}/{month}")
async def get_planilla(
    year: int,
    month: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("redexpress.view")),
):
    result = await db.execute(
        select(PlanillaPedido).where(
            PlanillaPedido.year == year,
            PlanillaPedido.month == month,
        )
    )
    rows = result.scalars().all()

    assigned = set() if current_user.is_superuser else await _get_user_locals(db, current_user.id)

    row_map = {r.local_nombre: r for r in rows}
    return [
        _row_to_dict(row_map[loc], current_user.is_superuser or loc in assigned)
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
    los local(es) asignados al usuario logueado. Sin permiso redexpress.view:
    el acceso lo da directamente estar en LocalAsignacion.

    Los superadmins no tienen LocalAsignacion propia: pueden pasar ?local=X
    para inspeccionar cualquier sucursal (misma pantalla "Mi pedido", con un
    selector). Sin ese query param, ven la pantalla vacía por defecto."""
    if current_user.is_superuser:
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
    if not current_user.is_superuser:
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

    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
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
    if not current_user.is_superuser:
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
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Solo superadmins pueden desconfirmar")

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
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Solo superadmins")

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
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Solo superadmins")

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
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Solo superadmins")

    result = await db.execute(select(LocalAsignacion).where(LocalAsignacion.id == asig_id))
    asig = result.scalar_one_or_none()
    if not asig:
        raise HTTPException(status_code=404, detail="No encontrada")

    await db.delete(asig)
    await db.commit()
    return {"ok": True}

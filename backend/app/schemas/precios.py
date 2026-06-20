from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional


class ProductoOut(BaseModel):
    id:           int
    tienda:       str
    url:          str
    nombre:       Optional[str]
    precio:       Optional[float]
    precio_lista: Optional[float]
    sku:          Optional[str]
    barcode:      Optional[str]
    marca:        Optional[str]
    categoria:    Optional[str]
    actualizado_en: Optional[datetime]

    model_config = {"from_attributes": True}


class ProductoSyncItem(BaseModel):
    """Un ítem del payload de sync. Permite actualizado_en como string ISO o datetime."""
    tienda:       str
    url:          str
    nombre:       Optional[str]  = None
    precio:       Optional[float] = None
    precio_lista: Optional[float] = None
    sku:          Optional[str]  = None
    barcode:      Optional[str]  = None
    marca:        Optional[str]  = None
    categoria:    Optional[str]  = None
    actualizado_en: Optional[str] = None   # ISO string "YYYY-MM-DDTHH:MM:SS"

    @field_validator("url")
    @classmethod
    def url_no_vacia(cls, v: str) -> str:
        if not v or not v.startswith("http"):
            raise ValueError("url inválida")
        return v


class SyncPayload(BaseModel):
    productos: list[ProductoSyncItem]


class SyncResult(BaseModel):
    upsertados: int
    total_enviados: int


class PreciosListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ProductoOut]

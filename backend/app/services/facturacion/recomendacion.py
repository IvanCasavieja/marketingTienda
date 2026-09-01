"""Cuenta recomendada por proveedor recurrente.

La regla nace del historial 2026: si un proveedor facturo en 2+ meses y
siempre a la misma cuenta, esa cuenta se recomienda sola al subir un PDF
suyo. Es la version deterministica de la cuenta_sugerida que DogTi adivina
leyendo el PDF -- cuando las dos existen, la recomendacion pisa a la
sugerencia, porque historial real le gana a una lectura del membrete.

El match es por nombre normalizado y, si no hay exacto, por similitud:
max(token_sort_ratio, token_set_ratio) >= 80. El umbral salio de medir los
pares reales del historial: las variantes del mismo proveedor dan 82.9-100
("CEPELINI FIORELLA" / "CEPPELINI GATTO FIORELLA" = 82.9; "HENDERSON" es
subconjunto de "HENDERSON Y CIA S A" y el set_ratio lo da 100) y el peor
par de proveedores DISTINTOS dio 76.2 (GEOCOM URUGUAY / INFONEGOCIOS
URUGUAY). Un match errado igual no carga nada solo: la cuenta queda
preseleccionada y la persona aprueba.
"""
import re
import unicodedata

from sqlalchemy import select

from app.models.facturacion_cuenta import FacturacionCuenta
from app.models.facturacion_proveedor_cuenta import FacturacionProveedorCuenta

_UMBRAL_SIMILITUD = 80


def normalizar_proveedor(nombre: str) -> str:
    """Mayusculas, sin tildes ni puntuacion, espacios colapsados."""
    s = unicodedata.normalize("NFKD", nombre or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9 ]+", " ", s.upper())
    return re.sub(r"\s+", " ", s).strip()


def elegir_cuenta(proveedor: str, mapeo: list[tuple[str, str]]) -> str | None:
    """El nombre de cuenta para este proveedor, o None si no hay match.

    `mapeo`: [(proveedor_normalizado, nombre_cuenta), ...]. Primero exacto;
    sin exacto, el mejor por similitud si supera el umbral. Funcion pura
    para poder testearla sin base.
    """
    objetivo = normalizar_proveedor(proveedor)
    if not objetivo:
        return None
    for prov, cuenta in mapeo:
        if prov == objetivo:
            return cuenta

    from rapidfuzz import fuzz

    mejor, mejor_score = None, 0.0
    for prov, cuenta in mapeo:
        score = max(fuzz.token_sort_ratio(objetivo, prov),
                    fuzz.token_set_ratio(objetivo, prov))
        if score > mejor_score:
            mejor, mejor_score = cuenta, score
    return mejor if mejor_score >= _UMBRAL_SIMILITUD else None


async def cuenta_recomendada(db, proveedor: str | None) -> str | None:
    """Nombre de la cuenta recomendada para este proveedor, o None.

    Solo cuentas activas: si la cuenta del mapeo se desactivo, no se
    recomienda nada y la persona elige a mano.
    """
    if not proveedor:
        return None
    filas = (await db.execute(
        select(FacturacionProveedorCuenta.proveedor, FacturacionCuenta.nombre)
        .join(FacturacionCuenta,
              FacturacionCuenta.id == FacturacionProveedorCuenta.cuenta_id)
        .where(FacturacionCuenta.activa.is_(True))
    )).all()
    return elegir_cuenta(proveedor, [(r.proveedor, r.nombre) for r in filas])

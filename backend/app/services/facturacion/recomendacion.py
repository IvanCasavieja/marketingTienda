"""Cuenta recomendada por proveedor recurrente.

La regla nace del historial 2026: si un proveedor facturo en 2+ meses y
siempre a la misma cuenta, esa cuenta se recomienda sola al subir un PDF
suyo. Es la version deterministica de la cuenta_sugerida que DogTi adivina
leyendo el PDF -- cuando las dos existen, la recomendacion pisa a la
sugerencia, porque historial real le gana a una lectura del membrete.

El match es por nombre normalizado y, si no hay exacto, por similitud
ESTRICTAMENTE mayor a 80, comparando el NUCLEO del nombre -- sin tokens de
una letra ni sufijos societarios (SA, SRL, SAS, LTDA...). Sin ese recorte,
"DENA S A" y "DEVON S A" (dos empresas distintas) daban 82.4 solo por
compartir el sufijo. El modo subconjunto (token_set_ratio, que da 100
cuando un nucleo esta contenido en otro) solo se admite si el nucleo mas
corto es distintivo -- 2+ tokens o un token de 8+ letras: "HENDERSON"
adentro de "HENDERSON Y CIA" si, pero "FILMS" adentro de "KAFKA FILMS" no.
El umbral estricto (>80, no >=) salio de medir pares reales: la variante
legitima "CEPELINI FIORELLA"/"CEPPELINI GATTO FIORELLA" da 82.9, mientras
que "PEREZ MAXIMILIANO"/"PASTOR MAXIMILIANO" (dos personas que solo
comparten el nombre de pila) da 80.0 clavado. Un match errado igual no
carga nada solo: la cuenta queda preseleccionada y la persona aprueba.
"""
import re
import unicodedata

from sqlalchemy import select

from app.models.facturacion_cuenta import FacturacionCuenta
from app.models.facturacion_proveedor_cuenta import FacturacionProveedorCuenta

_UMBRAL_SIMILITUD = 80
_SUFIJOS = {"SA", "SRL", "SAS", "LTDA", "LTD", "INC", "CIA"}


def normalizar_proveedor(nombre: str) -> str:
    """Mayusculas, sin tildes ni puntuacion, espacios colapsados."""
    s = unicodedata.normalize("NFKD", nombre or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9 ]+", " ", s.upper())
    return re.sub(r"\s+", " ", s).strip()


def _nucleo(nombre_norm: str) -> str:
    """El nombre sin tokens de una letra ni sufijos societarios.

    "S.A." normalizado queda como los tokens "S" y "A": comparar con eso
    adentro hace que dos empresas cortas distintas parezcan iguales. Si el
    recorte deja vacio (ej. "H CIA S R L"), se devuelve el nombre entero:
    mejor comparar con ruido que no comparar nada."""
    tokens = [t for t in nombre_norm.split()
              if len(t) > 1 and t not in _SUFIJOS]
    return " ".join(tokens) or nombre_norm


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

    def _score(a: str, b: str) -> float:
        s = fuzz.token_sort_ratio(a, b)
        corto = a if len(a) <= len(b) else b
        if " " in corto or len(corto) >= 8:
            s = max(s, fuzz.token_set_ratio(a, b))
        return s

    nucleo_objetivo = _nucleo(objetivo)
    mejor, mejor_score = None, 0.0
    # El orden de `mapeo` decide los empates (score estrictamente mayor
    # para reemplazar): el caller lo pasa ordenado para que la misma
    # factura reciba siempre la misma recomendacion.
    for prov, cuenta in mapeo:
        score = _score(nucleo_objetivo, _nucleo(prov))
        if score > mejor_score:
            mejor, mejor_score = cuenta, score
    return mejor if mejor_score > _UMBRAL_SIMILITUD else None


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
        # Orden estable: sin esto, un empate de score podia recomendar una
        # cuenta distinta en cada request.
        .order_by(FacturacionProveedorCuenta.proveedor)
    )).all()
    return elegir_cuenta(proveedor, [(r.proveedor, r.nombre) for r in filas])

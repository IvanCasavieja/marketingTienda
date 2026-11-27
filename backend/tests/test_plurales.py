"""Los plurales de toda la app y la casilla de cuenta automática (27/11/2026).

«15 permiso», «16 registro»: i18next 23 elige el plural con `_one` /
`_other`, y nueve claves seguían con `_plural` (el formato de i18next 20),
que hoy se ignora: con cualquier número salía el singular. Se lee el fuente
del frontend como texto, igual que test_rrss_pantalla, así corre con el resto
de la suite sin Node ni build.

Y la casilla del alta de usuario decía «Cuenta de agente… como la de
Valentina»: quien da de alta no sabe qué es un «agente» ni quién es Valentina.
Ahora dice que es una cuenta automática, que no es una persona.

SI UN TEST DE ACÁ FALLA no hay que "arreglar el test": volvió el bug.
"""
from __future__ import annotations

import json
import pathlib
import re

_RAIZ = pathlib.Path(__file__).resolve().parents[2]
_FRONT = _RAIZ / "frontend"
_LOCALES = _FRONT / "lib" / "locales"
_IDIOMAS = ("es", "en", "pt")

# Las nueve claves que estaban con `_plural`, con el archivo que las muestra.
_ARREGLADAS = {
    "admin.roles.permCount": "app/(dashboard)/admin/page.tsx",
    "admin.roleEditor.permsSelected": "app/(dashboard)/admin/page.tsx",
    "admin.auditLog.entryCount": "app/(dashboard)/admin/AuditLogTab.tsx",
    "facturacion.upload.analyze": "components/facturacion/FacturaUploadModal.tsx",
    "facturacion.upload.processing": "components/facturacion/FacturaUploadModal.tsx",
    "diccionario.totalCount": "app/(dashboard)/materiales/diccionario/page.tsx",
    "precios.chainNoData": "app/(dashboard)/precios/page.tsx",
    "precios.listas.productCount": "app/(dashboard)/precios/listas/page.tsx",
}
# `convertidor.merge.bannerTitle` (duplicados de productos) hoy no lo muestra ninguna pantalla;
# igual se arregló en los JSON, por si vuelve.

# Un `_other` sin `_one` ni clave base sale en crudo con count=1. Solo vale
# cuando la pantalla nunca lo pide con 1.
_SOLO_CON_MAS_DE_UNO = {
    # Revisor.tsx lo usa solo si `otras > 0`: siempre faltan 2 o más piezas.
    "calendario.revisar.faltanAlAprobarYOtras",
}


def _planas(idioma: str) -> dict[str, str]:
    datos = json.loads((_LOCALES / f"{idioma}.json").read_text(encoding="utf-8"))
    salida: dict[str, str] = {}

    def recorrer(nodo: dict, prefijo: str) -> None:
        for clave, valor in nodo.items():
            if isinstance(valor, dict):
                recorrer(valor, f"{prefijo}{clave}.")
            else:
                salida[f"{prefijo}{clave}"] = valor

    recorrer(datos, "")
    return salida


def _fuentes() -> str:
    archivos = list((_FRONT / "app").rglob("*.tsx")) + list((_FRONT / "components").rglob("*.tsx")) \
        + list((_FRONT / "lib").rglob("*.ts")) + list((_FRONT / "lib").rglob("*.tsx"))
    return "\n".join(a.read_text(encoding="utf-8") for a in archivos)


def test_no_queda_ninguna_clave_con_el_formato_viejo_de_plural():
    for idioma in _IDIOMAS:
        viejas = sorted(c for c in _planas(idioma) if c.endswith("_plural"))
        assert not viejas, (idioma, viejas, "i18next 23 ignora `_plural`: usá `_other`")


def test_cada_plural_tiene_su_singular():
    for idioma in _IDIOMAS:
        planas = _planas(idioma)
        for clave in planas:
            if not clave.endswith("_other"):
                continue
            base = clave[: -len("_other")]
            if base in _SOLO_CON_MAS_DE_UNO:
                continue
            assert base in planas or f"{base}_one" in planas, (idioma, clave, "con count=1 saldría la clave en crudo")


def test_las_nueve_claves_eligen_el_plural_en_los_tres_idiomas():
    for idioma in _IDIOMAS:
        planas = _planas(idioma)
        for clave in list(_ARREGLADAS) + ["convertidor.merge.bannerTitle"]:
            assert clave in planas and f"{clave}_other" in planas, (idioma, clave)
            assert planas[clave] != planas[f"{clave}_other"], (idioma, clave)


def test_las_pantallas_pasan_el_numero_y_no_piden_el_plural_a_mano():
    """i18next elige singular o plural solo si recibe `count`; pedir
    `X_plural` (o `X_other`) a mano saltea la regla de cada idioma."""
    for clave, archivo in _ARREGLADAS.items():
        fuente = (_FRONT / archivo).read_text(encoding="utf-8")
        assert re.search(rf't\("{re.escape(clave)}",\s*\{{\s*count:', fuente), (clave, archivo)
    assert not re.search(r't\(["\'][\w.]+_(plural|other|one)["\']', _fuentes()), "se pide una forma del plural a mano"


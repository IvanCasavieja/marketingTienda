"""El estándar por formato de las cenefas TI, como reglas fijas.

Pedido de Ivan (08/10/2026): "se supone que los formatos deberían compartir
los mismos tamaños: las 3xA4 todas los mismos tamaños, las A4 todos los mismos
tamaños, las A5... Quiero que estos escalones sean para absolutamente todas
las cenefas, reglas preestablecidas en los bloques de cada variable, dentro
de la plataforma".

Hasta hoy cada corrida medía su propia escalera (más de N caracteres -> tal
cuerpo) y la escribía en la plantilla que usaba: Limpieza terminó con unos
escalones, Non Food con otros, marca propia con otros, para el MISMO formato.
Acá hay UN estándar por formato (A4, 3xA4, A5, 6xA4), en
``app/data/escalones_por_formato.json``, y se inyecta en toda plantilla de
los mundos listados ahí en el mismo acto en que se guarda, por el mismo
mecanismo que el símbolo de promoOferta (ver reglas_fijas.py): son reglas
normales del motor, se ven en el panel marcadas como fijas, y resubir la PPT
no las borra.

Qué fija, por formato, sobre los cuadros que imprimen cada variable:

- ``descripcion``: el cuerpo BASE (el del diseño de PRODUCTOS TI: 50 pt en
  A4, 25 en 3xA4, 35 en A5, 17 en 6xA4), con una regla "si no está vacía", y
  la escalera por caracteres hacia abajo. La base está para que una
  plantilla cuyo diseño trae otro cuerpo (OFERTA GENERICA A4 viene a 70)
  imprima igual que las demás del formato.
- ``precioOferta``: el cuerpo base del número (228 / 100 / 144 / 70) y una
  escalera POR MONEDA Y POR CENTAVOS, porque "U$S 5.990" no mide lo mismo
  que "$ 599" ni "735,20" lo mismo que "735": la condición es compuesta
  (unidadMoneda es X, decimalPrecioOferta vacío o no, y precioOferta de más
  de N caracteres). Sin partir por centavos, los pocos precios con decimal
  arrastraban el cuerpo de todos los demás. Los pedazos volados del cuadro
  (el símbolo, los centavos) acompañan en proporción (ver apply_font_sizes).
- ``codigo``: el ANCHO del cuadro por cantidad de códigos (un grupo
  unificado "A - B - C" se parte hacia abajo si el cuadro no crece), capado
  al ancho de la celda. El cuerpo del código no se toca: es el único bloque
  sin regla de cuerpo (criterio de Ivan para el proyecto de estandarización).

Cómo se midió: con el motor real (detectar_solapes / detectar_desbordes),
producto por producto, sobre la unión de los listados de octubre 2026 (550
productos) contra las plantillas que comparten geometría (PRODUCTOS TI,
EXCLUSIVOS TI, TEMPORADA DE LYCP); el cuerpo válido para el formato es el
mínimo entre esas plantillas y la escalera monótona óptima sale por
programación dinámica. Las plantillas OFERTA GENERICA tienen cajas distintas
(la descripción de la 6xA4 mide 4,7 cm de ancho contra 6,6 de la referencia)
y reciben el mismo estándar: donde su caja no da, el preview lo avisa, y la
corrección es igualar la caja, no inventarle otra escalera.

Los ids de las reglas son uuid5 de (cuadro, clave): aplicar esto dos veces no
duplica nada y cambiar un número en el JSON se propaga solo en el próximo
guardado (la lista nueva reemplaza a la vieja, ver asegurar_reglas_fijas).
"""
from __future__ import annotations

import functools
import json
import uuid
from pathlib import Path
from typing import Any

_RUTA = Path(__file__).resolve().parents[2] / "data" / "escalones_por_formato.json"

# Namespace propio, distinto del de reglas_fijas: que un cuadro tenga una
# regla fija del símbolo y otra del estándar no puede dar el mismo id.
_NS_ESTANDAR = uuid.UUID("3c9d2f71-5b8e-4f0a-9e6d-1a2b3c4d5e6f")

CLAVE_BLOQUEADA = "bloqueada"
CLAVE_ESTANDAR = "estandar"   # marca en la regla: de qué formato salió

VAR_DESCRIPCION = "descripcion"
VAR_PRECIO = "precioOferta"
VAR_CODIGO = "codigo"
VAR_MONEDA = "unidadMoneda"
VAR_DECIMAL = "decimalPrecioOferta"


@functools.lru_cache(maxsize=1)
def cargar_estandar() -> dict[str, Any]:
    """El JSON del estándar, leído una vez por proceso."""
    with open(_RUTA, encoding="utf-8") as f:
        return json.load(f)


def _variables_del_componente(c: dict) -> set[str]:
    """Mismo criterio que reglas_fijas / component_renderer."""
    salida = {
        seg.get("value") for seg in (c.get("segments") or [])
        if seg.get("type") == "variable" and seg.get("value")
    }
    if c.get("variable"):
        salida.add(c["variable"])
    return salida


def formato_de(definition: dict) -> str | None:
    """La etiqueta de formato de la definición ("a4", "3xa4", "a5", "6xa4").

    Sale de donde el importador la deja: `hoja.formato_declarado`; si no,
    `master_format`; si no, el primero de `formats`.
    """
    hoja = definition.get("hoja") if isinstance(definition.get("hoja"), dict) else {}
    etiqueta = (hoja.get("formato_declarado") or definition.get("master_format")
                or next(iter(definition.get("formats") or []), None))
    return str(etiqueta).strip().lower() if etiqueta else None


def mundo_de(definition: dict, categoria: str | None = None) -> str | None:
    """El mundo (slug de cenefa_destinos) al que pertenece la plantilla.

    `categoria` manda si viene (las rutas la conocen por la fila de la tabla);
    si no, la que la definición traiga guardada.
    """
    valor = categoria or definition.get("category")
    return str(valor).strip() if valor else None


def estandar_para(definition: dict, categoria: str | None = None) -> dict | None:
    """El bloque del JSON que aplica a esta plantilla, o None si no le toca."""
    estandar = cargar_estandar()
    mundo = mundo_de(definition, categoria)
    formato = formato_de(definition)
    if not mundo or mundo not in (estandar.get("mundos") or []):
        return None
    return (estandar.get("formatos") or {}).get(formato) if formato else None


def _regla(comp_id: str, clave: str, nombre: str, condicion: dict, accion: dict, formato: str) -> dict:
    return {
        "id": str(uuid.uuid5(_NS_ESTANDAR, f"{comp_id}:{clave}")),
        "name": nombre,
        "condition": condicion,
        "action": accion,
        "target_component_id": comp_id,
        CLAVE_BLOQUEADA: True,
        CLAVE_ESTANDAR: formato,
    }


def _reglas_descripcion(comp_id: str, bloque: dict, formato: str) -> list[dict]:
    base = bloque.get("base_pt")
    salida = []
    if base:
        salida.append(_regla(comp_id, "descripcion:base",
                             f"Estándar {formato.upper()}: descripción a {base:g} pt",
                             {"field": VAR_DESCRIPCION, "operator": "is_not_empty"},
                             {"type": "set_font_size", "value": float(base)}, formato))
    for umbral, pt in bloque.get("escalera") or []:
        salida.append(_regla(comp_id, f"descripcion:>{int(umbral)}",
                             f"Estándar {formato.upper()}: descripción de más de {int(umbral)} caracteres a {pt:g} pt",
                             {"field": VAR_DESCRIPCION, "operator": "length_greater_than", "value": int(umbral)},
                             {"type": "set_font_size", "value": float(pt)}, formato))
    return salida


def _reglas_precio(comp_id: str, bloque: dict, formato: str) -> list[dict]:
    base = bloque.get("base_pt")
    salida = []
    if base:
        salida.append(_regla(comp_id, "precio:base",
                             f"Estándar {formato.upper()}: precio a {base:g} pt",
                             {"field": VAR_PRECIO, "operator": "is_not_empty"},
                             {"type": "set_font_size", "value": float(base)}, formato))
    for grupo in bloque.get("escaleras") or []:
        moneda = grupo.get("moneda") or "$"
        con_decimal = bool(grupo.get("con_decimal"))
        centavos = "con centavos" if con_decimal else "sin centavos"
        for umbral, pt in grupo.get("escalera") or []:
            salida.append(_regla(comp_id, f"precio:{moneda}:{'con' if con_decimal else 'sin'}:>{int(umbral)}",
                                 f"Estándar {formato.upper()}: precio en {moneda} {centavos} de más de {int(umbral)} caracteres a {pt:g} pt",
                                 {"operator": "and", "conditions": [
                                     {"field": VAR_MONEDA, "operator": "equals", "value": moneda},
                                     {"field": VAR_DECIMAL, "operator": "is_not_empty" if con_decimal else "is_empty"},
                                     {"field": VAR_PRECIO, "operator": "length_greater_than", "value": int(umbral)},
                                 ]},
                                 {"type": "set_font_size", "value": float(pt)}, formato))
    return salida


def _reglas_codigo(comp_id: str, bloque: dict, formato: str) -> list[dict]:
    salida = []
    for umbral, cm in bloque.get("anchos_cm") or []:
        salida.append(_regla(comp_id, f"codigo:>{int(umbral)}",
                             f"Estándar {formato.upper()}: código de más de {int(umbral)} caracteres en {cm:g} cm de ancho",
                             {"field": VAR_CODIGO, "operator": "length_greater_than", "value": int(umbral)},
                             {"type": "set_width", "value": float(cm)}, formato))
    return salida


def reglas_del_estandar(definition: dict, categoria: str | None = None) -> list[dict]:
    """Las reglas fijas del estándar para esta definición. [] si no le toca.

    Una por cuadro y por escalón, sobre los cuadros que imprimen la variable
    (en una hoja de varias cenefas, cada celda tiene su cuadro y recibe las
    suyas). Deterministas: misma plantilla, mismos ids.
    """
    bloque = estandar_para(definition, categoria)
    if not bloque:
        return []
    formato = formato_de(definition) or ""
    salida: list[dict] = []
    for comp in definition.get("components") or []:
        comp_id = comp.get("id")
        if not comp_id or comp.get("type", "text") != "text":
            continue
        usadas = _variables_del_componente(comp)
        if VAR_DESCRIPCION in usadas and bloque.get("descripcion"):
            salida += _reglas_descripcion(comp_id, bloque["descripcion"], formato)
        if VAR_PRECIO in usadas and bloque.get("precioOferta"):
            salida += _reglas_precio(comp_id, bloque["precioOferta"], formato)
        if VAR_CODIGO in usadas and bloque.get("codigo"):
            salida += _reglas_codigo(comp_id, bloque["codigo"], formato)
    return salida

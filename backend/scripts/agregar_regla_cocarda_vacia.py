"""Agrega las reglas de visibilidad que hacen que la cocarda de mecánica
("2x$XXX") desaparezca ENTERA cuando el producto no tiene mecánica
(tipoOferta vacío), en vez de dejar un cartelito suelto con el precio
repetido ("$179" sin el "2x").

Por qué hace falta un script aparte en vez de que el importer lo resuelva
solo: al separar la cocarda en cuadros de texto independientes (variables
por separado, decisión de Ivan), unidadMoneda/precioOferta/decimalPrecioOferta
de la cocarda quedan como componentes sueltos, indistinguibles a simple
vista de los MISMOS nombres de variable que usa el precio grande de abajo
(que sí tiene que seguir viéndose siempre). El motor de reglas
(rules_engine.py: evaluate_rules/apply_visibility) YA sabe ocultar un
componente según el valor de otra variable -- lo único que faltaba era
decirle CUÁLES tres componentes son los de la cocarda.

Los identifica por POSICIÓN: de todos los componentes que usan
unidadMoneda/precioOferta/decimalPrecioOferta, se queda con el más cercano a
tipoOferta (por variable) -- el de la cocarda siempre va pegado a tipoOferta
en el diseño, así que sea cual sea el layout real (A4, 3xA4, 6xA4...) el más
cercano es siempre el correcto, sin necesidad de coordenadas fijas.

Cuándo correrlo: cada vez que esta plantilla (o una nueva con el mismo
patrón de cocarda) se reimporta desde cero -- un reimport pisa `rules` con
una lista vacía, así que esta regla se pierde y hay que volver a agregarla.

Uso: python backend/scripts/agregar_regla_cocarda_vacia.py <template_id>
"""
import asyncio
import math
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.orm.attributes import flag_modified

from app.core.database import AsyncSessionLocal
import app.models  # noqa: F401 -- registra todos los modelos (Role incluido) antes de consultar
from app.models.cenefa_template_v2 import CenefaTemplateV2

# Variables que viven pegadas a tipoOferta en la cocarda y tienen que
# desaparecer junto con ella. decimalPrecioOferta puede no estar presente
# en todos los layouts (precio redondo en el diseño de referencia) -- no
# es un error si falta.
VARIABLES_COCARDA = ("unidadMoneda", "precioOferta", "decimalPrecioOferta")


def _centro(comp: dict) -> tuple[float, float]:
    bb = comp["base_bounds"]
    return (bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)


def _distancia(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def construir_reglas(components: list[dict]) -> list[dict]:
    ancla = next((c for c in components if c.get("variable") == "tipoOferta"), None)
    if ancla is None:
        print("Esta plantilla no tiene una cocarda de tipoOferta -- nada que hacer.")
        return []
    centro_ancla = _centro(ancla)

    reglas = []
    for var in VARIABLES_COCARDA:
        candidatos = [c for c in components if c.get("variable") == var]
        if not candidatos:
            continue
        mas_cercano = min(candidatos, key=lambda c: _distancia(_centro(c), centro_ancla))
        reglas.append({
            "target_component_id": mas_cercano["id"],
            "condition": {"field": "tipoOferta", "operator": "is_empty"},
            "action": {"type": "hide"},
        })
        print(f"  {var}: se oculta junto con tipoOferta (id={mas_cercano['id']})")
    return reglas


async def main(template_id: str):
    tid = uuid.UUID(template_id)
    async with AsyncSessionLocal() as db:
        t = await db.get(CenefaTemplateV2, tid)
        if t is None:
            print(f"No existe ninguna plantilla con id {template_id}")
            return

        nuevas = construir_reglas(t.definition["components"])
        if not nuevas:
            return

        # No pisa reglas que ya hubiera para otro componente -- solo
        # reemplaza las que apuntan a los mismos target_component_id que
        # estas 3, por si el script se corre dos veces.
        ids_nuevas = {r["target_component_id"] for r in nuevas}
        reglas_actuales = [
            r for r in (t.definition.get("rules") or [])
            if r.get("target_component_id") not in ids_nuevas
        ]
        definicion = dict(t.definition)
        definicion["rules"] = reglas_actuales + nuevas
        t.definition = definicion
        flag_modified(t, "definition")
        await db.commit()
        print(f"Listo -- {t.name} ({template_id}) actualizada con {len(nuevas)} reglas.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python agregar_regla_cocarda_vacia.py <template_id>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))

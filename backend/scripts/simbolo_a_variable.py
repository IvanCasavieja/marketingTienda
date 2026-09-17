"""Pasa los cuadros con el símbolo de moneda ESCRITO A MANO a <<unidadMoneda>>.

Decisión de Ivan (17/09/2026): "la idea es que las plantillas tengan, en vez de
$ o U$S, directamente la variable unidadMoneda".

Por qué importa más de lo que parece:

1. Un "$" escrito en el diseño imprime "$" SIEMPRE, también en un producto en
   dólares. La variable imprime "U$S" cuando corresponde -- el Convertidor la
   escribe leyendo la columna MONEDA del export de gestión.
2. Un cuadro sin ninguna variable es, para el motor, un "cuadro fijo", y los
   cuadros fijos pasan por una heurística que los hace desaparecer junto al
   cuadro vecino que se apague. Esa heurística nació para el "$" del diseño y
   hoy se lleva puesta cualquier etiqueta que quede a la misma altura: la
   palabra "OFERTA" desaparece de la Gran Bretaña A4 cuando `ofertaUno` viene
   vacía, porque las dos cajas están a la misma altura aunque haya 5 cm entre
   ellas. Sacando los "$" fijos, esa heurística se queda sin clientes
   legítimos y se puede eliminar.

Por defecto SIMULA. Con --aplicar escribe.

    python backend/scripts/simbolo_a_variable.py
    python backend/scripts/simbolo_a_variable.py --aplicar

Es idempotente: un cuadro ya convertido tiene variable y no se vuelve a tocar.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import AsyncSessionLocal
import app.models  # noqa: F401
from app.models.cenefa_template_v2 import CenefaTemplateV2
from app.services.cenefas.component_renderer import _variables_del_componente

# Lo que cuenta como "el símbolo escrito a mano". Deliberadamente corto: solo
# el símbolo SOLO, nada de "$ c/u" ni "Precio $" -- un cuadro que además diga
# otra cosa no es el símbolo del precio y no se toca.
SIMBOLOS = {"$", "u$s", "us$", "usd"}
VARIABLE = "unidadMoneda"


def convertible(c: dict) -> str | None:
    """El símbolo que tiene escrito, o None si este cuadro no se toca."""
    if c.get("type") != "text" or _variables_del_componente(c):
        return None
    if c.get("segments"):
        # Un cuadro compuesto ya tiene su propia estructura; el símbolo ahí es
        # un segmento y se trata aparte (no es un "cuadro fijo" para el motor).
        return None
    texto = str(c.get("static_value") or "").strip()
    return texto if texto.lower() in SIMBOLOS else None


async def main() -> int:
    aplicar = "--aplicar" in sys.argv
    print("APLICANDO (escribe en la base)\n" if aplicar else "SIMULACION -- no escribe nada\n")

    tocadas = total = 0
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(CenefaTemplateV2).order_by(CenefaTemplateV2.name))
        for tmpl in result.scalars().all():
            defin = tmpl.definition or {}
            comps = defin.get("components") or []
            cambios = []
            nuevos = []
            for c in comps:
                simbolo = convertible(c)
                if simbolo is None:
                    nuevos.append(c)
                    continue
                cambios.append((c.get("name"), simbolo, (c.get("style") or {}).get("font_size")))
                nuevo = {**c, "variable": VARIABLE}
                nuevo.pop("static_value", None)
                nuevos.append(nuevo)
            if not cambios:
                continue
            tocadas += 1
            total += len(cambios)
            print(f"  {tmpl.name[:46]:48} {len(cambios):>2} cuadros")
            for nombre, simbolo, pt in cambios:
                print(f"       {simbolo!r} a {pt} pt  ->  <<{VARIABLE}>>   (cuadro {nombre!r})")
            if aplicar:
                tmpl.definition = {**defin, "components": nuevos}
                flag_modified(tmpl, "definition")
        if aplicar:
            await db.commit()

    print(f"\n{'Convertidos' if aplicar else 'Se convertirian'}: {total} cuadros en {tocadas} plantillas")
    if not aplicar:
        print("Para aplicarlo: agregar --aplicar")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

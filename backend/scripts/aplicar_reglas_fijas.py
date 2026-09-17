"""Pone las reglas fijas en las plantillas que YA estaban guardadas.

Las nuevas las traen solas: `asegurar_reglas_fijas` corre al importar, al
crear, al actualizar y al generar (ver reglas_fijas.py). Las que ya viven en
la base nunca vuelven a pasar por ahí hasta que alguien las guarde, así que
este script las pone al día de una.

Por defecto SIMULA: muestra qué cambiaría en cada plantilla y no escribe
nada. Para aplicarlo de verdad hay que pasar --aplicar.

    python backend/scripts/aplicar_reglas_fijas.py            # simulacion
    python backend/scripts/aplicar_reglas_fijas.py --aplicar  # escribe

Es idempotente: correrlo dos veces deja lo mismo que correrlo una.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import AsyncSessionLocal
import app.models  # noqa: F401 -- registra los modelos antes de consultar
from app.models.cenefa_template_v2 import CenefaTemplateV2
from app.services.cenefas.reglas_fijas import (
    CLAVE_BLOQUEADA,
    VAR_DOMINANTE,
    asegurar_reglas_fijas,
)


def _segmentos(comp: dict) -> list[str]:
    return [
        f"<<{s.get('value')}>>" if s.get("type") == "variable" else repr(s.get("value"))
        for s in (comp.get("segments") or [])
    ] or [f"(sin segmentos, variable={comp.get('variable')!r})"]


def _cuadros_promo(defin: dict) -> list[dict]:
    salida = []
    for c in defin.get("components") or []:
        usa = {c.get("variable")} | {s.get("value") for s in (c.get("segments") or [])
                                     if s.get("type") == "variable"}
        if VAR_DOMINANTE in usa:
            salida.append(c)
    return salida


async def main() -> int:
    aplicar = "--aplicar" in sys.argv
    print("APLICANDO (escribe en la base)" if aplicar else "SIMULACION -- no escribe nada\n")

    tocadas = disenos_cambiados = 0
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(CenefaTemplateV2).order_by(CenefaTemplateV2.updated_at.desc()))
        for tmpl in result.scalars().all():
            antes = tmpl.definition or {}
            if not _cuadros_promo(antes):
                continue
            despues = asegurar_reglas_fijas(antes)

            fijas_antes = sum(1 for r in (antes.get("rules") or []) if r.get(CLAVE_BLOQUEADA))
            fijas_ahora = sum(1 for r in (despues.get("rules") or []) if r.get(CLAVE_BLOQUEADA))
            segs_antes = [_segmentos(c) for c in _cuadros_promo(antes)]
            segs_ahora = [_segmentos(c) for c in _cuadros_promo(despues)]
            cambio_diseno = segs_antes != segs_ahora
            if antes == despues:
                print(f"  =  {tmpl.name}  (ya estaba al dia)")
                continue

            tocadas += 1
            print(f"\n  *  {tmpl.name}   [{tmpl.category}]")
            print(f"       reglas fijas: {fijas_antes} -> {fijas_ahora}"
                  f"   (reglas de personas: "
                  f"{sum(1 for r in (despues.get('rules') or []) if not r.get(CLAVE_BLOQUEADA))})")
            if cambio_diseno:
                disenos_cambiados += 1
                print(f"       OJO, CAMBIA EL DISENO: se le agrega el simbolo de moneda")
                print(f"         antes:   {' + '.join(segs_antes[0])}")
                print(f"         despues: {' + '.join(segs_ahora[0])}")
            else:
                print(f"       diseno intacto: {' + '.join(segs_ahora[0])}")

            if aplicar:
                tmpl.definition = despues
                flag_modified(tmpl, "definition")
        if aplicar:
            await db.commit()

    print(f"\n{'Actualizadas' if aplicar else 'Se actualizarian'}: {tocadas} plantillas"
          f"   ({disenos_cambiados} con cambio de diseno)")
    if not aplicar:
        print("Para aplicarlo: agregar --aplicar")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

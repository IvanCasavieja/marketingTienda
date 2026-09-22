# -*- coding: utf-8 -*-
"""Le pone el PAPEL MEDIDO a las plantillas que se cargaron antes del 22/09/2026.

QUE PASO. El tamano de la hoja se leia del PPTX al importar
(``prs.slide_width/height``, un numero exacto), se usaba para adivinar la
etiqueta del formato y SE TIRABA: lo que se guardaba era ``master_format``,
que es una etiqueta y no una medida. De ahi en adelante nadie en el sistema
sabia cuanto media el papel. El preview lo sacaba de una tabla de formatos y,
cuando el contenido no le entraba, AGRANDABA LA HOJA hasta que entrara -- por
eso una 3xA4 SOLO X 25 se veia entera en pantalla y salia cortada de la
impresora.

Desde el 22/09/2026 ``import_pptx`` guarda ``definition["hoja"]``. Este script
es para las que ya estaban. NO HAY QUE PEDIRLE A NADIE QUE RESUBA NADA: el
PPTX original esta guardado entero en ``cenefa_templates_v2.source_pptx``, asi
que la medida se recupera exacta.

Igual no es obligatorio correrlo: ``GET /templates/{id}`` hace lo mismo para
una plantilla la primera vez que alguien la abre (``asegurar_hoja``). Este
script existe para hacerlo de una para toda la flota y, sobre todo, para poder
VER la tabla antes de que la vea Ivan: con ``--ver`` no escribe nada y lista
que papel tiene cada plantilla y si coincide con el papel de su formato.

    python scripts/backfill_hoja_desde_pptx.py --ver      # no toca nada
    python scripts/backfill_hoja_desde_pptx.py --escribir

LA COLUMNA "coinciden" NO ES UN ERROR CUANDO DICE NO. Las cuatro plantillas
apaisadas (Preciazos A5 y 6xA4, Mega Rompe Precios A5 y 6xA4) tienen la
etiqueta "a5" mal puesta por la deteccion vieja: su papel de verdad es una A4
horizontal de 29,7 x 21 y el de la etiqueta es una A5 horizontal. Ese "NO" es
justamente la razon por la que el papel se mide y no se deduce de la etiqueta.

LA BASE DE PRODUCCION SE ABRE EN SOLO LECTURA salvo con --escribir, y se abre
con ``statement_cache_size=0`` porque del otro lado hay un pooler de Supabase
que no soporta sentencias preparadas.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import select                                   # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified             # noqa: E402

from app.models.cenefa_template_v2 import CenefaTemplateV2      # noqa: E402
from app.services.cenefas.formatos_de_hoja import (             # noqa: E402
    misma_hoja, papel_cm,
)
from app.services.cenefas.pptx_importer import medir_hoja       # noqa: E402


async def main(escribir: bool) -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("falta DATABASE_URL (backend/.env)")
        return 2

    engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
    Session = async_sessionmaker(engine, expire_on_commit=False)

    cambiadas = 0
    async with Session() as db:
        filas = (await db.execute(
            select(CenefaTemplateV2).order_by(CenefaTemplateV2.name)
        )).scalars().all()

        print(f"{'plantilla':<44} {'formato':<9} {'papel medido':<16} "
              f"{'papel del formato':<18} {'coinciden'}")
        print("-" * 100)
        for t in filas:
            fmt = (t.definition or {}).get("master_format")
            medida = medir_hoja(t.source_pptx) if t.source_pptx else None
            if medida:
                real = (medida["ancho_cm"], medida["alto_cm"])
                texto_real = f"{real[0]:.3f}x{real[1]:.3f}"
            else:
                real, texto_real = None, "(sin PPTX)"
            delformato = papel_cm(fmt)
            ok = "si" if (real and misma_hoja(real, delformato)) else "NO"
            texto_fmt = f"{delformato[0]:.3f}x{delformato[1]:.3f}"
            print(f"{t.name[:43]:<44} {str(fmt):<9} {texto_real:<16} "
                  f"{texto_fmt:<18} {ok}")

            if not medida:
                continue
            hoja = (t.definition or {}).get("hoja")
            if isinstance(hoja, dict) and hoja.get("ancho_cm"):
                continue
            if escribir:
                t.definition["hoja"] = {
                    **medida,
                    "formato_declarado": fmt,
                    "formato_reconocido": None,
                }
                flag_modified(t, "definition")
            cambiadas += 1

        if escribir and cambiadas:
            await db.commit()

    await engine.dispose()
    print()
    print(f"{cambiadas} plantilla(s) {'actualizada(s)' if escribir else 'SIN hoja guardada'}.")
    if cambiadas and not escribir:
        print("Nada se escribio. Corre con --escribir para guardarlo.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--escribir", action="store_true",
                    help="guarda la hoja medida; sin esto solo muestra la tabla")
    ap.add_argument("--ver", action="store_true", help="explicito: no escribe nada")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(escribir=args.escribir and not args.ver)))

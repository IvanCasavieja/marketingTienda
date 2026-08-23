"""Borra las plantillas de cenefas guardadas con el vocabulario viejo.

Se corre UNA SOLA VEZ, después de que el motor nuevo esté desplegado y
andando. Las plantillas v2 existentes tienen el JSON con nombres de variable
que ya no existen (precioActual, precio4x3, segundaAclaracion...), así que no
matchean contra el Excel nuevo; las v1 pertenecen a un motor que se eliminó.
El equipo vuelve a subir sus PPTX desde el editor y quedan con el vocabulario
de 26 variables.

Antes de correrlo hay que tener el backup completo -- lo genera
`descargar_plantillas.py` y deja los PPTX, los definition.json y un
manifest.json en una carpeta. El script exige que ese manifest exista y que
cubra todo lo que va a borrar: sin eso, no borra nada.

    python scripts/limpiar_plantillas_viejas.py <carpeta_backup>          # simulacion
    python scripts/limpiar_plantillas_viejas.py <carpeta_backup> --borrar # borra de verdad
"""
import asyncio
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import asyncpg
from dotenv import load_dotenv


async def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    backup = pathlib.Path(sys.argv[1])
    borrar = "--borrar" in sys.argv

    manifest_path = backup / "manifest.json"
    if not manifest_path.exists():
        print(f"ERROR: no encuentro {manifest_path}. Sin backup verificado no se borra nada.")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    v1_backup = {int(x["id"]) for x in manifest.get("v1", [])}
    v2_backup = {str(x["id"]) for x in manifest.get("v2", [])}
    print(f"Backup: {len(v1_backup)} plantillas v1 y {len(v2_backup)} v2 en {backup}")

    load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")
    dsn = re.sub(r"^postgresql\+\w+://", "postgresql://", os.getenv("DATABASE_URL", "")).split("?")[0]
    if not dsn:
        print("ERROR: falta DATABASE_URL")
        return 1

    conn = await asyncpg.connect(dsn, timeout=30)
    try:
        v1_db = {r["id"] for r in await conn.fetch("select id from cenefa_templates")}
        v2_db = {str(r["id"]) for r in await conn.fetch("select id from cenefa_templates_v2")}
        print(f"Base:   {len(v1_db)} plantillas v1 y {len(v2_db)} v2")

        faltan_v1 = v1_db - v1_backup
        faltan_v2 = v2_db - v2_backup
        if faltan_v1 or faltan_v2:
            print()
            print("ERROR: hay plantillas en la base que NO estan en el backup.")
            print("  v1 sin respaldo:", sorted(faltan_v1) or "-")
            print("  v2 sin respaldo:", sorted(faltan_v2) or "-")
            print("Volve a correr descargar_plantillas.py antes de borrar.")
            return 1

        if not borrar:
            print()
            print("SIMULACION -- no se borro nada.")
            print(f"Con --borrar se eliminarian {len(v1_db)} filas de cenefa_templates")
            print(f"y {len(v2_db)} de cenefa_templates_v2.")
            return 0

        async with conn.transaction():
            n2 = await conn.execute("delete from cenefa_templates_v2")
            n1 = await conn.execute("delete from cenefa_templates")
        print()
        print("cenefa_templates_v2:", n2)
        print("cenefa_templates:   ", n1)
        print("Listo. El equipo tiene que volver a subir sus PPTX desde el editor.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

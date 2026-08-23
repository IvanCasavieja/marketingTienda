"""Baja TODAS las plantillas de cenefas guardadas a una carpeta local.

Deja los PPTX de las v1, y para cada v2 una carpeta con su definition.json y
su source.pptx cuando existe (las armadas a mano en el editor no tienen PPTX
de origen: de esas solo queda el JSON). Escribe tambien un manifest.json, que
es lo que despues exige limpiar_plantillas_viejas.py para permitir el borrado.

    python scripts/descargar_plantillas.py <carpeta_destino>
"""
import asyncio
import json
import os
import pathlib
import re
import sys
import unicodedata

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import asyncpg
from dotenv import load_dotenv


def slug(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9 _.-]+", "_", s).strip()
    return re.sub(r"\s+", " ", s)[:80] or "sin_nombre"


async def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    base = pathlib.Path(sys.argv[1])

    load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")
    dsn = re.sub(r"^postgresql\+\w+://", "postgresql://", os.getenv("DATABASE_URL", "")).split("?")[0]
    if not dsn:
        print("ERROR: falta DATABASE_URL")
        return 1

    d1 = base / "v1_plantillas_pptx"
    d2 = base / "v2_plantillas"
    d1.mkdir(parents=True, exist_ok=True)
    d2.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, list] = {"v1": [], "v2": []}

    conn = await asyncpg.connect(dsn, timeout=30)
    try:
        filas = await conn.fetch(
            "select id, name, format_name, is_active, created_at, file_bytes "
            "from cenefa_templates order by id"
        )
        for r in filas:
            estado = "activa" if r["is_active"] else "inactiva"
            destino = d1 / f"{r['id']:02d}_{slug(r['name'])}_{estado}.pptx"
            destino.write_bytes(r["file_bytes"])
            manifest["v1"].append({
                "id": r["id"], "name": r["name"], "format_name": r["format_name"],
                "is_active": r["is_active"], "created_at": str(r["created_at"]),
                "archivo": destino.name, "bytes": len(r["file_bytes"]),
            })
            print("v1", destino.name)

        filas = await conn.fetch(
            "select id, name, category, formats, definition, source_pptx, created_at "
            "from cenefa_templates_v2 order by created_at"
        )
        for r in filas:
            sub = d2 / f"{slug(r['name'])}_{str(r['id'])[:8]}"
            sub.mkdir(parents=True, exist_ok=True)
            definicion = r["definition"]
            if isinstance(definicion, str):
                definicion = json.loads(definicion)
            (sub / "definition.json").write_text(
                json.dumps(definicion, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tiene = bool(r["source_pptx"])
            if tiene:
                (sub / "source.pptx").write_bytes(r["source_pptx"])
            manifest["v2"].append({
                "id": str(r["id"]), "name": r["name"], "category": r["category"],
                "formats": list(r["formats"] or []), "created_at": str(r["created_at"]),
                "carpeta": sub.name, "tiene_source_pptx": tiene,
            })
            print("v2", sub.name, "| source.pptx:", "si" if tiene else "NO (armada en el editor)")
    finally:
        await conn.close()

    (base / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print()
    print(f"Backup en {base}: {len(manifest['v1'])} v1 + {len(manifest['v2'])} v2")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""Lista --y opcionalmente borra-- las entradas PLURALES del diccionario.

Una entrada plural es una fila de `sku_descripciones` cuya clave junta varios
SKU. Existen porque el Convertidor, al unificar, escribe la descripcion del
grupo bajo el codigo combinado (ver commitUnificacion/commitMerge en
ConvertidorGrid.tsx). Desde 08/2026 el grupo TAMBIEN se guarda en su propia
tabla `cenefa_grupos_unificados`, asi que la fila plural de aca es redundante
para los grupos nuevos.

Hay TRES formas de clave combinada conviviendo, ninguna normalizada:

    "A - B - C"   unificar categorias  (commitUnificacion, con espacios)
    "A-B"         merge M/A            (commitMerge, sin espacios, siempre 2)
    "A/B/C"       seed historico       (Gestion/Diccionario.xlsx)

Por defecto SOLO INFORMA. Para borrar hace falta --borrar, y antes escribe un
backup JSON con todo lo que va a borrar -- mismo criterio que
limpiar_plantillas_viejas.py: sin backup no se borra nada.

    DATABASE_URL=... python scripts/limpiar_plurales_diccionario.py
    DATABASE_URL=... python scripts/limpiar_plurales_diccionario.py --borrar backup.json
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

# Los tres separadores que realmente existen en la base.
_RE_SEP = re.compile(r"\s*[-/]\s*")


def partes(sku: str) -> list[str]:
    return [p for p in (x.strip() for x in _RE_SEP.split(sku or "")) if p]


def es_plural(sku: str) -> bool:
    return len(partes(sku)) >= 2


def norm_desc(t: str) -> str:
    """Para comparar dos descripciones ignorando acentos, puntuacion y caso."""
    s = unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def forma(sku: str) -> str:
    """Como esta escrita la clave. Sirve para saber que se esta barriendo."""
    ps = partes(sku)
    crudas = _RE_SEP.split(sku or "")
    if len(ps) != len(crudas) or len(set(ps)) < len(ps):
        return "MALFORMADA"          # "520221 -", "-", "X - X"
    if "/" in sku:
        return "seed (barra)"
    if " - " in sku:
        return "unificar"
    # Sin espacios y dos partes numericas correlativas: puede ser un RANGO de
    # articulos del seed, no una unificacion. Se marca, no se decide.
    if len(ps) == 2 and all(p.isdigit() for p in ps):
        a, b = int(ps[0]), int(ps[1])
        if len(ps[0]) == len(ps[1]) and 0 < b - a < 100:
            return "merge o RANGO (ambiguo)"
    return "merge M/A"


async def main() -> int:
    load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")
    raw_url = os.environ.get("DATABASE_URL", "")
    if not raw_url:
        print("ERROR: DATABASE_URL no definida (ponela en backend/.env o inline)")
        return 1
    dsn = re.sub(r"^postgresql\+asyncpg://", "postgresql://", raw_url)
    dsn = re.sub(r"^postgres://", "postgresql://", dsn)

    borrar = "--borrar" in sys.argv
    backup_path = None
    if borrar:
        resto = [a for a in sys.argv[1:] if a != "--borrar"]
        if not resto:
            print("ERROR: --borrar necesita una ruta de backup. Sin backup no se borra nada.")
            return 1
        backup_path = pathlib.Path(resto[0])

    # statement_cache_size=0: el DATABASE_URL de produccion apunta al pooler de
    # Supabase (puerto 6543, pgBouncer en modo transaccion), que no soporta los
    # prepared statements que asyncpg usa por defecto -- sin esto la conexion
    # falla con DuplicatePreparedStatementError en la segunda consulta.
    conn = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        filas = await conn.fetch(
            "SELECT id, sku, descripcion, updated_by_id, updated_at "
            "FROM sku_descripciones ORDER BY sku"
        )
        plurales = [dict(f) for f in filas if es_plural(f["sku"])]
        singulares = {f["sku"]: dict(f) for f in filas if not es_plural(f["sku"])}

        print()
        print(f"TOTAL en el diccionario : {len(filas)}")
        print(f"  singulares            : {len(singulares)}")
        print(f"  plurales              : {len(plurales)}")

        # --- que se estaria barriendo, por forma de la clave -----------------
        por_forma: dict[str, list] = {}
        for p in plurales:
            por_forma.setdefault(forma(p["sku"]), []).append(p)
        print()
        print("PLURALES POR FORMA DE CLAVE")
        for f, items in sorted(por_forma.items(), key=lambda kv: -len(kv[1])):
            print(f"  {f:<26} {len(items):>5}")

        # --- el mismo conjunto escrito mas de una vez ------------------------
        por_conjunto: dict[tuple, list[str]] = {}
        for p in plurales:
            por_conjunto.setdefault(tuple(sorted(partes(p["sku"]))), []).append(p["sku"])
        dups = {k: v for k, v in por_conjunto.items() if len(v) > 1}
        print()
        print(f"GRUPOS ESCRITOS MAS DE UNA VEZ: {len(dups)}")
        for k, v in list(dups.items())[:15]:
            print("  " + " + ".join(k))
            for clave in v:
                print(f"      -> {clave!r}")

        # --- LA FUGA: singulares con el texto de un grupo -------------------
        # Esto NO lo arregla el borrado de plurales: estas filas son SINGULARES.
        fugas = []
        for p in plurales:
            for parte in partes(p["sku"]):
                s = singulares.get(parte)
                if s and norm_desc(s["descripcion"]) == norm_desc(p["descripcion"]):
                    fugas.append({
                        "sku": parte,
                        "descripcion_actual": s["descripcion"],
                        "vino_del_plural": p["sku"],
                        "otros_sku_del_grupo": [x for x in partes(p["sku"]) if x != parte],
                        "updated_by_id": s["updated_by_id"],
                    })
        print()
        print("=" * 72)
        print(f"SINGULARES CON TEXTO DE GRUPO (la fuga): {len(fugas)}")
        print("Estas filas son SINGULARES -- borrar los plurales NO las arregla.")
        print("=" * 72)
        for f in fugas:
            print(f"  SKU {f['sku']:<14} {f['descripcion_actual']}")
            otros = ", ".join(f["otros_sku_del_grupo"])
            print(f"      del plural {f['vino_del_plural']!r}  (con {otros})")

        # --- grupos que van a resucitar -------------------------------------
        try:
            grupos = await conn.fetchval("SELECT count(*) FROM cenefa_grupos_unificados")
        except Exception:
            grupos = None
        if grupos:
            print()
            print(f"AVISO: cenefa_grupos_unificados tiene {grupos} grupos y es OTRA tabla.")
            print("  Borrar los plurales de aca no la toca: grupos_para_skus los va a seguir")
            print("  detectando y el boton Aplicar vuelve a escribir la fila plural.")

        if not borrar:
            print()
            print("(simulacion -- no se borro nada. Agregar --borrar <backup.json> para ejecutar)")
            return 0

        # --- backup obligatorio antes de borrar -----------------------------
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(json.dumps({
            "plurales_borrados": [
                {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in p.items()}
                for p in plurales
            ],
            "fugas_detectadas": fugas,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print()
        print(f"Backup escrito en {backup_path} ({len(plurales)} filas)")

        ids = [p["id"] for p in plurales]
        borradas = await conn.fetchval(
            "WITH d AS ("
            "  DELETE FROM sku_descripciones WHERE id = ANY($1::int[]) RETURNING 1"
            ") SELECT count(*) FROM d",
            ids,
        )
        print(f"BORRADAS {borradas} filas plurales de sku_descripciones.")
        print(f"Quedan {len(singulares)} singulares intactas.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

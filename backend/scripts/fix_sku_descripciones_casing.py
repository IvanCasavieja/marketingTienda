"""
Script standalone -- usa asyncpg directo, sin dependencias de la app.
Re-castea las descripciones ya guardadas en sku_descripciones para que
respeten la regla de estilo vigente en convertidor_ai.py (_STYLE_RULES):
minúscula tipo oración en español (mayúscula solo al principio del texto y
en la letra que sigue a cada punto), marca siempre en MAYÚSCULA COMPLETA,
unidades siempre en minúscula. Antes de ese fix la regla pedía Formato De
Título (cada palabra con mayúscula) -- este script re-castea lo que quedó
guardado con esa regla vieja.

Heurística y su límite: se asume que cualquier palabra ya en MAYÚSCULA
COMPLETA (2+ letras, no una unidad conocida) es la marca y se deja intacta
-- misma convención que la regla ya exigía antes y después del fix, así que
sigue siendo una señal confiable. Pero SOLO se reformatea una fila si
además tiene alguna letra en minúscula en el resto del texto (mixed case) --
si la fila entera está en mayúscula o entera en minúscula no hay forma de
saber cuál era "la marca" ahí, así que se la deja afuera del fix automático
y se lista aparte para revisión manual (probablemente son filas que vienen
del Diccionario.xlsx original, nunca pasaron por esta regla).

No agrega ni saca puntos, ni reordena palabras -- solo cambia mayúscula por
minúscula y viceversa. Si una fila no tiene ningún punto ni ninguna palabra
en mayúscula completa, no hay nada que este script pueda inferir con
confianza sobre ella.

Uso:
  DATABASE_URL=postgresql+asyncpg://... python backend/scripts/fix_sku_descripciones_casing.py --dry-run
  DATABASE_URL=postgresql+asyncpg://... python backend/scripts/fix_sku_descripciones_casing.py --yes
"""
import argparse
import asyncio
import os
import re
import sys

try:
    import asyncpg
except ImportError:
    print("ERROR: pip install asyncpg")
    sys.exit(1)


_UNIT_TOKENS = {"ml", "g", "kg", "kgs", "gr", "grs", "l", "lt", "lts", "un", "u", "cc", "cm", "mm"}
_TOKEN_RE = re.compile(r"\S+|\s+")
_TRAILING_PUNCT_RE = re.compile(r"^(.*?)([.,;:]*)$", re.DOTALL)


def _split_core_and_trail(token: str) -> tuple[str, str]:
    m = _TRAILING_PUNCT_RE.match(token)
    return m.group(1), m.group(2)


def _is_brand_token(core: str) -> bool:
    letters = [c for c in core if c.isalpha()]
    if len(letters) < 2:
        return False
    if "".join(letters).lower() in _UNIT_TOKENS:
        return False
    return core.isupper()


def to_sentence_case(text: str) -> str:
    """Re-castea a minúscula tipo oración en español, preservando palabras
    ya en MAYÚSCULA COMPLETA (asumidas marca) y las mayúsculas de principio
    de texto / después de cada punto."""
    parts = _TOKEN_RE.findall(text)
    out = []
    start_of_sentence = True
    for part in parts:
        if part.isspace():
            out.append(part)
            continue
        core, trail = _split_core_and_trail(part)
        if _is_brand_token(core):
            new_core = core
        else:
            lowered = core.lower()
            new_core = (lowered[0].upper() + lowered[1:]) if start_of_sentence and lowered else lowered
        out.append(new_core + trail)
        start_of_sentence = "." in trail
    return "".join(out)


def _should_reformat(text: str) -> bool:
    """Solo tiene sentido re-castear si el texto ya distingue mayúscula de
    minúscula (mixed case) Y tiene al menos una palabra que se lee como
    marca -- una fila toda en mayúscula o toda en minúscula no da ninguna
    pista confiable de dónde está la marca."""
    if not any(c.islower() for c in text):
        return False
    return any(_is_brand_token(_split_core_and_trail(part)[0]) for part in text.split())


async def run(dry_run: bool, limit: int | None, sample_size: int) -> None:
    raw_url = os.environ.get("DATABASE_URL", "")
    if not raw_url:
        print("ERROR: DATABASE_URL no definida")
        sys.exit(1)
    dsn = re.sub(r"^postgresql\+asyncpg://", "postgresql://", raw_url)
    dsn = re.sub(r"^postgres://", "postgresql://", dsn)

    conn = await asyncpg.connect(dsn)
    try:
        query = "SELECT id, sku, descripcion FROM sku_descripciones ORDER BY id"
        if limit:
            query += f" LIMIT {limit}"
        rows = await conn.fetch(query)

        to_update: list[tuple[int, str, str]] = []  # (id, original, nuevo)
        unchanged = 0
        no_pattern: list[tuple[str, str]] = []  # (sku, descripcion) sin patrón reconocible

        for row in rows:
            original = row["descripcion"]
            if not _should_reformat(original):
                no_pattern.append((row["sku"], original))
                continue
            nuevo = to_sentence_case(original)
            if nuevo != original:
                to_update.append((row["id"], original, nuevo))
            else:
                unchanged += 1

        print(f"Total filas: {len(rows)}")
        print(f"A actualizar: {len(to_update)}")
        print(f"Sin cambios (ya estaban correctas): {unchanged}")
        print(f"Sin patrón reconocible -- no tocadas, revisar a mano ({len(no_pattern)}):")

        if to_update:
            print(f"\nMuestra de cambios (hasta {sample_size} de {len(to_update)}):")
            for _id, orig, nuevo in to_update[:sample_size]:
                print(f"  ANTES:    {orig}")
                print(f"  DESPUES:  {nuevo}\n")

        if no_pattern:
            print(f"\nMuestra sin patrón reconocible (hasta {sample_size} de {len(no_pattern)}):")
            for sku, desc in no_pattern[:sample_size]:
                print(f"  SKU {sku}: {desc}")

        if dry_run:
            print("\n[DRY RUN] no se escribió nada.")
            return

        if to_update:
            await conn.executemany(
                "UPDATE sku_descripciones SET descripcion = $1, updated_at = now() WHERE id = $2",
                [(nuevo, _id) for _id, _orig, nuevo in to_update],
            )
        print(f"\nListo -- {len(to_update)} filas actualizadas.")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Solo simula y muestra la muestra de cambios, no escribe nada")
    parser.add_argument("--yes", action="store_true", help="Saltea la confirmación interactiva")
    parser.add_argument("--limit", type=int, default=None, help="Limitar a las primeras N filas (para probar)")
    parser.add_argument("--sample-size", type=int, default=20, help="Cuántas filas mostrar de muestra (default 20)")
    args = parser.parse_args()

    if not args.dry_run and not args.yes:
        print("Esto va a reescribir descripciones en sku_descripciones de la base conectada por DATABASE_URL.")
        confirm = input("Escribí CONFIRMAR para continuar: ")
        if confirm.strip() != "CONFIRMAR":
            print("Cancelado.")
            sys.exit(0)

    asyncio.run(run(args.dry_run, args.limit, args.sample_size))


if __name__ == "__main__":
    main()

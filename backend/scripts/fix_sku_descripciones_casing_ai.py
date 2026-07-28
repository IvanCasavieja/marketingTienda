"""
Standalone script -- usa asyncpg + anthropic directo, sin dependencias de la app.
Re-castea, vía Tinín (Claude), las filas de sku_descripciones que el heurístico
puro de fix_sku_descripciones_casing.py no supo clasificar (ninguna palabra en
MAYÚSCULA COMPLETA que sirva de señal de marca) -- ver ese script para la regla
de estilo completa y para _should_reformat, que se reusa acá tal cual para
encontrar el mismo conjunto de filas "sin patrón reconocible".

Por qué hace falta IA para este resto: esas filas caen en dos grupos que el
heurístico no puede distinguir con texto plano -- (a) genuinamente no tienen
marca (ej. "Acolchado Fantasía. Varios Colores.") y alcanza con bajar todo a
minúscula, o (b) tienen una marca real pero en Formato De Título en vez de
MAYÚSCULA COMPLETA (ej. "Pine", "Quebec" en árboles de navidad), que hay que
detectar por significado, no por may/min existente. Tinín decide caso por
caso cuál es cuál.

Guardrail: Tinín NUNCA debería reescribir contenido, solo mayúsculas/minúsculas.
Cada respuesta se valida comparando original.lower() == propuesta.lower() -- si
no coinciden letra por letra (agregó, sacó o cambió algo más que el casing), la
fila se descarta y queda en "rechazadas" para revisión manual en vez de
aplicarse. Esto contiene alucinaciones sin depender de que el modelo se porte
bien.

A diferencia de fix_sku_descripciones_casing.py, el --dry-run de ESTE script
sí gasta tokens reales de la API de Claude (para poder mostrar qué propondría
Tinín) -- lo único que evita es el UPDATE final a la base.

Uso:
  DATABASE_URL=... ANTHROPIC_API_KEY=... python backend/scripts/fix_sku_descripciones_casing_ai.py --dry-run
  DATABASE_URL=... ANTHROPIC_API_KEY=... python backend/scripts/fix_sku_descripciones_casing_ai.py --yes
"""
import argparse
import asyncio
import json
import os
import re
import sys

try:
    import asyncpg
except ImportError:
    print("ERROR: pip install asyncpg")
    sys.exit(1)

try:
    import anthropic
except ImportError:
    print("ERROR: pip install anthropic")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fix_sku_descripciones_casing import _should_reformat  # noqa: E402

# Mismo modelo y precios de referencia que backend/app/services/debate_service.py
# y backend/app/core/ai_pricing.py -- duplicado a mano acá porque este script no
# importa la app (mismo criterio que el resto de fix_sku_descripciones_casing.py).
_MODEL = "claude-sonnet-4-6"
_PRICE_IN_PER_TOKEN = 3.00 / 1_000_000
_PRICE_OUT_PER_TOKEN = 15.00 / 1_000_000

_CHUNK_SIZE = 20

_SYSTEM_PROMPT = """\
Sos Tinín, el asistente de estilo del Convertidor de Excel de Tienda Inglesa.

Te paso descripciones de producto que ya están en el catálogo, y para cada una \
tenés que decidir si tiene una marca (nombre propio de fabricante o de línea de \
producto, ej. "CAÑUELAS", "PAGANINI", "Pine", "Quebec") escrita en Formato De \
Título en vez de MAYÚSCULA COMPLETA, y devolverla re-casteada según esta regla:

- Si encontrás una marca: ponela en MAYÚSCULA COMPLETA (la palabra entera), y \
el resto del texto en minúscula tipo oración en español (mayúscula solo en la \
primera letra de todo el texto y en la primera letra de la palabra que sigue a \
cada punto).
- Si NO hay ninguna marca identificable (son productos genéricos: "Acolchado", \
"Alfombra", "Aguja", etc.): todo el texto en minúscula tipo oración, sin \
ninguna palabra en mayúscula completa.
- Las unidades de medida (ml, g, kg, kgs, gr, grs, l, lt, lts, un, u, cc, cm, mm) \
SIEMPRE en minúscula, nunca las confundas con marca.
- Sé conservador: si no estás seguro de que una palabra sea marca (¿nombre \
propio de fabricante, o simplemente una palabra del idioma con mayúscula \
inicial por venir en Formato De Título?), no la subas a mayúscula completa -- \
tratala como texto normal.
- PROHIBIDO cambiar una sola letra, palabra, tilde o signo de puntuación del \
texto -- SOLO se permite cambiar mayúscula por minúscula y viceversa. No \
agregues ni saques puntos. No reordenes palabras. No corrijas errores de \
tipeo ni ortografía. Si el texto no tiene ninguna marca y ya está en \
minúscula, devolvelo idéntico."""

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _strip_json_fence(text: str) -> str:
    return _JSON_FENCE_RE.sub("", text).strip()


def _build_prompt(textos: list[str]) -> str:
    lineas = [f'{n}. "{t}"' for n, t in enumerate(textos, start=1)]
    listado = "\n".join(lineas)
    return (
        f"Re-casteá estas {len(textos)} descripciones:\n\n{listado}\n\n"
        'Devolvé SOLO un JSON con esta forma exacta: {"descripciones": {"1": "texto...", "2": "texto...", ...}} '
        "-- una entrada por cada número de la lista, en el mismo orden, con el texto completo re-casteado "
        "(o idéntico si no hace falta ningún cambio). Sin comentarios ni texto fuera del JSON."
    )


def _same_letters(a: str, b: str) -> bool:
    """Guardrail contra alucinaciones de contenido: mismo texto salvo mayúsculas/minúsculas."""
    return a.lower() == b.lower()


async def _ask_claude(client: "anthropic.Anthropic", prompt: str) -> tuple[str, int, int]:
    def _sync():
        resp = client.messages.create(
            model=_MODEL,
            max_tokens=2000,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text, resp.usage.input_tokens, resp.usage.output_tokens
    return await asyncio.to_thread(_sync)


async def run(dry_run: bool, limit: int | None, sample_size: int) -> None:
    raw_url = os.environ.get("DATABASE_URL", "")
    if not raw_url:
        print("ERROR: DATABASE_URL no definida")
        sys.exit(1)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY no definida")
        sys.exit(1)
    client = anthropic.Anthropic(api_key=api_key)

    dsn = re.sub(r"^postgresql\+asyncpg://", "postgresql://", raw_url)
    dsn = re.sub(r"^postgres://", "postgresql://", dsn)

    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch("SELECT id, sku, descripcion FROM sku_descripciones ORDER BY id")

        candidatos = [r for r in rows if not _should_reformat(r["descripcion"])]
        if limit:
            candidatos = candidatos[:limit]

        print(f"Total filas en la tabla: {len(rows)}")
        print(f"Candidatas (sin patrón reconocible por el heurístico puro): {len(candidatos)}")
        if not candidatos:
            return

        to_update: list[tuple[int, str, str]] = []
        unchanged = 0
        rejected: list[tuple[str, str, str]] = []  # (sku, original, propuesta) -- guardrail activado
        failed_ids: list[int] = []
        total_in = total_out = 0
        n_chunks = (len(candidatos) - 1) // _CHUNK_SIZE + 1

        for i in range(0, len(candidatos), _CHUNK_SIZE):
            chunk = candidatos[i:i + _CHUNK_SIZE]
            textos = [r["descripcion"] for r in chunk]
            prompt = _build_prompt(textos)
            try:
                content, in_tok, out_tok = await _ask_claude(client, prompt)
                total_in += in_tok
                total_out += out_tok
                descripciones = json.loads(_strip_json_fence(content)).get("descripciones", {})
            except Exception as exc:
                print(f"  [chunk {i // _CHUNK_SIZE + 1}/{n_chunks}] fallo -- {exc}")
                failed_ids.extend(r["id"] for r in chunk)
                continue

            for n, r in enumerate(chunk, start=1):
                nuevo = descripciones.get(str(n))
                original = r["descripcion"]
                if not isinstance(nuevo, str) or not nuevo.strip():
                    failed_ids.append(r["id"])
                    continue
                nuevo = nuevo.strip()
                if not _same_letters(nuevo, original):
                    rejected.append((r["sku"], original, nuevo))
                    continue
                if nuevo != original:
                    to_update.append((r["id"], original, nuevo))
                else:
                    unchanged += 1

            print(f"  [chunk {i // _CHUNK_SIZE + 1}/{n_chunks}] procesado -- {len(to_update)} a actualizar hasta ahora")

        costo = (total_in * _PRICE_IN_PER_TOKEN) + (total_out * _PRICE_OUT_PER_TOKEN)
        print(f"\nTokens: {total_in} in / {total_out} out -- costo estimado ${costo:.4f}")
        print(f"A actualizar: {len(to_update)}")
        print(f"Sin cambios (Tinín no encontró nada para recastear): {unchanged}")
        print(f"Rechazadas por el guardrail (cambió algo más que mayúsculas): {len(rejected)}")
        print(f"Fallidas (chunk con error o respuesta faltante): {len(failed_ids)}")

        if to_update:
            print(f"\nMuestra de cambios (hasta {sample_size} de {len(to_update)}):")
            for _id, orig, nuevo in to_update[:sample_size]:
                print(f"  ANTES:    {orig}")
                print(f"  DESPUES:  {nuevo}\n")

        if rejected:
            print(f"\nMuestra de rechazadas por el guardrail (hasta {sample_size} de {len(rejected)}):")
            for sku, orig, nuevo in rejected[:sample_size]:
                print(f"  SKU {sku}")
                print(f"    ORIGINAL:  {orig}")
                print(f"    PROPUESTA: {nuevo}  <- descartada, cambia contenido\n")

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
    parser.add_argument("--dry-run", action="store_true", help="Simula y muestra la muestra de cambios (SÍ gasta tokens de la API), no escribe nada")
    parser.add_argument("--yes", action="store_true", help="Saltea la confirmación interactiva")
    parser.add_argument("--limit", type=int, default=None, help="Limitar a las primeras N filas candidatas (para probar)")
    parser.add_argument("--sample-size", type=int, default=20, help="Cuántas filas mostrar de muestra (default 20)")
    args = parser.parse_args()

    if not args.dry_run and not args.yes:
        print("Esto va a reescribir descripciones en sku_descripciones de la base conectada por DATABASE_URL, usando IA.")
        confirm = input("Escribí CONFIRMAR para continuar: ")
        if confirm.strip() != "CONFIRMAR":
            print("Cancelado.")
            sys.exit(0)

    asyncio.run(run(args.dry_run, args.limit, args.sample_size))


if __name__ == "__main__":
    main()

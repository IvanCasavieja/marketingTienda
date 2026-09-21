"""Regenera app/services/scraper/sucursales_gdu.json desde la API de GDU.

Esa lista es la que usa la búsqueda de precios para saber qué sucursales existen
y a qué cadena pertenece cada una. Es un archivo, no una consulta: la búsqueda no
puede ir a la red por esto en cada consulta. La contra es que se queda vieja —
pasó: el 21/09/2026 tenía 72 sucursales cuando GDU ya tenía 100 activas, y las 27
que faltaban (Devoto Express y Fresh Market, todas con precio propio) no
aparecían en ninguna búsqueda.

Correrlo cada tanto, y cuando se sepa que GDU abrió o cerró tiendas:

    python scripts/actualizar_sucursales_gdu.py            # muestra qué cambiaría
    python scripts/actualizar_sucursales_gdu.py --escribir  # lo guarda
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.scraper import gdu_rest as gdu  # noqa: E402

DESTINO = Path(gdu.__file__).parent / "sucursales_gdu.json"


def main() -> int:
    ap = argparse.ArgumentParser(description="Actualiza la lista de sucursales de GDU")
    ap.add_argument("--escribir", action="store_true", help="sin esto, solo muestra el diff")
    args = ap.parse_args()

    antes = gdu._load_branch_meta()
    sucursales = gdu.descargar_sucursales()
    ahora = {s["id"]: s for s in sucursales}

    nuevas = [s for i, s in ahora.items() if i not in antes]
    bajas = [(i, m["nombre"]) for i, m in antes.items() if i not in ahora]
    print(f"Guardadas hoy: {len(antes)}   |   la API devuelve: {len(ahora)}")
    print("Por cadena:", dict(Counter(s["cadena"] for s in sucursales)))
    if nuevas:
        print(f"\nNUEVAS ({len(nuevas)}):")
        for s in sorted(nuevas, key=lambda x: (x["cadena"], x["id"])):
            print(f"  + {s['id']:<8} {s['cadena']:<7} {s['nombre']}")
    if bajas:
        print(f"\nYA NO ESTÁN ({len(bajas)}):")
        for i, nombre in sorted(bajas):
            print(f"  - {i:<8} {nombre}")
    if not nuevas and not bajas:
        print("\nSin cambios.")

    if not args.escribir:
        print("\n(no se escribió nada; agregá --escribir)")
        return 0

    agrupado: dict[str, list] = {}
    for s in sorted(sucursales, key=lambda x: (x["cadena"], x["id"])):
        agrupado.setdefault(s["cadena"], []).append(s)
    DESTINO.write_text(json.dumps(agrupado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nEscrito: {DESTINO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

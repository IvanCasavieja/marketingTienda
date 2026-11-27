"""Corre una eval: python -m evals.run <agente> [--datos <carpeta>] [--repeticiones 3] [--modelo <id>]

Llama a la IA DE VERDAD (gasta), con los casos de --datos, y dice qué
porcentaje acertó. Con --repeticiones corre cada caso varias veces y mide
también la consistencia (la IA no contesta siempre igual). Guarda la corrida
en evals/resultados/ y la compara con la anterior del mismo agente y modelo.
Ver evals/README.md.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).parent
AGENTES = ["dogti", "brief", "revisor", "catti", "dontino"]


def preparar_entorno(archivo_env: str | None = None) -> None:
    """La clave sale del entorno, de backend/.env o de --env. Lo demás que
    pide la configuración (base, cifrado) no se usa acá: va de relleno."""
    if archivo_env:
        for linea in Path(archivo_env).read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, v = linea.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    os.environ.setdefault("APP_SECRET_KEY", "solo-evals")
    os.environ.setdefault("ENCRYPTION_KEY", "Y2q_vIGd2FgQ4CqY3Fh3du3ZehOWmx4pVHPfpJC44bA=")
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://nadie:nada@127.0.0.1:5432/no_se_usa")


_preparar_entorno = preparar_entorno  # nombre anterior


# Modelos que la tabla de la plataforma (app/core/ai_pricing.py) todavía no
# tiene: US$ por millón de tokens, entrada y salida (precios de la API al 27/11/2026).
_PRECIOS_EXTRA = {"claude-haiku-5-5": (0.10, 0.50)}


def _costo(modelo: str, entrada: int, salida: int) -> float | None:
    if modelo in _PRECIOS_EXTRA:
        e, s = _PRECIOS_EXTRA[modelo]
        return round((entrada * e + salida * s) / 1_000_000, 6)
    try:
        from app.core.ai_pricing import estimate_cost
        return float(estimate_cost("anthropic", modelo, entrada, salida))
    except Exception:
        return None


def _archivo_de(agente: str, modelo: str) -> str:
    return f"{agente}--{modelo}--"


def _anterior(agente: str, modelo: str) -> dict | None:
    archivos = sorted((AQUI / "resultados").glob(_archivo_de(agente, modelo) + "*.json"))
    return json.loads(archivos[-1].read_text(encoding="utf-8")) if archivos else None


async def _correr_todo(modulo, casos: list[dict], clave: str, repeticiones: int) -> list[dict]:
    import anthropic

    cliente = anthropic.AsyncAnthropic(api_key=clave, max_retries=4)
    semaforo = asyncio.Semaphore(4)

    async def uno(caso: dict, vuelta: int) -> dict:
        async with semaforo:
            inicio = time.monotonic()
            fila = {"id": caso["id"], "vuelta": vuelta}
            try:
                salida, entrada, sale = await modulo.correr(caso, cliente)
                puntajes = modulo.puntuar(caso, salida)
                if hasattr(modulo, "juzgar"):  # lo que no se puede medir con código lo mira un juez
                    extra, e2, s2 = await modulo.juzgar(caso, salida, cliente)
                    puntajes.update(extra)
                    fila.update(juez_entrada=e2, juez_salida=s2)
                fila.update(puntajes=puntajes, entrada=entrada, salida=sale)
            except Exception as exc:  # un caso roto no tira la corrida: cuenta como error
                fila.update(error=f"{type(exc).__name__}: {exc}"[:200], puntajes={}, entrada=0, salida=0)
            fila["segundos"] = round(time.monotonic() - inicio, 1)
            print(f"  {'✗' if 'error' in fila else '✓'} {caso['id']} · vuelta {vuelta} ({fila['segundos']} s)", flush=True)
            return fila

    return await asyncio.gather(*(uno(c, v) for c in casos for v in range(1, repeticiones + 1)))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("agente", choices=AGENTES)
    ap.add_argument("--datos", default=os.environ.get("EVALS_DATOS"), help="carpeta con los casos (o EVALS_DATOS)")
    ap.add_argument("--modelo", help="probar otro modelo en vez del de producción")
    ap.add_argument("--repeticiones", type=int, default=1, help="cuántas veces corre cada caso (consistencia)")
    ap.add_argument("--limite", type=int, help="correr solo los primeros N casos")
    ap.add_argument("--env", help="archivo con ANTHROPIC_API_KEY=... (si no está en el entorno ni en backend/.env)")
    ap.add_argument("--no-guardar", action="store_true")
    a = ap.parse_args()

    preparar_entorno(a.env)
    import importlib

    from app.core.config import settings
    from evals import metricas

    if not settings.ANTHROPIC_API_KEY:
        raise SystemExit("Falta ANTHROPIC_API_KEY: ponela en el entorno, en backend/.env o pasá --env <archivo>.")
    modulo = importlib.import_module(f"evals.{a.agente}")
    carpeta = Path(a.datos) if a.datos else AQUI / "ejemplos" / a.agente
    if not carpeta.is_dir():
        raise SystemExit(f"No existe la carpeta de casos: {carpeta}")
    casos = modulo.cargar(carpeta)[: a.limite]
    if not casos:
        raise SystemExit(f"No hay casos en {carpeta} (ver evals/README.md).")
    if a.modelo:
        modulo.fijar_modelo(a.modelo)
    modelo = modulo.modelo_actual()

    print(f"\nEval de {a.agente} · {len(casos)} casos × {a.repeticiones} · modelo {modelo}\n")
    filas = asyncio.run(_correr_todo(modulo, casos, settings.ANTHROPIC_API_KEY, a.repeticiones))

    resumen = metricas.resumir([f["puntajes"] for f in filas])
    # Consistencia: de los casos que corrieron todas sus vueltas, cuántos dieron
    # exactamente lo mismo en todas.
    por_caso: dict[str, list[dict]] = {}
    for f in filas:
        por_caso.setdefault(f["id"], []).append(f)
    estables = [all(v["puntajes"] == vs[0]["puntajes"] and "error" not in v for v in vs) for vs in por_caso.values()]
    consistencia = metricas.porcentaje(sum(estables), len(estables)) if a.repeticiones > 1 else None
    siempre_bien = metricas.porcentaje(
        sum(all("error" not in v and all(x is not False for x in v["puntajes"].values()) for v in vs)
            for vs in por_caso.values()), len(por_caso))

    entrada, salida = sum(f["entrada"] for f in filas), sum(f["salida"] for f in filas)
    costo = _costo(modelo, entrada, salida)
    juez = _costo("claude-opus-5-5", sum(f.get("juez_entrada", 0) for f in filas),
                  sum(f.get("juez_salida", 0) for f in filas))
    tiempos = sorted(f["segundos"] for f in filas)
    fallas: dict = {}
    for f in filas:
        malas = [f["error"]] if "error" in f else [k for k, v in f["puntajes"].items() if v is False]
        if malas:
            fallas.setdefault(f["id"], {}).setdefault(", ".join(malas), 0)
            fallas[f["id"]][", ".join(malas)] += 1
    corrida = {
        "agente": a.agente, "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"), "modelo": modelo,
        "casos": len(casos), "repeticiones": a.repeticiones, "corridas": len(filas),
        "errores": sum("error" in f for f in filas), "metricas": resumen,
        "casos_perfectos": siempre_bien, "consistencia": consistencia,
        "tokens_entrada": entrada, "tokens_salida": salida, "costo_usd": costo,
        "costo_por_caso_usd": round(costo / len(filas), 4) if costo is not None else None,
        "costo_del_juez_usd": juez if juez else None,
        "segundos_mediana": tiempos[len(tiempos) // 2], "segundos_p90": tiempos[int(len(tiempos) * 0.9) - 1],
        # Solo ids y qué falló (y en cuántas vueltas): nada del contenido de los casos.
        "fallas": fallas,
    }
    antes = (_anterior(a.agente, modelo) or {}).get("metricas", {})
    print(f"\n{'Métrica':<36}{'Acierto':>9}{'Corridas':>10}   vs. anterior")
    for nombre, r in resumen.items():
        dif = ""
        if nombre in antes and antes[nombre]["porcentaje"] is not None:
            d = r["porcentaje"] - antes[nombre]["porcentaje"]
            dif = "=" if d == 0 else f"{'▲' if d > 0 else '▼'} {abs(d):.1f}"
        print(f"{nombre:<36}{r['porcentaje']:>8}%{r['aciertos']:>6}/{r['casos']:<4} {dif}")
    print(f"\nCasos perfectos en todas sus vueltas: {siempre_bien}%"
          + (f" · consistencia: {consistencia}%" if consistencia is not None else ""))
    print(f"Errores de corrida: {corrida['errores']} · mediana {corrida['segundos_mediana']} s · "
          f"{entrada + salida:,} tokens" + (f" · US$ {costo:.3f}" if costo is not None else ""))
    if fallas:
        print("Para mirar:", json.dumps(fallas, ensure_ascii=False))
    if not a.no_guardar:
        (AQUI / "resultados").mkdir(exist_ok=True)
        archivo = AQUI / "resultados" / f"{_archivo_de(a.agente, modelo)}{datetime.now().strftime('%Y-%m-%d-%H%M')}.json"
        archivo.write_text(json.dumps(corrida, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Guardado en {archivo.relative_to(AQUI.parent)}")


if __name__ == "__main__":
    main()

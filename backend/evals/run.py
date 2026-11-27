"""Corre una eval: python -m evals.run <dogti|brief|revisor> --datos <carpeta>

Llama a la IA DE VERDAD (gasta), con los casos de --datos, y dice qué
porcentaje acertó. Guarda la corrida en evals/resultados/ y la compara con la
anterior del mismo agente. Ver evals/README.md.
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


def _preparar_entorno(archivo_env: str | None) -> None:
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


def _costo(modelo: str, entrada: int, salida: int) -> float | None:
    try:
        from app.core.ai_pricing import estimate_cost
        return float(estimate_cost("anthropic", modelo, entrada, salida))
    except Exception:
        return None


def _anterior(agente: str) -> dict | None:
    archivos = sorted((AQUI / "resultados").glob(f"{agente}-*.json"))
    return json.loads(archivos[-1].read_text(encoding="utf-8")) if archivos else None


async def _correr_todo(modulo, casos: list[dict], clave: str) -> list[dict]:
    import anthropic

    cliente = anthropic.AsyncAnthropic(api_key=clave)
    semaforo = asyncio.Semaphore(3)

    async def uno(caso: dict) -> dict:
        async with semaforo:
            inicio = time.monotonic()
            fila = {"id": caso["id"]}
            try:
                salida, entrada, sale = await modulo.correr(caso, cliente)
                fila.update(puntajes=modulo.puntuar(caso, salida), entrada=entrada, salida=sale)
            except Exception as exc:  # un caso roto no tira la corrida: cuenta como error
                fila.update(error=f"{type(exc).__name__}: {exc}"[:200], puntajes={}, entrada=0, salida=0)
            fila["segundos"] = round(time.monotonic() - inicio, 1)
            print(f"  {'✗' if 'error' in fila else '✓'} {caso['id']} ({fila['segundos']} s)", flush=True)
            return fila

    return await asyncio.gather(*(uno(c) for c in casos))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("agente", choices=["dogti", "brief", "revisor"])
    ap.add_argument("--datos", default=os.environ.get("EVALS_DATOS"), help="carpeta con los casos (o EVALS_DATOS)")
    ap.add_argument("--modelo", help="probar otro modelo en vez del de producción")
    ap.add_argument("--limite", type=int, help="correr solo los primeros N casos")
    ap.add_argument("--env", help="archivo con ANTHROPIC_API_KEY=... (si no está en el entorno ni en backend/.env)")
    ap.add_argument("--no-guardar", action="store_true")
    a = ap.parse_args()

    _preparar_entorno(a.env)
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

    print(f"\nEval de {a.agente} · {len(casos)} casos · modelo {modelo}\n")
    filas = asyncio.run(_correr_todo(modulo, casos, settings.ANTHROPIC_API_KEY))

    resumen = metricas.resumir([f["puntajes"] for f in filas])
    entrada, salida = sum(f["entrada"] for f in filas), sum(f["salida"] for f in filas)
    costo = _costo(modelo, entrada, salida)
    corrida = {
        "agente": a.agente, "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"), "modelo": modelo,
        "casos": len(casos), "errores": sum("error" in f for f in filas), "metricas": resumen,
        "tokens_entrada": entrada, "tokens_salida": salida, "costo_usd": costo,
        "segundos_por_caso": round(sum(f["segundos"] for f in filas) / len(filas), 1),
        # Solo ids y qué falló: nada del contenido de los casos (el repo es público).
        "fallas": {f["id"]: f.get("error") or [k for k, v in f["puntajes"].items() if v is False]
                   for f in filas if "error" in f or any(v is False for v in f["puntajes"].values())},
    }
    antes = (_anterior(a.agente) or {}).get("metricas", {})
    print(f"\n{'Métrica':<34}{'Acierto':>9}{'Casos':>8}   vs. anterior")
    for nombre, r in resumen.items():
        dif = ""
        if nombre in antes and antes[nombre]["porcentaje"] is not None:
            d = r["porcentaje"] - antes[nombre]["porcentaje"]
            dif = "=" if d == 0 else f"{'▲' if d > 0 else '▼'} {abs(d):.1f}"
        print(f"{nombre:<34}{r['porcentaje']:>8}%{r['aciertos']:>5}/{r['casos']:<3}  {dif}")
    print(f"\nErrores de corrida: {corrida['errores']} · {corrida['segundos_por_caso']} s por caso · "
          f"{entrada + salida:,} tokens" + (f" · US$ {costo:.3f}" if costo is not None else ""))
    if corrida["fallas"]:
        print("Para mirar:", json.dumps(corrida["fallas"], ensure_ascii=False))
    if not a.no_guardar:
        (AQUI / "resultados").mkdir(exist_ok=True)
        archivo = AQUI / "resultados" / f"{a.agente}-{datetime.now().strftime('%Y-%m-%d-%H%M')}.json"
        archivo.write_text(json.dumps(corrida, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Guardado en {archivo.relative_to(AQUI.parent)}")


if __name__ == "__main__":
    main()

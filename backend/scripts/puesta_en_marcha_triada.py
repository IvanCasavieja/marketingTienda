"""Puesta en marcha de La Triada con datos REALES y con Meridian adentro.

Pedido de Ivan (22/09/2026): "quiero que comiences con la tríada de una vez,
incluí el modelo Meridian para su correcto análisis de campañas".

Lo que había ese día, medido en producción:
  - campaign_metrics tenía SOLO datos de prueba: 90 días (8/04 -> 6/07/2026) de
    cuentas inventadas (generate_*_fake_data.py). La Triada analizaba eso.
  - platform_connections estaba VACÍA: ninguna cuenta real conectada.
  - Meridian estaba dormido a propósito: el contexto que le llega a La Triada
    (debate_service._build_meridian_context) solo se prende si el modelo se
    entrenó con 52+ semanas, y había 13.

Los conectores reales (Meta, Google Ads, TikTok, DV360, GA4) ya estaban
escritos, y `sync_platform` acepta un rango de fechas: el historial se puede
traer de una vez, no hace falta esperar un año juntándolo. Este script hace
eso, en orden, con las cuentas que estén conectadas:

  1. Verifica que haya cuentas conectadas. Sin ninguna, se frena y dice cuáles
     faltan: es lo único que este script no puede resolver.
  2. Respalda y borra los datos de prueba: toda fila de campaign_metrics cuya
     cuenta NO es una de las conectadas. Con eso nunca toca una cuenta real.
     Solo con --borrar-datos-de-prueba; sin eso muestra qué borraría.
  3. Trae N meses de historial (13 por defecto: así Meridian supera las 52
     semanas) de cada plataforma, de a un mes, con el mismo `sync_platform` que
     usa la app.
  4. Exporta, entrena Meridian (con .venv-meridian: TensorFlow no entra en el
     servidor) y sube el resumen. Si quedó con 52+ semanas, La Triada lo empieza
     a usar sola.

Uso, desde backend/:
    python scripts/puesta_en_marcha_triada.py                     # solo mira
    python scripts/puesta_en_marcha_triada.py --borrar-datos-de-prueba --traer-historial
    python scripts/puesta_en_marcha_triada.py ... --meses 18 --sin-meridian
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from sqlalchemy import delete, not_, select, true  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.campaign_metric import CampaignMetric  # noqa: E402
from app.models.platform_connection import Platform, PlatformConnection  # noqa: E402
from app.services.metrics_service import sync_platform  # noqa: E402

# Qué hace falta para conectar cada plataforma. Es lo que se le dice a la
# persona cuando no hay nada conectado: el único bloqueo que este script no
# puede resolver solo.
_QUE_HACE_FALTA = {
    Platform.META: "Meta Ads: token de un usuario del sistema del Business Manager (ads_read) + ID de la cuenta publicitaria",
    Platform.GOOGLE_ANALYTICS: "Google Analytics 4: ID de la propiedad + token de acceso y de refresco (es el KPI de Meridian: la facturación)",
    Platform.TIKTOK: "TikTok Ads: token + ID del anunciante",
    Platform.GOOGLE_ADS: "Google Ads (si se invierte): token de acceso y de refresco + developer token",
}

MERIDIAN_PY = REPO / ".venv-meridian" / "Scripts" / "python.exe"
BACKUPS = BACKEND / "backups"


def _meses(hasta: date, cuantos: int) -> list[tuple[date, date]]:
    """Rangos de a un mes, del más viejo al más nuevo. De a un mes y no todo
    junto: las APIs de publicidad limitan cuántos días devuelven por pedido, y si
    un mes falla los otros quedan guardados."""
    rangos = []
    fin = hasta
    for _ in range(cuantos):
        ini = fin - timedelta(days=29)  # 30 días justos, contando los dos extremos
        rangos.append((ini, fin))
        fin = ini - timedelta(days=1)
    return list(reversed(rangos))


async def _conexiones(db) -> list[PlatformConnection]:
    r = await db.execute(select(PlatformConnection).where(PlatformConnection.is_active == True))  # noqa: E712
    return list(r.scalars())


async def paso_1_conexiones(db) -> list[PlatformConnection]:
    conexiones = await _conexiones(db)
    print("\n=== 1. Cuentas conectadas")
    if not conexiones:
        print("   NINGUNA. La Triada no tiene datos reales hasta que se conecte al menos una cuenta.")
        print("   Se cargan en la pantalla Conexiones de la plataforma. Hace falta, por plataforma:")
        for texto in _QUE_HACE_FALTA.values():
            print("     -", texto)
        return []
    for c in conexiones:
        print(f"   {c.platform.value:<18} cuenta {c.account_id}  ({c.account_name or 'sin nombre'})")
    faltan = [p for p in _QUE_HACE_FALTA if p not in {c.platform for c in conexiones}]
    if Platform.GOOGLE_ANALYTICS in faltan:
        print("   OJO: falta Google Analytics 4. Meridian mide contra la facturación de GA4: sin eso no se puede entrenar.")
    return conexiones


async def paso_2_datos_de_prueba(db, conexiones, borrar: bool) -> None:
    reales = [c.account_id for c in conexiones]
    filtro = not_(CampaignMetric.account_id.in_(reales)) if reales else true()
    r = await db.execute(select(CampaignMetric).where(filtro))
    filas = list(r.scalars())
    print("\n=== 2. Datos de prueba (filas de cuentas que NO están conectadas)")
    por_cuenta: dict[tuple, int] = {}
    for f in filas:
        k = (f.platform.value, f.account_id)
        por_cuenta[k] = por_cuenta.get(k, 0) + 1
    for (p, a), n in sorted(por_cuenta.items()):
        print(f"   {p:<18} cuenta {a:<22} {n} filas")
    if not filas:
        print("   ninguna: la base ya tiene solo datos de cuentas conectadas.")
        return
    if not borrar:
        print(f"   {len(filas)} filas. No se borra nada sin --borrar-datos-de-prueba.")
        return
    BACKUPS.mkdir(exist_ok=True)
    ruta = BACKUPS / f"campaign_metrics_datos_de_prueba_{datetime.now():%Y-%m-%d_%H%M}.json"
    ruta.write_text(json.dumps([
        {c.name: (getattr(f, c.name).isoformat() if hasattr(getattr(f, c.name), "isoformat")
                  else getattr(f, c.name).value if hasattr(getattr(f, c.name), "value") else getattr(f, c.name))
         for c in CampaignMetric.__table__.columns}
        for f in filas
    ], ensure_ascii=False, default=str), encoding="utf-8")
    await db.execute(delete(CampaignMetric).where(filtro))
    await db.commit()
    print(f"   borradas {len(filas)} filas. Respaldo: {ruta.relative_to(REPO)}")


async def paso_3_historial(db, conexiones, meses: int) -> None:
    print(f"\n=== 3. Historial: {meses} meses por plataforma, de a un mes")
    hasta = date.today() - timedelta(days=1)
    for plataforma in sorted({c.platform for c in conexiones}, key=lambda p: p.value):
        total = 0
        for ini, fin in _meses(hasta, meses):
            try:
                n = await sync_platform(db, plataforma, ini, fin)
                await db.commit()
                total += n
                print(f"   {plataforma.value:<18} {ini} -> {fin}: {n} filas")
            except Exception as exc:  # un mes que falla no tira los otros
                await db.rollback()
                print(f"   {plataforma.value:<18} {ini} -> {fin}: FALLÓ ({str(exc)[:160]})")
        print(f"   {plataforma.value}: {total} filas en total")


def _correr(cmd: list[str], cwd: Path) -> None:
    print("   $", " ".join(str(c) for c in cmd))
    r = subprocess.run(cmd, cwd=cwd, env={**os.environ, "TF_CPP_MIN_LOG_LEVEL": "2", "PYTHONIOENCODING": "utf-8"})
    if r.returncode != 0:
        raise SystemExit(f"falló: {' '.join(str(c) for c in cmd)}")


def paso_4_meridian() -> None:
    print("\n=== 4. Meridian: exportar, entrenar y subir el resumen")
    if not MERIDIAN_PY.exists():
        raise SystemExit(f"No está {MERIDIAN_PY}: ver meridian_mmm/README.md para crear .venv-meridian.")
    _correr([sys.executable, "scripts/export_metrics_for_meridian.py"], BACKEND)
    _correr([str(MERIDIAN_PY), "fit_model.py"], REPO / "meridian_mmm")
    _correr([sys.executable, "scripts/import_meridian_summary.py"], BACKEND)


async def paso_5_estado(db) -> None:
    from app.models.meridian_channel_summary import MeridianChannelSummary
    r = await db.execute(select(MeridianChannelSummary))
    filas = list(r.scalars())
    confiable = bool(filas) and all(f.reliable for f in filas)
    print("\n=== 5. Resultado")
    for f in filas:
        print(f"   {f.channel:<10} ROI {f.roi:.2f}  contribución {f.pct_of_contribution:.1%}  confiable={f.reliable}")
    print("   La Triada " + ("YA USA Meridian en cada análisis." if confiable else
                             "todavía NO usa Meridian: el modelo tiene menos de 52 semanas."))


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--borrar-datos-de-prueba", action="store_true")
    ap.add_argument("--traer-historial", action="store_true")
    ap.add_argument("--meses", type=int, default=13)
    ap.add_argument("--sin-meridian", action="store_true")
    a = ap.parse_args()

    async with AsyncSessionLocal() as db:
        conexiones = await paso_1_conexiones(db)
        await paso_2_datos_de_prueba(db, conexiones, a.borrar_datos_de_prueba and bool(conexiones))
        if not conexiones:
            print("\nSin cuentas conectadas no hay nada más para hacer.")
            return
        if a.traer_historial:
            await paso_3_historial(db, conexiones, a.meses)
        else:
            print("\n=== 3. Historial: no se trae nada sin --traer-historial")
        if not a.sin_meridian and a.traer_historial:
            paso_4_meridian()
        await paso_5_estado(db)


if __name__ == "__main__":
    asyncio.run(main())

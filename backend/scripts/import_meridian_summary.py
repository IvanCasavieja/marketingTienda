"""
Importa el resumen por canal que fit_model.py generó
(meridian_mmm/output/meridian_channel_summary.csv) a la tabla
meridian_channel_summary, para que debate_service.py pueda consultarlo sin
necesitar acceso al filesystem del pipeline de modelado (corre en otro
entorno — ver meridian_mmm/README.md, .venv-meridian no tiene acceso a
Postgres).

Reemplaza la tabla entera en cada corrida (delete + insert) — no acumula
historial, solo la última foto del modelo. Así un canal que desaparezca
entre una corrida y la siguiente no queda como dato viejo colgado.

Uso (con el venv del backend, DESPUÉS de correr fit_model.py con
.venv-meridian):
  python scripts/import_meridian_summary.py

Requiere DATABASE_URL apuntando a la base real (mismo .env que usa la app).
"""
import asyncio
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
import app.models  # noqa: E402,F401
from app.models.role import Role  # noqa: E402,F401
from app.models.meridian_channel_summary import MeridianChannelSummary  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CSV_PATH = REPO_ROOT / "meridian_mmm" / "output" / "meridian_channel_summary.csv"


def read_rows() -> list[dict]:
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"{CSV_PATH} está vacío — ¿corriste fit_model.py?")
    return rows


async def main() -> None:
    if not CSV_PATH.exists():
        raise SystemExit(
            f"No existe {CSV_PATH}. Corré primero fit_model.py con .venv-meridian."
        )
    rows = read_rows()
    fitted_at = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        await db.execute(delete(MeridianChannelSummary))
        for row in rows:
            db.add(MeridianChannelSummary(
                channel=row["channel"],
                spend=float(row["spend"]),
                pct_of_spend=float(row["pct_of_spend"]),
                incremental_outcome=float(row["incremental_outcome"]),
                pct_of_contribution=float(row["pct_of_contribution"]),
                roi=float(row["roi"]),
                mroi=float(row["mroi"]),
                reliable=row["reliable"].strip().lower() == "true",
                fitted_at=fitted_at,
            ))
        await db.commit()

    print(f"{len(rows)} canales importados desde {CSV_PATH.relative_to(REPO_ROOT)}")
    print(f"reliable={rows[0]['reliable']} (True = 52+ semanas de historia al fitear)")


if __name__ == "__main__":
    asyncio.run(main())

"""
run_scraper_local.py — Corre el scraper completo en local y sube a Supabase.

Uso desde el directorio backend/:
    python scripts/run_scraper_local.py          # full scan (Tata + Farmashop + GDU)
    python scripts/run_scraper_local.py --gdu    # solo GDU (Geant/Disco/Devoto)

Carga .env.scraper si existe, sino usa .env.
"""
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Cargar env ANTES de importar cualquier módulo de app
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent.parent   # backend/
sys.path.insert(0, str(_ROOT))         # permite importar `app` desde cualquier directorio

def _load_env(path: Path, override: bool = False):
    """Carga variables de un archivo .env. override=True pisa valores ya seteados."""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if override:
            os.environ[key] = val
        else:
            os.environ.setdefault(key, val)

# Orden de carga: primero .env.scraper (valores base opcionales),
# luego .env con override=True (siempre gana — tiene los valores reales de Supabase).
_env_scraper = _ROOT / ".env.scraper"
if _env_scraper.exists():
    _load_env(_env_scraper, override=False)

_env_base = _ROOT / ".env"
if _env_base.exists():
    _load_env(_env_base, override=True)
    print(f"[env] cargado desde .env")
elif not _env_scraper.exists():
    print("[env] WARNING: no se encontró .env ni .env.scraper", file=sys.stderr)

# El motor async de SQLAlchemy necesita postgresql+asyncpg://, no postgresql://
_db_url = os.environ.get("DATABASE_URL", "")
if _db_url.startswith("postgresql://") and "+asyncpg" not in _db_url:
    os.environ["DATABASE_URL"] = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

os.environ.setdefault("SCRAPER_DATA_DIR", str(_ROOT / "scraper_data"))
_DATA_DIR = Path(os.environ["SCRAPER_DATA_DIR"])

# config.py valida ENCRYPTION_KEY y APP_SECRET_KEY al importar.
# El scraper no los usa, pero pydantic los exige. Generamos valores válidos si son placeholders.
def _ensure_valid_fernet(key: str) -> str:
    from cryptography.fernet import Fernet, InvalidToken
    try:
        Fernet(key.encode())
        return key
    except Exception:
        return Fernet.generate_key().decode()

_enc = os.environ.get("ENCRYPTION_KEY", "")
os.environ["ENCRYPTION_KEY"] = _ensure_valid_fernet(_enc)
os.environ.setdefault("APP_SECRET_KEY", "scraper-local-dummy-key-not-used")
_DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_DATA_DIR / "run.log", mode="w", encoding="utf-8"),
    ],
)

log = logging.getLogger("run_scraper_local")


# ---------------------------------------------------------------------------
# Sync a Supabase
# ---------------------------------------------------------------------------
async def _sync():
    from app.services.scraper_sync import _sync_to_postgres, _sync_to_historial
    log.info("Sincronizando productos a PostgreSQL...")
    await _sync_to_postgres()
    log.info("Guardando historial diario...")
    await _sync_to_historial()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Scraper local de precios UY")
    parser.add_argument("--gdu", action="store_true", help="Solo GDU (Geant/Disco/Devoto)")
    args = parser.parse_args()

    from app.services.scraper.fases import run_full, run_gdu_only
    from app.services.scraper import store

    if args.gdu:
        log.info("=== MODO: GDU only ===")
        run_gdu_only()
    else:
        log.info("=== MODO: Full scan (Tata + Farmashop + GDU) ===")
        run_full()

    totales = store.contar()
    log.info("Scraping completado — %s", {t: n for t, n in totales.items()})

    if not any(totales.values()):
        log.error("SQLite vacío — nada que sincronizar. Revisá los logs de arriba.")
        sys.exit(1)

    log.info("Subiendo a Supabase...")
    asyncio.run(_sync())
    log.info("¡Listo! Datos actualizados en Supabase.")


if __name__ == "__main__":
    main()

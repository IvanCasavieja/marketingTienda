"""
run_scan.py — Scraper de precios MKTG Platform.
Corre localmente. Guarda en SQLite intermedio y al final exporta a Excel.
Sin dependencia de PostgreSQL / Supabase.

USO:
  python run_scan.py full       → Todo (Tata + Farmashop + Botiga + GDU + ElDorado)
  python run_scan.py tata       → Solo Ta-Ta
  python run_scan.py farmashop  → Solo Farmashop
  python run_scan.py botiga     → Solo Botiga
  python run_scan.py gdu_rest   → Solo GDU REST (Disco/Devoto/Géant)
  python run_scan.py eldorado   → Solo El Dorado

Al final de cada scan crea:
  archivos/YYYY-MM-DD/precios_YYYY-MM-DD.xlsx
"""
import sys, asyncio, os, logging, time, smtplib, threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

# ── Cargar .env ANTES de importar cualquier módulo de la app ──────────────────
os.environ.setdefault("APP_ENV", "production")

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

_data_dir = os.environ.get("SCRAPER_DATA_DIR", "C:/tmp/scraper")
os.environ["SCRAPER_DATA_DIR"] = _data_dir
Path(_data_dir).mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
log = logging.getLogger("run_scan")

_executor = ThreadPoolExecutor(max_workers=1)

# ── Estadísticas globales del run ─────────────────────────────────────────────

_stats: dict = {
    "inicio":      None,
    "fases":       [],
    "total_prods": 0,
    "errores":     [],
}


def _fmt_dur(segundos: float) -> str:
    m, s = divmod(int(segundos), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s" if h else f"{m}m {s}s"


# ── Notificaciones por email ──────────────────────────────────────────────────

def _notificar(asunto: str, cuerpo: str) -> None:
    email = os.environ.get("NOTIFY_EMAIL")
    host  = os.environ.get("NOTIFY_SMTP_HOST", "smtp.gmail.com")
    port  = int(os.environ.get("NOTIFY_SMTP_PORT", "587"))
    user  = os.environ.get("NOTIFY_SMTP_USER")
    pwd   = os.environ.get("NOTIFY_SMTP_PASS")
    if not all([email, user, pwd]):
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = f"[MKTG Scraper] {asunto}"
        msg["From"]    = user
        msg["To"]      = email
        msg.set_content(cuerpo)
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls()
            s.login(user, pwd)
            s.send_message(msg)
        log.info("Notificacion enviada a %s", email)
    except Exception as e:
        log.warning("No se pudo enviar notificacion email: %s", e)


def _notificar_error(nombre_fase: str, exc: Exception) -> None:
    _stats["errores"].append(f"{nombre_fase}: {exc}")
    _notificar(
        f"ERROR en {nombre_fase}",
        f"El scan falló en la fase: {nombre_fase}\n\nError: {exc}\n\nRevisa la terminal.",
    )


def _notificar_completado(tipo: str) -> None:
    dur   = _fmt_dur(time.time() - _stats["inicio"])
    prods = _stats["total_prods"]
    lineas = [f"Scan {tipo.upper()} completado en {dur}", f"Total productos: {prods:,}", ""]
    for f in _stats["fases"]:
        estado = "OK" if f["ok"] else "ERROR"
        lineas.append(f"  [{estado}] {f['nombre']}: {f['productos']:,} — {_fmt_dur(f['fin'] - f['inicio'])}")
    if _stats["errores"]:
        lineas.append("\nErrores:")
        for e in _stats["errores"]:
            lineas.append(f"  - {e}")
    _notificar(f"Scan {tipo.upper()} completado", "\n".join(lineas))


# ── Wrapper de fase ───────────────────────────────────────────────────────────

async def _correr_fase(nombre: str, fn_blocking, *args) -> int:
    """Corre una fase bloqueante en el executor. Acumula en SQLite (sin sync a Postgres)."""
    from app.services.scraper import store
    loop  = asyncio.get_event_loop()
    t0    = time.time()
    ok    = True
    prods = 0
    log.info("▶ %s — iniciando", nombre)
    try:
        n_antes = sum(store.contar().values())
        await loop.run_in_executor(_executor, fn_blocking, *args)
        n_despues = sum(store.contar().values())
        prods = n_despues - n_antes
        dur = _fmt_dur(time.time() - t0)
        log.info("✓ %s — %d productos | %s", nombre, prods, dur)
    except Exception as exc:
        ok  = False
        dur = _fmt_dur(time.time() - t0)
        log.error("✗ %s — FALLÓ en %s: %s", nombre, dur, exc, exc_info=True)
        _notificar_error(nombre, exc)
    finally:
        _stats["fases"].append({
            "nombre":    nombre,
            "inicio":    t0,
            "fin":       time.time(),
            "productos": prods,
            "ok":        ok,
        })
        _stats["total_prods"] += prods
    return prods


# ── Export a Excel desde SQLite ───────────────────────────────────────────────

async def _export_excel_local():
    """Lee el SQLite y exporta a Excel en archivos/YYYY-MM-DD/."""
    from datetime import date as _date
    script = Path(__file__).parent / "scripts" / "export_sqlite.py"
    fecha  = str(_date.today())
    db_path = Path(_data_dir) / "productos.db"
    log.info("Export Excel → archivos/%s/  (SQLite: %s)", fecha, db_path)
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(script),
            "--fecha",  fecha,
            "--db",     str(db_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await proc.communicate()
        for line in out.decode("utf-8", errors="replace").splitlines():
            log.info("[export] %s", line)
        if proc.returncode == 0:
            log.info("Export completado.")
        else:
            log.warning("Export terminó con código %d", proc.returncode)
    except Exception as e:
        log.warning("Export falló: %s", e)


# ── Runners por cadena ────────────────────────────────────────────────────────

async def run_tata():
    from app.services.scraper.fases import run_tata_fase
    prog = Path(_data_dir) / "progreso_tata.json"
    if prog.exists():
        prog.unlink()
    for fase in (1, 2, 3, 4):
        await _correr_fase(f"Tata fase {fase}/4", run_tata_fase, fase)
    log.info("=== TATA COMPLETADO ===")


async def run_farmashop():
    from app.services.scraper.fases import run_farmashop_fase
    prog = Path(_data_dir) / "progreso_farmashop.json"
    if prog.exists():
        prog.unlink()
    for fase in (1, 2, 3, 4):
        await _correr_fase(f"Farmashop fase {fase}/4", run_farmashop_fase, fase)
    log.info("=== FARMASHOP COMPLETADO ===")


async def run_botiga():
    from app.services.scraper.fases import run_botiga_fase
    prog = Path(_data_dir) / "progreso_botiga.json"
    if prog.exists():
        prog.unlink()
    for fase in (1, 2, 3, 4):
        await _correr_fase(f"Botiga fase {fase}/4", run_botiga_fase, fase)
    log.info("=== BOTIGA COMPLETADO ===")


async def run_gdu_rest():
    """GDU via REST API — Disco/Devoto/Géant, 4 fases secuenciales en SQLite local."""
    from app.services.scraper.fases import run_gdu_rest_fase, PROGRESO_GDU_REST
    if PROGRESO_GDU_REST.exists():
        PROGRESO_GDU_REST.unlink()
    for fase in (1, 2, 3, 4):
        await _correr_fase(f"GDU REST fase {fase}/4", run_gdu_rest_fase, fase)
    log.info("=== GDU REST COMPLETADO ===")


async def run_eldorado():
    """El Dorado via VTEX IO Intelligent Search — 17 tiendas con precios por sucursal."""
    from app.services.scraper.fases import run_eldorado_fase, PROGRESO_ELDORADO
    if PROGRESO_ELDORADO.exists():
        PROGRESO_ELDORADO.unlink()
    for fase in (1, 2, 3, 4):
        await _correr_fase(f"ElDorado fase {fase}/4", run_eldorado_fase, fase)
    log.info("=== EL DORADO COMPLETADO ===")


async def run_full():
    from app.services.scraper import store
    store.limpiar()  # SQLite limpio al inicio de cada scan completo
    await run_tata()
    await run_farmashop()
    await run_botiga()
    await run_gdu_rest()
    await run_eldorado()
    log.info("=== SCAN COMPLETO — %d productos en SQLite ===", _stats["total_prods"])
    await _export_excel_local()


# ── Entry point ───────────────────────────────────────────────────────────────

OPCIONES = {
    "tata":      run_tata,
    "farmashop": run_farmashop,
    "botiga":    run_botiga,
    "gdu_rest":  run_gdu_rest,
    "eldorado":  run_eldorado,
    "full":      run_full,
}

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="MKTG Platform Scraper de Precios")
    ap.add_argument("tipo", nargs="?", default="full",
                    choices=list(OPCIONES.keys()),
                    help="Scan a correr (default: full)")
    ap.add_argument("--child", action="store_true",
                    help="Modo hijo — suprime notificaciones email")
    parsed = ap.parse_args()

    tipo     = parsed.tipo.lower()
    is_child = parsed.child
    fn       = OPCIONES[tipo]

    _stats["inicio"] = time.time()
    inicio_fmt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log.info("=" * 60)
    log.info("MKTG Platform Scraper — %s — %s", tipo.upper(), inicio_fmt)
    log.info("=" * 60)

    if not is_child:
        _notificar(
            f"Scan {tipo.upper()} iniciado",
            f"El scan {tipo.upper()} arrancó a las {inicio_fmt}.",
        )

    try:
        asyncio.run(fn())
        dur = _fmt_dur(time.time() - _stats["inicio"])
        log.info("=" * 60)
        log.info("FINALIZADO en %s — %d productos totales", dur, _stats["total_prods"])
        log.info("=" * 60)
        if not is_child:
            _notificar_completado(tipo)
    except KeyboardInterrupt:
        log.warning("Scan interrumpido por el usuario (Ctrl+C)")
    except Exception as exc:
        log.error("Error fatal: %s", exc, exc_info=True)
        if not is_child:
            _notificar_error("run_scan (fatal)", exc)
        sys.exit(1)

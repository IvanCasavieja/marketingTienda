"""
run_scan.py — Scraper de precios MKTG Platform.
Corre localmente y sincroniza al PostgreSQL remoto (Supabase).

USO:
  python run_scan.py gdu        → Geant + Disco + Devoto  (~2h)
  python run_scan.py tata       → Solo Ta-Ta               (~30min)
  python run_scan.py farmashop  → Solo Farmashop           (~15min)
  python run_scan.py full       → Todo                     (~3h)

NOTIFICACIONES (opcional):
  Agregar en backend/.env:
    NOTIFY_EMAIL=ivanmichelcasavieja@gmail.com
    NOTIFY_SMTP_HOST=smtp.gmail.com
    NOTIFY_SMTP_PORT=587
    NOTIFY_SMTP_USER=tu_cuenta@gmail.com
    NOTIFY_SMTP_PASS=tu_app_password_de_gmail
"""
import sys, asyncio, os, logging, time, smtplib, subprocess, threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

# ── Cargar .env ANTES de importar cualquier módulo de la app ──────────────────
# APP_ENV debe ser "production" antes de cargar .env para que database.py
# no active echo=True en SQLAlchemy (que inunda el log con cada INSERT).
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
    "inicio":       None,
    "fases":        [],   # {"nombre", "inicio", "fin", "productos", "ok"}
    "total_prods":  0,
    "errores":      [],
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
        return   # no configurado → silencioso

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
        f"El scan falló en la fase: {nombre_fase}\n\nError: {exc}\n\nRevisa la terminal para más detalles.",
    )


def _notificar_completado(tipo: str) -> None:
    dur   = _fmt_dur(time.time() - _stats["inicio"])
    prods = _stats["total_prods"]
    lineas = [f"Scan {tipo.upper()} completado en {dur}", f"Total productos sincronizados: {prods:,}", ""]
    for f in _stats["fases"]:
        estado = "OK" if f["ok"] else "ERROR"
        lineas.append(f"  [{estado}] {f['nombre']}: {f['productos']:,} productos — {_fmt_dur(f['fin'] - f['inicio'])}")
    if _stats["errores"]:
        lineas.append("\nErrores encontrados:")
        for e in _stats["errores"]:
            lineas.append(f"  - {e}")
    _notificar(f"Scan {tipo.upper()} completado", "\n".join(lineas))


# ── Sync a PostgreSQL remoto ──────────────────────────────────────────────────

async def _sync() -> int:
    from app.services.scraper_sync import _sync_to_postgres, _sync_to_historial
    from app.services.scraper import store
    n = len(store.todos())
    await _sync_to_postgres()
    await _sync_to_historial()
    return n


# ── Wrapper de fase con timing y stats ───────────────────────────────────────

async def _correr_fase(nombre: str, fn_blocking, *args) -> int:
    loop  = asyncio.get_event_loop()
    t0    = time.time()
    ok    = True
    prods = 0
    log.info("▶ %s — iniciando", nombre)
    try:
        await loop.run_in_executor(_executor, fn_blocking, *args)
        prods = await _sync()
        from app.services.scraper import store
        store.limpiar()
        dur = _fmt_dur(time.time() - t0)
        log.info("✓ %s — %d productos | %s", nombre, prods, dur)
    except Exception as exc:
        ok  = False
        dur = _fmt_dur(time.time() - t0)
        log.error("✗ %s — FALLÓ en %s: %s", nombre, dur, exc, exc_info=True)
        _notificar_error(nombre, exc)
    finally:
        _stats["fases"].append({
            "nombre":   nombre,
            "inicio":   t0,
            "fin":      time.time(),
            "productos": prods,
            "ok":       ok,
        })
        _stats["total_prods"] += prods
    return prods


# ── Runners ───────────────────────────────────────────────────────────────────

async def run_gdu():
    from app.services.scraper import store
    from app.services.scraper.fases import run_gdu_fase
    store.limpiar()
    prog = Path(_data_dir) / "progreso_gdu.json"
    if prog.exists():
        prog.unlink()
    for fase in (1, 2, 3, 4):
        await _correr_fase(f"GDU fase {fase}/4", run_gdu_fase, fase)
    log.info("=== GDU COMPLETADO — total acumulado: %d productos ===", _stats["total_prods"])


async def run_tata():
    from app.services.scraper import store
    from app.services.scraper.fases import run_tata_fase
    store.limpiar()
    prog = Path(_data_dir) / "progreso_tata.json"
    if prog.exists():
        prog.unlink()
    for fase in (1, 2, 3, 4):
        await _correr_fase(f"Tata fase {fase}/4", run_tata_fase, fase)
    log.info("=== TATA COMPLETADO ===")


async def run_farmashop():
    from app.services.scraper import store
    from app.services.scraper.fases import run_farmashop_fase
    store.limpiar()
    prog = Path(_data_dir) / "progreso_farmashop.json"
    if prog.exists():
        prog.unlink()
    for fase in (1, 2, 3, 4):
        await _correr_fase(f"Farmashop fase {fase}/4", run_farmashop_fase, fase)
    log.info("=== FARMASHOP COMPLETADO ===")


async def run_gdu_rest():
    """GDU via REST API — Disco/Devoto/Géant, 1 registro por producto × sucursal."""
    from app.services.scraper import store
    from app.services.scraper.fases import run_gdu_rest_fase, PROGRESO_GDU_REST
    store.limpiar()
    if PROGRESO_GDU_REST.exists():
        PROGRESO_GDU_REST.unlink()
    for fase in (1, 2, 3, 4):
        await _correr_fase(f"GDU REST fase {fase}/4", run_gdu_rest_fase, fase)
    log.info("=== GDU REST COMPLETADO ===")


async def run_botiga():
    """Runner de Botiga (botiga.farmashop.com.uy) — Magento 2.4 GraphQL.
    Incluye validación de URLs 404 post-scraping (ver botiga_graphql.validar_urls).
    GDU Playwright se omite intencionalmente — reemplazado por gdu_full_scan.py (REST API).
    """
    from app.services.scraper import store
    from app.services.scraper.fases import run_botiga_fase
    store.limpiar()
    prog = Path(_data_dir) / "progreso_botiga.json"
    if prog.exists():
        prog.unlink()
    for fase in (1, 2, 3, 4):
        await _correr_fase(f"Botiga fase {fase}/4", run_botiga_fase, fase)
    log.info("=== BOTIGA COMPLETADO ===")


async def run_full():
    await run_tata()
    await run_farmashop()
    await run_botiga()
    await run_gdu_rest()
    log.info("=== SCAN COMPLETO FINALIZADO — %d productos totales ===", _stats["total_prods"])


async def run_full_parallel():
    """Corre Tata, Farmashop y Botiga en subprocesos paralelos independientes.
    GDU se omite — reemplazado por gdu_full_scan.py (REST API, sin Playwright).
    """
    script    = Path(__file__).resolve()
    base_data = Path(_data_dir)
    procs: dict[str, subprocess.Popen] = {}

    for target in ("tata", "farmashop", "botiga"):
        sub_dir = base_data / target
        sub_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["SCRAPER_DATA_DIR"] = str(sub_dir)
        proc = subprocess.Popen(
            [sys.executable, str(script), target, "--child"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        procs[target] = proc
        log.info("▶ Subproceso %s lanzado (PID %d, dir=%s)", target.upper(), proc.pid, sub_dir)

    def _stream(label: str, proc: subprocess.Popen):
        try:
            for line in proc.stdout:
                log.info("[%s] %s", label, line.rstrip())
        except Exception:
            pass

    stream_threads = [
        threading.Thread(target=_stream, args=(label.upper(), proc), daemon=True)
        for label, proc in procs.items()
    ]
    for t in stream_threads:
        t.start()

    results: dict[str, int] = {}

    def _wait(label: str, proc: subprocess.Popen):
        proc.wait()
        results[label] = proc.returncode
        estado = "OK" if proc.returncode == 0 else f"ERROR (código {proc.returncode})"
        log.info("✓ Subproceso %s terminado — %s", label.upper(), estado)

    wait_threads = [
        threading.Thread(target=_wait, args=(label, proc))
        for label, proc in procs.items()
    ]
    for t in wait_threads:
        t.start()
    for t in wait_threads:
        t.join()
    for t in stream_threads:
        t.join(timeout=10)

    ok = all(rc == 0 for rc in results.values())
    if ok:
        log.info("=== SCAN PARALELO COMPLETADO — todos los scrapers OK ===")
    else:
        failures = [k for k, v in results.items() if v != 0]
        log.error("=== SCAN PARALELO COMPLETADO CON ERRORES — fallaron: %s ===", failures)


# ── Entry point ───────────────────────────────────────────────────────────────

OPCIONES = {
    "gdu":      run_gdu,       # Playwright GDU — deprecado
    "gdu_rest": run_gdu_rest,  # GDU via REST API (1 registro por producto × sucursal)
    "tata":     run_tata,
    "farmashop": run_farmashop,
    "botiga":   run_botiga,
    "full":     run_full,      # tata + farmashop + botiga + gdu_rest
    "parallel": run_full_parallel,
}

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="MKTG Platform Scraper de Precios")
    ap.add_argument("tipo", nargs="?", default="full",
                    choices=list(OPCIONES.keys()),
                    help="Scan a correr (default: full)")
    ap.add_argument("--child", action="store_true",
                    help="Modo hijo — suprime notificaciones email (usado por run_full_parallel)")
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
            f"El scan {tipo.upper()} arrancó a las {inicio_fmt}.\nTe avisamos cuando termine.",
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

"""El mantenimiento de arranque corre SOLO en el servidor desplegado.

Por qué existe este archivo: backend/.env de una PC de trabajo apunta a la
MISMA base de producción (ONBOARDING y PENDIENTES lo indican así), y varias de
las tareas que corren al arrancar son destructivas. La peor es
recuperar_jobs_huerfanos: marca como error TODO job pending/running anterior al
arranque y le VACÍA staged_data / staged_source_pptx / staged_excel_bytes, sin
deshacer. Levantar el backend en una laptop para probar algo le mataba la
corrida —y el Excel subido— a quien estuviera generando cenefas en la oficina.

La señal es RENDER_GIT_COMMIT, que Render inyecta en cada deploy y en una PC no
existe. Es la misma que /health ya usa para reportar el commit desplegado, y se
verificó contra los dos entornos: producción devuelve el hash, local "dev".

Si alguien vuelve a arrancar estas tareas sin condición, estos tests fallan.
"""
import os

import pytest

from app.core.config import Settings


def _settings(**env) -> Settings:
    """Settings() con env controlado (los campos obligatorios ya los pone conftest)."""
    return Settings(**env)


# ---------------------------------------------------------------------------
# Automático (MANTENIMIENTO_AL_ARRANCAR sin definir)
# ---------------------------------------------------------------------------

def test_una_pc_no_corre_mantenimiento(monkeypatch):
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    s = _settings()
    assert s.es_servidor_desplegado is False
    assert s.corre_mantenimiento is False


def test_el_servidor_desplegado_si_corre_mantenimiento(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "dd19026abc")
    s = _settings()
    assert s.es_servidor_desplegado is True
    assert s.corre_mantenimiento is True


def test_render_git_commit_vacia_no_alcanza(monkeypatch):
    # Una env var definida pero vacía no es un deploy — que no abra la puerta.
    monkeypatch.setenv("RENDER_GIT_COMMIT", "")
    assert _settings().corre_mantenimiento is False


# ---------------------------------------------------------------------------
# Override explícito: gana sobre la detección automática, en los dos sentidos
# ---------------------------------------------------------------------------

def test_forzar_true_en_una_pc(monkeypatch):
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    assert _settings(MANTENIMIENTO_AL_ARRANCAR=True).corre_mantenimiento is True


def test_forzar_false_en_el_servidor(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "dd19026abc")
    assert _settings(MANTENIMIENTO_AL_ARRANCAR=False).corre_mantenimiento is False


# ---------------------------------------------------------------------------
# El lifespan realmente consulta el flag para CADA tarea destructiva
# ---------------------------------------------------------------------------

def test_el_lifespan_gatea_todas_las_tareas():
    """Ninguna tarea de arranque queda suelta.

    Se lee el fuente en vez de arrancar la app porque arrancarla con el
    mantenimiento encendido tocaría la base de verdad — que es justamente lo
    que este cambio impide.
    """
    ruta = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
    with open(ruta, encoding="utf-8") as fh:
        fuente = fh.read()

    assert "mantenimiento = settings.corre_mantenimiento" in fuente

    # Migraciones + migrate_roles + recuperar_jobs_huerfanos van todas adentro
    # de _run_migrations(), así que alcanza con que su create_task esté gateado.
    assert "if mantenimiento:\n        asyncio.create_task(_run_migrations())" in fuente

    # Y cada loop periódico, con su propio guard.
    for flag in (
        "SYNC_INTERVAL_HOURS",
        "WATCHLIST_CHECK_INTERVAL_HOURS",
        "CAMPAIGN_ALERTS_CHECK_INTERVAL_HOURS",
        "COTIZACION_AUTO_UPDATE",
        "CENEFAS_CURADURIA",
    ):
        assert f"if mantenimiento and settings.{flag}" in fuente, (
            f"{flag} arranca sin consultar el mantenimiento — una PC apuntada a "
            f"produccion volveria a correr esa tarea"
        )

    # La purga es la excepcion: hace una pasada apenas arranca, asi que la lanza
    # _run_migrations cuando termina, y queda gateada por el mismo
    # `if mantenimiento` que _run_migrations. Arrancada en el cuerpo del
    # lifespan, en un servidor nuevo corria antes que las migraciones y fallaba
    # con 'relation "cenefa_jobs" does not exist' (visto el 10/09/2026).
    lanzar_purga = "asyncio.create_task(run_purga_cenefas_loop())"
    assert fuente.count(lanzar_purga) == 1, "la purga se lanza en mas de un lugar, o en ninguno"
    donde = fuente.index(lanzar_purga)
    inicio = fuente.index("async def _run_migrations():")
    fin = fuente.index("if mantenimiento:" + chr(10) + "        asyncio.create_task(_run_migrations())")
    assert inicio < donde < fin, "la purga tiene que arrancar adentro de _run_migrations"
    assert fuente.index("recuperar_jobs_huerfanos(arranque)") < donde, (
        "la purga tiene que arrancar despues de migrar y de recuperar los jobs huerfanos"
    )


# ---------------------------------------------------------------------------
# Una migracion rota tiene que dejar rastro en el log
# ---------------------------------------------------------------------------

def test_alembic_no_le_pisa_el_logging_al_backend():
    """Hasta el 10/09/2026, migrations/env.py llamaba a fileConfig() siempre,
    tambien cuando lo invocaba el lifespan del backend. Eso apagaba el logger de
    app.main y dejaba todo en WARNING: una migracion rota no escribia "Alembic
    migration failed", Alembic deshacia la transaccion entera, y el servidor
    quedaba con la base vacia respondiendo /health 200. Se descubrio levantando
    la plataforma desde cero en Docker.
    """
    base = os.path.join(os.path.dirname(__file__), "..")
    with open(os.path.join(base, "migrations", "env.py"), encoding="utf-8") as fh:
        env = fh.read()
    with open(os.path.join(base, "app", "main.py"), encoding="utf-8") as fh:
        main = fh.read()
    assert 'config.attributes.get("configure_logger", True)' in env
    assert 'cfg.attributes["configure_logger"] = False' in main

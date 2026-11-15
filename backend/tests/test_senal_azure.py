"""La señal de "servidor desplegado" y el commit de /health, también en Azure.

Complementa test_arranque_mantenimiento.py (que cubre Render y la PC). En Azure
Container Apps no existe RENDER_GIT_COMMIT: la plataforma inyecta
CONTAINER_APP_NAME, y el commit lo pasa el deploy en GIT_COMMIT
(.github/workflows/deploy-azure.yml).
"""
from app.core.config import Settings, commit_desplegado

_SENALES = ("RENDER_GIT_COMMIT", "CONTAINER_APP_NAME", "GIT_COMMIT")


def _limpiar(monkeypatch):
    for nombre in _SENALES:
        monkeypatch.delenv(nombre, raising=False)


def test_azure_container_apps_es_servidor_desplegado(monkeypatch):
    _limpiar(monkeypatch)
    monkeypatch.setenv("CONTAINER_APP_NAME", "mktg-backend")
    s = Settings()
    assert s.es_servidor_desplegado is True
    assert s.corre_mantenimiento is True


def test_git_commit_solo_no_abre_el_freno(monkeypatch):
    # GIT_COMMIT es un nombre genérico: que una PC lo tenga definido no la
    # convierte en el servidor.
    _limpiar(monkeypatch)
    monkeypatch.setenv("GIT_COMMIT", "dd19026abc")
    s = Settings()
    assert s.es_servidor_desplegado is False
    assert s.corre_mantenimiento is False


def test_container_app_name_vacia_no_alcanza(monkeypatch):
    _limpiar(monkeypatch)
    monkeypatch.setenv("CONTAINER_APP_NAME", "")
    assert Settings().corre_mantenimiento is False


def test_commit_en_una_pc_es_dev(monkeypatch):
    _limpiar(monkeypatch)
    assert commit_desplegado() == "dev"


def test_commit_en_azure_sale_de_git_commit(monkeypatch):
    _limpiar(monkeypatch)
    monkeypatch.setenv("GIT_COMMIT", "0123456789abcdef")
    assert commit_desplegado() == "0123456"


def test_commit_en_render_no_cambia(monkeypatch):
    _limpiar(monkeypatch)
    monkeypatch.setenv("RENDER_GIT_COMMIT", "dd19026abc")
    monkeypatch.setenv("GIT_COMMIT", "ffffffffff")
    assert commit_desplegado() == "dd19026"

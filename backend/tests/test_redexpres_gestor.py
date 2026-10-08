"""Perfil completo de Redexpres: superusuarios y quien tenga redexpres.manage."""
from types import SimpleNamespace

from app.api.routes.redexpres import _es_gestor


def test_gestor_es_superusuario_o_tiene_manage():
    assert _es_gestor(SimpleNamespace(is_superuser=True, permissions=[]))
    assert _es_gestor(SimpleNamespace(is_superuser=False, permissions=["redexpres.view", "redexpres.manage"]))
    assert not _es_gestor(SimpleNamespace(is_superuser=False, permissions=["redexpres.view"]))
    assert not _es_gestor(SimpleNamespace(is_superuser=False, permissions=None))

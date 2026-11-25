"""Un pedido de Redexpres confirmado no se puede cambiar por la API (H-020).

La pantalla bloquea los campos, pero el PATCH tiene que frenarlo igual: si no,
cualquiera con la sesión del local (o el gestor sin querer) lo pisaba.
Sin base: una base de mentira que devuelve siempre la misma fila.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes.redexpres import PlanillaRowUpdate, update_row


class _Res:
    def __init__(s, r):
        s.r = r

    def scalar_one_or_none(s):
        return s.r


class _Db:
    def __init__(s, r):
        s.r = r
        s.commit_llamado = False

    async def execute(s, *a, **k):
        return _Res(s.r)

    async def commit(s):
        s.commit_llamado = True


_GESTOR = SimpleNamespace(is_superuser=True, permissions=[], id=1)


def _patch(db, update):
    return asyncio.run(update_row(2026, 12, "Nativo Florida", update, db=db, current_user=_GESTOR))


def test_confirmado_no_se_cambia_ni_siendo_gestor():
    fila = SimpleNamespace(confirmado=True, pinchos=45)
    db = _Db(fila)
    with pytest.raises(HTTPException) as e:
        _patch(db, PlanillaRowUpdate(pinchos=3))
    assert e.value.status_code == 409
    assert "desconfirmarlo" in e.value.detail
    assert fila.pinchos == 45
    assert not db.commit_llamado


def test_confirmado_tampoco_acepta_extras():
    fila = SimpleNamespace(confirmado=True, pinchos=45, extras={})
    db = _Db(fila)
    with pytest.raises(HTTPException) as e:
        _patch(db, PlanillaRowUpdate(extras={"x": 1}))
    assert e.value.status_code == 409
    assert fila.extras == {}
    assert not db.commit_llamado

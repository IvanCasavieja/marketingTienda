"""La contraseña se cambia cada 60 días (Ivan, 24/11/2026: "que sea de 60
días el cambio"; antes eran 20). Los logins de sucursal quedan afuera, como
siempre: comparten la contraseña y no la pueden cambiar ellos.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.core import deps


def _pide(dias: int | None, *, primera_vez=False, sucursal=False) -> bool:
    cambiada = None if dias is None else datetime.now(timezone.utc) - timedelta(days=dias)
    usuario = SimpleNamespace(must_change_password=primera_vez, password_changed_at=cambiada)
    return asyncio.run(deps._needs_password_change(usuario, db=None, es_sucursal=sucursal))


def test_son_60_dias():
    assert deps._PASSWORD_MAX_AGE_DAYS == 60


def test_antes_de_los_60_no_se_pide():
    assert not _pide(21) and not _pide(59)


def test_pasados_los_60_se_pide():
    assert _pide(61)


def test_la_primera_vez_se_pide_igual():
    assert _pide(0, primera_vez=True)


def test_un_login_de_sucursal_nunca():
    assert not _pide(400, sucursal=True)

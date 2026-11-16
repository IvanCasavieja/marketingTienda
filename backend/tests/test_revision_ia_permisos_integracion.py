"""La IA que revisa las piezas, junto con las cuentas externas (integración del
16/11/2026): pedir las observaciones de la IA siendo quien entrega tiene que dar
403, no reventar. Antes de integrar, `_puede_ver` pasó a pedir también el
responsable de la tarea (para filtrar a la agencia) y la ruta de la IA lo
seguía llamando con dos datos: 500 en vez de 403."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.api.routes.revision_ia as rutas
from app.models.entregas import CalendarioEntrega, CalendarioVersion


class _Base:
    def __init__(self, version, entrega):
        self._por_clase = {CalendarioVersion: version, CalendarioEntrega: entrega}

    async def get(self, clase, _id):
        return self._por_clase.get(clase)


def _usuario(**kw):
    base = dict(id=7, is_active=True, is_superuser=False, permissions=["calendario.view"],
                mundos=["tienda_inglesa"], es_externo=False, empresa=None)
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.parametrize("externo", [False, True])
def test_quien_entrega_pide_la_revision_ia_y_recibe_403(monkeypatch, externo):
    tarea = SimpleNamespace(id="ta-1", asignado_a_id=7)
    barra = SimpleNamespace(id="br-1", mundo="tienda_inglesa")
    version = SimpleNamespace(id="ve-1", tarea_id="ta-1")
    entrega = SimpleNamespace(tarea_id="ta-1", aprobadores=[99], responsable_id=7)

    async def _tarea_y_barra(db, tarea_id, usuario, **kw):
        return tarea, barra

    monkeypatch.setattr(rutas, "_tarea_y_barra", _tarea_y_barra)
    monkeypatch.setattr(rutas, "puede_ver_revision", lambda u, e, t, v: False)
    usuario = _usuario(es_externo=externo, empresa="Agencia Pampa" if externo else None)
    with pytest.raises(HTTPException) as e:
        asyncio.run(rutas._version_visible(_Base(version, entrega), "ve-1", usuario))
    assert e.value.status_code == 403

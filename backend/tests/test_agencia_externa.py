"""Las cuentas externas: la agencia adentro, con la vista limitada (0068).

Pedido de Ivan (15/11/2026): "que la agencia en un futuro tenga acceso a la
plataforma… limitar también las vistas… que solamente puedan ver el
calendario actual, no lo que viene dentro de 2 o 3 meses".

Lo que se fija acá, sin base (lo que pasa con la base y la API de punta a
punta está en test_agencia_externa_api.py, que corre si hay una base de
prueba):

- La ventana: [hoy - 7, fin del mes + 7], en hora de Uruguay, con los bordes
  de mes, el cambio de año y la hora de Montevideo.
- Un externo nunca tiene permisos de gestión ni de admin, ni pasa como
  superadmin, aunque estén en su lista.
- Solo llega a su sesión, al calendario y a su campanita.
- Don Tino, si algún día se lo habilitan, le contesta solo de su ventana y sus
  tareas.
- No recibe avisos configurados.
"""
import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes.admin import CreateUserRequest, _ensure_externo_puede_tener
from app.api.routes.entregas import DecisionNueva
from app.core import externos
from app.core.deps import require_any_permission, require_permission
from app.services import calendario_consultas as cc
from app.services.calendario_avisos import puede_recibir_el_aviso

# ---------------------------------------------------------------------------
# La ventana
# ---------------------------------------------------------------------------


def test_la_ventana_va_de_una_semana_atras_al_fin_de_mes_mas_una_semana():
    assert externos.ventana(date(2026, 11, 15), 7, 7) == (date(2026, 11, 8), date(2026, 12, 7))


def test_la_ventana_usa_los_dias_de_la_configuracion():
    assert externos.ventana(date(2026, 11, 15), 0, 0) == (date(2026, 11, 15), date(2026, 11, 30))
    assert externos.ventana(date(2026, 11, 15), 3, 10) == (date(2026, 11, 12), date(2026, 12, 10))
    # Por defecto, la de settings (EXTERNOS_DIAS_ANTES / _DESPUES = 7).
    assert externos.ventana(date(2026, 11, 15)) == (date(2026, 11, 8), date(2026, 12, 7))


def test_los_bordes_del_mes():
    # El 1: arranca en el mes anterior y termina el 7 del que viene.
    assert externos.ventana(date(2026, 11, 1), 7, 7) == (date(2026, 10, 25), date(2026, 12, 7))
    # El último día: igual hasta el 7 del que viene.
    assert externos.ventana(date(2026, 11, 30), 7, 7) == (date(2026, 11, 23), date(2026, 12, 7))
    # Febrero, bisiesto y no.
    assert externos.ventana(date(2028, 2, 10), 7, 7)[1] == date(2028, 3, 7)
    assert externos.fin_de_mes(date(2028, 2, 10)) == date(2028, 2, 29)
    assert externos.fin_de_mes(date(2027, 2, 10)) == date(2027, 2, 28)


def test_el_cambio_de_anio():
    # Fines de diciembre: la ventana termina en enero del año siguiente.
    assert externos.ventana(date(2026, 12, 28), 7, 7) == (date(2026, 12, 21), date(2027, 1, 7))
    # Principios de enero: arranca en diciembre del año anterior.
    assert externos.ventana(date(2027, 1, 3), 7, 7) == (date(2026, 12, 27), date(2027, 2, 7))
    assert externos.meses_de_la_ventana((date(2026, 12, 21), date(2027, 1, 7))) == ["2026-12", "2027-01"]


def test_hoy_es_el_de_montevideo_y_no_el_de_greenwich():
    # 30/11 a las 22:30 en Montevideo = 1/12 01:30 en UTC: sigue siendo noviembre.
    ahora_utc = datetime(2026, 12, 1, 1, 30, tzinfo=timezone.utc)
    assert externos.hoy_en_uruguay(ahora_utc) == date(2026, 11, 30)
    assert externos.ventana_de_hoy(ahora_utc) == (date(2026, 11, 23), date(2026, 12, 7))
    # A las 3:30 UTC ya es 1/12 también en Montevideo: la ventana pasa a diciembre.
    assert externos.ventana_de_hoy(datetime(2026, 12, 1, 3, 30, tzinfo=timezone.utc)) == (
        date(2026, 11, 24), date(2027, 1, 7))
    # Fin de año: 31/12 a las 23 en Montevideo ya es 2027 en UTC.
    assert externos.hoy_en_uruguay(datetime(2027, 1, 1, 2, 0, tzinfo=timezone.utc)) == date(2026, 12, 31)


V = (date(2026, 11, 8), date(2026, 12, 7))


@pytest.mark.parametrize("desde,hasta,esperado", [
    (date(2026, 11, 15), date(2026, 11, 20), True),     # este mes
    (date(2026, 12, 7), date(2026, 12, 20), True),      # arranca justo el último día
    (date(2026, 10, 1), date(2026, 11, 8), True),       # termina justo el primero
    (date(2026, 10, 1), date(2027, 1, 30), True),       # la cruza entera
    (date(2026, 12, 8), date(2026, 12, 20), False),     # el mes que viene, pasado el margen
    (date(2027, 2, 15), date(2027, 2, 20), False),      # dentro de 3 meses
    (date(2026, 10, 1), date(2026, 11, 7), False),      # el mes pasado
    (date(2026, 11, 20), date(2026, 11, 10), True),     # fechas al revés: un día, adentro
])
def test_que_acciones_tocan_la_ventana(desde, hasta, esperado):
    assert externos.toca(desde, hasta, V) is esperado


# ---------------------------------------------------------------------------
# Permisos
# ---------------------------------------------------------------------------

def _usuario(uid=50, *permisos, externo=True, super_=False, empresa="Agencia Pampa", mundos=("tienda_inglesa",)):
    return SimpleNamespace(
        id=uid, full_name=f"Persona {uid}", email=f"p{uid}@x.uy", permissions=list(permisos),
        is_superuser=super_, is_active=True, es_externo=externo, empresa=empresa, mundos=list(mundos),
    )


def test_un_externo_solo_puede_ver_el_calendario():
    assert externos.permisos_no_permitidos(["calendario.view"]) == []
    assert externos.permisos_no_permitidos(["calendario.view", "calendario.tareas", "platform.admin"]) == [
        "calendario.tareas", "platform.admin"]


def test_aunque_tenga_un_permiso_de_mas_en_la_lista_no_le_sirve():
    raro = _usuario(50, "calendario.view", "calendario.edit", "calendario.tareas", "platform.admin", super_=True)
    assert externos.puede_tener(raro, "calendario.view")
    for p in ("calendario.edit", "calendario.tareas", "calendario.retail_media", "platform.admin", "precios.search"):
        assert not externos.puede_tener(raro, p)
    # Uno del equipo, como siempre.
    assert externos.puede_tener(_usuario(1, externo=False, super_=True), "platform.admin")
    assert externos.puede_tener(_usuario(2, "calendario.edit", externo=False), "calendario.edit")


def test_require_permission_le_niega_a_un_externo_lo_que_no_es_suyo():
    raro = _usuario(50, "calendario.view", "calendario.edit", "facturacion.view", super_=True)
    assert asyncio.run(require_permission("calendario.view")(raro)) is raro
    for p in ("calendario.edit", "facturacion.view", "platform.admin"):
        with pytest.raises(HTTPException) as e:
            asyncio.run(require_permission(p)(raro))
        assert e.value.status_code == 403
    with pytest.raises(HTTPException):
        asyncio.run(require_any_permission("calendario.tareas", "calendario.edit")(raro))


def test_el_panel_no_le_da_a_un_externo_permisos_de_gestion():
    externo = _usuario(50, "calendario.view")
    _ensure_externo_puede_tener(externo, ["calendario.view"])
    _ensure_externo_puede_tener(externo, [])
    for de_mas in (["calendario.tareas"], ["calendario.edit"], ["calendario.retail_media"], ["platform.admin"],
                   ["platform.users.manage"], ["ai.don_tino"]):
        with pytest.raises(HTTPException) as e:
            _ensure_externo_puede_tener(externo, ["calendario.view", *de_mas])
        assert e.value.status_code == 422
    # A uno del equipo no le aplica.
    _ensure_externo_puede_tener(_usuario(2, externo=False), ["calendario.tareas", "platform.admin"])


def test_el_alta_de_una_cuenta_externa_trae_la_empresa():
    datos = CreateUserRequest(email="ana@pampa.uy", full_name="Ana", password="x", es_externo=True,
                              empresa="  Agencia   Pampa ", mundos=["tienda_inglesa"])
    assert datos.es_externo and externos.limpiar_empresa(datos.empresa) == "Agencia Pampa"
    assert CreateUserRequest(email="a@b.uy", full_name="A", password="x").es_externo is False


def test_la_misma_empresa_se_reconoce_sin_mayusculas_ni_espacios_de_mas():
    assert externos.misma_empresa("Agencia Pampa", "agencia  pampa ")
    assert not externos.misma_empresa("Agencia Pampa", "Estudio Sur")
    assert not externos.misma_empresa(None, None)
    assert not externos.misma_empresa("", "")


@pytest.mark.parametrize("ruta,permitida", [
    ("/api/v1/auth/me", True),
    ("/api/v1/auth/change-password", True),
    ("/api/v1/calendario/datos", True),
    ("/api/v1/calendario/entregas", True),
    ("/api/v1/notificaciones", True),
    ("/api/v1/notificaciones/no-leidas/count", True),
    ("/api/v1/admin/users", False),
    ("/api/v1/colocacion/resumen", False),
    ("/api/v1/colocacion/mis-fotos", False),
    ("/api/v1/redexpres/meses", False),
    ("/api/v1/precios/buscar", False),
    ("/api/v1/watchlist", False),
    ("/api/v1/tools/cenefas/v2/templates", False),
    ("/api/v1/facturacion/resumen", False),
    ("/api/v1/chat/message", False),
    ("/api/v1/ia/brief/ordenar", False),
    ("/api/v1/analytics/x", False),
    ("/api/v1/calendariox", False),
])
def test_un_externo_solo_llega_a_su_sesion_al_calendario_y_a_su_campanita(ruta, permitida):
    assert externos.ruta_permitida(ruta, "/api/v1") is permitida


def test_un_externo_no_recibe_avisos_configurados():
    del_equipo = _usuario(2, "calendario.view", externo=False)
    agencia = _usuario(50, "calendario.view")
    assert puede_recibir_el_aviso(del_equipo, "tienda_inglesa")
    assert not puede_recibir_el_aviso(agencia, "tienda_inglesa")


def test_la_decision_puede_llevar_una_nota_interna():
    d = DecisionNueva(decision="cambios", comentario="Subí el logo", notaInterna="Comercial no confirmó el precio")
    assert d.notaInterna == "Comercial no confirmó el precio"
    assert DecisionNueva(decision="aprobada").notaInterna is None


# ---------------------------------------------------------------------------
# La huella de lo que ve (su "revisión")
# ---------------------------------------------------------------------------

def test_la_huella_es_la_misma_si_lo_que_ve_es_lo_mismo():
    a = {"mundo": "tienda_inglesa", "barras": [{"id": "b1", "nombre": "Ciberlunes"}]}
    b = {"barras": [{"nombre": "Ciberlunes", "id": "b1"}], "mundo": "tienda_inglesa"}
    assert externos.huella(a) == externos.huella(b)
    assert externos.huella(a) != externos.huella({**a, "barras": [{"id": "b1", "nombre": "Ciberlunes 2"}]})
    # Entra en un número de JavaScript sin perder precisión.
    assert 0 <= externos.huella(a) < 2 ** 53


# ---------------------------------------------------------------------------
# Don Tino, si algún día se le habilita a una cuenta externa
# ---------------------------------------------------------------------------

HOY = date(2026, 11, 15)
AGENCIA = _usuario(50, "calendario.view", "ai.don_tino")
OTRA_AGENCIA = _usuario(51, "calendario.view", empresa="Estudio Sur")
COLEGA = _usuario(52, "calendario.view", empresa="agencia pampa")
DEL_EQUIPO = _usuario(2, "calendario.view", "calendario.tareas", externo=False)


def _barra(id, nombre, desde, hasta, seccion="comercial"):
    return SimpleNamespace(id=id, mundo="tienda_inglesa", nombre=nombre, banda="MEGA EVENTO", seccion=seccion,
                           desde=desde, hasta=hasta, formato=None, hora=None, estado="pendiente")


def _tarea(id, barra_id, titulo, asignado, vence=HOY, parent=None):
    return SimpleNamespace(id=id, barra_id=barra_id, parent_id=parent, titulo=titulo, descripcion=None,
                           estado="pendiente", asignado_a_id=asignado, vence=vence)


BARRAS = [
    _barra("b-ahora", "Black Friday", date(2026, 11, 20), date(2026, 11, 29)),
    _barra("b-futuro", "Navidad SECRETA de febrero", date(2027, 2, 10), date(2027, 2, 20)),
    _barra("b-pasado", "Día del Niño PASADO", date(2026, 8, 1), date(2026, 8, 10)),
]
TAREAS = [
    _tarea("t-mia", "b-ahora", "Afiche de Black Friday", 50, parent="t-madre"),
    _tarea("t-madre", "b-ahora", "Madre INTERNA de promo", 2),
    _tarea("t-ajena", "b-ahora", "Tarea INTERNA de otro", 2),
    _tarea("t-mia-futura", "b-futuro", "Mi tarea del FUTURO", 50, vence=date(2027, 2, 1)),
    _tarea("t-otra-agencia", "b-ahora", "Tarea de OTRA agencia", 51),
]
PIEZAS = [
    SimpleNamespace(id="p1", barra_id="b-ahora", area="fisico", formato="Cenefas", estado="pendiente",
                    desde=None, hasta=None, hora=None, en_sharepoint=False),
    SimpleNamespace(id="p2", barra_id="b-futuro", area="fisico", formato="Cenefa FUTURA", estado="pendiente",
                    desde=None, hasta=None, hora=None, en_sharepoint=False),
]
AVISOS = [SimpleNamespace(id="a1", barra_id="b-ahora", dias_antes=3, destinatarios=[2, 50])]


class FuenteSinFiltro:
    """Como una consulta con un bug: devuelve todo, sin mirar mundo ni fechas.
    La de la agencia tiene que recortar igual."""

    def _b(self, i):
        return next(b for b in BARRAS if b.id == i)

    async def barras(self, mundos, *, rango=None, secciones=None, ids=None):
        return [b for b in BARRAS if ids is None or b.id in ids]

    async def piezas_de(self, ids):
        return list(PIEZAS)

    async def tareas_de(self, ids):
        return list(TAREAS)

    async def avisos_de(self, ids):
        return list(AVISOS)

    async def piezas_con_accion(self, mundos, desde, hasta):
        return [(p, self._b(p.barra_id)) for p in PIEZAS]

    async def tareas_con_accion(self, mundos, **kw):
        return [(t, self._b(t.barra_id)) for t in TAREAS]

    async def titulos_de_tareas(self, ids):
        return {t.id: t.titulo for t in TAREAS if t.id in ids}

    async def avisos_con_accion(self, mundos, desde, hasta):
        return [(a, self._b(a.barra_id)) for a in AVISOS]

    async def personas_activas(self):
        return [AGENCIA, OTRA_AGENCIA, COLEGA, DEL_EQUIPO]


def _tino(nombre, usuario=AGENCIA, args=None):
    salida = asyncio.run(cc.ejecutar(nombre, args or {}, usuario, None, hoy=HOY, fuente=FuenteSinFiltro()))
    return json.loads(salida), salida


@pytest.mark.parametrize("herramienta,args", [
    ("calendario_acciones", {}),
    ("calendario_acciones", {"periodo": "mes_que_viene"}),
    ("calendario_acciones", {"desde": "2027-02-01", "hasta": "2027-02-28"}),
    ("calendario_accion", {"accion_id": "b-ahora"}),
    ("calendario_accion", {"texto": "Black"}),
    ("calendario_piezas", {"desde": "2026-01-01", "hasta": "2027-03-01"}),
    ("calendario_tareas", {}),
    ("calendario_tareas", {"responsable": "todos", "estados": ["pendiente", "en-proceso", "hecha"]}),
])
def test_don_tino_no_le_cuenta_a_la_agencia_nada_fuera_de_su_ventana_ni_de_otros(herramienta, args):
    _, texto = _tino(herramienta, args=args)
    for secreto in ("SECRETA", "PASADO", "FUTURO", "FUTURA", "INTERNA", "OTRA agencia"):
        assert secreto not in texto, (herramienta, secreto, texto)


def test_don_tino_le_muestra_a_la_agencia_sus_tareas_de_la_ventana():
    datos, texto = _tino("calendario_tareas")
    assert [t["titulo"] for t in datos["tareas"]] == ["Afiche de Black Friday"]
    datos, _ = _tino("calendario_accion", args={"accion_id": "b-ahora"})
    assert datos["accion"]["nombre"] == "Black Friday"
    assert "avisos" not in datos or datos["avisos"] == []


def test_una_accion_fuera_de_la_ventana_no_existe_para_don_tino():
    datos, _ = _tino("calendario_accion", args={"accion_id": "b-futuro"})
    assert "error" in datos


def test_ni_la_carga_del_equipo_ni_los_avisos():
    for herramienta in ("calendario_carga", "calendario_avisos"):
        datos, texto = _tino(herramienta)
        assert "error" in datos and "externa" in datos["error"]
        assert "Black Friday" not in texto


def test_al_equipo_don_tino_le_sigue_contando_todo():
    datos, texto = _tino("calendario_tareas", usuario=DEL_EQUIPO, args={"responsable": "todos"})
    assert "Tarea INTERNA de otro" in texto

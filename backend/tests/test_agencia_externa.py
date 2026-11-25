"""Las cuentas externas: la agencia adentro, con la vista limitada (0069).

Pedido de Ivan (15/11/2026): "que la agencia en un futuro tenga acceso a la
plataforma… limitar también las vistas… que solamente puedan ver el
calendario actual, no lo que viene dentro de 2 o 3 meses".

Lo que se fija acá, sin base (lo que pasa con la base y la API de punta a
punta está en test_agencia_externa_api.py, que corre si hay una base de
prueba):

- La ventana (qué fechas ve) ahora es el alcance de cada persona: ver
  test_alcance_del_calendario.py.
- Un externo nunca tiene permisos de gestión ni de admin, ni pasa como
  superadmin, aunque estén en su lista.
- Solo llega a su sesión, al calendario y a su campanita.
- Don Tino, si algún día se lo habilitan, le contesta solo de su ventana y sus
  tareas.
- No recibe avisos configurados.
"""
import asyncio
import json
from datetime import date
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
# Desde la 0070 la ventana no es de las cuentas externas sino de cada persona
# (su alcance: No lo ve / 1 mes / 2 meses / 12 meses / Todo), y la de la
# agencia arranca en "No lo ve". Las cuentas de la ventana (bordes de mes, de
# año, la hora de Montevideo) están en test_alcance_del_calendario.py.

# ---------------------------------------------------------------------------
# Permisos
# ---------------------------------------------------------------------------

def _usuario(uid=50, *permisos, externo=True, super_=False, empresa="Agencia Pampa", mundos=("tienda_inglesa",),
             alcance=None):
    return SimpleNamespace(
        id=uid, full_name=f"Persona {uid}", email=f"p{uid}@x.uy", permissions=list(permisos),
        is_superuser=super_, is_active=True, es_externo=externo, empresa=empresa, mundos=list(mundos),
        calendario_alcance=alcance or ("nada" if externo else "todo"),
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


def test_la_misma_empresa_tambien_sin_tildes_y_con_la_enie_como_n():
    """19/11/2026: la empresa se escribía a mano, y una cuenta con
    «Disenadores» (sin ñ) quedaba en otra agencia que no veía sus tarjetas."""
    for escrita in ("Disenadores", "diseñadores ", "  DISEÑADORES", "Diséñadores"):
        assert externos.misma_empresa(escrita, "Diseñadores"), escrita
    assert externos.clave_de_empresa("  Another   MONDAY ") == "another monday"
    assert externos.clave_de_empresa("Ñandú Estudio") == "nandu estudio"
    assert externos.clave_de_empresa("   ") is None
    assert not externos.misma_empresa("Diseñadores", "Diseño")


def test_al_guardar_una_agencia_que_ya_existe_queda_como_ya_esta():
    from app.core.tableros import TABLEROS, tablero_de

    existentes = [*TABLEROS, "Agencia Pampa"]
    assert externos.empresa_como_ya_esta("disenadores ", existentes) == "Diseñadores"
    assert externos.empresa_como_ya_esta("AGENCIA  PAMPA", existentes) == "Agencia Pampa"
    # Una nueva, como vino (sin espacios de más); vacía, nada.
    assert externos.empresa_como_ya_esta("  Estudio   Nuevo ", existentes) == "Estudio Nuevo"
    assert externos.empresa_como_ya_esta("  ", existentes) is None
    # La lista para elegir: cada una una vez, como la escribió la primera.
    assert externos.sin_repetir([*TABLEROS, "Disenadores", "agencia pampa", "Agencia Pampa", None, ""]) == [
        "Publicis", "Another Monday", "Diseñadores", "agencia pampa"]
    assert tablero_de("disenadores") == "Diseñadores" and tablero_de("Otra") is None


def test_una_tarjeta_de_disenadores_es_de_la_cuenta_de_disenadores_aunque_falte_la_enie():
    cuenta = _usuario(60, "calendario.view", empresa="Disenadores")
    tarjeta = SimpleNamespace(asignado_a_id=None, para="agencia", agencia="Diseñadores")
    assert externos.es_tarea_propia(cuenta, tarjeta)
    assert not externos.es_tarea_propia(cuenta, SimpleNamespace(asignado_a_id=None, para="agencia", agencia="Publicis"))


@pytest.mark.parametrize("ruta,permitida", [
    ("/api/v1/auth/me", True),
    ("/api/v1/auth/change-password", True),
    ("/api/v1/calendario/datos", True),
    ("/api/v1/calendario/entregas", True),
    ("/api/v1/notificaciones", True),
    ("/api/v1/notificaciones/no-leidas/count", True),
    ("/api/v1/guia", True),
    ("/api/v1/guiax", False),
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
# Con "1 mes" (25/10 al 30/11): la agencia arranca en "No lo ve" (0070), y
# para probar qué le recorta Don Tino hace falta que vea algo.
AGENCIA = _usuario(50, "calendario.view", "ai.don_tino", alcance="1m")
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
AVISOS = [
    SimpleNamespace(id="a1", barra_id="b-ahora", dias_antes=3, destinatarios=[2, 50]),
    # De una acción fuera de "1 mes" que sale DENTRO del mes (90 días antes del
    # 10/02 es el 12/11): para probar que a quien la ve limitada no se le
    # cuenta aunque la fecha del aviso caiga en lo que pregunta.
    SimpleNamespace(id="a2", barra_id="b-futuro", dias_antes=90, destinatarios=[2]),
]


class FuenteSinFiltro:
    """Como una consulta con un bug: devuelve todo, sin mirar mundo ni fechas.
    La de la agencia tiene que recortar igual.

    `tarjetas`: las tareas que tienen su tarjeta en el tablero (entregas).
    Por defecto ninguna: «Mi tarea del FUTURO» es una tarea sin tarjeta, y
    esas la agencia no las ve fuera de su ventana (como en Mis tareas)."""

    def __init__(self, tarjetas=()):
        self.tarjetas = set(tarjetas)

    def _b(self, i):
        return next(b for b in BARRAS if b.id == i)

    async def tareas_con_tarjeta(self, ids):
        return {i for i in ids if i in self.tarjetas}

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


def _tino(nombre, usuario=AGENCIA, args=None, tarjetas=()):
    salida = asyncio.run(cc.ejecutar(nombre, args or {}, usuario, None, hoy=HOY, fuente=FuenteSinFiltro(tarjetas)))
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


def test_a_una_agencia_que_no_ve_el_calendario_don_tino_no_le_cuenta_nada_mas_que_lo_suyo():
    """«No lo ve» (lo que tiene una agencia por defecto): del calendario,
    nada. Lo suyo sí (19/11/2026, "Don Tino debe amoldarse a cada usuario"):
    sus tarjetas, que en su tablero ve siempre; esta cuenta no tiene ninguna."""
    sin_calendario = _usuario(53, "calendario.view", "ai.don_tino")
    for herramienta in ("calendario_acciones", "calendario_accion"):
        datos, texto = _tino(herramienta, usuario=sin_calendario, args={"accion_id": "b-ahora"})
        assert "error" in datos and "Black Friday" not in texto
    datos, texto = _tino("calendario_tareas", usuario=sin_calendario, tarjetas={"t-mia", "t-mia-futura"})
    assert datos["tareas"] == [] and datos["solo_las_suyas"]
    assert "Black Friday" not in texto and "FUTURO" not in texto


def test_a_la_agencia_le_cuenta_sus_tarjetas_aunque_la_accion_quede_fuera_de_su_ventana():
    """Sus tarjetas las ve siempre en su tablero (0070): Don Tino también
    (19/11/2026). De la acción, el nombre y las fechas, sin link ni id, como
    en su tablero; la ficha de la acción y lo de los demás siguen cerrados.
    Una tarea suya SIN tarjeta fuera de su ventana, no: como en Mis tareas."""
    datos, texto = _tino("calendario_tareas", tarjetas={"t-mia-futura"})
    assert [t["titulo"] for t in datos["tareas"]] == ["Afiche de Black Friday", "Mi tarea del FUTURO"]
    futura = datos["tareas"][1]["accion"]
    assert futura["nombre"] == "Navidad SECRETA de febrero" and futura["fuera_de_lo_que_ve"] is True
    assert "link" not in futura and "id" not in futura
    assert (futura["desde"], futura["hasta"]) == ("2027-02-10", "2027-02-20")
    for secreto in ("INTERNA", "OTRA agencia", "PASADO"):
        assert secreto not in texto, secreto
    datos, _ = _tino("calendario_accion", args={"accion_id": "b-futuro"}, tarjetas={"t-mia-futura"})
    assert "error" in datos
    # Sin tarjeta, la de febrero no.
    datos, _ = _tino("calendario_tareas")
    assert [t["titulo"] for t in datos["tareas"]] == ["Afiche de Black Friday"]


def test_a_la_agencia_lo_mio_son_las_tarjetas_de_su_agencia():
    """«¿Qué tengo pendiente?» (responsable 'yo'): a una agencia, las tarjetas
    de su agencia, como en su tablero, aunque no estén a su nombre."""
    de_la_agencia = SimpleNamespace(id="t-pampa", barra_id="b-ahora", parent_id=None, titulo="Banner de la agencia",
                                    descripcion=None, estado="pendiente", asignado_a_id=None, vence=HOY,
                                    para="agencia", agencia="agencia pampa")
    TAREAS.append(de_la_agencia)
    try:
        datos, texto = _tino("calendario_tareas", args={"responsable": "yo"})
    finally:
        TAREAS.remove(de_la_agencia)
    assert [t["titulo"] for t in datos["tareas"]] == ["Afiche de Black Friday", "Banner de la agencia"]
    assert "OTRA agencia" not in texto and "INTERNA" not in texto


def test_al_equipo_don_tino_le_sigue_contando_todo():
    datos, texto = _tino("calendario_tareas", usuario=DEL_EQUIPO, args={"responsable": "todos"})
    assert "Tarea INTERNA de otro" in texto
    # El aviso de la acción de febrero, a quien ve todo, sí.
    _, texto = _tino("calendario_avisos", usuario=DEL_EQUIPO, args={"desde": "2026-11-01", "hasta": "2026-11-30"})
    assert "SECRETA" in texto


# Alguien del EQUIPO con el calendario en "1 mes" (0070): Don Tino le recorta
# las fechas como la pantalla, pero no las tareas de los demás (es del equipo).
INTERNO_1M = _usuario(3, "calendario.view", externo=False, alcance="1m")


@pytest.mark.parametrize("herramienta,args", [
    ("calendario_acciones", {}),
    ("calendario_acciones", {"desde": "2027-02-01", "hasta": "2027-02-28"}),
    ("calendario_piezas", {"desde": "2026-01-01", "hasta": "2027-03-01"}),
    ("calendario_tareas", {"responsable": "todos"}),
    ("calendario_avisos", {}),
    ("calendario_avisos", {"desde": "2026-11-01", "hasta": "2026-11-30"}),
])
def test_don_tino_le_recorta_las_fechas_a_alguien_del_equipo_con_un_mes(herramienta, args):
    """Si la condición volviera a ser solo para las cuentas externas, Don Tino
    le contaría la «Navidad SECRETA de febrero» que en la pantalla no ve
    (revisión del 16/11/2026: no había prueba)."""
    _, texto = _tino(herramienta, usuario=INTERNO_1M, args=args)
    for secreto in ("SECRETA", "FUTURA", "FUTURO", "PASADO"):
        assert secreto not in texto, (herramienta, secreto, texto)


def test_a_alguien_del_equipo_con_un_mes_le_cuenta_las_tareas_de_los_demas_de_su_ventana():
    _, texto = _tino("calendario_tareas", usuario=INTERNO_1M, args={"responsable": "todos"})
    assert "Tarea INTERNA de otro" in texto

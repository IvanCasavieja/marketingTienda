"""La guía de uso y lo que sabe Don Tino salen de la misma fuente (25/11/2026).

Ivan: "hay que actualizar la guía de uso y fijarse que Don Tino pueda manejar
toda la app". La guía vive en app/services/guia.py: de ahí la pantalla
(/ayuda, GET /guia) y el prompt de Don Tino. Lo que se fija acá: cada tipo de
cuenta ve lo suyo, no quedan cosas que ya no existen, y Don Tino lleva el
mismo texto.
"""
import asyncio
from types import SimpleNamespace

from app.services import guia


def _usuario(*permisos, externo=False, super_=False, mundos=("tienda_inglesa",), alc="todo", uid=1):
    return SimpleNamespace(
        id=uid, is_superuser=super_, es_externo=externo, permissions=list(permisos), mundos=list(mundos),
        calendario_alcance=alc, empresa="Publicis" if externo else None,
    )


EQUIPO = _usuario("calendario.view", "calendario.edit", "calendario.tareas", "calendario.pedidos", "ai.don_tino",
                  "cenefas.view")
AGENCIA = _usuario("calendario.view", externo=True, alc="nada")
LOCAL = _usuario("ai.don_tino", mundos=("redexpres",))


def _claves(usuario, local=False):
    return [s.clave for s in guia.secciones_para(usuario, local)]


def test_el_equipo_ve_el_nucleo_y_sus_herramientas():
    claves = _claves(EQUIPO)
    for c in ("primeros-pasos", "calendario", "ficha", "crear-tarea", "tablero", "tarjeta", "revisar", "mis-tareas",
              "cenefas", "don-tino"):
        assert c in claves, c
    # Lo que no tiene, no.
    for c in ("agencia", "mi-pedido", "fotos", "planilla", "finanzas", "admin", "precios"):
        assert c not in claves, c


def test_la_agencia_ve_solo_lo_suyo():
    claves = _claves(AGENCIA)
    assert claves == ["primeros-pasos", "tarjeta", "agencia"]
    # De lo básico, solo su menú: ni el de Tienda ni el de los locales.
    basico = guia.secciones_para(AGENCIA, False)[0]
    textos = " ".join(p for parte in basico.partes for p in parte.puntos)
    assert "Mi tablero" in textos and "Fotos para subir" not in textos and "Herramientas" not in textos


def test_un_local_ve_su_pedido_y_sus_fotos():
    assert _claves(LOCAL, local=True) == ["primeros-pasos", "mi-pedido", "fotos", "don-tino"]


def test_quien_no_ve_el_calendario_no_tiene_su_guia_pero_si_mis_tareas_y_el_tablero():
    sin_cal = _usuario("calendario.view", "calendario.pedidos", alc="nada")
    claves = _claves(sin_cal)
    assert "calendario" not in claves and "ficha" not in claves
    assert "mis-tareas" in claves and "tablero" in claves


def test_las_partes_se_recortan_por_permiso_y_mundo():
    # Sin calendario.edit: no le explica cómo crear acciones.
    solo_ver = _usuario("calendario.view")
    cal = next(s for s in guia.secciones_para(solo_ver, False) if s.clave == "calendario")
    assert "Crear y cambiar acciones" not in [p.titulo for p in cal.partes]
    # Fuera de Tienda Inglesa no aparece lo de los headers ni el Excel del cronograma.
    redex = _usuario("calendario.view", "calendario.edit", mundos=("redexpres",))
    cal = next(s for s in guia.secciones_para(redex, False) if s.clave == "calendario")
    titulos = [p.titulo for p in cal.partes]
    assert "Envíos, Retail Media y headers" not in titulos and "De dónde salen las fechas" not in titulos


def test_el_superadmin_ve_todo_lo_del_equipo():
    claves = _claves(_usuario(super_=True))
    for c in ("planilla", "colocacion", "finanzas", "admin", "precios", "rrss", "medios", "convertidor"):
        assert c in claves, c


def test_no_quedan_cosas_que_ya_no_existen():
    texto = guia.como_texto()
    # Una tarea = un pedido (0090): ni subtareas ni «Pedir una pieza» como botón.
    assert "Subtarea" not in texto and "**Pedir una pieza**" not in texto
    assert texto.count("subtareas") == 1  # solo el «Ya no hay subtareas»
    # La revisión: Avanzar y Aprobar y terminar, no "Aprobar" a secas.
    assert "**Avanzar**" in texto and "**Aprobar y terminar**" in texto
    assert "**Aprobar**" not in texto
    # La ficha ya no tiene pestañas.
    assert "pestaña Tareas" not in texto
    # La validación de RRSS ya no guarda historial (26/11/2026): cada una se
    # borra sola a las 24 horas, y la pestaña se llama «Las de hoy».
    rrss = next(s for s in guia.SECCIONES if s.clave == "rrss")
    rrss_texto = guia.como_texto((rrss,))
    assert "Historial" not in rrss_texto
    assert "**Las de hoy**" in rrss_texto and "24 horas" in rrss_texto


def test_don_tino_lleva_la_misma_guia():
    from app.api.routes import chat

    assert guia.como_texto(base_url=chat._BASE_URL) in chat._SYSTEM_PROMPT
    for s in guia.SECCIONES:
        assert s.titulo in chat._SYSTEM_PROMPT


def test_el_chat_le_dice_que_partes_puede_usar():
    from app.api.routes import chat

    texto = chat._contexto_del_dia(EQUIPO, secciones=["El calendario", "Tableros"])
    assert "De la guía, puede usar: El calendario; Tableros." in texto
    assert "De la guía" not in chat._contexto_del_dia(EQUIPO)


def test_el_json_de_la_pantalla():
    secciones = guia.como_json(guia.secciones_para(LOCAL, True))
    pedido = next(s for s in secciones if s["clave"] == "mi-pedido")
    assert pedido["ruta"] == "/redexpres/mi-pedido" and pedido["icono"]
    assert pedido["partes"][0]["titulo"] == "Cargar" and pedido["partes"][0]["puntos"]
    assert set(pedido["partes"][0]) == {"titulo", "puntos", "numerada"}


class _DbSinLocal:
    async def execute(self, *_a, **_k):
        return SimpleNamespace(first=lambda: None)


class _DbConLocal:
    async def execute(self, *_a, **_k):
        return SimpleNamespace(first=lambda: (7,))


def test_la_ruta_manda_lo_de_cada_uno():
    from app.api.routes.guia import ver_guia

    agencia = asyncio.run(ver_guia(current_user=AGENCIA, db=_DbSinLocal()))
    assert [s["clave"] for s in agencia["secciones"]] == ["primeros-pasos", "tarjeta", "agencia"]
    local = asyncio.run(ver_guia(current_user=LOCAL, db=_DbConLocal()))
    assert "mi-pedido" in [s["clave"] for s in local["secciones"]]


def test_la_agencia_llega_a_la_guia_y_a_nada_mas_nuevo():
    from app.core import externos

    assert externos.ruta_permitida("/api/v1/guia", "/api/v1")
    assert not externos.ruta_permitida("/api/v1/guiax", "/api/v1")

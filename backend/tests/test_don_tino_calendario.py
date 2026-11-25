"""Don Tino lee el calendario con los permisos de quien pregunta.

Pedido (15/11/2026): que se le pueda preguntar "¿qué piezas de Express vencen
esta semana y siguen sin aprobar?", "¿qué tengo que hacer hoy?", "¿cómo viene
el Ciberlunes?" o "¿quién está más cargado la semana que viene?", y que arme
el estado para gerencia.

Lo que se fija acá, sin base y sin la API:
- Nadie ve nada de un mundo que no abre: ni pidiéndolo por nombre, ni por id,
  ni aunque la consulta a la base (simulada acá a propósito "rota", sin filtro
  de mundo) devolviera filas de otro negocio.
- Sin `calendario.view` no hay herramientas del calendario.
- "Esta semana", "mañana"... se resuelven en hora de Uruguay.
- Lo que devuelve cada herramienta tiene tope de tamaño, y si se recorta lo dice.
- El chat de punta a punta (con la API simulada con la forma real): el modelo
  pide una herramienta, se le contesta con datos del calendario y su
  respuesta vuelve con los links a las acciones; el uso queda registrado.
"""
import asyncio
import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.services import calendario_consultas as cc

HOY = date(2026, 11, 15)  # domingo


# ---------------------------------------------------------------------------
# Datos de prueba
# ---------------------------------------------------------------------------

def _usuario(uid, nombre, mundos, *permisos, super_=False, activo=True):
    return SimpleNamespace(
        id=uid, full_name=nombre, email=f"u{uid}@x.uy", mundos=list(mundos),
        permissions=list(permisos), is_superuser=super_, is_active=activo,
    )


ANA = _usuario(1, "Ana Tienda", ["tienda_inglesa"], "calendario.view", "ai.don_tino")
RAUL = _usuario(2, "Raúl Redexpres", ["redexpres"], "calendario.view", "ai.don_tino")
SIN_CALENDARIO = _usuario(3, "Sole Sin", ["redexpres"], "ai.don_tino")
JEFA = _usuario(4, "Jefa", [], super_=True)
LUCIA = _usuario(5, "Lucía Ambas", ["tienda_inglesa", "redexpres"], "calendario.view")


def _barra(id, mundo, nombre, desde, hasta, banda="MEGA EVENTO", seccion="comercial", **kw):
    return SimpleNamespace(id=id, mundo=mundo, nombre=nombre, banda=banda, seccion=seccion,
                           desde=desde, hasta=hasta, formato=kw.get("formato"), hora=kw.get("hora"),
                           estado=kw.get("estado"))


def _pieza(id, barra_id, formato, estado, desde=None, area="fisico"):
    return SimpleNamespace(id=id, barra_id=barra_id, area=area, formato=formato, estado=estado,
                           desde=desde, hasta=None, hora=None, en_sharepoint=False)


def _tarea(id, barra_id, titulo, estado="pendiente", asignado=None, vence=None, parent=None, descripcion=None):
    return SimpleNamespace(id=id, barra_id=barra_id, parent_id=parent, titulo=titulo, descripcion=descripcion,
                           estado=estado, asignado_a_id=asignado, vence=vence)


def _aviso(id, barra_id, dias, destinatarios):
    return SimpleNamespace(id=id, barra_id=barra_id, dias_antes=dias, destinatarios=destinatarios)


BARRAS = [
    _barra("br-ciber", "tienda_inglesa", "Ciberlunes SECRETO TI", date(2026, 11, 16), date(2026, 11, 18)),
    _barra("br-ciber-25", "tienda_inglesa", "Ciberlunes SECRETO TI", date(2025, 11, 3), date(2025, 11, 5)),
    _barra("br-red", "redexpres", "Ofertas de la red", date(2026, 11, 10), date(2026, 11, 20), banda="Promociones"),
    _barra("br-red-env", "redexpres", "Mail a locales", date(2026, 11, 12), date(2026, 11, 12),
           banda="email", seccion="envio", formato="Mailing digital", estado="pendiente"),
]
PIEZAS = [
    _pieza("p1", "br-ciber", "Cenefas TI", "pendiente"),
    _pieza("p2", "br-red", "Cenefas red", "en-proceso", desde=date(2026, 11, 13)),
    _pieza("p3", "br-red", "Afiche red", "aprobado"),
]
TAREAS = [
    _tarea("t1", "br-ciber", "Tarea SECRETA de TI", asignado=1, vence=date(2026, 11, 15)),
    _tarea("t2", "br-red", "Revisar cenefas", asignado=2, vence=date(2026, 11, 15)),
    _tarea("t3", "br-red", "Tarea vencida", asignado=2, vence=date(2026, 11, 2)),
    # Asignada a Ana, que no ve Redexpres: en Redexpres no se dice su nombre.
    _tarea("t4", "br-red", "Para alguien de afuera", asignado=1, vence=date(2026, 11, 18)),
    _tarea("t5", "br-red", "Sin dueño", vence=date(2026, 11, 19)),
    _tarea("t6", "br-red", "Hecha", estado="hecha", asignado=2, vence=date(2026, 11, 14)),
]
AVISOS = [
    _aviso("a1", "br-ciber", 1, [1]),
    _aviso("a2", "br-red", 0, [2, 1]),
]


class FuenteFalsa:
    """Datos en memoria. A propósito NO filtra por mundo (como una consulta
    con un bug): las herramientas tienen que filtrar igual. Guarda con qué
    mundos se la llamó."""

    def __init__(self, barras=BARRAS, piezas=PIEZAS, tareas=TAREAS, avisos=AVISOS):
        self._barras, self._piezas, self._tareas, self._avisos = barras, piezas, tareas, avisos
        self.mundos_pedidos: list[list[str]] = []

    def _b(self, barra_id):
        return next(b for b in self._barras if b.id == barra_id)

    async def barras(self, mundos, *, rango=None, secciones=None, ids=None):
        self.mundos_pedidos.append(list(mundos))
        out = list(self._barras)
        if ids is not None:
            out = [b for b in out if b.id in ids]
        if rango is not None:
            out = [b for b in out if b.desde <= rango[1] and b.hasta >= rango[0]]
        if secciones:
            out = [b for b in out if b.seccion in secciones]
        return out

    async def piezas_de(self, ids):
        return [p for p in self._piezas if p.barra_id in ids]

    async def tareas_de(self, ids):
        return [t for t in self._tareas if t.barra_id in ids]

    async def avisos_de(self, ids):
        return [a for a in self._avisos if a.barra_id in ids]

    async def piezas_con_accion(self, mundos, desde, hasta):
        self.mundos_pedidos.append(list(mundos))
        return [(p, self._b(p.barra_id)) for p in self._piezas
                if desde <= (p.desde or self._b(p.barra_id).desde) <= hasta]

    async def tareas_con_accion(self, mundos, *, estados, rango, incluir_vencidas, incluir_sin_fecha, hoy):
        self.mundos_pedidos.append(list(mundos))
        return [(t, self._b(t.barra_id)) for t in self._tareas]

    async def titulos_de_tareas(self, ids):
        return {t.id: t.titulo for t in self._tareas if t.id in ids}

    async def avisos_con_accion(self, mundos, desde, hasta):
        self.mundos_pedidos.append(list(mundos))
        return [(a, self._b(a.barra_id)) for a in self._avisos]

    async def personas_activas(self):
        return [ANA, RAUL, SIN_CALENDARIO, JEFA, LUCIA]


def _correr(nombre, usuario, args=None, fuente=None):
    fuente = fuente or FuenteFalsa()
    salida = asyncio.run(cc.ejecutar(nombre, args or {}, usuario, None, hoy=HOY, fuente=fuente))
    return json.loads(salida), salida, fuente


# ---------------------------------------------------------------------------
# Fechas en hora de Uruguay
# ---------------------------------------------------------------------------

def test_hoy_es_el_dia_de_montevideo_aunque_en_utc_ya_sea_manana():
    # Domingo 15/11 a las 22:30 en Montevideo = lunes 16/11 01:30 UTC.
    ahora_utc = datetime(2026, 11, 16, 1, 30, tzinfo=timezone.utc)
    assert cc.hoy_en_uruguay(ahora_utc) == date(2026, 11, 15)


def test_las_semanas_van_de_lunes_a_domingo():
    assert cc.rango_de_periodo("esta_semana", HOY) == (date(2026, 11, 9), date(2026, 11, 15))
    assert cc.rango_de_periodo("semana_que_viene", HOY) == (date(2026, 11, 16), date(2026, 11, 22))
    assert cc.rango_de_periodo("semana_pasada", HOY) == (date(2026, 11, 2), date(2026, 11, 8))
    lunes = date(2026, 11, 16)
    assert cc.rango_de_periodo("esta_semana", lunes) == (date(2026, 11, 16), date(2026, 11, 22))


def test_hoy_manana_y_los_meses():
    assert cc.rango_de_periodo("hoy", HOY) == (HOY, HOY)
    assert cc.rango_de_periodo("manana", HOY) == (date(2026, 11, 16),) * 2
    assert cc.rango_de_periodo("mañana", HOY) == (date(2026, 11, 16),) * 2
    assert cc.rango_de_periodo("este_mes", HOY) == (date(2026, 11, 1), date(2026, 11, 30))
    assert cc.rango_de_periodo("mes_que_viene", date(2026, 12, 20)) == (date(2027, 1, 1), date(2027, 1, 31))
    assert cc.rango_de_periodo("mes_pasado", date(2026, 1, 10)) == (date(2025, 12, 1), date(2025, 12, 31))
    assert cc.rango_de_periodo("proximos_7_dias", HOY) == (HOY, date(2026, 11, 21))


def test_un_periodo_inventado_o_una_fecha_rota_vuelven_como_error():
    datos, _, _ = _correr("calendario_acciones", RAUL, {"periodo": "el_finde_largo"})
    assert "período" in datos["error"]
    datos, _, _ = _correr("calendario_acciones", RAUL, {"desde": "28/11/2026"})
    assert "AAAA-MM-DD" in datos["error"]
    datos, _, _ = _correr("calendario_acciones", RAUL, {"desde": "2026-11-30", "hasta": "2026-11-01"})
    assert "anterior" in datos["error"]


def test_cuando_dice_en_palabras_donde_esta_la_accion():
    assert cc.cuando(date(2026, 11, 16), date(2026, 11, 18), HOY) == "arranca mañana"
    assert cc.cuando(date(2026, 11, 10), date(2026, 11, 20), HOY) == "en curso, termina en 5 días"
    assert cc.cuando(date(2026, 11, 1), date(2026, 11, 14), HOY) == "terminó ayer"
    assert cc.cuando(HOY, HOY, HOY, es_envio=True) == "sale hoy"


# ---------------------------------------------------------------------------
# Permisos: solo los mundos que la persona abre
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("herramienta,args", [
    ("calendario_acciones", {"periodo": "este_mes"}),
    ("calendario_acciones", {"texto": "ciberlunes"}),
    ("calendario_piezas", {"periodo": "este_mes"}),
    ("calendario_tareas", {}),
    ("calendario_carga", {"periodo": "este_mes"}),
    ("calendario_avisos", {"periodo": "este_mes"}),
])
def test_sin_el_mundo_no_ve_nada_de_ese_mundo(herramienta, args):
    """Raúl solo abre Redexpres. La fuente falsa le devuelve TODO (como una
    consulta sin filtro): igual no puede aparecer nada de Tienda Inglesa."""
    datos, crudo, fuente = _correr(herramienta, RAUL, args)
    assert "error" not in datos, datos
    assert "SECRETO" not in crudo and "SECRETA" not in crudo and "br-ciber" not in crudo
    assert "Tienda Inglesa" not in crudo
    # Y a la base se le pidió solo su mundo.
    assert fuente.mundos_pedidos and all(m == ["redexpres"] for m in fuente.mundos_pedidos)


def test_pedir_un_mundo_ajeno_es_un_error_y_no_se_consulta_nada():
    datos, _, fuente = _correr("calendario_piezas", RAUL, {"mundo": "tienda_inglesa"})
    assert "no tiene acceso a Tienda Inglesa" in datos["error"]
    assert fuente.mundos_pedidos == []
    # Por nombre también: "Express" es Tienda Express, que tampoco abre.
    datos, _, _ = _correr("calendario_acciones", RAUL, {"mundo": "express"})
    assert "no tiene acceso a Tienda Express" in datos["error"]


def test_una_accion_ajena_no_se_encuentra_ni_por_id_ni_por_nombre():
    datos, _, _ = _correr("calendario_accion", RAUL, {"accion_id": "br-ciber"})
    assert "No encontré esa acción" in datos["error"]
    datos, crudo, _ = _correr("calendario_accion", RAUL, {"texto": "Ciberlunes"})
    assert "No encontré ninguna acción" in datos["error"]
    assert "SECRETO" not in crudo


def test_sin_calendario_view_no_hay_nada():
    for herramienta in cc.HERRAMIENTAS:
        datos, _, fuente = _correr(herramienta, SIN_CALENDARIO, {"texto": "x"})
        assert "calendario.view" in datos["error"]
        assert fuente.mundos_pedidos == []


def test_quien_no_ve_ese_mundo_aparece_sin_nombre():
    """La tarea t4 es de Ana, que no abre Redexpres: Lucía (que abre los dos)
    la ve en Redexpres como "alguien que ya no ve este calendario", igual que
    en la ficha. Y su propio nombre sale con "(vos)"."""
    datos, crudo, _ = _correr("calendario_accion", LUCIA, {"accion_id": "br-red"})
    responsables = {t["titulo"]: t["responsable"] for t in datos["tareas"]}
    assert responsables["Para alguien de afuera"] == cc.NADIE
    assert responsables["Revisar cenefas"] == "Raúl Redexpres"
    assert responsables["Sin dueño"] == "sin asignar"
    assert "Ana Tienda" not in crudo


def test_el_superadmin_ve_todos_los_mundos():
    datos, crudo, _ = _correr("calendario_acciones", JEFA, {"periodo": "este_mes"})
    assert {a["id"] for a in datos["acciones"]} == {"br-ciber", "br-red", "br-red-env"}


# ---------------------------------------------------------------------------
# Lo que contesta cada herramienta
# ---------------------------------------------------------------------------

def test_cada_accion_trae_su_link_para_abrirla():
    datos, _, _ = _correr("calendario_acciones", RAUL, {"periodo": "este_mes"})
    red = next(a for a in datos["acciones"] if a["id"] == "br-red")
    assert red["link"] == "/calendario?accion=br-red"
    assert red["piezas"] == {"total": 2, "en-proceso": 1, "aprobado": 1}
    assert red["cuando"] == "en curso, termina en 5 días"


def test_entre_dos_con_el_mismo_nombre_elige_la_proxima_y_avisa_la_otra():
    datos, _, _ = _correr("calendario_accion", ANA, {"texto": "ciberlunes"})
    assert datos["accion"]["id"] == "br-ciber"
    assert [o["id"] for o in datos["otras_coincidencias"]] == ["br-ciber-25"]
    assert datos["resumen_piezas"] == {"total": 1, "pendiente": 1}


def test_piezas_que_vencen_en_la_semana_y_siguen_sin_aprobar():
    datos, _, _ = _correr("calendario_piezas", RAUL, {"periodo": "esta_semana", "estados": ["pendiente", "en-proceso"]})
    # p2 sale el 13/11 (fecha propia); el envío suelto el 12/11. p3 está aprobada.
    assert [(p["formato"], p["sale"]) for p in datos["piezas"]] == [
        ("Mailing digital", "2026-11-12"), ("Cenefas red", "2026-11-13"),
    ]
    assert all(p["atrasada"] for p in datos["piezas"])  # ya salieron y siguen sin aprobar
    assert datos["piezas"][0]["envio_suelto"] is True


def test_que_tengo_que_hacer_hoy_trae_lo_de_hoy_y_lo_vencido():
    datos, _, _ = _correr("calendario_tareas", RAUL, {"responsable": "yo", "periodo": "hoy"})
    assert [t["titulo"] for t in datos["tareas"]] == ["Revisar cenefas", "Tarea vencida"]
    assert datos["vencidas"] == 1
    assert datos["tareas"][0]["responsable"] == "Raúl Redexpres (vos)"


def test_una_persona_que_no_existe_es_un_error_claro():
    datos, _, _ = _correr("calendario_tareas", RAUL, {"responsable": "Pepe"})
    assert "No encontré a nadie" in datos["error"]
    # Y alguien que existe pero no ve Redexpres tampoco se encuentra por nombre.
    datos, _, _ = _correr("calendario_tareas", RAUL, {"responsable": "Ana"})
    assert "No encontré a nadie" in datos["error"]


def test_la_carga_ordena_de_mas_a_menos_cargado():
    datos, _, _ = _correr("calendario_carga", RAUL, {"periodo": "esta_semana"})
    personas = [p["persona"] for p in datos["personas"]]
    assert personas[0] == "Raúl Redexpres (vos)"  # 1 vence en la semana + 1 vencida
    raul = datos["personas"][0]
    assert (raul["vencen_en_el_periodo"], raul["vencidas"], raul["abiertas"]) == (1, 1, 2)
    assert cc.NADIE in personas and "sin asignar" in personas
    assert "Ana Tienda" not in json.dumps(datos, ensure_ascii=False)


def test_avisos_para_mi():
    datos, _, _ = _correr("calendario_avisos", RAUL, {"desde": "2026-11-01", "hasta": "2026-11-30", "para": "yo"})
    assert [a["accion"]["id"] for a in datos["avisos"]] == ["br-red"]
    assert datos["avisos"][0]["para"] == ["Raúl Redexpres (vos)", cc.NADIE]


# ---------------------------------------------------------------------------
# Tamaño
# ---------------------------------------------------------------------------

def test_a_json_recorta_y_lo_dice():
    datos = {"hoy": "2026-11-15", "items": [{"nombre": "x" * 200, "n": i} for i in range(400)]}
    salida = cc.a_json(datos, ("items",), max_bytes=5_000)
    assert len(salida.encode("utf-8")) <= 5_000
    leido = json.loads(salida)
    assert leido["recortado"]["items"]["total"] == 400
    assert 0 < leido["recortado"]["items"]["mostrados"] < 400
    assert len(leido["items"]) == leido["recortado"]["items"]["mostrados"]
    # Lo primero (lo más urgente) es lo que queda.
    assert leido["items"][0]["n"] == 0


def test_a_json_no_toca_lo_que_entra():
    datos = {"items": [1, 2, 3]}
    assert json.loads(cc.a_json(datos, ("items",))) == datos


def test_un_mes_enorme_no_pasa_del_tope():
    """300 acciones con nombres largos y 10 tareas cada una: lo que viaja al
    modelo no pasa de MAX_BYTES, y dice que hay más."""
    barras = [
        _barra(f"br-{i}", "redexpres", f"Acción número {i} " + "con un nombre larguísimo " * 6,
               date(2026, 11, 1 + i % 28), date(2026, 11, 2 + i % 28))
        for i in range(300)
    ]
    tareas = [_tarea(f"t-{i}-{j}", f"br-{i}", "Tarea " * 30, asignado=2, vence=date(2026, 11, 20),
                     descripcion="detalle " * 200)
              for i in range(300) for j in range(10)]
    fuente = FuenteFalsa(barras=barras, piezas=[], tareas=tareas, avisos=[])
    for herramienta, args in [
        ("calendario_acciones", {"periodo": "este_mes"}),
        ("calendario_tareas", {}),
        ("calendario_accion", {"accion_id": "br-1"}),
        ("calendario_carga", {"periodo": "este_mes"}),
    ]:
        _, crudo, _ = _correr(herramienta, RAUL, args, fuente=fuente)
        assert len(crudo.encode("utf-8")) <= cc.MAX_BYTES, herramienta
        assert "error" not in json.loads(crudo)
    datos, _, _ = _correr("calendario_acciones", RAUL, {"periodo": "este_mes"}, fuente=fuente)
    assert datos["total"] == 300 and "recortado" in datos


def test_los_textos_largos_se_cortan():
    assert cc.corto("a" * 500, 10) == "a" * 9 + "…"
    assert cc.corto("  dos   espacios  ", 50) == "dos espacios"


# ---------------------------------------------------------------------------
# El chat, de punta a punta, con la API simulada
# ---------------------------------------------------------------------------

def _app_de_chat(usuario, monkeypatch, api):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from app.api.routes import chat
    from app.core.config import settings
    from app.core.database import get_db
    from app.core.deps import get_current_user
    from app.core.rate_limit import limiter
    from app.services import ia_cliente

    agregados = []

    class SesionFalsa:
        def add(self, fila):
            agregados.append(fila)

    async def db_falsa():
        yield SesionFalsa()

    async def usuario_actual():
        return usuario

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-simulada")
    monkeypatch.setattr(ia_cliente, "cliente_anthropic", api.cliente)
    monkeypatch.setattr(cc, "FuenteCalendario", lambda db: FuenteFalsa())
    limiter.reset()
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(chat.router)
    app.dependency_overrides[get_db] = db_falsa
    app.dependency_overrides[get_current_user] = usuario_actual
    return TestClient(app), agregados


def test_el_chat_usa_la_herramienta_y_contesta_con_el_link(monkeypatch):
    import ia_simulada as sim
    from app.core.config import settings
    from app.models.ai_usage_log import AIUsageLog

    api = sim.ApiGrabada([
        sim.mensaje([sim.pensamiento(), sim.texto("Me fijo."),
                     sim.herramienta("calendario_accion", {"texto": "Ofertas de la red"})],
                    "tool_use", entrada=900, salida=60, cache_escrito=11_000),
        sim.mensaje([sim.pensamiento(), sim.texto(
            "[Ofertas de la red](/calendario?accion=br-red) viene bien: 1 de 2 piezas aprobadas.")],
            entrada=2_500, salida=200, cache_leido=11_000),
    ])
    cliente, agregados = _app_de_chat(RAUL, monkeypatch, api)
    r = cliente.post("/chat/message", json={"message": "¿Cómo viene Ofertas de la red?", "history": []})
    assert r.status_code == 200, r.text
    assert "(/calendario?accion=br-red)" in r.json()["reply"]

    primero, segundo = api.pedidos
    assert primero["model"] == settings.MODELO_IA
    assert primero["max_tokens"] == 4_000
    nombres = [t["name"] for t in primero["tools"]]
    assert "calendario_accion" in nombres and "buscar_precio" not in nombres
    # La fecha va en un bloque aparte, después del que se cachea.
    assert primero["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "domingo" in primero["system"][1]["text"] or "Hoy es" in primero["system"][1]["text"]
    # La segunda vuelta lleva el pedido del modelo tal cual (con su razonamiento)
    # y el resultado de la herramienta, con el link y sin nada de otro mundo.
    assert [b["type"] for b in segundo["messages"][1]["content"]] == ["thinking", "text", "tool_use"]
    resultado = segundo["messages"][2]["content"][0]
    assert resultado["type"] == "tool_result"
    contenido = json.loads(resultado["content"])
    assert contenido["accion"]["link"] == "/calendario?accion=br-red"
    assert "SECRETO" not in resultado["content"]
    # Las dos llamadas quedaron registradas, con la caché sumada como entrada.
    usos = [f for f in agregados if isinstance(f, AIUsageLog)]
    assert [(u.feature, u.input_tokens, u.output_tokens) for u in usos] == [
        ("don_tino_home", 11_900, 60), ("don_tino_home", 13_500, 200),
    ]


def test_sin_calendario_view_el_modelo_ni_ve_las_herramientas(monkeypatch):
    import ia_simulada as sim

    api = sim.ApiGrabada([sim.mensaje([sim.texto("No tengo acceso al calendario.")])])
    cliente, _ = _app_de_chat(SIN_CALENDARIO, monkeypatch, api)
    r = cliente.post("/chat/message", json={"message": "¿Qué tengo que hacer hoy?", "history": []})
    assert r.status_code == 200
    # Ninguna del calendario ni del tablero. Es de Redexpres: desde el
    # 25/11/2026 se le ofrece la de los pedidos (ve solo su local).
    nombres = [t["name"] for t in api.pedidos[0].get("tools", [])]
    assert nombres == ["redexpres_pedidos"]


def test_si_el_modelo_igual_pide_una_herramienta_del_calendario_se_corta(monkeypatch):
    """Aunque el modelo la pidiera (no se le ofreció), sin el permiso no se
    ejecuta: vuelve un error y no se toca la base."""
    from app.api.routes.chat import _ejecutar_tool

    salida = asyncio.run(_ejecutar_tool("calendario_tareas", {"responsable": "yo"}, SIN_CALENDARIO, None))
    assert "calendario.view" in json.loads(salida)["error"]

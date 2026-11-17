"""El tablero de tarjetas estilo Trello (0070), sin base.

Pedido de Ivan (16/11/2026): "una vista estilo Trello: Ingresado, En proceso,
Esperando feedback, Finalizado, Archivado. Podemos ir arrastrando las
tarjetas. Una vez finalizadas, 10 días después pasan solas a Archivado". Y
para que ande rápido, lo archivado hace 30 días o más ni se carga.

Lo que se fija acá:
- la columna sale del momento de la entrega y de sus fechas;
- qué movimientos puede hacer cada uno (la agencia, el equipo, quien aprueba);
- cuándo se archiva sola y cuándo se oculta;
- el catálogo de tipos de tarea (nombre "<Acción> - <Tipo>", lo tildado con
  sus medidas) y cómo se parte una búsqueda;
- de quién es una tarjeta (la ve siempre, aunque la campaña quede fuera de su
  alcance) y los avisos.
"""
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.routes.calendario import TareaDePlantilla, TareaNueva, es_pieza, puede_crear_tarea, tareas_de_plantilla
from app.services import entregas as reglas
from app.services import tipos_de_tarea as tipos


def _utc(y, m, d, h=15):
    return datetime(y, m, d, h, tzinfo=timezone.utc)


HOY = date(2026, 11, 16)


def _col(momento, iniciada=False, **kw):
    return reglas.columna_de(momento, iniciada=iniciada, hoy=kw.pop("hoy", HOY), dias_para_archivar=10, **kw)


# ---------------------------------------------------------------------------
# Las columnas
# ---------------------------------------------------------------------------

def test_las_columnas_salen_del_momento():
    assert _col("produccion") == "ingresado"
    assert _col("produccion", iniciada=True) == "en-proceso"
    assert _col("cambios") == "en-proceso"
    assert _col("cambios", iniciada=True) == "en-proceso"
    assert _col("revision") == "esperando"
    assert _col("aprobada", finalizada_at=_utc(2026, 11, 15)) == "finalizado"


def test_a_los_10_dias_de_finalizada_pasa_sola_a_archivado():
    # Finalizada el 6/11: el 15 sigue en Finalizado, el 16 ya está archivada.
    fin = _utc(2026, 11, 6)
    assert _col("aprobada", finalizada_at=fin, hoy=date(2026, 11, 15)) == "finalizado"
    assert _col("aprobada", finalizada_at=fin, hoy=date(2026, 11, 16)) == "archivado"
    # "Con la fecha simulada 11 días después", archivada.
    assert _col("aprobada", finalizada_at=_utc(2026, 11, 5), hoy=HOY) == "archivado"


def test_el_dia_de_finalizada_es_el_de_montevideo():
    # 1/11 a las 01:00 UTC es todavía 31/10 en Montevideo: se cuenta desde el 31.
    assert reglas.se_archiva_sola(datetime(2026, 11, 1, 1, tzinfo=timezone.utc), None, date(2026, 11, 10), 10)
    assert not reglas.se_archiva_sola(datetime(2026, 11, 1, 4, tzinfo=timezone.utc), None, date(2026, 11, 10), 10)


def test_archivada_a_mano_y_sacada_del_archivo():
    assert _col("aprobada", finalizada_at=_utc(2026, 11, 15), archivada_at=_utc(2026, 11, 15)) == "archivado"
    # Sacada del archivo a mano: vuelve a contar 10 días desde ahí (si no, se
    # volvería a archivar en el acto).
    viejo = _utc(2026, 10, 1)
    assert _col("aprobada", finalizada_at=viejo, desarchivada_at=_utc(2026, 11, 14)) == "finalizado"
    assert _col("aprobada", finalizada_at=viejo, desarchivada_at=_utc(2026, 11, 1)) == "archivado"


def test_a_los_30_dias_en_archivado_se_oculta():
    # Finalizada el 1/10: se archiva el 11/10 y se oculta el 10/11.
    fin = _utc(2026, 10, 1)
    assert not reglas.oculta(fin, None, None, date(2026, 11, 9), 10, 30)
    assert reglas.oculta(fin, None, None, date(2026, 11, 10), 10, 30)
    # Archivada a mano el 20/10: se oculta el 19/11.
    assert not reglas.oculta(fin, _utc(2026, 10, 20), None, date(2026, 11, 18), 10, 30)
    assert reglas.oculta(fin, _utc(2026, 10, 20), None, date(2026, 11, 19), 10, 30)
    assert reglas.dia_de_archivo(fin, None, None, 10) == date(2026, 10, 11)


# ---------------------------------------------------------------------------
# Quién mueve qué
# ---------------------------------------------------------------------------

AGENCIA = reglas.QuienMueve(es_externo=True, entrega=True, decide=False, del_equipo_de_la_tarjeta=False)
OTRA_AGENCIA = reglas.QuienMueve(es_externo=True, entrega=False, decide=False, del_equipo_de_la_tarjeta=False)
APROBADORA = reglas.QuienMueve(es_externo=False, entrega=False, decide=True, del_equipo_de_la_tarjeta=True)
DEL_EQUIPO_SIN_TURNO = reglas.QuienMueve(es_externo=False, entrega=False, decide=False, del_equipo_de_la_tarjeta=True)
AJENO = reglas.QuienMueve(es_externo=False, entrega=False, decide=False, del_equipo_de_la_tarjeta=False)


def _mov(desde, a, quien, hay=False):
    return reglas.movimiento(desde, a, quien, hay_versiones=hay)


def _no(desde, a, quien, codigo, hay=False):
    with pytest.raises(reglas.MovimientoInvalido) as e:
        _mov(desde, a, quien, hay)
    assert e.value.codigo == codigo, str(e.value)
    return str(e.value)


def test_la_agencia_arranca_y_entrega():
    assert _mov("ingresado", "en-proceso", AGENCIA) == "arrancar"
    assert _mov("en-proceso", "ingresado", AGENCIA) == "volver"
    # A Esperando feedback se llega entregando: el arrastre abre "Entregar".
    assert "entregá los materiales" in _no("en-proceso", "esperando", AGENCIA, 409)
    assert "entregá los materiales" in _no("ingresado", "esperando", AGENCIA, 409)


def test_la_agencia_no_finaliza_ni_aprueba_ni_archiva():
    for desde in ("ingresado", "en-proceso", "esperando", "archivado"):
        assert "no puede finalizar" in _no(desde, "finalizado", AGENCIA, 403)
    _no("esperando", "en-proceso", AGENCIA, 403)
    _no("finalizado", "archivado", AGENCIA, 403)
    _no("archivado", "finalizado", AGENCIA, 403)


def test_otra_agencia_no_mueve_nada():
    _no("ingresado", "en-proceso", OTRA_AGENCIA, 403)
    _no("en-proceso", "esperando", OTRA_AGENCIA, 403)


def test_el_equipo_pide_cambios_aprueba_y_archiva():
    assert _mov("esperando", "en-proceso", APROBADORA, hay=True) == "pedir-cambios"
    assert _mov("esperando", "finalizado", APROBADORA, hay=True) == "aprobar"
    assert _mov("finalizado", "archivado", APROBADORA, hay=True) == "archivar"
    assert _mov("archivado", "finalizado", APROBADORA, hay=True) == "desarchivar"
    # Si no le toca en la cadena, no decide (lo que respeta la cadena de aprobadores).
    _no("esperando", "finalizado", DEL_EQUIPO_SIN_TURNO, 403, hay=True)
    _no("esperando", "en-proceso", DEL_EQUIPO_SIN_TURNO, 403, hay=True)
    # Pero sí archiva lo que lleva.
    assert _mov("finalizado", "archivado", DEL_EQUIPO_SIN_TURNO) == "archivar"
    _no("finalizado", "archivado", AJENO, 403)


def test_movimientos_que_no_existen():
    _no("ingresado", "finalizado", APROBADORA, 422)
    _no("en-proceso", "finalizado", APROBADORA, 422, hay=True)
    # Con una entrega esperando feedback, primero se decide: no se archiva.
    assert "aprobarla o pedir cambios" in _no("esperando", "archivado", APROBADORA, 422, hay=True)
    _no("finalizado", "en-proceso", APROBADORA, 422, hay=True)
    _no("esperando", "ingresado", APROBADORA, 422, hay=True)
    # Lo ya entregado no vuelve a Ingresado.
    assert "no vuelve a Ingresado" in _no("en-proceso", "ingresado", AGENCIA, 422, hay=True)
    assert _mov("en-proceso", "en-proceso", AGENCIA) == "nada"


def test_los_destinos_para_mover_a():
    assert reglas.destinos_posibles("ingresado", AGENCIA, hay_versiones=False) == ["en-proceso", "esperando"]
    assert reglas.destinos_posibles("en-proceso", AGENCIA, hay_versiones=True) == ["esperando"]
    assert reglas.destinos_posibles("esperando", AGENCIA, hay_versiones=True) == []
    assert reglas.destinos_posibles("esperando", APROBADORA, hay_versiones=True) == ["en-proceso", "finalizado"]
    assert reglas.destinos_posibles("finalizado", APROBADORA, hay_versiones=True) == ["archivado"]
    assert reglas.destinos_posibles("en-proceso", OTRA_AGENCIA, hay_versiones=True) == []
    # El equipo también la archiva (cancelada) desde Ingresado o En proceso.
    assert reglas.destinos_posibles("ingresado", APROBADORA, hay_versiones=False) == ["en-proceso", "archivado"]
    assert reglas.destinos_posibles("en-proceso", DEL_EQUIPO_SIN_TURNO, hay_versiones=True) == ["archivado"]
    # Archivada sin terminar: sale del archivo solo a su columna.
    assert reglas.destinos_posibles("archivado", APROBADORA, hay_versiones=False, vuelve_a="ingresado") == ["ingresado"]
    assert reglas.destinos_posibles("archivado", AGENCIA, hay_versiones=False, vuelve_a="ingresado") == []


def test_movimientos_prohibidos_para_alguien_del_equipo_que_no_lleva_la_tarjeta():
    """Quien no tiene nada que ver con la tarjeta (ve el tablero entero con
    «Todo») no la arranca, no la vuelve, no la archiva ni la saca del archivo.
    El equipo de la tarjeta sí la puede arrancar (revisión del 16/11/2026)."""
    _no("ingresado", "en-proceso", AJENO, 403)
    _no("en-proceso", "ingresado", AJENO, 403)
    _no("archivado", "finalizado", AJENO, 403)
    _no("ingresado", "archivado", AJENO, 403)
    assert _mov("ingresado", "en-proceso", APROBADORA) == "arrancar"


# ---------------------------------------------------------------------------
# Una pieza cancelada (revisión del 16/11/2026)
# ---------------------------------------------------------------------------

def test_archivada_sin_terminar_va_a_archivado():
    """Antes solo se archivaba una finalizada: una pieza cancelada quedaba
    para siempre en Ingresado o En proceso. Archivada a mano manda sobre el
    momento."""
    hace_un_rato = _utc(2026, 11, 16, 12)
    assert _col("produccion", archivada_at=hace_un_rato) == "archivado"
    assert _col("produccion", iniciada=True, archivada_at=hace_un_rato) == "archivado"
    assert _col("cambios", archivada_at=hace_un_rato) == "archivado"
    assert _col("revision", archivada_at=hace_un_rato) == "archivado"
    # Y a los 30 días en Archivado se oculta, como una finalizada.
    assert reglas.oculta(None, _utc(2026, 10, 1), None, date(2026, 10, 31), 10, 30)
    assert not reglas.oculta(None, _utc(2026, 10, 1), None, date(2026, 10, 30), 10, 30)


def test_el_equipo_archiva_una_pieza_cancelada_y_la_saca_a_su_columna():
    assert _mov("ingresado", "archivado", APROBADORA) == "archivar"
    assert _mov("en-proceso", "archivado", DEL_EQUIPO_SIN_TURNO, hay=True) == "archivar"
    _no("ingresado", "archivado", AGENCIA, 403)
    _no("en-proceso", "archivado", AGENCIA, 403, hay=True)

    def sacar(a, quien, vuelve_a):
        return reglas.movimiento("archivado", a, quien, hay_versiones=False, vuelve_a=vuelve_a)

    assert sacar("ingresado", APROBADORA, "ingresado") == "desarchivar"
    assert sacar("en-proceso", DEL_EQUIPO_SIN_TURNO, "en-proceso") == "desarchivar"
    with pytest.raises(reglas.MovimientoInvalido) as e:
        sacar("finalizado", APROBADORA, "ingresado")
    assert e.value.codigo == 422 and "Ingresado" in str(e.value)
    with pytest.raises(reglas.MovimientoInvalido) as e:
        sacar("ingresado", AGENCIA, "ingresado")
    assert e.value.codigo == 403
    with pytest.raises(reglas.MovimientoInvalido) as e:
        sacar("ingresado", AJENO, "ingresado")
    assert e.value.codigo == 403


def test_a_que_columna_vuelve_al_sacarla_del_archivo():
    def entrega(momento, iniciada=None, ronda=0):
        return SimpleNamespace(momento=momento, iniciada_at=iniciada, ronda=ronda, archivada_at=_utc(2026, 11, 16))

    assert reglas.columna_al_desarchivar(entrega("aprobada")) == "finalizado"
    assert reglas.columna_al_desarchivar(entrega("produccion")) == "ingresado"
    assert reglas.columna_al_desarchivar(entrega("produccion", iniciada=_utc(2026, 11, 10))) == "en-proceso"
    assert reglas.columna_al_desarchivar(entrega("cambios", ronda=1)) == "en-proceso"
    assert reglas.columna_al_desarchivar(entrega("revision", ronda=1)) == "esperando"
    assert reglas.archivada_sin_terminar(entrega("produccion"))
    assert not reglas.archivada_sin_terminar(entrega("aprobada"))
    assert not reglas.archivada_sin_terminar(SimpleNamespace(momento="produccion", archivada_at=None))


# ---------------------------------------------------------------------------
# De quién es una tarjeta
# ---------------------------------------------------------------------------

def _tarea(**kw):
    base = dict(id="ta-1", asignado_a_id=None, creado_por_id=2, para="agencia", agencia="Agencia Pampa")
    base.update(kw)
    return SimpleNamespace(**base)


def test_la_tarjeta_de_la_agencia_es_de_todas_sus_cuentas():
    entrega = SimpleNamespace(creado_por_id=2, aprobadores=[3])
    ana = SimpleNamespace(id=50, es_externo=True, empresa="agencia  pampa")
    bruno = SimpleNamespace(id=51, es_externo=True, empresa="Estudio Sur")
    assert reglas.es_tarjeta_propia(ana, _tarea(), entrega)
    assert not reglas.es_tarjeta_propia(bruno, _tarea(), entrega)
    # Una para Tienda asignada a otra persona no es de la agencia.
    assert not reglas.es_tarjeta_propia(ana, _tarea(para="tienda", agencia=None, asignado_a_id=7), entrega)


def test_del_equipo_es_suya_si_la_hace_la_pidio_o_la_aprueba():
    entrega = SimpleNamespace(creado_por_id=2, aprobadores=[3, 4])
    for uid in (2, 3, 4):
        assert reglas.es_tarjeta_propia(SimpleNamespace(id=uid, es_externo=False, empresa=None), _tarea(), entrega)
    assert reglas.es_tarjeta_propia(SimpleNamespace(id=9, es_externo=False, empresa=None),
                                    _tarea(para="tienda", agencia=None, asignado_a_id=9), entrega)
    assert not reglas.es_tarjeta_propia(SimpleNamespace(id=8, es_externo=False, empresa=None), _tarea(), entrega)


def test_quien_crea_que():
    lucia = SimpleNamespace(id=1, es_externo=False, is_superuser=False,
                            permissions=["calendario.view", "calendario.edit", "calendario.pedidos"])
    lider = SimpleNamespace(id=2, es_externo=False, is_superuser=False, permissions=["calendario.view", "calendario.tareas"])
    agencia = SimpleNamespace(id=3, es_externo=True, is_superuser=False, permissions=["calendario.view"])
    # Tareas y piezas las crea quien tiene calendario.pedidos (17/11/2026);
    # editar el calendario solo ya no alcanza.
    assert puede_crear_tarea(lucia, pieza=True)
    assert puede_crear_tarea(lucia, pieza=False)
    solo_edita = SimpleNamespace(id=4, es_externo=False, is_superuser=False, permissions=["calendario.view", "calendario.edit"])
    assert not puede_crear_tarea(solo_edita, pieza=True) and not puede_crear_tarea(solo_edita, pieza=False)
    assert puede_crear_tarea(lider, pieza=False) and puede_crear_tarea(lider, pieza=True)
    assert not puede_crear_tarea(agencia, pieza=True)
    assert es_pieza(SimpleNamespace(tipo="banners", para="tienda"))
    assert es_pieza(SimpleNamespace(tipo=None, para="agencia"))
    assert es_pieza(SimpleNamespace(tipo=None, para="fuera"))
    assert not es_pieza(SimpleNamespace(tipo=None, para="tienda"))


# ---------------------------------------------------------------------------
# Los tipos de tarea
# ---------------------------------------------------------------------------

def test_el_nombre_de_la_tarjeta_se_arma_solo():
    assert tipos.nombre_de_tarjeta("Ciberlunes", "banners") == "Ciberlunes - Banners"
    assert tipos.nombre_de_tarjeta("  Black   Friday ", "emm") == "Black Friday - Email marketing (EMM)"
    assert tipos.nombre_de_tarjeta("", "cenefas") == "Cenefas"


def test_las_opciones_se_limpian_y_quedan_en_el_orden_del_catalogo():
    assert tipos.opciones_validas("banners", ["checkout", "Header", "HEADER", " Slider fila fino "]) == [
        "Header", "Slider fila fino", "Checkout"]
    # Banners deja agregar otras; Pantallas no.
    assert tipos.opciones_validas("banners", ["Header", "Banner de prueba"]) == ["Header", "Banner de prueba"]
    with pytest.raises(ValueError):
        tipos.opciones_validas("pantallas", ["Diagonal"])
    with pytest.raises(ValueError):
        tipos.opciones_validas("no-existe", [])


def test_la_descripcion_lleva_las_medidas():
    texto = tipos.descripcion_del_pedido("banners", ["Header", "Checkout"], {"cta": "Ver ofertas"})
    assert texto == "Banners: Header (web 1920×416 · mobile 640×260), Checkout (web 412×157)\nCTA: Ver ofertas"
    assert tipos.descripcion_del_pedido("cenefas", ["A5"], None) == "Cenefas: A5 (2 por hoja · 210×148,5 mm)"
    assert tipos.descripcion_del_pedido("whatsapp", [], None) == "Envío WhatsApp: imagen de 1080×1350 px · 4:5 vertical"
    assert tipos.descripcion_del_pedido("totem", [], None) is None


def test_redes_sociales_se_pide_por_proporcion():
    # Ivan, 17/11/2026: "redes sociales son opciones 1:1 4:5 9:16 16:9".
    redes = tipos.tipo_de("redes")
    assert redes["nombre"] == "Redes sociales" and redes["pieza"] == "redes"
    assert [o["nombre"] for o in redes["opciones"]] == ["1:1", "4:5", "9:16", "16:9"]
    assert tipos.opciones_validas("redes", ["16:9", "1:1"]) == ["1:1", "16:9"]
    with pytest.raises(ValueError):
        tipos.opciones_validas("redes", ["3:2"])
    assert tipos.nombre_de_tarjeta("Ciberlunes", "redes") == "Ciberlunes - Redes sociales"
    assert tipos.descripcion_del_pedido("redes", ["4:5", "9:16"], None) == "Redes sociales: 4:5, 9:16"


def test_estan_todas_las_piezas_que_pide_el_equipo():
    # "banners, rrss, cartelería, mailing, emm, push, mensaje de wsp" (17/11/2026).
    nombres = [t["nombre"] for t in tipos.TIPOS_DE_TAREA]
    for nombre in ("Banners", "Redes sociales", "Cartelería", "Mailing", "Email marketing (EMM)", "Push", "Envío WhatsApp"):
        assert nombre in nombres, nombre
    assert tipos.tipo_de("material")["nombre"] == "Cartelería"  # la clave no cambia
    assert tipos.nombre_de_tarjeta("Ciberlunes", "push") == "Ciberlunes - Push"
    assert tipos.opciones_validas("push", []) == []


def test_push_lleva_titulo_link_y_fecha_y_hora():
    # Ivan, 17/11/2026: "descripción y título de la push... link de destino, y
    # la fecha y hora". El texto va en la descripción de la tarea.
    d = tipos.detalles_validos("push", {
        "titulo": "  Llegó el   Ciberlunes ", "link": " https://www.tiendainglesa.com.uy/ciber ",
        "envio": "2026-11-20T18:30"}, [])
    assert d == {"titulo": "Llegó el Ciberlunes", "link": "https://www.tiendainglesa.com.uy/ciber",
                 "envio": "2026-11-20T18:30"}
    assert tipos.descripcion_del_pedido("push", [], d) == (
        "Título de la push: Llegó el Ciberlunes\n"
        "Link de destino: https://www.tiendainglesa.com.uy/ciber\n"
        "Fecha y hora de envío: 20/11/2026 18:30")
    # Todo es opcional: sin datos, nada.
    assert tipos.detalles_validos("push", {"titulo": "", "link": None}, []) == {}
    for malo in ({"link": "tiendainglesa.com.uy"}, {"link": "javascript:alert(1)"}, {"envio": "mañana"},
                 {"envio": "1900-01-01T10:00"}, {"titulo": "x" * 121}, {"titulo": 5}):
        with pytest.raises(ValueError):
            tipos.detalles_validos("push", malo, [])


def test_el_email_marketing_no_es_el_mailing():
    emm = tipos.tipo_de("emm")
    mailing = tipos.tipo_de("mailing")
    assert emm["nombre"] == "Email marketing (EMM)" and "600 px" in emm["opciones"][0]["medida"]
    assert [o["nombre"] for o in mailing["opciones"]] == ["Digital", "Físico (impreso)"]
    assert all("Mailing digital" not in o["nombre"] for t in tipos.TIPOS_DE_TAREA for o in t["opciones"])
    # Los bloques solo si se pidió "en bloques"; las páginas del mailing, sí.
    assert tipos.detalles_validos("emm", {"bloques": 5}, ["En bloques"]) == {"bloques": 5}
    assert tipos.detalles_validos("emm", {"bloques": 5}, ["Una sola imagen"]) == {}
    assert tipos.detalles_validos("mailing", {"paginas": "16"}, ["Físico (impreso)"]) == {"paginas": 16}
    with pytest.raises(ValueError):
        tipos.detalles_validos("emm", {"bloques": 9}, ["En bloques"])
    with pytest.raises(ValueError):
        tipos.detalles_validos("banners", {"cta": "Comprá ya"}, ["Header"])


def test_el_catalogo_para_la_pantalla_lleva_el_tipo_de_pieza():
    """«Más opciones» de Pedir una pieza arranca con el mismo tipo de pieza
    que pondría el servidor: antes el catálogo no lo mandaba y la pieza
    quedaba como «Otro» (revisión del 16/11/2026)."""
    for t in tipos.para_la_pantalla():
        assert t["clave"] and t["nombre"]
        assert t["pieza"] == tipos.tipo_de(t["clave"])["pieza"]
        # Y es una de las que acepta PUT /entregas: si no, «Más opciones» la
        # mandaría y el servidor la rechazaría (o caería en «Otro»).
        assert t["pieza"] in reglas.TIPOS_DE_PIEZA, t["clave"]


def test_un_numero_gigante_en_los_datos_del_pedido_es_un_error_claro():
    """Un 1e400 en el JSON llega como infinito, e int(infinito) no es un
    ValueError: contestaba 500 (revisión del 16/11/2026)."""
    with pytest.raises(ValueError):
        tipos.detalles_validos("emm", {"bloques": float("inf")}, ["En bloques"])
    with pytest.raises(ValueError):
        TareaNueva(id="ta-1", tipo="emm", opciones=["En bloques"], detalles={"bloques": float("inf")})
    with pytest.raises(ValueError):
        TareaDePlantilla(id="a", titulo="EMM", tipo="emm", opciones=["En bloques"], detalles={"bloques": float("-inf")})


def test_el_buscador_saca_tambien_las_tildes_de_las_mayusculas():
    """Que lower() de la base baje «Í» depende de su configuración regional:
    la traducción lleva también las mayúsculas acentuadas."""
    from app.api.routes.entregas import _TILDES

    con, sin = _TILDES
    assert len(con) == len(sin)
    traduccion = str.maketrans(con, sin)
    assert "DÍA DEL NIÑO ÁÉÍÓÚÜÇ".translate(traduccion) == "DiA DEL NInO aeiouuc"
    assert "día del niño".translate(traduccion) == "dia del nino"


def test_el_retrabajo_ordena_personas_y_agencias_de_afuera_sin_romper():
    """En una pieza de una agencia de afuera el retrabajo es de la agencia
    (por su nombre), no de quien la carga: se mezclan ids y textos."""
    m = reglas.metricas_de_retrabajo([
        ("banner", 7, "tienda_inglesa", 1), ("banner", "fuera:estudio x", "tienda_inglesa", 3),
        ("banner", 8, "tienda_inglesa", 2), ("otro", 8, "tienda_inglesa", 1),
        ("banner", None, "tienda_inglesa", 1),
    ])
    # Con las mismas fases, primero las personas y después las agencias
    # (antes, comparar 7 con "fuera:estudio x" levantaba un TypeError).
    assert [g["clave"] for g in m["porResponsable"]] == [8, None, 7, "fuera:estudio x"]


@pytest.mark.parametrize("texto,palabras", [
    ("Ciberlunes - Banners", ["ciberlunes", "banners"]),
    ("ciberlunes banners", ["ciberlunes", "banners"]),
    ("CÍBERLUNES—banners", ["ciberlunes", "banners"]),
    ("Día del Niño", ["dia", "del", "nino"]),
    ("  ", []),
])
def test_la_busqueda_no_mira_mayusculas_tildes_ni_el_guion(texto, palabras):
    assert tipos.palabras_de_busqueda(texto) == palabras


def test_una_tarea_con_tipo_no_necesita_titulo_y_una_comun_si():
    t = TareaNueva(id="ta-1", tipo="banners", opciones=["header"], para="agencia", agencia="Pampa")
    assert t.opciones == ["Header"] and t.titulo == ""
    with pytest.raises(ValueError):
        TareaNueva(id="ta-2", titulo="  ")


def test_la_plantilla_con_tipo_nombra_la_tarjeta_como_la_accion():
    tareas = [
        TareaDePlantilla(id="a", titulo="Banners", tipo="banners", opciones=["Header"], para="agencia",
                         agencia="Agencia Pampa", ancla="inicio", dias=-3).model_dump(),
        TareaDePlantilla(id="b", titulo="Retiro", ancla="fin", dias=1).model_dump(),
    ]
    plan = tareas_de_plantilla(tareas, {"a": "ta-a", "b": "ta-b"}, date(2026, 11, 30), date(2026, 12, 2), "Ciberlunes")
    a, b = plan
    assert a["titulo"] == "Ciberlunes - Banners" and a["para"] == "agencia" and a["vence"] == date(2026, 11, 27)
    assert b["titulo"] == "Retiro" and b["para"] == "tienda" and b["tipo"] is None


def test_una_plantilla_de_afuera_necesita_quien_cargue():
    with pytest.raises(ValueError):
        TareaDePlantilla(id="a", titulo="Mailing", para="fuera", agencia="Estudio X")
    ok = TareaDePlantilla(id="a", titulo="Mailing", para="fuera", agencia=" Estudio  X ", asignadoA=3)
    assert ok.agencia == "Estudio X"


# ---------------------------------------------------------------------------
# Las entregas con las que nace y los avisos
# ---------------------------------------------------------------------------

def test_nace_con_una_fase_que_aprueba_quien_la_pidio():
    conf = reglas.config_por_defecto(7, "Que se lea el precio", "banners", ["Header"], {"cta": "Ver más"})
    assert conf["fases"] == ["Entrega"] and conf["aprobadores"] == [7]
    assert conf["tipo_pieza"] == "banner"
    assert conf["brief"]["detalle"] == (
        "Banners: Header (web 1920×416 · mobile 640×260)\nCTA: Ver más\nQue se lea el precio")
    assert reglas.config_por_defecto(7, None)["brief"] == {} and reglas.config_por_defecto(7, None)["tipo_pieza"] == "otro"


def test_el_aviso_dice_quien_pidio_que():
    texto = reglas.mensaje_de_tarjeta_nueva("Iván", "Ciberlunes - Banners", ["Header", "Slider fila fino"], date(2026, 11, 25))
    assert texto == "Iván te pidió: Ciberlunes - Banners (Header, Slider fila fino). Es para el 25/11."
    varias = reglas.mensaje_de_tarjetas_nuevas("Lucía", [
        ("Ciberlunes - Banners", ["Header"], date(2026, 11, 27)),
        ("Ciberlunes - Cenefas", ["A4"], date(2026, 11, 25)),
    ])
    assert varias == "Lucía te pidió 2 tarjetas: Ciberlunes - Banners y Ciberlunes - Cenefas. La primera es para el 25/11."

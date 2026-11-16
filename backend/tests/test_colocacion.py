"""La foto de colocación: promo la pide desde la ficha de una acción, cada
local la sube desde el teléfono y promo la aprueba o la devuelve.

Lo que se fija acá es lo que no depende de la base: qué locales tiene cada
mundo, cuándo un local figura atrasado, cómo se cuenta el porcentaje, qué
imagen se acepta, quién puede ver qué y qué dice cada aviso. El recorrido
entero (con Postgres y el navegador) se probó a mano: ver el informe del PR.
"""
import io
import os
import pathlib
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image
from pydantic import ValidationError

from app.api.routes import colocacion as rutas
from app.api.routes.calendario import _barra_json
from app.api.routes.watchlist import _notif_visible
from app.services import colocacion as reglas

HOY = date(2026, 11, 15)


def _imagen(formato="JPEG", tamano=(1280, 960), color=(200, 30, 30)) -> bytes:
    salida = io.BytesIO()
    Image.new("RGB", tamano, color).save(salida, format=formato)
    return salida.getvalue()


def _usuario(*permisos, mundos=("redexpres",), super_=False):
    return SimpleNamespace(is_superuser=super_, permissions=list(permisos), mundos=list(mundos))


# --- Qué locales tiene cada mundo -------------------------------------------

def test_redexpres_pide_a_los_locales_redex():
    assert reglas.tipo_de_local("redexpres") == "redex"


def test_tienda_inglesa_queda_lista_para_cuando_haya_locales_tienda():
    assert reglas.tipo_de_local("tienda_inglesa") == "tienda"


@pytest.mark.parametrize("mundo", ["tienda_express", "tienda_viajes", "tienda_farma", "no_existe"])
def test_los_mundos_sin_locales_no_piden_fotos(mundo):
    assert reglas.tipo_de_local(mundo) is None


def test_los_tipos_son_los_de_local_asignaciones():
    # Si alguien agrega un tipo nuevo acá, tiene que existir en el panel de
    # usuarios (local_asignaciones.tipo): hoy son estos dos.
    assert set(reglas.TIPO_DE_LOCAL_POR_MUNDO.values()) <= {"redex", "tienda"}


# --- Fecha límite y atrasos ---------------------------------------------------

def test_por_defecto_el_dia_siguiente_al_inicio():
    assert reglas.limite_por_defecto(date(2026, 11, 20), HOY) == date(2026, 11, 21)


def test_si_la_accion_ya_arranco_el_limite_es_manana():
    """Un límite que ya pasó dejaría a todos los locales atrasados apenas se pide."""
    assert reglas.limite_por_defecto(date(2026, 11, 1), HOY) == date(2026, 11, 16)
    assert reglas.limite_por_defecto(HOY, HOY) == date(2026, 11, 16)


def test_el_dia_limite_todavia_no_esta_atrasado():
    assert reglas.estado_visible("pendiente", HOY, HOY) == "pendiente"


def test_pasado_el_limite_sin_foto_esta_atrasado():
    assert reglas.estado_visible("pendiente", HOY, HOY + timedelta(days=1)) == "atrasada"


def test_una_devuelta_que_no_se_arreglo_a_tiempo_esta_atrasada():
    assert reglas.estado_visible("devuelta", HOY, HOY + timedelta(days=2)) == "atrasada"


@pytest.mark.parametrize("estado", ["enviada", "aprobada"])
def test_con_foto_enviada_o_aprobada_no_esta_atrasado(estado):
    """La que espera revisión no es del local: lo que falta es que promo la mire."""
    assert reglas.estado_visible(estado, HOY, HOY + timedelta(days=5)) == estado


def test_mando_tarde_se_mira_en_hora_de_uruguay():
    limite = date(2026, 11, 16)
    # 01:00 del 17 en Greenwich son las 22:00 del 16 acá: llegó a tiempo.
    assert not reglas.mando_tarde(datetime(2026, 11, 17, 1, 0, tzinfo=timezone.utc), limite, reglas.URUGUAY)
    assert reglas.mando_tarde(datetime(2026, 11, 17, 4, 0, tzinfo=timezone.utc), limite, reglas.URUGUAY)
    assert not reglas.mando_tarde(None, limite, reglas.URUGUAY)


# --- El resumen y el porcentaje ---------------------------------------------

def test_el_porcentaje_es_de_las_aprobadas():
    r = reglas.resumen(["aprobada", "aprobada", "enviada", "pendiente", "atrasada"])
    assert r == {
        "total": 5, "pendientes": 1, "enviadas": 1, "aprobadas": 2, "devueltas": 0, "atrasadas": 1,
        "porcentaje": 40,
    }


def test_sin_locales_el_porcentaje_es_cero():
    assert reglas.resumen([])["porcentaje"] == 0


def test_el_porcentaje_se_redondea():
    assert reglas.resumen(["aprobada", "pendiente", "pendiente"])["porcentaje"] == 33


# --- Qué puede hacer el local -------------------------------------------------

@pytest.mark.parametrize("estado,puede", [
    ("pendiente", True), ("enviada", True), ("devuelta", True), ("aprobada", False),
])
def test_una_aprobada_no_se_toca(estado, puede):
    assert reglas.puede_subir(estado) is puede


def test_mandaron_todos():
    assert reglas.mandaron_todos(["enviada", "aprobada"])
    assert not reglas.mandaron_todos(["enviada", "pendiente"])
    assert not reglas.mandaron_todos(["enviada", "devuelta"])
    assert not reglas.mandaron_todos([])


def test_sacar_la_ultima_foto_vuelve_a_como_estaba():
    assert reglas.estado_al_sacar_la_ultima("enviada", None) == "pendiente"
    assert reglas.estado_al_sacar_la_ultima("enviada", "No se ve la cabecera") == "devuelta"
    assert reglas.estado_al_sacar_la_ultima("devuelta", "x") == "devuelta"


# --- Las imágenes -------------------------------------------------------------

@pytest.mark.parametrize("formato,tipo", [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")])
def test_acepta_jpeg_png_y_webp(formato, tipo):
    imagen = reglas.validar_imagen(_imagen(formato))
    assert (imagen.tipo, imagen.ancho, imagen.alto) == (tipo, 1280, 960)


def test_el_tipo_sale_de_los_bytes_y_no_del_nombre():
    assert reglas.tipo_real(b"%PDF-1.7 ...") is None
    assert reglas.tipo_real(b"GIF89a....") is None
    assert reglas.tipo_real(_imagen("PNG")) == "image/png"


def test_texto_con_nombre_de_foto_no_pasa():
    with pytest.raises(reglas.ImagenInvalida, match="no es una imagen"):
        reglas.validar_imagen(b"<html>no soy una foto</html>" * 20)


def test_una_cabecera_de_jpeg_con_basura_no_pasa():
    with pytest.raises(reglas.ImagenInvalida, match="dañada"):
        reglas.validar_imagen(b"\xff\xd8\xff\xe0" + b"\x00" * 4000)


def test_un_jpeg_cortado_a_la_mitad_no_pasa():
    """Se cayó la señal a mitad de la subida: con verify() solo pasaba."""
    entero = io.BytesIO()
    Image.effect_noise((800, 600), 60).convert("RGB").save(entero, format="JPEG", quality=80)
    datos = entero.getvalue()
    with pytest.raises(reglas.ImagenInvalida, match="dañada o incompleta"):
        reglas.validar_imagen(datos[: len(datos) // 2])


def test_mas_de_3_mb_no_pasa():
    with pytest.raises(reglas.ImagenInvalida, match="máximo es 3 MB"):
        reglas.validar_imagen(b"\xff\xd8\xff" + b"0" * (3 * 1024 * 1024))


def test_la_miniatura_tiene_su_propio_tope():
    with pytest.raises(reglas.ImagenInvalida, match="La miniatura pesa"):
        reglas.validar_imagen(b"\xff\xd8\xff" + b"0" * 400_000, reglas.MAX_BYTES_MINIATURA, "La miniatura")


def test_vacia_no_pasa():
    with pytest.raises(reglas.ImagenInvalida, match="vacía"):
        reglas.validar_imagen(b"")


def test_una_imagen_de_un_par_de_pixeles_no_es_una_foto():
    with pytest.raises(reglas.ImagenInvalida, match="demasiado chica"):
        reglas.validar_imagen(_imagen("PNG", (40, 40)))


def test_una_imagen_gigante_no_se_decodifica():
    with pytest.raises(reglas.ImagenInvalida, match="demasiado grande"):
        reglas.validar_imagen(_imagen("PNG", (4001, 3000)))


def test_png_con_otro_contenido_no_pasa():
    """Empieza como PNG y adentro es un JPEG: Pillow lo lee como JPEG."""
    trucho = b"\x89PNG\r\n\x1a\n" + _imagen("JPEG")[8:]
    with pytest.raises(reglas.ImagenInvalida):
        reglas.validar_imagen(trucho)


def test_la_miniatura_que_hace_el_servidor():
    mini = reglas.hacer_miniatura(_imagen("PNG", (1600, 900)))
    with Image.open(io.BytesIO(mini)) as im:
        assert im.format == "JPEG"
        assert max(im.size) == reglas.LADO_MINIATURA


def test_una_miniatura_de_algo_roto_es_un_error_para_la_persona():
    with pytest.raises(reglas.ImagenInvalida):
        reglas.hacer_miniatura(b"\xff\xd8\xff" + b"0" * 100)


# --- Espacio y purga -----------------------------------------------------------

def test_el_tope_de_espacio():
    mb = 1024 * 1024
    assert reglas.entra_en_el_tope(299 * mb, 500_000, 300)
    assert not reglas.entra_en_el_tope(300 * mb, 1, 300)
    assert reglas.entra_en_el_tope(10_000 * mb, 1, 0)  # 0 = sin tope


def test_la_purga_es_120_dias_despues_del_fin():
    assert reglas.corte_de_purga(date(2027, 3, 31), 120) == date(2026, 12, 1)


def test_la_purga_y_el_tope_vienen_de_la_configuracion():
    from app.core.config import Settings
    s = Settings()
    assert s.COLOCACION_RETENCION_DIAS == 120
    assert s.COLOCACION_TOPE_MB == 300


def test_la_purga_arranca_adentro_de_las_migraciones():
    """Como la de cenefas: hace una pasada apenas arranca, y en una base nueva
    la tabla todavía no existe. Y solo en el servidor desplegado."""
    fuente = (pathlib.Path(__file__).resolve().parent.parent / "app" / "main.py").read_text(encoding="utf-8")
    lanzar = "asyncio.create_task(run_purga_colocacion_loop())"
    assert fuente.count(lanzar) == 1
    inicio = fuente.index("async def _run_migrations():")
    fin = fuente.index("if mantenimiento:\n        asyncio.create_task(_run_migrations())")
    assert inicio < fuente.index(lanzar) < fin


# --- Quién puede qué ----------------------------------------------------------

def test_promo_necesita_editar_el_calendario_en_ese_mundo():
    assert rutas.es_promo_del_mundo(_usuario("calendario.view", "calendario.edit"), "redexpres")
    assert not rutas.es_promo_del_mundo(_usuario("calendario.view"), "redexpres")
    assert not rutas.es_promo_del_mundo(_usuario("calendario.edit", mundos=("tienda_inglesa",)), "redexpres")
    assert rutas.es_promo_del_mundo(_usuario(super_=True, mundos=()), "redexpres")


def test_un_login_de_sucursal_no_es_promo():
    assert not rutas.es_promo_del_mundo(_usuario("ai.don_tino"), "redexpres")


def test_el_local_solo_ve_lo_de_su_local():
    yo = _usuario("ai.don_tino")
    mios = {("ALTOSUR 1 (425)", "redex")}
    assert rutas.es_del_local(yo, mios, "ALTOSUR 1 (425)", "redex", "redexpres")
    assert not rutas.es_del_local(yo, mios, "PINAMAR (290)", "redex", "redexpres")


def test_el_tipo_del_local_tiene_que_ser_el_del_pedido():
    """Un local de Tienda Inglesa con el mismo nombre que uno de Redexpres no
    ve el pedido del otro."""
    yo = _usuario("ai.don_tino", mundos=("redexpres", "tienda_inglesa"))
    assert not rutas.es_del_local(yo, {("Centro", "tienda")}, "Centro", "redex", "redexpres")


def test_el_local_tiene_que_abrir_el_mundo_de_la_accion():
    yo = _usuario("ai.don_tino", mundos=("redexpres",))
    assert not rutas.es_del_local(yo, {("Centro", "tienda")}, "Centro", "tienda", "tienda_inglesa")


def test_un_superusuario_sin_local_no_es_un_local():
    assert not rutas.es_del_local(_usuario(super_=True), set(), "ALTOSUR 1 (425)", "redex", "redexpres")


def test_los_locales_elegidos_tienen_que_tener_usuario():
    with pytest.raises(HTTPException) as e:
        rutas._validar_locales(["Inventado"], ["A", "B"])
    assert e.value.status_code == 422
    with pytest.raises(HTTPException):
        rutas._validar_locales(["  "], ["A"])
    assert rutas._validar_locales(["B", "A", "B", " A "], ["A", "B"]) == ["B", "A"]


# --- La campanita --------------------------------------------------------------

def _aviso(origen):
    return SimpleNamespace(origen_tipo=origen)


@pytest.mark.parametrize("origen", [reglas.ORIGEN_PEDIDO, reglas.ORIGEN_DEVUELTA])
def test_al_local_le_llegan_sus_avisos_sin_tener_permisos(origen):
    """Un login de sucursal tiene solo Don Tino: sin esta regla caía en la de
    precios y no veía que le pidieron una foto."""
    local = _usuario("ai.don_tino")
    assert _notif_visible(local, _aviso(origen), es_sucursal=True)
    assert not _notif_visible(local, _aviso(origen), es_sucursal=False)


def test_el_aviso_de_que_mandaron_todos_es_de_promo():
    assert _notif_visible(_usuario("calendario.view", "calendario.edit"), _aviso(reglas.ORIGEN_COMPLETA))
    assert not _notif_visible(_usuario("calendario.view"), _aviso(reglas.ORIGEN_COMPLETA))
    assert not _notif_visible(_usuario("ai.don_tino"), _aviso(reglas.ORIGEN_COMPLETA), es_sucursal=True)


def test_los_avisos_de_antes_siguen_igual():
    assert _notif_visible(_usuario("calendario.view"), _aviso("calendario_tarea"))
    assert not _notif_visible(_usuario("ai.don_tino"), _aviso(None), es_sucursal=True)


def test_lo_que_dicen_los_avisos():
    assert rutas.mensaje_pedido("Combo Desayuno", date(2026, 11, 16)) == (
        "Te pidieron una foto de «Combo Desayuno» para ver cómo quedó en el local. Hay tiempo hasta el 16/11."
    )
    assert rutas.mensaje_devuelta("Combo", "  No se ve la cabecera 4 ") == "Te devolvieron la foto de «Combo»: No se ve la cabecera 4"
    assert rutas.mensaje_devuelta("Combo", "x" * 500).endswith("…")
    assert rutas.mensaje_completa("Combo", 60) == "Los 60 locales mandaron la foto de «Combo». Faltan revisarlas."
    assert rutas.mensaje_completa("Combo", 1) == "El local mandó la foto de «Combo». Falta revisarla."


def test_las_referencias_empiezan_por_la_accion():
    """Es lo que usa la campanita para saber a dónde llevar."""
    assert rutas.referencia_local("br-1", 7) == "br-1:7"
    assert rutas.referencia_pedido("br-1", 3) == "br-1:3"


# --- Lo que viaja ---------------------------------------------------------------

def test_los_datos_del_calendario_traen_solo_el_resumen_del_pedido():
    barra = SimpleNamespace(
        id="br-1", mundo="redexpres", seccion="comercial", banda="Cartelería", carril=0, nombre="Combo",
        color=None, desde=date(2026, 11, 9), hasta=date(2026, 11, 22),
    )
    resumen = {"pedido": 1, "locales": 60, "limite": "2026-11-10"}
    assert _barra_json(barra, [], [], [], resumen)["fotos"] == resumen
    assert "fotos" not in _barra_json(barra, [], [], [], None)


def test_el_comentario_de_una_devolucion_tiene_que_decir_algo():
    with pytest.raises(ValidationError):
        rutas.Devolucion(comentario="  ")
    assert rutas.Devolucion(comentario="  No se ve la cabecera 4 ").comentario == "No se ve la cabecera 4"


def test_la_fecha_limite_tiene_que_ser_real():
    with pytest.raises(ValidationError):
        rutas.PedidoNuevo(limite=date(202, 11, 16))
    assert rutas.PedidoNuevo(indicacion="   ").indicacion is None


def test_la_subida_tiene_su_propio_limite_por_minuto():
    from app.core.rate_limit import limiter
    assert "app.api.routes.colocacion.subir_foto" in limiter._route_limits


def test_las_fotos_no_se_comen_el_limite_general():
    """60 miniaturas por tablero: con el balde general de 200 por minuto,
    abrir dos tableros seguidos daba 429."""
    from app.core.rate_limit import limiter
    assert "app.api.routes.colocacion.ver_foto" in limiter._route_limits


def test_las_rutas_estan_registradas():
    # Desde FastAPI 0.139 el router de la API no aplana las rutas incluidas:
    # se mira que esté incluido y, en el suyo, que estén las rutas.
    fuente = (pathlib.Path(__file__).resolve().parent.parent / "app" / "api" / "__init__.py").read_text(encoding="utf-8")
    assert "router.include_router(colocacion.router)" in fuente
    caminos = {r.path for r in rutas.router.routes}
    for camino in (
        "/colocacion/mis-fotos", "/colocacion/acciones/{barra_id}", "/colocacion/fotos/{foto_id}",
        "/colocacion/locales/{local_id}/fotos", "/colocacion/resumen",
    ):
        assert camino in caminos


def test_la_migracion_va_despues_de_la_0063():
    ruta = pathlib.Path(__file__).resolve().parent.parent / "migrations" / "versions" / "0064_foto_de_colocacion.py"
    fuente = ruta.read_text(encoding="utf-8")
    assert 'revision = "0064"' in fuente and 'down_revision = "0063"' in fuente
    assert "def downgrade" in fuente

"""Entregas por fases con rondas de corrección (pedido de Ivan, 15/11/2026).

"Una tarea tiene fase 1, fase 2, fase 3…; se entrega, se aprueba o vuelve con
correcciones, la agencia devuelve con las correcciones aplicadas, puede volver
otra vez, hasta que se aprueba." Más la aprobación en cadena y la medición del
retrabajo. El "aprobado con cambios" se sacó el 19/11/2026: acá se fija que ya
no se acepta y que las decisiones viejas guardadas así se siguen leyendo como
aprobadas.

Lo que se fija acá es lo que no depende de la base: a quién le toca decidir,
cuándo una versión queda aprobada o vuelve, qué pasa con las fases y con la
tarea, cómo se cuenta el retrabajo y qué se acepta como imagen, link o brief.
El recorrido completo (con la base y el navegador) se probó a mano: ver el
informe del 15/11/2026.
"""
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.routes.entregas import DecisionNueva, EntregaConfig, MarcaNueva
from app.api.routes.watchlist import _notif_visible
from app.services.entregas import (
    CAMPOS_DEL_BRIEF, DECISION_VIEJA, DECISIONES, FASES_POR_DEFECTO, MAX_BYTES_IMAGEN, MAX_BYTES_MINIATURA,
    MAX_IMAGENES, ORIGEN, TIPOS_DE_PIEZA,
    FaseExistente, NoPuedeDecidir, a_quien_le_toca, aprobadores_validos, dias_de_retencion, estado_de_tarea,
    estados_de_fases, limpiar_brief, link_valido, lugar_para_decidir, mensaje_de_aprobacion, mensaje_de_cambios,
    mensaje_para_revisar, metricas_de_retrabajo, momento_de, nombres_de_fases, plan_de_fases, referencia,
    resultado_de_version, tipo_de_imagen, validar_decision, validar_imagen, vencio,
)
from app.services.espacio import MENSAJE_SIN_LUGAR, entra

PROMO, MARCA, COMERCIAL, AGENCIA, LIDER = 1, 2, 3, 4, 5
CADENA = [PROMO, MARCA, COMERCIAL]

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 100


# --- La cadena de aprobación -----------------------------------------------

def test_una_version_nueva_la_revisa_el_primero_de_la_cadena():
    assert a_quien_le_toca(CADENA, []) == PROMO
    assert resultado_de_version(CADENA, []) == "revision"


def test_cuando_aprueba_uno_pasa_al_siguiente():
    assert a_quien_le_toca(CADENA, [(PROMO, "aprobada")]) == MARCA
    assert a_quien_le_toca(CADENA, [(PROMO, "aprobada"), (MARCA, "aprobada")]) == COMERCIAL


def test_aprobada_cuando_aprueban_todos():
    decisiones = [(PROMO, "aprobada"), (MARCA, "aprobada"), (COMERCIAL, "aprobada")]
    assert resultado_de_version(CADENA, decisiones) == "aprobada"
    assert a_quien_le_toca(CADENA, decisiones) is None


def test_una_decision_vieja_aprobada_con_cambios_se_sigue_leyendo_como_aprobada():
    """«Aprobado con cambios» se sacó el 19/11/2026, pero en producción hay
    decisiones de esa semana guardadas así: la cadena las tiene que seguir
    contando como aprobadas (si no, una versión quedaría trabada o volvería a
    pedirle la decisión a quien ya decidió)."""
    assert DECISION_VIEJA == "aprobada-con-cambios" and DECISION_VIEJA not in DECISIONES
    assert a_quien_le_toca(CADENA, [(PROMO, DECISION_VIEJA)]) == MARCA
    decisiones = [(PROMO, "aprobada"), (MARCA, "aprobada"), (COMERCIAL, DECISION_VIEJA)]
    assert resultado_de_version(CADENA, decisiones) == "aprobada"
    assert a_quien_le_toca(CADENA, decisiones) is None
    # Quien ya decidió así no vuelve a decidir: le toca al siguiente.
    assert lugar_para_decidir(MARCA, False, CADENA, [(PROMO, DECISION_VIEJA)], AGENCIA) == (MARCA, 1, False)
    with pytest.raises(NoPuedeDecidir) as e:
        lugar_para_decidir(COMERCIAL, False, CADENA, decisiones, AGENCIA)
    assert e.value.codigo == 409  # ya se decidió


def test_aprobado_con_cambios_ya_no_se_acepta():
    """Ivan (19/11/2026): "me resulta raro ese botón. No creo que sume nada".
    Quedan 'aprobada' y 'cambios'; la decisión vieja se rechaza con un
    mensaje que dice qué elegir en su lugar."""
    assert DECISIONES == ("aprobada", "cambios")
    assert validar_decision("aprobada") == "aprobada"
    assert validar_decision(" cambios ") == "cambios"
    with pytest.raises(ValueError, match="ya no existe"):
        validar_decision("aprobada-con-cambios")
    with pytest.raises(ValueError, match="no existe"):
        validar_decision("rechazada")
    with pytest.raises(ValueError):
        validar_decision("")


def test_si_cualquiera_pide_cambios_vuelve_a_la_agencia():
    assert resultado_de_version(CADENA, [(PROMO, "cambios")]) == "cambios"
    assert resultado_de_version(CADENA, [(PROMO, "aprobada"), (MARCA, "cambios")]) == "cambios"
    assert a_quien_le_toca(CADENA, [(PROMO, "aprobada"), (MARCA, "cambios")]) is None


def test_sin_cadena_decide_el_respaldo_y_con_una_alcanza():
    """Si le sacaron todos los aprobadores a mitad de camino, la versión no
    puede quedar trabada."""
    assert resultado_de_version([], []) == "revision"
    assert a_quien_le_toca([], []) is None
    assert resultado_de_version([], [(None, "aprobada")]) == "aprobada"


def test_si_se_saca_de_la_cadena_al_que_faltaba_queda_aprobada():
    assert resultado_de_version([PROMO], [(PROMO, "aprobada")]) == "aprobada"


# --- Quién puede decidir ---------------------------------------------------

def test_decide_el_aprobador_de_turno():
    assert lugar_para_decidir(PROMO, False, CADENA, [], AGENCIA) == (PROMO, 0, False)
    assert lugar_para_decidir(MARCA, False, CADENA, [(PROMO, "aprobada")], AGENCIA) == (MARCA, 1, False)


def test_el_que_sigue_no_puede_adelantarse():
    with pytest.raises(NoPuedeDecidir) as e:
        lugar_para_decidir(MARCA, False, CADENA, [], AGENCIA)
    assert e.value.codigo == 403
    assert "Todavía no te toca" in str(e.value)


def test_quien_no_esta_en_la_cadena_no_decide():
    with pytest.raises(NoPuedeDecidir) as e:
        lugar_para_decidir(99, False, CADENA, [], AGENCIA)
    assert e.value.codigo == 403


def test_quien_lidera_decide_como_respaldo_en_nombre_del_de_turno():
    assert lugar_para_decidir(LIDER, True, CADENA, [(PROMO, "aprobada")], AGENCIA) == (MARCA, 1, True)


def test_nadie_decide_sobre_lo_que_subio_ni_siquiera_quien_lidera():
    with pytest.raises(NoPuedeDecidir):
        lugar_para_decidir(AGENCIA, True, CADENA, [], AGENCIA)


def test_una_version_ya_decidida_es_409():
    """Dos personas decidiendo a la vez: la segunda se entera de que ya está."""
    with pytest.raises(NoPuedeDecidir) as e:
        lugar_para_decidir(MARCA, False, CADENA, [(PROMO, "cambios")], AGENCIA)
    assert e.value.codigo == 409


def test_el_mismo_aprobador_no_decide_dos_veces():
    with pytest.raises(NoPuedeDecidir):
        lugar_para_decidir(PROMO, False, CADENA, [(PROMO, "aprobada")], AGENCIA)


# --- Fases, momento y tarea ------------------------------------------------

def test_se_trabaja_una_fase_por_vez():
    assert estados_de_fases(["pendiente", "pendiente", "pendiente"]) == ["en-curso", "pendiente", "pendiente"]
    assert estados_de_fases(["aprobada", "en-curso", "pendiente"]) == ["aprobada", "en-curso", "pendiente"]
    assert estados_de_fases(["aprobada", "pendiente", "pendiente"]) == ["aprobada", "en-curso", "pendiente"]
    assert estados_de_fases(["aprobada", "aprobada"]) == ["aprobada", "aprobada"]


def test_las_columnas_del_tablero():
    assert momento_de(True, None) == "produccion"
    assert momento_de(True, "revision") == "revision"
    assert momento_de(True, "cambios") == "cambios"
    assert momento_de(False, "aprobada") == "aprobada"


def test_la_tarea_cambia_sola_de_estado():
    assert estado_de_tarea("produccion", False, "pendiente") == "pendiente"
    assert estado_de_tarea("revision", True, "pendiente") == "en-proceso"
    assert estado_de_tarea("cambios", True, "en-proceso") == "en-proceso"
    assert estado_de_tarea("produccion", True, "en-proceso") == "en-proceso"
    assert estado_de_tarea("aprobada", True, "en-proceso") == "hecha"


def test_una_fase_nueva_despues_de_aprobada_la_reabre():
    assert estado_de_tarea("produccion", True, "hecha") == "en-proceso"
    assert estado_de_tarea("produccion", False, "hecha") == "pendiente"


def test_recorrido_entero_de_dos_fases():
    """El recorrido que se probó en el navegador, regla por regla: fase 1 con
    cambios y después aprobada por los dos, fase 2 aprobada a la primera."""
    cadena = [PROMO, MARCA]
    # Fase 1, ronda 1: PROMO pide cambios.
    assert resultado_de_version(cadena, [(PROMO, "cambios")]) == "cambios"
    assert momento_de(True, "cambios") == "cambios"
    # Ronda 2: PROMO aprueba, MARCA aprueba -> la fase se aprueba.
    r2 = [(PROMO, "aprobada"), (MARCA, "aprobada")]
    assert resultado_de_version(cadena, r2) == "aprobada"
    assert estados_de_fases(["aprobada", "pendiente"]) == ["aprobada", "en-curso"]
    assert momento_de(True, None) == "produccion"
    # Fase 2, ronda 1: aprobada por los dos -> la tarea queda hecha.
    assert resultado_de_version(cadena, [(PROMO, "aprobada"), (MARCA, "aprobada")]) == "aprobada"
    assert estado_de_tarea(momento_de(False, "aprobada"), True, "en-proceso") == "hecha"
    # Retrabajo: fase 1 en 2 rondas, fase 2 en 1.
    m = metricas_de_retrabajo([("cenefa", AGENCIA, "tienda_inglesa", 2), ("cenefa", AGENCIA, "tienda_inglesa", 1)])
    assert m["rondasPromedio"] == 1.5 and m["aLaPrimera"] == 50


# --- Cambiar las fases -----------------------------------------------------

def _fases(*estados_y_versiones):
    return [FaseExistente(f"fa-{i}", e, v) for i, (e, v) in enumerate(estados_y_versiones)]


def test_se_puede_agregar_una_fase_al_final_y_renombrar():
    existentes = _fases(("aprobada", True), ("en-curso", False))
    plan = plan_de_fases(existentes, [("fa-0", "Boceto"), ("fa-1", "Arte final v2"), (None, "Adaptaciones")])
    assert plan == [("fa-0", "Boceto"), ("fa-1", "Arte final v2"), (None, "Adaptaciones")]


def test_no_se_saca_una_fase_con_versiones():
    existentes = _fases(("en-curso", True), ("pendiente", False))
    with pytest.raises(ValueError, match="versiones"):
        plan_de_fases(existentes, [("fa-1", "Arte final")])


def test_lo_trabajado_va_primero_y_en_el_mismo_orden():
    existentes = _fases(("aprobada", True), ("en-curso", True), ("pendiente", False))
    with pytest.raises(ValueError, match="primero"):
        plan_de_fases(existentes, [("fa-1", "B"), ("fa-0", "A"), ("fa-2", "C")])
    with pytest.raises(ValueError, match="primero"):
        plan_de_fases(existentes, [(None, "Nueva"), ("fa-0", "A"), ("fa-1", "B")])


def test_lo_no_trabajado_se_saca_o_se_mueve():
    existentes = _fases(("en-curso", False), ("pendiente", False), ("pendiente", False))
    assert plan_de_fases(existentes, [("fa-2", "C"), ("fa-0", "A")]) == [("fa-2", "C"), ("fa-0", "A")]


def test_una_fase_de_otra_tarea_no_se_acepta():
    with pytest.raises(ValueError, match="ya no existe"):
        plan_de_fases(_fases(("en-curso", False)), [("fa-de-otra", "X")])


def test_los_nombres_de_las_fases():
    assert nombres_de_fases(["  Boceto ", "Arte final"]) == ["Boceto", "Arte final"]
    with pytest.raises(ValueError):
        nombres_de_fases([])
    with pytest.raises(ValueError):
        nombres_de_fases(["Boceto", "  "])
    # Sin tope de trabajo desde el 17/11/2026: 9, 10 o más fases valen; solo
    # se frena un pedido mal armado.
    assert len(nombres_de_fases(["x"] * 9)) == 9
    with pytest.raises(ValueError):
        nombres_de_fases(["x"] * 101)


def test_devolver_una_aprobada_abre_entrega_n():
    from app.services.entregas import mensaje_de_devolucion, nombre_de_fase_nueva, puede_devolver
    assert nombre_de_fase_nueva(["Entrega"]) == "Entrega 2"
    assert nombre_de_fase_nueva(["Entrega", "Entrega 2"]) == "Entrega 3"
    assert nombre_de_fase_nueva(["Boceto", "Arte final"]) == "Entrega 3"
    # Si alguien ya la nombró así a mano, sigue contando.
    assert nombre_de_fase_nueva(["Entrega", "entrega 3"]) == "Entrega 4"
    # La devuelve quien aprueba o quien lidera, y solo ya aprobada.
    assert puede_devolver(5, False, [5, 6], "aprobada")
    assert puede_devolver(9, True, [5], "aprobada")
    assert not puede_devolver(9, False, [5], "aprobada")
    for momento in ("produccion", "revision", "cambios"):
        assert not puede_devolver(5, True, [5], momento)
    texto = mensaje_de_devolucion("Lucía", "Ciber - Banners", "Ciberlunes", "Entrega 2", "  El precio  cambió ")
    assert texto == "Lucía devolvió «Ciber - Banners» (Ciberlunes) para corregir: El precio cambió. Te toca entregar Entrega 2."


def test_cada_tipo_de_pieza_tiene_fases_por_defecto_y_formulario():
    assert set(FASES_POR_DEFECTO) == set(TIPOS_DE_PIEZA) == set(CAMPOS_DEL_BRIEF)
    assert FASES_POR_DEFECTO["cenefa"] == ["Boceto", "Arte final"]
    # El texto libre (para dictar por voz) está en todos.
    assert all("detalle" in campos for campos in CAMPOS_DEL_BRIEF.values())


# --- Aprobadores -----------------------------------------------------------

def test_los_aprobadores():
    assert aprobadores_validos([3, 1, 2]) == [3, 1, 2]
    with pytest.raises(ValueError, match="al menos"):
        aprobadores_validos([])
    with pytest.raises(ValueError, match="dos veces"):
        aprobadores_validos([1, 1])
    with pytest.raises(ValueError):
        aprobadores_validos(list(range(1, 8)))


# --- El pedido a la agencia (brief) ----------------------------------------

def test_el_brief_de_una_cenefa():
    brief = limpiar_brief("cenefa", {
        "medidas": " A4 ", "cantidad": "120", "precio": "$ 199", "vigenciaDesde": "2026-12-01",
        "vigenciaHasta": "2026-12-24", "legales": "Válido hasta agotar stock", "detalle": "Navidad",
        "asunto": "esto es de un mailing", "vacio": "",
    })
    assert brief == {
        "medidas": "A4", "cantidad": 120, "precio": "$ 199", "vigenciaDesde": "2026-12-01",
        "vigenciaHasta": "2026-12-24", "legales": "Válido hasta agotar stock", "detalle": "Navidad",
    }


def test_el_brief_valida_cada_campo():
    with pytest.raises(ValueError, match="número"):
        limpiar_brief("cenefa", {"cantidad": "muchas"})
    with pytest.raises(ValueError, match="año"):
        limpiar_brief("mailing", {"fechaEnvio": "0202-12-01"})
    with pytest.raises(ValueError, match="anterior"):
        limpiar_brief("banner", {"desde": "2026-12-10", "hasta": "2026-12-01"})
    with pytest.raises(ValueError, match="http"):
        limpiar_brief("banner", {"link": "javascript:alert(1)"})
    with pytest.raises(ValueError, match="opción"):
        limpiar_brief("redes", {"formato": "Afiche"})
    with pytest.raises(ValueError, match="no existe"):
        limpiar_brief("afiche", {})
    assert limpiar_brief("redes", {"formato": "Reel", "copy": "¡Llegó!"}) == {"formato": "Reel", "copy": "¡Llegó!"}
    assert limpiar_brief("otro", None) == {}


def test_un_brief_demasiado_largo_no_entra():
    with pytest.raises(ValueError, match="largo"):
        limpiar_brief("mailing", {"asunto": "x" * 301})


# --- Links e imágenes ------------------------------------------------------

def test_el_link_al_original_solo_web():
    assert link_valido("  https://drive.google.com/x  ") == "https://drive.google.com/x"
    assert link_valido("") is None and link_valido(None) is None
    for malo in ("javascript:alert(1)", "data:text/html,hola", "ftp://x", "//x.com"):
        with pytest.raises(ValueError):
            link_valido(malo)


def test_las_imagenes_se_reconocen_por_sus_primeros_bytes():
    assert tipo_de_imagen(JPEG) == "image/jpeg"
    assert tipo_de_imagen(PNG) == "image/png"
    assert tipo_de_imagen(WEBP) == "image/webp"
    assert tipo_de_imagen(b"GIF89a" + b"\x00" * 10) is None
    assert tipo_de_imagen(b"<svg xmlns=...>") is None
    assert tipo_de_imagen(b"%PDF-1.4") is None


def test_una_imagen_que_no_es_imagen_no_entra_aunque_diga_jpg():
    with pytest.raises(ValueError, match="JPG, PNG ni WebP"):
        validar_imagen(b"<html><script>alert(1)</script></html>")


def test_el_tope_de_peso():
    """La base es de 500 MB para toda la plataforma: 2 MB por imagen como
    mucho (comprimida en el navegador pesa 50-250 KB), hasta 4 por ronda."""
    assert MAX_BYTES_IMAGEN == 2 * 1024 * 1024 and MAX_IMAGENES == 4
    assert validar_imagen(JPEG) == "image/jpeg"
    with pytest.raises(ValueError, match="2 MB"):
        validar_imagen(b"\xff\xd8\xff" + b"\x00" * MAX_BYTES_IMAGEN)
    with pytest.raises(ValueError, match="vacía"):
        validar_imagen(b"")
    with pytest.raises(ValueError, match="256 KB"):
        validar_imagen(b"\xff\xd8\xff" + b"\x00" * 300_000, maximo=MAX_BYTES_MINIATURA, que="La miniatura")


# --- Cuándo se borran las imágenes y el freno de espacio -------------------

def test_las_imagenes_de_versiones_no_finales_se_borran_a_los_30_dias():
    fin = date(2026, 12, 24)
    assert dias_de_retencion(False) == 30
    assert not vencio(fin, False, date(2027, 1, 23))
    assert vencio(fin, False, date(2027, 1, 24))


def test_las_de_la_version_final_a_los_120():
    fin = date(2026, 12, 24)
    assert dias_de_retencion(True) == 120
    assert not vencio(fin, True, date(2027, 1, 24))
    assert not vencio(fin, True, date(2027, 4, 23))
    assert vencio(fin, True, date(2027, 4, 24))


def test_el_freno_de_espacio():
    mb = 1024 * 1024
    assert entra(300 * mb, 2 * mb, 400)
    assert entra(398 * mb, 2 * mb, 400)
    assert not entra(399 * mb, 2 * mb, 400)
    assert not entra(401 * mb, 0, 400)
    # Sin tope configurado, no frena.
    assert entra(10_000 * mb, mb, 0)


def test_el_mensaje_de_base_llena_dice_que_hacer():
    assert "avisale a quien administra Core Tienda" in MENSAJE_SIN_LUGAR


# --- Lo que llega del front ------------------------------------------------

def test_una_marca_va_sobre_la_imagen():
    MarcaNueva(imagenId="im-1", x=0, y=1, texto=" Subir el logo ")
    for x, y in ((-0.1, 0.5), (0.5, 1.2)):
        with pytest.raises(ValidationError):
            MarcaNueva(imagenId="im-1", x=x, y=y, texto="x")
    with pytest.raises(ValidationError):
        MarcaNueva(imagenId="im-1", x=0.5, y=0.5, texto="   ")
    assert MarcaNueva(imagenId="im-1", x=0.5, y=0.5, texto=" Subir el logo ").texto == "Subir el logo"


def test_las_decisiones_posibles():
    for d in ("aprobada", "cambios"):
        assert DecisionNueva(decision=d).decision == d
    # El cuerpo acepta cualquier texto corto: la ruta lo controla con
    # validar_decision para contestar con un mensaje claro (ver
    # test_aprobado_con_cambios_ya_no_se_acepta).
    DecisionNueva(decision="aprobada-con-cambios")
    with pytest.raises(ValidationError):
        DecisionNueva(decision="x" * 41)


def test_la_configuracion_pide_un_tipo_conocido():
    EntregaConfig(tipoPieza="cenefa", aprobadores=[1], fases=[{"nombre": "Boceto"}])
    with pytest.raises(ValidationError):
        EntregaConfig(tipoPieza="afiche", aprobadores=[1], fases=[{"nombre": "Boceto"}])


# --- Retrabajo -------------------------------------------------------------

def test_las_metricas_de_retrabajo():
    filas = [
        ("cenefa", AGENCIA, "tienda_inglesa", 1),
        ("cenefa", AGENCIA, "tienda_inglesa", 3),
        ("mailing", 9, "tienda_inglesa", 1),
        ("banner", AGENCIA, "redexpres", 2),
    ]
    m = metricas_de_retrabajo(filas)
    assert m["fases"] == 4
    assert m["rondasPromedio"] == 1.75
    assert m["aLaPrimera"] == 50
    por_tipo = {g["clave"]: g for g in m["porTipo"]}
    assert por_tipo["cenefa"]["rondasPromedio"] == 2 and por_tipo["cenefa"]["aLaPrimera"] == 50
    assert por_tipo["mailing"]["aLaPrimera"] == 100
    assert [g["clave"] for g in m["porTipo"]] == ["cenefa", "mailing", "banner"]
    por_responsable = {g["clave"]: g for g in m["porResponsable"]}
    assert por_responsable[AGENCIA]["fases"] == 3 and por_responsable[AGENCIA]["rondasPromedio"] == 2
    assert {g["clave"]: g["fases"] for g in m["porMundo"]} == {"tienda_inglesa": 3, "redexpres": 1}


def test_sin_fases_aprobadas_no_hay_promedio():
    m = metricas_de_retrabajo([])
    assert m["fases"] == 0 and m["rondasPromedio"] is None and m["aLaPrimera"] is None


# --- Los avisos ------------------------------------------------------------

def test_la_referencia_lleva_a_la_tarea():
    ref = referencia("br-1", "ta-2", "ve-3", "revisar-7")
    assert ref.split(":")[:2] == ["br-1", "ta-2"]
    assert len(referencia("b" * 64, "t" * 64, "v" * 64, "revisar-123456")) <= 255


def test_los_textos_de_los_avisos():
    assert mensaje_para_revisar("Agencia Sur", 2, "Arte final", "Cenefa Navidad", "Navidad") == (
        "Agencia Sur entregó la ronda 2 de Arte final en «Cenefa Navidad» (Navidad). Te toca revisarla."
    )
    assert "Ahora te toca revisarla a vos" in mensaje_para_revisar(
        "", 1, "Boceto", "X", "Y", aprobo_antes="Marca",
    )
    assert mensaje_de_cambios("Promo", 1, "Boceto", "X", 2).endswith("(2 marcas). Te toca entregar la ronda 2.")
    aprobada = mensaje_de_aprobacion(
        "Comercial", 2, "Boceto", "X", siguiente_fase="Arte final", sigue_revisando=None, terminada=False,
    )
    assert aprobada == "Comercial aprobó la ronda 2 de Boceto de «X». Te toca entregar Arte final."
    assert "con cambios" not in aprobada and "justes" not in aprobada
    assert mensaje_de_aprobacion(
        "Marca", 1, "Arte final", "X", siguiente_fase=None, sigue_revisando=None, terminada=True,
    ).endswith("la tarea quedó hecha.")
    assert mensaje_de_aprobacion(
        "Marca", 1, "Boceto", "X", siguiente_fase=None, sigue_revisando="Comercial", terminada=False,
    ).endswith("Ahora la revisa Comercial.")
    largo = mensaje_de_aprobacion(
        "M" * 400, 1, "F" * 400, "T", siguiente_fase=None, sigue_revisando=None, terminada=False,
    )
    assert len(largo) <= 700


def test_la_campanita_muestra_los_avisos_de_entregas_a_quien_ve_el_calendario():
    def usuario(*permisos):
        return SimpleNamespace(is_superuser=False, permissions=list(permisos))

    aviso = SimpleNamespace(origen_tipo=ORIGEN)
    assert ORIGEN == "calendario_entrega"
    assert _notif_visible(usuario("calendario.view"), aviso)
    assert not _notif_visible(usuario("precios.search"), aviso)

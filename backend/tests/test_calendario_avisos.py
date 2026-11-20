"""Los avisos del calendario: solo los que alguien configuró.

Pedido de Ivan (28/09/2026): se apaga el aviso automático de 10 días. "Cuando
realmente nos llegue una notificación, es porque alguien la configuró y porque
realmente vale la pena". Lo que se fija acá:

  - la ventana es "faltan N días o menos y todavía no arrancó", no "faltan
    exactamente N": si el servidor estuvo caído un par de días, el aviso sale
    igual en vez de perderse;
  - un aviso sale una vez por persona dentro de su ventana: correr la acción un
    día no lo repite, correrla a otro mes lo vuelve a armar;
  - la referencia empieza por el id de la acción, que es lo que usa la
    campanita para llevar a su ficha;
  - no queda ningún rastro del aviso automático.
"""
import inspect
from datetime import date, datetime, timezone

from app.services import calendario_avisos
from app.services.calendario_avisos import inicio_de_ventana, mensaje, referencia, toca_avisar


# ---------------------------------------------------------------------------
# La ventana
# ---------------------------------------------------------------------------

def test_avisa_el_dia_que_toca():
    assert toca_avisar(date(2026, 10, 12), 10, hoy=date(2026, 10, 2))


def test_avisa_tambien_si_el_servidor_estuvo_caido_y_faltan_menos():
    assert toca_avisar(date(2026, 10, 12), 10, hoy=date(2026, 10, 9))


def test_no_avisa_antes_de_tiempo():
    assert not toca_avisar(date(2026, 10, 12), 10, hoy=date(2026, 10, 1))


def test_no_avisa_una_accion_que_ya_arranco():
    assert not toca_avisar(date(2026, 10, 12), 10, hoy=date(2026, 10, 13))


def test_el_dia_que_arranca_todavia_entra():
    assert toca_avisar(date(2026, 10, 12), 10, hoy=date(2026, 10, 12))


def test_sesenta_dias_antes_cruza_de_mes():
    assert toca_avisar(date(2026, 12, 1), 60, hoy=date(2026, 10, 2))
    assert not toca_avisar(date(2026, 12, 1), 60, hoy=date(2026, 10, 1))


# ---------------------------------------------------------------------------
# La referencia
# ---------------------------------------------------------------------------

def test_la_referencia_empieza_por_la_accion():
    ref = referencia("br-abc-1", "av-xyz-2")
    assert ref.split(":")[0] == "br-abc-1"


def test_la_ventana_arranca_a_las_cero_horas_de_uruguay_del_dia_del_aviso():
    ventana = inicio_de_ventana(date(2026, 10, 12), 10)
    assert ventana == datetime(2026, 10, 2, 3, 0, tzinfo=timezone.utc)


def test_correr_la_accion_un_dia_no_vuelve_a_mandar_el_aviso():
    # Salió el 03/10 para una acción del 12/10. Si la acción pasa al 13/10, la
    # ventana nueva arranca el 03/10: el aviso ya salió adentro, no se repite.
    salio = datetime(2026, 10, 3, 15, 0, tzinfo=timezone.utc)
    assert salio >= inicio_de_ventana(date(2026, 10, 13), 10)


def test_correr_la_accion_lejos_vuelve_a_armar_el_aviso():
    # La misma acción pasa a diciembre: la ventana nueva arranca el 22/11,
    # después del aviso viejo, así que vuelve a salir para la fecha nueva.
    salio = datetime(2026, 10, 3, 15, 0, tzinfo=timezone.utc)
    assert salio < inicio_de_ventana(date(2026, 12, 2), 10)


# ---------------------------------------------------------------------------
# El texto
# ---------------------------------------------------------------------------

def test_el_mensaje_dice_cuanto_falta_la_fecha_y_quien_lo_configuro():
    texto = mensaje("Fiesta de Italia", "MEGA EVENTO", date(2026, 10, 12), date(2026, 10, 2), "Ivan")
    assert "Fiesta de Italia" in texto
    assert "MEGA EVENTO" in texto
    assert "en 10 días" in texto
    assert "12/10" in texto
    assert "Ivan" in texto


def test_el_mensaje_no_dice_en_1_dias():
    assert "arranca mañana" in mensaje("X", "", date(2026, 10, 12), date(2026, 10, 11), None)
    assert "arranca hoy" in mensaje("X", "", date(2026, 10, 12), date(2026, 10, 12), None)


def test_una_accion_sin_nombre_igual_se_entiende():
    assert mensaje("", "", date(2026, 10, 12), date(2026, 10, 2), None).startswith("Sin nombre")


def test_una_accion_con_categoria_la_lleva_entre_parentesis():
    texto = mensaje("Fiesta de Italia", "MEGA EVENTO", date(2026, 10, 12), date(2026, 10, 2), None)
    assert texto == "Fiesta de Italia (MEGA EVENTO) arranca en 10 días, el 12/10."


def test_una_accion_sin_categoria_va_sin_parentesis():
    # Desde el 12/11/2026 una acción se crea sin preguntar de qué tipo es y
    # guarda 'Sin categoría' en la banda: "Fiesta de Italia (Sin categoría)
    # arranca..." no le dice nada a quien recibe el aviso.
    texto = mensaje("Fiesta de Italia", "Sin categoría", date(2026, 10, 12), date(2026, 10, 2), "Ivan")
    assert "(" not in texto and ")" not in texto
    assert "Sin categoría" not in texto
    assert texto == "Fiesta de Italia arranca en 10 días, el 12/10. Aviso configurado por Ivan."


def test_sin_categoria_es_la_misma_con_mayusculas_o_espacios_de_mas():
    for banda in ("SIN CATEGORÍA", "sin categoría", "  Sin categoría "):
        texto = mensaje("Fiesta de Italia", banda, date(2026, 10, 12), date(2026, 10, 2), None)
        assert texto == "Fiesta de Italia arranca en 10 días, el 12/10.", banda


def test_el_aviso_de_un_envio_no_cambia():
    texto = mensaje("Mailing Día de la Madre", "email", date(2026, 10, 12), date(2026, 10, 2), None, es_envio=True)
    assert texto == "Mailing Día de la Madre (Email) sale en 10 días, el 12/10."


# ---------------------------------------------------------------------------
# El automático no vuelve
# ---------------------------------------------------------------------------

def test_no_queda_el_aviso_automatico_de_diez_dias():
    fuente = inspect.getsource(calendario_avisos)
    assert "DIAS_DE_AVISO" not in fuente
    assert "calendario_accion" not in fuente, (
        "el aviso automático escribía con origen 'calendario_accion': si vuelve a "
        "aparecer, vuelven a llegar avisos que nadie configuró"
    )


# ---------------------------------------------------------------------------
# Desde la fecha de un envío (0084, Ivan 20/11/2026)
# ---------------------------------------------------------------------------

def test_un_aviso_de_un_envio_se_cuenta_desde_que_sale():
    from types import SimpleNamespace
    from app.services.calendario_avisos import fecha_base
    barra = SimpleNamespace(desde=date(2026, 11, 22))
    assert fecha_base(barra, None) == date(2026, 11, 22)
    assert fecha_base(barra, SimpleNamespace(desde=date(2026, 11, 25))) == date(2026, 11, 25)
    # Al envío le sacaron la fecha: sale con la acción.
    assert fecha_base(barra, SimpleNamespace(desde=None)) == date(2026, 11, 22)


def test_el_aviso_de_un_envio_dice_que_envio_sale():
    from types import SimpleNamespace
    from app.services.calendario_avisos import mensaje_de_envio
    barra = SimpleNamespace(nombre="Ciberlunes", desde=date(2026, 11, 22))
    pieza = SimpleNamespace(area="email", formato="Mailing digital", desde=date(2026, 11, 25))
    texto = mensaje_de_envio(pieza, barra, date(2026, 11, 25), date(2026, 11, 22), "Valentina")
    assert texto == "Ciberlunes · Mailing digital (Email) sale en 3 días, el 25/11. Aviso configurado por Valentina."

"""Todo lo que vale SOLO para el destino de pruebas. Nada de acá toca producción.

Este archivo existe por un pedido explícito de Ivan (17/09/2026): que lo que
se está probando viva aislado, en un archivo dedicado, "para que no salpique
para ningún costado, porque hasta ahora lo que tenemos por suerte está
funcionando bien".

La regla de aislamiento, entonces:

    NADA de este archivo puede correr sobre una plantilla que no sea del
    destino `pruebas`. Toda función pública empieza chequeando `es_de_pruebas`
    y se va sin hacer nada si no lo es.

Y al revés: el motor genérico no sabe que esto existe más allá de UNA llamada,
al final del render, que es un no-op en todos los demás mundos. Se eligió una
pasada final sobre el archivo ya armado en vez de hilar un parámetro por
`_render_slide` -> `_place_component` -> `_populate_text_frame`, justamente
para no tocar funciones que usan los siete mundos de producción.

-----------------------------------------------------------------------------
Qué se está probando: devolverle el autoajuste a PowerPoint
-----------------------------------------------------------------------------

El motor genérico APAGA el autoajuste en todos los cuadros: saca el
a:normAutofit / a:spAutoFit que traiga el shape del diseñador y deja
a:noAutofit (ver `_forzar_sin_autoajuste` en component_renderer.py). Es del
14/09/2026 y fue deliberado: al eliminar el achique propio del motor, el de
PowerPoint quedó como único actor y achicaba todo sin que el preview lo
mostrara, con lo cual el archivo no se parecía a la pantalla.

Lo que buscamos probar acá es lo contrario: que una descripción larga o un
precio largo NO desborden ni se superpongan, y que eso ya esté resuelto al
abrir el archivo, sin que nadie tenga que tocar cuadro por cuadro.

Ojo con lo que este experimento SÍ y NO prueba:

  - Poner <a:normAutofit/> declara "achicá el texto si no entra", pero el que
    tiene que hacerlo es PowerPoint, al renderizar. Si PowerPoint solo
    respeta un `fontScale` YA guardado en el archivo (que es lo que hace
    sospechar el síntoma que reporta Ivan: "siempre tuve que tocar el cuadro
    para que se formateara"), entonces activarlo solo no alcanza y el paso
    siguiente es calcular nosotros ese `fontScale` y escribirlo.
  - Por eso el primer experimento es exactamente este: activarlo pelado,
    bajar la PPT y mirar. El resultado decide el paso siguiente, en vez de
    que lo decidamos de antemano.

Cambiar de variante es cambiar `MODO` acá abajo. Ningún otro archivo.
"""
import math

from lxml import etree
from pptx.oxml.ns import qn

from app.services.cenefas.font_metrics import ancho_texto_cm
from app.services.cenefas.reglas_medicion import REGLAS

# El slug del destino de pruebas, tal como está en la tabla `cenefa_destinos`
# ("Pruebas -- Corridas de prueba. No suman al informe de produccion",
# cobrable=false). Es la ÚNICA puerta de entrada a este archivo.
SLUG = "pruebas"


# Qué autoajuste se le escribe a cada cuadro en el destino de pruebas.
#
#   "noAutofit"     -> <a:noAutofit/>. Lo mismo que producción. Está para
#                      poder comparar contra el comportamiento de hoy sin
#                      cambiar de plantilla.
#   "normAutofit"   -> <a:normAutofit/> PELADO. Dice "reducí el texto al
#                      desbordarse" pero sin escala guardada.
#   "escala_fija"   -> <a:normAutofit fontScale="50000"/>, o sea 50% puesto a
#                      mano. No prueba nuestra cuenta: prueba si PowerPoint
#                      OBEDECE un número escrito por nosotros.
#   "escala_medida" -> <a:normAutofit fontScale="N"/> con N calculado midiendo
#                      el texto contra la caja (ver `_escala_que_entra`).
#   "spAutoFit"     -> <a:spAutoFit/>. Agranda la CAJA hasta que el texto
#                      entre, en vez de achicar el texto. Para un precio
#                      suele romper el diseño; está para descartarlo con
#                      evidencia y no de palabra.
#   "ciclo"         -> una variante por HOJA, en el orden de la tabla de
#                      abajo. Es el modo del experimento: un solo PPTX donde
#                      lo único que cambia entre hojas es el autoajuste, así
#                      se comparan mirando el mismo cartel al lado.
MODO = "ciclo"

# El orden del ciclo. La hoja 1 es la foto del problema (lo de hoy) y cada
# hoja siguiente responde una pregunta distinta:
#
#   hoja 2 vs hoja 1 -> ¿PowerPoint recalcula solo al abrir?
#   hoja 3           -> ¿obedece un fontScale que escribimos nosotros?
#   hoja 4           -> ¿nuestra medición da una escala razonable?
#   hoja 5           -> ¿agrandar la caja es viable o rompe el diseño?
CICLO = ("noAutofit", "normAutofit", "escala_fija", "escala_medida", "spAutoFit")

# El 50% del modo "escala_fija". En centésimas de punto porcentual, que es
# como lo escribe el esquema: 50000 = 50,000%.
_ESCALA_FIJA = 50000

_TAGS = {
    "noAutofit":     "a:noAutofit",
    "normAutofit":   "a:normAutofit",
    "escala_fija":   "a:normAutofit",
    "escala_medida": "a:normAutofit",
    "spAutoFit":     "a:spAutoFit",
}

# Piso de la escala medida. Por debajo de esto el texto deja de leerse en un
# cartel de góndola, y un cuadro que necesite menos que esto es un problema de
# diseño --la caja está mal-- que achicar solo esconde en vez de resolver.
_ESCALA_MINIMA = 25000

# Los tres son mutuamente excluyentes en el esquema: hay que sacar el que
# esté antes de poner el nuevo.
_TODOS = ("a:normAutofit", "a:spAutoFit", "a:noAutofit")


def es_de_pruebas(template_def: dict | None) -> bool:
    """True solo si esta definición pertenece al destino de pruebas.

    Lee `category`, que es el slug del destino (lo mismo que guarda la columna
    `cenefa_templates_v2.category`).

    Ojo con un detalle que costó encontrar: al 17/09/2026, 9 de las 22
    plantillas guardadas NO tenían `category` adentro del JSON --solo en la
    columna-- así que preguntarle a la definición daba None y el aislamiento
    habría sido de mentira en esos casos. Por eso `_resolve_template_v2`
    estampa la columna en la definición antes de entregarla al motor. Si algún
    día esta función empieza a devolver False donde no debe, ese es el lugar
    donde mirar.
    """
    if not isinstance(template_def, dict):
        return False
    return str(template_def.get("category") or "").strip().lower() == SLUG


def _escala_que_entra(shape) -> int:
    """A qué porcentaje hay que dibujar este texto para que entre en su caja.

    Devuelve centésimas de punto porcentual (100000 = 100%, o sea sin achicar).

    La cuenta es a propósito la más simple que puede servir, y mide contra la
    caja PROPIA y nada más -- ni los vecinos ni la hoja, que es el criterio
    que fijó Ivan el 11/09/2026 y lo que evitó el enredo del achique viejo.

    Ojo con cuánto vale este número: al 17/09/2026 el 42% de los cuadros de
    las plantillas usan tipografías que NO están en la tabla de anchos y caen
    al ancho de reserva (0,52 em). Y peor: "Arial Black" cae por prefijo en
    "Arial", que es bastante más angosta, así que ahí se SUBESTIMA el ancho
    --el lado peligroso-- y la escala sale más grande de lo que hace falta.
    Antes de confiar en este modo hay que correr
    ``scripts/generar_font_metrics.py`` en una máquina que tenga esas fuentes.
    Por eso el experimento trae además el modo "escala_fija": ese prueba el
    MECANISMO sin depender de esta medición.
    """
    tf = shape.text_frame
    texto = tf.text or ""
    if not texto.strip():
        return 100000

    tam = None
    for para in tf.paragraphs:
        for run in para.runs:
            if run.font.size:
                tam = max(tam or 0, run.font.size.pt)
    if not tam:
        return 100000

    familia = None
    negrita = False
    for para in tf.paragraphs:
        for run in para.runs:
            familia = run.font.name or familia
            negrita = bool(run.font.bold) or negrita

    ancho_caja = shape.width / 360000.0
    alto_caja  = shape.height / 360000.0
    if ancho_caja <= 0 or alto_caja <= 0:
        return 100000

    # Ancho: el renglón más largo del texto tal como quedó escrito.
    ancho_texto = max(
        (ancho_texto_cm(linea, tam, familia, negrita) for linea in texto.splitlines() if linea),
        default=0.0,
    )
    por_ancho = ancho_caja / ancho_texto if ancho_texto > ancho_caja else 1.0

    # Alto: cuántos renglones entran, contando el corte por palabra que hace
    # PowerPoint cuando el texto es más ancho que la caja.
    alto_linea = tam / 72.0 * 2.54 * REGLAS.alto_de_linea
    renglones = 0
    for linea in (texto.splitlines() or [""]):
        w = ancho_texto_cm(linea, tam, familia, negrita)
        renglones += max(1, math.ceil(w / ancho_caja)) if ancho_caja > 0 else 1
    alto_texto = renglones * alto_linea
    por_alto = alto_caja / alto_texto if alto_texto > alto_caja else 1.0

    escala = int(round(min(por_ancho, por_alto) * 100000))
    return max(_ESCALA_MINIMA, min(100000, escala))


def _escribir_autoajuste(body_pr, tag: str, escala: int | None = None) -> None:
    """Deja `tag` como ÚNICO autoajuste de este bodyPr, en la posición correcta.

    El orden de los hijos de a:bodyPr lo fija el esquema (el autoajuste va
    después de a:prstTxWarp y antes de a:scene3d), así que se reemplaza en el
    lugar del que había en vez de appendear al final -- si no, un shape
    preservado que traiga elementos posteriores queda con el XML fuera de
    orden y PowerPoint lo rechaza. Mismo criterio que `_forzar_sin_autoajuste`.
    """
    posicion = None
    for nombre in _TODOS:
        for el in body_pr.findall(qn(nombre)):
            if posicion is None:
                posicion = list(body_pr).index(el)
            body_pr.remove(el)
    nuevo = etree.Element(qn(tag))
    # El fontScale va en centésimas de punto porcentual y solo lo admite
    # a:normAutofit. 100% se omite: escribirlo no aporta nada y ensucia el
    # archivo con un atributo que dice "no achiques".
    if escala is not None and tag == "a:normAutofit" and escala < 100000:
        nuevo.set("fontScale", str(int(escala)))
    if posicion is None:
        body_pr.append(nuevo)
    else:
        body_pr.insert(posicion, nuevo)


def aplicar_autofit(prs, template_def: dict | None) -> int:
    """Le devuelve el autoajuste a TODOS los cuadros de texto, solo en pruebas.

    Corre sobre la presentación ya armada, justo antes de guardarla: para
    entonces el motor genérico ya dejó `a:noAutofit` en cada cuadro, y acá se
    pisa con lo que diga `MODO`.

    Devuelve cuántos cuadros se tocaron (0 fuera del destino de pruebas), para
    poder afirmar en un test que producción no se toca -- y no solamente
    suponerlo.
    """
    if not es_de_pruebas(template_def):
        return 0

    tocados = 0
    for i, slide in enumerate(prs.slides):
        # En "ciclo", cada HOJA lleva una variante distinta: el mismo cartel,
        # con el mismo texto, cambiando solo el autoajuste. Si hay más hojas
        # que variantes se repite el ciclo, así una corrida larga igual sirve.
        variante = CICLO[i % len(CICLO)] if MODO == "ciclo" else MODO
        tag = _TAGS.get(variante)
        if tag is None:
            continue
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            body_pr = shape.text_frame._txBody.find(qn("a:bodyPr"))
            if body_pr is None:
                continue
            escala = None
            if variante == "escala_fija":
                escala = _ESCALA_FIJA
            elif variante == "escala_medida":
                escala = _escala_que_entra(shape)
            _escribir_autoajuste(body_pr, tag, escala)
            tocados += 1
        _anotar_variante(slide, i + 1, variante)
    return tocados


# Qué se lee en las notas de cada hoja. Va en las NOTAS y no en el diseño para
# no cambiarle un milímetro al cartel: el experimento tiene que comparar
# carteles idénticos.
_EXPLICACION = {
    "noAutofit":     "Autoajuste APAGADO. Es exactamente lo que sale hoy en produccion: la foto del problema, el patron contra el que comparar las otras hojas.",
    "normAutofit":   "Autoajuste PRENDIDO pero sin escala guardada. La pregunta central: sale ya achicado, o sale igual de desbordado que la hoja 1? Probá tambien hacer clic en el cuadro, escribir un espacio y borrarlo: si AHI se achica, PowerPoint tiene el autoajuste pero solo lo ejecuta cuando algo lo despierta.",
    "escala_fija":   "Autoajuste con una escala del 50% puesta A MANO por nosotros. No prueba nuestra cuenta: prueba si PowerPoint obedece un numero que escribimos. Si esta hoja abre con el texto a la mitad sin tocar nada, el camino esta confirmado.",
    "escala_medida": "Autoajuste con la escala que CALCULO el motor midiendo el texto contra su caja. Aca si se juzga nuestra medicion: el texto queda adentro, sin desbordar y sin quedar ridiculamente chico?",
    "spAutoFit":     "En vez de achicar el texto, agranda la CAJA hasta que entre. Esperable que el precio se coma el cuadro de al lado o se vaya de la hoja; esta para poder descartarlo con evidencia.",
}


def _anotar_variante(slide, numero: int, variante: str) -> None:
    """Escribe en las notas de la hoja qué variante le tocó.

    Sin esto el PPTX es cinco hojas parecidas y no hay forma de saber cuál es
    cuál mirándolas. En las notas y no en el cartel, a propósito.
    """
    try:
        slide.notes_slide.notes_text_frame.text = (
            f"HOJA {numero} -- variante: {variante}\n\n{_EXPLICACION.get(variante, '')}"
        )
    except Exception:
        # Un layout sin notas no puede voltear una corrida por un cartelito.
        pass

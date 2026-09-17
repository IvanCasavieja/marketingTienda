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
from lxml import etree
from pptx.oxml.ns import qn

# El slug del destino de pruebas, tal como está en la tabla `cenefa_destinos`
# ("Pruebas -- Corridas de prueba. No suman al informe de produccion",
# cobrable=false). Es la ÚNICA puerta de entrada a este archivo.
SLUG = "pruebas"


# Qué autoajuste se le escribe a cada cuadro en el destino de pruebas.
#
#   "normAutofit"  -> <a:normAutofit/> pelado. "Reducir el texto al
#                     desbordarse", sin escala guardada. Es el que pidió Ivan
#                     probar primero, y el que dice si PowerPoint recalcula
#                     solo al abrir o se queda esperando una edición.
#   "spAutoFit"    -> <a:spAutoFit/>. Agranda la CAJA hasta que el texto
#                     entre, en vez de achicar el texto. Sirve para una
#                     descripción; para un precio suele romper el diseño.
#   "noAutofit"    -> <a:noAutofit/>. Lo mismo que producción. Está acá para
#                     poder comparar contra el comportamiento de hoy sin
#                     cambiar de plantilla.
MODO = "normAutofit"

_MODOS = {
    "normAutofit": "a:normAutofit",
    "spAutoFit":   "a:spAutoFit",
    "noAutofit":   "a:noAutofit",
}

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


def _escribir_autoajuste(body_pr, tag: str) -> None:
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
    tag = _MODOS.get(MODO)
    if tag is None:
        return 0

    tocados = 0
    for slide in prs.slides:
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            body_pr = shape.text_frame._txBody.find(qn("a:bodyPr"))
            if body_pr is None:
                continue
            _escribir_autoajuste(body_pr, tag)
            tocados += 1
    return tocados

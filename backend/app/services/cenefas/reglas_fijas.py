"""Reglas que impone el sistema y que una resubida de PPTX no puede borrar.

Existe por un problema concreto: `import_pptx` devuelve siempre
``"rules": []``. Cada vez que alguien vuelve a subir la PPT de una plantilla,
TODAS sus reglas se pierden. Hasta ahora eso se compensaba a mano --ver
``scripts/agregar_regla_cocarda_vacia.py``, cuyo docstring dice literalmente
"cuándo correrlo: cada vez que esta plantilla se reimporta desde cero"--, o
sea que la corrección dependía de que alguien se acordara.

Una regla fija se re-inyecta sola en TODOS los caminos por los que una
definición se guarda o se usa: al importar, al crear, al actualizar y al
correr un job con reglas sobreescritas. Borrarla desde la UI no sirve de
nada: vuelve en el siguiente guardado. Por eso viaja marcada con
``bloqueada: True``, para que el panel de reglas la muestre como lo que es
--algo que el sistema garantiza, no algo que alguien escribió-- en vez de
ofrecer un botón de borrar que no borra.

Son reglas normales del motor (mismo esquema, mismos operadores): se ven en
el panel junto a las demás y se evalúan igual. Eso es deliberado, decisión
de Ivan (17/09/2026): "quiero que la regla la hagas adentro de la plataforma,
no una regla externa, porque si no después no entendemos de dónde carajo
salen las cosas".

-----------------------------------------------------------------------------
Qué garantiza hoy: el símbolo de moneda al lado de ``promoOferta``
-----------------------------------------------------------------------------

``promoOferta`` es la variable que ocupa el cuadro grande EN LUGAR del precio
(ver el bloque del principio de variables.py). Lleva dos especies de dato
distintas según la mecánica:

    Combo "3x$160"  ->  promoOferta = 160    un NÚMERO (el total del combo)
    M x N  "2x1"    ->  promoOferta = "2x1"  un TEXTO (el literal)

El símbolo de moneda corresponde solo en el primer caso. Como el diseño lo
dibuja pegado --mismo cuadro-- y el cuadro no sabe qué especie le tocó, un
M x N salía impreso como "$2x1" (visto en vivo en la 3xA4, 17/09/2026).

La señal que los separa está en el propio dato y no hace falta inventar un
operador para leerla: un M x N SIEMPRE trae la "x" que lo define ("2x1",
"4x3", "6x4"), y el total de un combo es un número pelado que nunca la
tiene. O sea que alcanza con ``contains`` "x", que ya existe en el motor, en
su espejo del navegador y en el desplegable del panel.

Se generan DOS reglas por símbolo, las dos de ocultar:

    1. si promoOferta está VACÍA    -> sin esto el cuadro imprime un "$"
                                       huérfano en todo producto sin promo,
                                       que son la mayoría. No es cosmético:
                                       es la razón por la que agregarle el
                                       símbolo a un diseño que no lo tenía
                                       sería un bug si fuera solo.
    2. si promoOferta CONTIENE "x"  -> el M x N.

Juntas dicen: el símbolo aparece solo cuando lo que sigue es plata.
"""
import uuid
from typing import Any

# Namespace propio para los ids de las reglas fijas. Derivarlos (uuid5) en vez
# de sortearlos (uuid4) es lo que hace que aplicar esto dos veces no duplique
# nada: la misma plantilla y el mismo cuadro dan SIEMPRE el mismo id, así que
# la segunda pasada reconoce la regla que dejó la primera.
_NS_REGLAS_FIJAS = uuid.UUID("6f1b1c1e-7a3d-5e2b-9c44-2b6f0d9a8e11")

# La marca que distingue una regla del sistema de una escrita por una persona.
CLAVE_BLOQUEADA = "bloqueada"

# La variable del símbolo de moneda ("$" / "U$S"), ver variables.py.
VAR_SIMBOLO = "unidadMoneda"

# Un segmento FIJO (texto escrito en el diseño, no variable) que hace de
# símbolo de moneda. Las plantillas de Preciazos componen el cuadro como
# "<<tipoOferta>> $ <<promoOferta>>", con el "$" tipeado en el medio en vez de
# puesto como variable: para lo que nos importa --cuándo se muestra-- es
# exactamente lo mismo y se trata igual.
_SIMBOLOS_FIJOS = {"$", "u$s", "us$", "usd"}

VAR_DOMINANTE = "promoOferta"


def _variables_del_componente(c: dict) -> set[str]:
    """Las variables que ese cuadro imprime, sea directo o por segmentos.

    Mismo criterio que component_renderer._variables_del_componente. Un cuadro
    importado suele traer las DOS cosas: `variable` con el nombre principal y
    `segments` con el desglose real.
    """
    salida = {
        seg.get("value") for seg in (c.get("segments") or [])
        if seg.get("type") == "variable" and seg.get("value")
    }
    if c.get("variable"):
        salida.add(c["variable"])
    return salida


def _es_simbolo_fijo(seg: dict) -> bool:
    return (seg.get("type") == "static"
            and str(seg.get("value", "")).strip().lower() in _SIMBOLOS_FIJOS)


def _indice_del_simbolo(comp: dict) -> int | None:
    """En qué segmento vive el símbolo de moneda de este cuadro, si ya está."""
    for i, seg in enumerate(comp.get("segments") or []):
        if seg.get("type") == "variable" and seg.get("value") == VAR_SIMBOLO:
            return i
        if _es_simbolo_fijo(seg):
            return i
    return None


def _asegurar_simbolo(comp: dict) -> tuple[dict, int, bool]:
    """Devuelve (cuadro, índice del símbolo, si hubo que agregarlo).

    Cuatro anatomías reales, medidas sobre las 11 plantillas que hoy tienen
    cuadro de promoOferta (17/09/2026):

      a) [<<unidadMoneda>>, <<promoOferta>>]                  -> ya está
      b) [<<tipoOferta>>, " $ ", <<promoOferta>>]             -> ya está (fijo)
      c) [<<promoOferta>>]                                    -> se inserta
      d) sin segmentos, `variable: "promoOferta"` suelta      -> se construye

    En (c) y (d) el símbolo se agrega HEREDANDO el cuerpo del segmento de
    promoOferta, o sea del mismo tamaño que el número. No es un valor
    inventado: es lo que esos mismos diseños ya hacen. Medido el 17/09/2026
    sobre el "$" que cada plantilla le dibuja a su `precioOferta`:

        Red Expres-202608-3xA4   97 / 97     ratio 1,00
        3xA4 HELVETICO           97 / 97     ratio 1,00
        3xA4 SOLO X 25           96 / 96     ratio 1,00
        A4 HELVETICO            239 / 239    ratio 1,00
        Red Expres 17 A4        108 / 180    ratio 0,60
        Cenefas 3xA4             61 / 97     ratio 0,63

    Las cuatro primeras son justamente las que hoy NO tienen símbolo al lado
    de promoOferta, y las cuatro usan 1,00 en el precio. Las dos que sí lo
    tienen (0,60 / 0,63) no pasan por acá, porque el símbolo ya existe.

    Si alguien quiere afinarlo lo hace en el editor y queda: esto no vuelve a
    tocar un cuadro que ya tiene su símbolo.
    """
    idx = _indice_del_simbolo(comp)
    if idx is not None:
        return comp, idx, False

    segs = list(comp.get("segments") or [])
    if segs:
        destino = next((i for i, s in enumerate(segs)
                        if s.get("type") == "variable" and s.get("value") == VAR_DOMINANTE), None)
        if destino is None:
            return comp, -1, False
        estilo = dict(segs[destino].get("style") or {})
    else:
        # Cuadro sin segmentos: imprime `variable` suelta. Se convierte al
        # formato de dos segmentos, que es como quedan los importados y lo que
        # el resto del motor ya sabe dibujar (el propio cuadro conserva su
        # `variable`, igual que en las plantillas del grupo (a)).
        destino = 0
        estilo = dict((comp.get("style") or {}))
        estilo.pop("line_height_pt", None)
        segs = [{"type": "variable", "value": VAR_DOMINANTE, "style": dict(estilo)}]

    simbolo = {"type": "variable", "value": VAR_SIMBOLO, "style": estilo}
    segs.insert(destino, simbolo)
    return {**comp, "segments": segs}, destino, True


def _regla(comp_id: str, idx: int, sufijo: str, nombre: str, condicion: dict) -> dict:
    return {
        "id": str(uuid.uuid5(_NS_REGLAS_FIJAS, f"{comp_id}:{idx}:{sufijo}")),
        "name": nombre,
        "action": {"type": "hide"},
        "condition": condicion,
        "target_component_id": comp_id,
        "target_segment_index": idx,
        CLAVE_BLOQUEADA: True,
    }


def reglas_del_simbolo(comp_id: str, idx: int) -> list[dict]:
    """Las dos reglas fijas del símbolo de moneda de un cuadro de promoOferta."""
    return [
        _regla(comp_id, idx, "vacia",
               "Ocultar el símbolo de moneda si promoOferta está vacío",
               {"field": VAR_DOMINANTE, "operator": "is_empty"}),
        _regla(comp_id, idx, "mxn",
               "Ocultar el símbolo de moneda si promoOferta es un M x N",
               {"field": VAR_DOMINANTE, "operator": "contains", "value": "x"}),
    ]


def asegurar_reglas_fijas(definition: dict[str, Any] | None) -> dict[str, Any] | None:
    """Garantiza las reglas fijas de una definición. Idempotente.

    Devuelve una copia nueva; no muta la que recibe. Una definición sin
    cuadros de promoOferta vuelve igual (salvo por la copia).

    Las reglas fijas se REEMPLAZAN, no se acumulan: si ya había una con el
    mismo id --porque esta función ya corrió antes-- se descarta la vieja y
    queda la recién calculada. Así, cambiar el texto o la condición acá se
    propaga solo en el próximo guardado, sin dejar versiones viejas dando
    vueltas.
    """
    if not isinstance(definition, dict):
        return definition

    fijas: list[dict] = []
    componentes: list[dict] = []

    for comp in (definition.get("components") or []):
        if VAR_DOMINANTE not in _variables_del_componente(comp) or not comp.get("id"):
            componentes.append(comp)
            continue
        comp, idx, _ = _asegurar_simbolo(comp)
        componentes.append(comp)
        if idx >= 0:
            fijas.extend(reglas_del_simbolo(comp["id"], idx))

    if not fijas:
        return {**definition, "components": componentes}

    # Las reglas de las personas se conservan tal cual, en su orden. Las fijas
    # van primero, para que se lean arriba de todo en el panel.
    #
    # Se descarta toda regla YA marcada como bloqueada que no esté en la lista
    # recién calculada: son de una corrida anterior de esto mismo, sobre una
    # versión del diseño que ya no existe (un cuadro que se borró, un símbolo
    # que cambió de índice). Sin esto quedarían apuntando a segmentos que se
    # movieron y ocultarían el pedazo equivocado.
    ids_fijas = {r["id"] for r in fijas}
    de_personas = [r for r in (definition.get("rules") or [])
                   if r.get("id") not in ids_fijas and not r.get(CLAVE_BLOQUEADA)]

    return {**definition, "components": componentes, "rules": fijas + de_personas}

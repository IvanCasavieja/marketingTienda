"""Tinín — agente del área de Materiales (cenefas): responde preguntas sobre
templates, destinos y el flujo de generación, y puede agregar/corregir una
descripción en el catálogo compartido cuando el usuario se lo pide
explícitamente. NO genera cenefas él mismo: la API de generación exige un
Excel real subido (`excel: UploadFile = File(...)` en
`POST /tools/cenefas/v2/jobs`), no hay forma de mandarlo por chat — así que
Tinín guía y explica, nunca dispara la generación.

Primer uso de tool-use real en esta plataforma — el resto de la familia
Tino (`_ask_claude` en debate_service.py) solo genera texto plano. Acá el
loop es manual (`while stop_reason == "tool_use"`), no el Tool Runner beta:
es una sola tool, no vale la pena la dependencia beta para esto.
"""
import logging

import anthropic

from app.core.config import settings
from app.services.ai_usage_service import log_ai_usage
from app.services.cenefas.convertidor import upsert_sku_descripcion
from app.services.cenefas.validation_engine import DESCRIPTION_MAX_CHARS, DESCRIPTION_WARN_CHARS
from app.services.tino_personas import TININ_BASE

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"  # misma familia Tino, mismo modelo que debate_service.py/dona_tina_precios.py
_META = ("anthropic", _MODEL)
_MAX_TOOL_ITERATIONS = 4  # tope duro contra un loop de tool-use que no converge

_CONOCIMIENTO = f"""
CÓMO SE ARMAN LOS TEMPLATES:
- Hay UN SOLO sistema desde 08/2026: el editor visual en /materiales/cenefas/v2. Se arma un template desde cero o importando un PPTX existente, con componentes (texto/imagen/forma) atados a variables. Todos los mundos usan el mismo editor y el mismo motor; antes Redexpres tenía uno aparte y ya no existe.
- El motor respeta el PPTX tal cual se sube: no agranda, no achica y no mueve nada solo. Si un texto no entra, se corrige el dato o el diseño.

LAS VARIABLES (32, mismo nombre en el Excel, en el PPTX y en el editor):
codigo, descripcion, mecanica, tipoOferta, tipoOfertaComprando, unidad, unidadMoneda, precioRegular, precioOferta, promoOferta, ofertaUno, ofertaDos, ofertaTres, ofertaCuatro, precioBanco, banco, vigencia, aclaracionUno, aclaracionDos, aclaracionTres, legales, dia, mes, año, y el decimal de cada precio (decimalPrecioRegular, decimalPrecioOferta, decimalPromoOferta, decimalPrecioUno, decimalPrecioDos, decimalPrecioTres, decimalPrecioCuatro, decimalPrecioBanco).
- tipoOferta es el anuncio de la mecánica ("6x4", "2x", "2da al 50%"). En Redexpres va grande arriba del precio; en Rompe del Finde va en la cocarda roja al costado. Es TEXTO aunque traiga números: se imprime tal cual, no se le separa el decimal. OJO con el combo: ahí va SOLO la cantidad ("2x"), no "2x$299" — el precio lo pone precioOferta al lado (ver LA REGLA DE tipoOferta más abajo).
- tipoOfertaComprando ("Comprando 2") y unidad ("unidad") son SOLO de Rompe del Finde: ahí la mecánica se reparte en tres lugares -- la cocarda con el literal, "Comprando N" arriba del precio y "unidad" abajo. En Redexpres esa misma mecánica va entera adentro de `mecanica` ("$75,33 la unidad.") y las dos nuevas quedan vacías.
- Ninguna es obligatoria: lo que no esté queda vacío.
- Cada precio va partido en entero + decimal, en dos variables. El decimal lleva la coma adelante (",50") y queda vacío si el precio es redondo.
- unidadMoneda ES el símbolo de moneda ("$" o "U$S", desde 2026-08-29): el Convertidor la escribe siempre, leyendo la columna MONEDA de gestión, y el diseño la dibuja al lado de cada precio con <<unidadMoneda>>. Una fila en dólares sale con U$S sola.
- precioRegular es el precio anterior/tachado; precioOferta es el vigente, el que se muestra grande.
- precioOferta ES SIEMPRE UN PRECIO, en todos los mundos: nunca lleva un literal de mecánica adentro. Cuando una cenefa tiene que mostrar "6x4" en el lugar del precio, eso va en promoOferta, que el diseño dibuja SUPERPUESTA encima del cuadro del precio: con mecánica trae el literal y tapa al precio, sin mecánica queda vacía y se ve el precio. Decisión de Ivan del 2026-08-26; el porqué está escrito arriba de todo en variables.py.
- legales solo se sustituye si al generar se tilda "Usar legales" (muchas plantillas ya lo traen impreso). La leyenda de alcohol se SUMA a ese texto cuando la categoría lo pide.

LOS MUNDOS:
Redexpres, Rompe Precios, Parrilla y Vinos y los que el equipo cree desde el selector ("Nuevo mundo"). Un mundo solo agrupa las plantillas de una campaña: NO cambia las columnas del Excel ni el comportamiento. Todos usan las mismas 26 variables.

EL CONVERTIDOR (/materiales/convertidor) — ahí se resuelve la mecánica:
1. Se sube el export crudo de gestión.
2. Pantalla de mapeo: se elige a qué columna del archivo corresponde cada variable cuyo nombre cambia entre exports (tipoOferta, ofertaUno..Cuatro, precioBanco, banco, vigencia, aclaracionUno..Tres, legales, dia, mes, año). El mapeo se puede guardar como plantilla reutilizable. Lo mapeado a mano SIEMPRE gana sobre lo calculado.
3. Grilla: se revisan y corrigen las filas; lo que quedó marcado pide revisión humana.
4. Se descarga el Excel con las 26 columnas, o se aprieta "Convertir a cenefa" para ir directo al generador sin bajar el archivo.
Si el archivo trae VARIAS HOJAS, cada una es un listado aparte y se convierte por separado: el panel las muestra como 1, 2, 3 con su nombre y su cantidad de filas, y cada una lleva su propio mapeo y su propia grilla. La hoja curada a mano (la que trae los SKU combinables unidos con "/" y la mecánica en COMENTARIO) suele ser la que va a imprenta, no el export crudo.

LAS COLUMNAS QUE NO RECONOZCO (yo las mapeo, desde 2026-08-26):
- El Convertidor reconoce por nombre las columnas del export de gestión (CODIGO, NOMBRE DE ARTICULO, OFERTA, OFERTADET...). Las que no reconoce se ignoraban en silencio: si el archivo traía "PVP" o "IMPORTE ANTERIOR", esa columna no existía para el resto del proceso y nadie se enteraba hasta ver la cenefa sin ese dato.
- Ahora en la pantalla de mapeo hay un panel donde yo miro esas columnas --con sus valores de ejemplo-- y digo a qué campo creo que corresponde cada una. No aplico nada solo: propongo, la persona confirma o corrige.
- Los campos a los que puedo atar una columna son 12: codigo, nombreArticulo, descripcionExcel, descripcionWeb, moneda, precioAnterior, precio, oferta, ofertaDet, comprador, fechaInicio, fechaFin.
- Lo que se confirma queda APRENDIDO para siempre: de ahí en adelante esa columna la resuelve el código, sin gastar una llamada a IA nunca más. Conviene contestar hasta las que no sirven ("no es ninguno" también se guarda), porque eso hace que la próxima vez la lista sea corta.
- Ojo: esto mapea COLUMNA -> campo. Es distinto de la pantalla de mapeo de siempre, que va al revés (variable -> columna) y sirve para las variables que el export no trae nunca (vigencia, legales, banco, dia/mes/año).

LOS GRUPOS UNIFICADOS (varios SKU, un solo cartel):
- Cuando dos o más SKU comparten un cartel ("Coca Cola Light o Zero 2.25 L"), se unifican en la grilla y quedan como una sola fila con el código combinado.
- Desde 2026-08-26 el grupo se recuerda por su CONJUNTO de SKU, no por el código combinado. La diferencia importa: guardado como código ("63009 - 211797") solo sirve si mañana viene EXACTAMENTE la misma combinación; guardada la lista, se puede detectar que vinieron 2 de los 3.
- Al armar la grilla busco los grupos guardados que tocan esos SKU y aviso dos cosas distintas:
  * Vino ENTERO: ya escribiste esa descripción una vez, se reusa tal cual con un botón.
  * Vino INCOMPLETO: es el aviso que importa. La descripción guardada menciona un producto que HOY NO ESTÁ EN OFERTA, y un cartel de góndola no puede anunciar algo que no se vende a ese precio. Hay que reescribirla con los que sí vinieron, y por eso ahí NO hay botón de aplicar.
- Las descripciones INDIVIDUALES de cada SKU siguen en el Diccionario (sku_descripciones): son las que permiten rearmar el texto de un grupo parcial.
- El mismo conjunto en otro orden es el mismo grupo: no se duplica.
- Desde 2026-08-27 propongo DOS O TRES redacciones por grupo y la persona elige en un desplegable, en vez de una sola. La razón importa: yo solo veo los productos que están EN OFERTA, no el surtido completo de la góndola, así que "todas las variedades" PUEDE SER MENTIRA. Si hay cuatro modelos de bicicleta R20 y solo dos están en oferta, un cartel que dice "todas las variedades" promete algo que no se cumple. Las opciones van ordenadas de la más segura a la más riesgosa: (1) enumerando lo que realmente vino ("Cappuccino SAINT CAFÉ chocolate, tradicional y vainilla. 6 sobres"), que nunca miente; (2) sin prometer que están todas ("en 3 variedades", "variedades surtidas"), que es la que sirve cuando son demasiadas para enumerar; (3) "todas las variedades", última y solo como opción. El campo sigue siendo editable: el desplegable elige el ángulo, la persona ajusta el texto.
- Ya NO hay tope de SKUs por grupo. Antes la descripción del grupo se guardaba bajo el código combinado de todos sus SKU y esa columna aguantaba 64 caracteres, así que un grupo de 11 productos (unos 130 caracteres) no se podía guardar y salía "este grupo tiene demasiados SKUs". Desde la migración 0049 la columna aguanta 600, o sea unos 60 SKU: en la práctica el tope dejó de existir.
- Después de aprobar, el botón pasa a "Editar" y se puede corregir ahí mismo, sin salir al Diccionario ni volver a cargar el Excel. Vale para las descripciones sueltas y para los grupos. Guardar de nuevo pisa lo anterior y no duplica nada.

LOS ARTÍCULOS DE 100 g (decisión de Ivan, 2026-08-26):
- La fiambrería y los quesos de corte se venden por 100 g: el cartel muestra el precio de los 100 g, NO el del kilo.
- Hay dos errores distintos y la app los avisa por separado. Uno: la descripción todavía dice "Kg" y hay que pasarla a 100 g (aviso `esFiambreKg`, y ahí el modal de IA propone descripción + precio÷10 juntos). El otro: la descripción YA dice "100 g" pero el precio que mandó gestión sigue siendo el del kilo (aviso `precioDeKiloEn100g`).
- El segundo pasó de verdad y se imprimió, en el Rompe del Finde del 27 al 30 de agosto de 2026: Jamón Crudo a 1.100 cuando los 100 g eran 110, Queso Colonia a 590 cuando eran 59, Jamón Cocido Extra a 840 cuando eran 84. Se corrigieron los DOS precios de cada uno (el regular tachado y el de oferta), porque gestión los mandó los dos en kilo.
- No se pide que el comprador sea FIAMBRERIA: el queso de corte puede venir por LACTEOS y tiene el mismo problema.
- La app NO divide sola: marca las filas, propone el valor y una persona confirma con el botón "Pasar los precios a 100 g". Un falso positivo acá imprime un precio diez veces más barato en la góndola, así que la decisión no es automática.
- Hay un tercer caso, desde 2026-08-27: el nombre de gestión NO DICE NINGUNA unidad ("MORCILLA DULCE DON JOAQUIN", "MUZZA NATURALACT", "PANCETA AHUMADA VILLA MARGARITA"). Ahí yo escribía la descripción sin gramaje y el cartel no decía por cuánto se cobra -- correcto de mi parte, porque tengo prohibido inventar datos que no estén en la fuente, pero inútil en góndola. Ahora la plataforma me pasa la unidad de cobro junto con el nombre y la descripción tiene que terminar con ella, escrita "100g" o "Kg": "Muzzarella NATURALACT. 100g", "Morcilla dulce DON JOAQUIN. Kg".
- Quién va con qué: por 100 g van los quesos de corte, la panceta, el jamón, el salame/salamín y todo lo que venga por un comprador de FIAMBRERIA. Por kilo van la morcilla y el chorizo. Frankfurters y panchos no llevan unidad de cobro: van por envase y el peso del envase no se puede adivinar. Si el nombre YA trae su propia cantidad ("Muzzarella CONAPROLE 500 g") manda el nombre: eso es un paquete que se vende por unidad, no producto de corte.
- Esas filas aparecen en el mismo botón de "Generar descripciones y confirmar precios con IA", incluso si ya tenían descripción del catálogo escrita sin gramaje. Las que alguien escribió a mano en la columna Descripción del Excel quedan afuera: esas no se reescriben.

LA REGLA DE tipoOferta (decisión de Ivan, 2026-08-25, corregida el 2026-08-29) — es la que más se pregunta:
tipoOferta se llena SOLO cuando OFERTADET es una mecánica de verdad. Sale de OFERTADET y NUNCA de OFERTA.
DOS REGLAS DE FONDO, que son las que más me equivocaba antes:
  (a) precioOferta ES UN PRECIO, SIEMPRE. Nunca lleva un literal ni un texto.
  (b) el literal que TAPA el cuadro del precio es promoOferta, y se usa SOLO en M x N.
- Combo ("2x$299") -> tipoOferta "2x" (SOLO la cantidad, NO el literal entero), ofertaUno "2x", precioOferta el TOTAL (299), promoOferta VACÍA, mecanica "Comprando 2, $149,50 la unidad.", tipoOfertaComprando "Comprando 2", unidad "unidad". El unitario sale de DIVIDIR el total, no de la columna PRECIO. El cartel se lee juntando la cocarda y el precio: "2x $299". Si a tipoOferta le mandás "2x$299" entero, el precio queda escrito dos veces, uno al lado del otro.
- M x N ("6x4", "2x1") -> tipoOferta el literal ("2x1"), promoOferta el MISMO literal (es lo que tapa el cuadro del precio), precioOferta el número de la columna PRECIO (49,50), ofertaUno VACÍA, mecanica "$49,50 la unidad." Acá no hay un precio de oferta que anunciar —por eso el literal ocupa el cuadro— pero precioOferta igual lleva el unitario, que es un número.
- N unidad al XX% ("2da unidad al 50%") -> tipoOferta "2da al 50%", precioOferta el de la columna PRECIO, promoOferta VACÍA, mecanica "2da unidad al 50%."
- Precio fijo, % descuento, % Descuentos y CUALQUIER OTRA COSA -> tipoOferta VACÍA y mecanica "Precio Final". No hay nada que anunciar, así que no hay cocarda: da igual lo que diga OFERTA ("Precio Oferta", "sin detalle", "20%OFF", "-0.26" son todos jerga interna o un ratio, no un anuncio).
- Si OFERTADET es un tipo que el motor no conoce, la fila queda con el aviso `ofertadet_desconocido` y pierde la mecánica ENTERA: sin cocarda, sin "Comprando N", sin unidad. Desde 2026-08-26 eso lo resuelvo yo: en la grilla, adentro del aviso, miro ese OFERTADET junto con lo que trae la columna OFERTA en esas filas y propongo a qué familia corresponde (combo, mxn, segunda o sin_mecanica). Se pregunta por TIPO y no por fila: cuarenta filas con el mismo OFERTADET nuevo son UNA pregunta. La persona confirma o corrige, y lo confirmado queda APRENDIDO: de ahí en adelante ese OFERTADET lo resuelve el código, igual que los hardcodeados, y no vuelve a pasar por mí nunca. Confirmar rehace la grilla, porque la mecánica la resuelve el backend. "sin_mecanica" es una respuesta tan válida como las otras: quiere decir "esto no anuncia nada", y guardarla es lo que hace que el aviso deje de aparecer. Ante la duda va esa, porque elegir mal una de las otras tres no deja el cartel vacío: lo deja MINTIENDO. Un "2x1" resuelto como combo imprime un precio unitario que no existe.
Gestión escribe OFERTA de dos formas ("2x$299" pelado, o "Coca Cola Zero 2.25 L 2x$299" con el nombre adelante). Las dos funcionan: el literal se busca dentro del texto y a la cocarda va limpio.

DOS COSAS MÁS SOBRE LA COLUMNA OFERTA (desde 2026-08-27):
- tipoOferta YA NO SE PIDE en la pantalla de mapeo cuando el archivo trae una columna OFERTA. El Convertidor la reconoce por nombre y de ahí saca el literal (leído junto con OFERTADET), así que no hay nada que mapear. Y mapearla igual era contraproducente: lo mapeado a mano GANA sobre lo calculado, así que a la cocarda iba el texto CRUDO de OFERTA ("Coca Cola Zero 2.25 L 2x$299") en vez del literal limpio. Si el archivo NO trae columna OFERTA, tipoOferta sí aparece para mapearla a otra columna, o se deja vacía.
- Cuando la columna OFERTA trae PRECIOS en vez de titulares, la pantalla de mapeo avisa antes de convertir, con los valores que lo delatan. Pasa cuando alguien edita el Excel a mano: sin el aviso el Convertidor la seguía leyendo como titular, la mecánica quedaba con `combo_no_parseable` y el precio que estaba ahí al lado no lo usaba nadie. El aviso ofrece leerla como el precio de oferta, ignorarla, o mandarla a otro campo -- y "dejala como está" también es una respuesta. La app NO lo cambia sola: cuál es el precio de oferta cuando hay una columna PRECIO y además una OFERTA con números es una pregunta de negocio. Esa decisión vale SOLO para esa corrida y no se aprende, porque es un accidente de ese archivo y no una convención de nombres (los nombres de columna nuevos sí se aprenden, eso es otra cosa).

CÓMO SE GENERA UNA CENEFA (siempre así, nunca instantáneo):
1. En /materiales/cenefas se elige el mundo, la plantilla y se sube el Excel.
2. Preview: el sistema valida y muestra cuántos productos matcheó y qué variables faltan.
3. Confirmar: recién ahí se renderiza el PPTX final para descargar.
Esto SIEMPRE requiere un Excel real subido por el usuario — vos (Tinín) no podés generar una cenefa desde el chat, ni inventar un Excel. Si te piden "generame una cenefa", explicá el paso a paso de arriba y decí que tienen que subir el Excel ellos — nunca digas que la vas a generar vos ni que ya la generaste.

Si la descripción de un producto viene mal escrita del sistema de gestión, recomendá primero el Convertidor — matchea por SKU contra el catálogo compartido y deja lo que falta en rojo para completar a mano o con IA.
"""

_SYSTEM_PROMPT = f"{TININ_BASE}\n\n{_CONOCIMIENTO}"

_TOOLS = [
    {
        "name": "actualizar_descripcion_sku",
        "description": (
            "Agrega o corrige la descripción de un SKU en el catálogo compartido de cenefas. "
            "Usar únicamente cuando el usuario pida explícitamente guardar/corregir una "
            "descripción, pasando el código y el texto nuevo — nunca de forma preventiva."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sku": {
                    "type": "string",
                    "description": "Código de producto, tal cual aparece en el sistema de gestión",
                },
                "descripcion": {
                    "type": "string",
                    "description": (
                        f"Descripción corta para el cartel. Apuntá a menos de {DESCRIPTION_WARN_CHARS} "
                        f"caracteres, nunca más de {DESCRIPTION_MAX_CHARS}."
                    ),
                },
            },
            "required": ["sku", "descripcion"],
        },
    },
]

# Los mundos de cenefas se crean desde la UI (ver cenefa_destinos), así que
# no se pueden enumerar acá. Solo el Convertidor tiene una línea propia; para
# cualquier destino se arma con su slug (ver _contexto_line).
_CONTEXTOS = {
    "convertidor": "El usuario está en el Convertidor de Excel.",
}


def _contexto_line(contexto: str | None) -> str:
    if not contexto:
        return ""
    if contexto in _CONTEXTOS:
        return _CONTEXTOS[contexto]
    legible = contexto.replace("_", " ")
    return f"El usuario está generando cenefas del mundo {legible}."


# Cuantas filas de la grilla se le pasan. Es un tope de costo y de ruido: con
# mas de esto el modelo se pierde y la consulta se encarece sin mejorar la
# respuesta. Se mandan primero las que tienen algo marcado, que son de las que
# se pregunta.
_MAX_FILAS_CONTEXTO = 40

# Solo estas columnas. El resto no ayuda a explicar por que una fila esta
# marcada y solo agrega tokens.
_CAMPOS_FILA = (
    "codigo", "descripcion", "mecanica", "tipoOferta",
    "precioRegular", "precioOferta",
    "ofertaOrigen", "ofertaDet", "moneda", "nombreArticulo",
)


def _bloque_filas(filas: list[dict] | None) -> str:
    """Las filas de la grilla que la persona tiene delante, como texto.

    Sin esto Tinin contesta a ciegas: ante "por que el SKU 608094 esta en
    morado" solo puede tirar hipotesis, porque no ve ni la fila ni sus avisos.
    Con las filas puede hacer lo unico que resuelve esa pregunta: comparar la
    marcada contra una que no lo esta.
    """
    if not filas:
        return ""
    # Primero las marcadas: son de las que se pregunta.
    ordenadas = sorted(filas, key=lambda f: 0 if (f.get("warnings") or []) else 1)
    recorte = ordenadas[:_MAX_FILAS_CONTEXTO]

    lineas = [
        "Estas son las filas que el usuario tiene en pantalla ahora mismo. "
        "Cuando pregunte por una, mirala aca y compara contra otra que no este "
        "marcada, en vez de suponer:",
    ]
    for f in recorte:
        partes = [f'{c}={str(f.get(c) or "")!r}' for c in _CAMPOS_FILA if str(f.get(c) or "").strip()]
        avisos = f.get("warnings") or []
        marca = f'  MARCADA: {", ".join(avisos)}' if avisos else "  (sin marcar)"
        lineas.append("  - " + " ".join(partes) + marca)
    if len(filas) > len(recorte):
        lineas.append(f"  ... y {len(filas) - len(recorte)} filas mas que no se incluyeron.")
    return "\n".join(lineas)


async def _ejecutar_tool(db, user_id: int, name: str, tool_input: dict) -> tuple[str, bool]:
    """Devuelve (texto_resultado, is_error) — nunca levanta, el error se le
    devuelve a Claude como tool_result para que pueda reaccionar (pedir el
    dato de nuevo, avisar al usuario, etc.)."""
    if name != "actualizar_descripcion_sku":
        return f"Herramienta desconocida: {name}", True
    try:
        sku_norm = await upsert_sku_descripcion(
            db, tool_input.get("sku", ""), tool_input.get("descripcion", ""), user_id
        )
        descripcion_guardada = tool_input.get("descripcion", "").strip()[:300]
        return f'Guardado: SKU {sku_norm} -> "{descripcion_guardada}"', False
    except ValueError as e:
        return str(e), True


async def consultar(
    mensaje: str, historial: list[dict], contexto: str | None, db, user_id: int,
    filas: list[dict] | None = None,
) -> dict:
    """historial: turnos previos como [{"role": "user"|"assistant", "content": str}]
    — solo texto plano, sin bloques de tool-use de turnos anteriores (el
    frontend solo guarda la respuesta final de cada turno, no el intercambio
    interno de tools). Devuelve {"respuesta": str, "usage_items": [...]}.

    No commitea — el caller es dueño de la transacción (igual que
    generar_descripciones en convertidor_ai.py), así se persiste en un solo
    commit tanto el ai_usage_log acumulado como cualquier descripción que la
    tool haya guardado en el camino."""
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY no configurado")

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    messages: list[dict] = [{"role": m["role"], "content": m["content"]} for m in historial]
    partes = [x for x in (_contexto_line(contexto), _bloque_filas(filas)) if x]
    user_content = "\n\n".join([*partes, mensaje]) if partes else mensaje
    messages.append({"role": "user", "content": user_content})

    # Lo que el equipo ya aprendió y una persona aprobó. Va en el system para
    # que valga en todos los turnos, no solo en el primero. Sin nada aprobado
    # queda vacío y el agente funciona igual que antes; si falla, se ignora:
    # el conocimiento suma contexto, nunca puede voltear el chat.
    sistema = _SYSTEM_PROMPT
    try:
        from app.services.cenefas.conocimiento import contexto_para_el_agente
        aprendido = await contexto_para_el_agente(db)
        if aprendido:
            sistema = f"{_SYSTEM_PROMPT}\n\n{aprendido}"
    except Exception:
        logger.warning("no se pudo cargar el conocimiento aprobado", exc_info=True)

    usage_items: list[dict] = []

    for _ in range(_MAX_TOOL_ITERATIONS):
        response = await client.messages.create(
            model=_MODEL,
            max_tokens=1000,
            system=sistema,
            tools=_TOOLS,
            messages=messages,
        )
        usage_items.append({
            "provider": _META[0], "model": _META[1],
            "input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens,
        })
        await log_ai_usage(
            db, user_id, "tinin_cenefas", _META[0], _META[1],
            response.usage.input_tokens, response.usage.output_tokens,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            texto = next((b.text for b in response.content if b.type == "text"), "")
            return {"respuesta": texto, "usage_items": usage_items}

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            resultado, is_error = await _ejecutar_tool(db, user_id, block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": resultado,
                "is_error": is_error,
            })
        messages.append({"role": "user", "content": tool_results})

    logger.warning("tinin_agent.consultar: se alcanzó el tope de %d iteraciones de tool-use", _MAX_TOOL_ITERATIONS)
    return {
        "respuesta": "Se me complicó terminar de procesar tu pedido — probá de nuevo con un mensaje más puntual.",
        "usage_items": usage_items,
    }

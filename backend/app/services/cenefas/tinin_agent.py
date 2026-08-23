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

LAS VARIABLES (26, mismo nombre en el Excel, en el PPTX y en el editor):
codigo, descripcion, mecanica, precioRegular, precioOferta, ofertaUno, ofertaDos, ofertaTres, ofertaCuatro, precioBanco, banco, vigencia, aclaracionUno, aclaracionDos, aclaracionTres, legales, dia, mes, año, y el decimal de cada precio (decimalPrecioRegular, decimalPrecioOferta, decimalPrecioUno, decimalPrecioDos, decimalPrecioTres, decimalPrecioCuatro, decimalPrecioBanco).
- Ninguna es obligatoria: lo que no esté queda vacío.
- Cada precio va partido en entero + decimal, en dos variables. El decimal lleva la coma adelante (",50") y queda vacío si el precio es redondo.
- El símbolo de moneda NO es una variable: va como texto fijo en el diseño.
- precioRegular es el precio anterior/tachado; precioOferta es el vigente, el que se muestra grande.
- legales solo se sustituye si al generar se tilda "Usar legales" (muchas plantillas ya lo traen impreso). La leyenda de alcohol se SUMA a ese texto cuando la categoría lo pide.

LOS MUNDOS:
Redexpres, Rompe Precios, Parrilla y Vinos y los que el equipo cree desde el selector ("Nuevo mundo"). Un mundo solo agrupa las plantillas de una campaña: NO cambia las columnas del Excel ni el comportamiento. Todos usan las mismas 26 variables.

EL CONVERTIDOR (/materiales/convertidor) — ahí se resuelve la mecánica:
1. Se sube el export crudo de gestión.
2. Pantalla de mapeo: se elige a qué columna del archivo corresponde cada variable cuyo nombre cambia entre exports (ofertaUno..Cuatro, vigencia, aclaracionUno..Tres, legales). El mapeo se puede guardar como plantilla reutilizable.
3. Grilla: se revisan y corrigen las filas; lo que quedó marcado pide revisión humana.
4. Se descarga el Excel con las 26 columnas, o se aprieta "Convertir a cenefa" para ir directo al generador sin bajar el archivo.
El Convertidor arma la mecánica a partir de OFERTADET/OFERTA: Combo "3x99" -> ofertaUno "3x", precioOferta 99, mecanica "Comprando 3, $33 la unidad."; M x N "2x1" -> precioOferta toma el literal "2x1" y mecanica arma el unitario con la columna PRECIO; Precio fijo o % descuento -> mecanica "Precio Final".

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


async def consultar(mensaje: str, historial: list[dict], contexto: str | None, db, user_id: int) -> dict:
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
    contexto_line = _contexto_line(contexto)
    user_content = f"{contexto_line}\n\n{mensaje}" if contexto_line else mensaje
    messages.append({"role": "user", "content": user_content})

    usage_items: list[dict] = []

    for _ in range(_MAX_TOOL_ITERATIONS):
        response = await client.messages.create(
            model=_MODEL,
            max_tokens=1000,
            system=_SYSTEM_PROMPT,
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

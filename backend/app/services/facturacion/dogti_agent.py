"""Chat de DogTi -- responde preguntas sobre el presupuesto y los canjes, y
puede consultar datos reales con tools de solo lectura (consultar_dashboard,
buscar_movimientos, buscar_canjes) cuando el resumen fijo que ya tiene en el
contexto no alcanza para responder algo puntual (ej. "cuánto gastamos con
[proveedor] este año").

Mismo patrón de loop de tool-use que tinin_agent.py -- a diferencia de
Tinín, ninguna de las tools de acá escribe nada: crear un movimiento o canje
sigue siendo exclusivo del flujo subir->revisar->confirmar (ver
documentos.py), nunca por chat. Si algún día DogTi necesita una acción real
de escritura desde el chat, sumar esa tool acá es un cambio acotado a este
archivo -- pero hoy es una decisión deliberada, no una limitación técnica."""
import json

import anthropic

from app.core.config import settings
from app.services.ai_usage_service import log_ai_usage
from app.services.facturacion import documentos as documentos_service
from app.services.tino_personas import DOGTI_BASE

_MODEL = settings.MODELO_IA  # el de toda la familia -- ver MODELO_IA en config.py
_META = ("anthropic", _MODEL)
_MAX_TOOL_ITERATIONS = 4  # tope duro contra un loop de tool-use que no converge

_CONOCIMIENTO = """
Facturación tiene una o más cuentas de presupuesto (ver la lista de cuentas
si hace falta distinguirlas). Los movimientos (entradas/salidas) y los
canjes con marcas/proveedores nacen de facturas en PDF: la persona las sube
desde el botón "Subir factura" del dashboard, vos (DogTi) proponés los
datos leyendo el PDF, y recién se guardan cuando la persona revisa y
confirma lo que propusiste. Nunca generás ni confirmás un movimiento o
canje por chat -- si te piden crear uno, explicá que tienen que subir la
factura correspondiente desde esa pantalla.

Ya tenés en este mensaje un resumen del estado actual (saldo, totales de
canjes). Para preguntas más específicas -- un proveedor puntual, un período,
una cuenta distinta a la que ya tenés, el detalle de los canjes -- usá las
tools disponibles en vez de inventar un número o decir que no sabés.
""".strip()

_SYSTEM_PROMPT = f"{DOGTI_BASE}\n\n{_CONOCIMIENTO}"

_TOOLS = [
    {
        "name": "consultar_dashboard",
        "description": (
            "Trae los totales actuales de presupuesto (entradas, salidas, saldo) y canjes "
            "(valor total, por estado) de una cuenta específica. Usala cuando te pregunten por "
            "una cuenta distinta a la que ya tenés resumida en el contexto."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cuenta_id": {"type": "integer", "description": "ID de la cuenta a consultar"},
            },
        },
    },
    {
        "name": "buscar_movimientos",
        "description": (
            "Busca movimientos (entradas/salidas) del ledger de presupuesto con filtros, y "
            "devuelve el monto total que matchea (sobre TODOS los que matchean, no solo los que "
            "se listan). Usala para preguntas sobre un proveedor, un período o un tipo concreto."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "proveedor": {"type": "string", "description": "Nombre o parte del nombre del proveedor/marca"},
                "desde": {"type": "string", "description": "Fecha desde, formato YYYY-MM-DD"},
                "hasta": {"type": "string", "description": "Fecha hasta, formato YYYY-MM-DD"},
                "tipo": {"type": "string", "enum": ["entrada", "salida"]},
                "cuenta_id": {"type": "integer"},
            },
        },
    },
    {
        "name": "buscar_canjes",
        "description": "Busca canjes con marcas/proveedores, con filtros por estado o cuenta.",
        "input_schema": {
            "type": "object",
            "properties": {
                "estado": {"type": "string", "enum": ["pendiente", "activo", "cerrado"]},
                "cuenta_id": {"type": "integer"},
            },
        },
    },
]


async def _ejecutar_tool(db, name: str, tool_input: dict) -> str:
    """Todas las tools de acá son de solo lectura -- nunca levantan, un error
    de datos (ej. cuenta_id inexistente) se le devuelve a Claude como
    resultado para que pueda reaccionar, no rompe el turno."""
    if name == "consultar_dashboard":
        cuenta_id = tool_input.get("cuenta_id")
        resumen = await documentos_service.obtener_dashboard(
            db, limit=1, offset=0, presupuesto_cuenta_id=cuenta_id, canjes_cuenta_id=cuenta_id,
        )
        return json.dumps(resumen, ensure_ascii=False, default=str)
    if name == "buscar_movimientos":
        resultado = await documentos_service.buscar_movimientos_filtrados(
            db,
            proveedor=tool_input.get("proveedor"),
            desde=tool_input.get("desde"),
            hasta=tool_input.get("hasta"),
            tipo=tool_input.get("tipo"),
            cuenta_id=tool_input.get("cuenta_id"),
        )
        return json.dumps(resultado, ensure_ascii=False, default=str)
    if name == "buscar_canjes":
        resultado = await documentos_service.buscar_canjes_filtrados(
            db, estado=tool_input.get("estado"), cuenta_id=tool_input.get("cuenta_id"),
        )
        return json.dumps(resultado, ensure_ascii=False, default=str)
    return json.dumps({"error": f"Herramienta desconocida: {name}"})


def _resumen_dashboard(resumen: dict | None) -> str:
    """Convierte el resumen que ya calcula obtener_dashboard() en un bloque
    de contexto compacto -- se le da siempre de arranque para no gastar una
    vuelta de tool-use en lo más común (¿cómo vamos de saldo?); las tools
    quedan para profundizar más allá de esto."""
    if not resumen:
        return ""
    presupuesto = resumen.get("presupuesto", {})
    canjes = resumen.get("canjes", {})
    return (
        "\n\nESTADO ACTUAL DEL PRESUPUESTO (usalo para responder con números reales):\n"
        f"- Entradas totales: {presupuesto.get('entradas_total', 0)}\n"
        f"- Salidas totales: {presupuesto.get('salidas_total', 0)}\n"
        f"- Saldo: {presupuesto.get('saldo', 0)}\n"
        f"- Canjes, valor total: {canjes.get('total_valor', 0)}\n"
        f"- Canjes por estado: {canjes.get('por_estado', {})}\n"
    )


async def consultar(
    mensaje: str,
    historial: list[dict],
    contexto: str | None,
    db,
    user_id: int,
    resumen_dashboard: dict | None = None,
) -> dict:
    """Mismo contrato que tinin_agent.consultar (mensaje, historial,
    contexto, db, user_id) -> {"respuesta": str, "usage_items": [...]} para
    que DogTiFloating.tsx sea un espejo estructural de TininFloating.tsx.
    historial: turnos previos como [{"role": "user"|"assistant", "content": str}].
    No commitea -- el caller es dueño de la transacción."""
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY no configurado")

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    system = _SYSTEM_PROMPT + _resumen_dashboard(resumen_dashboard)
    messages: list[dict] = [{"role": m["role"], "content": m["content"]} for m in historial]
    messages.append({"role": "user", "content": mensaje})

    usage_items: list[dict] = []

    for _ in range(_MAX_TOOL_ITERATIONS):
        response = await client.messages.create(
            model=_MODEL, max_tokens=800, system=system, tools=_TOOLS, messages=messages,
        )
        usage_items.append({
            "provider": _META[0], "model": _META[1],
            "input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens,
        })
        await log_ai_usage(
            db, user_id, "facturacion_dogti", _META[0], _META[1],
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
            resultado = await _ejecutar_tool(db, block.name, block.input)
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": resultado})
        messages.append({"role": "user", "content": tool_results})

    return {
        "respuesta": "Se me complicó terminar de procesar tu consulta — probá con un mensaje más puntual.",
        "usage_items": usage_items,
    }

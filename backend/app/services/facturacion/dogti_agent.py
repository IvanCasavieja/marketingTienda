"""Chat de DogTi -- responde preguntas sobre el presupuesto y los canjes.

Sin loop de tool-use a propósito, a diferencia de tinin_agent.py: DogTi no
tiene ninguna acción de escritura confirmada en este alcance -- crear un
movimiento o canje solo pasa por el flujo subir->revisar->confirmar (ver
documentos.py), nunca por chat. Si más adelante necesita una acción real
desde acá, pasar al patrón de tinin_agent.py es un cambio acotado a este
archivo."""
import anthropic

from app.core.config import settings
from app.core.llm_retry import llm_call_with_retry
from app.services.ai_usage_service import log_ai_usage
from app.services.tino_personas import DOGTI_BASE

_MODEL = "claude-sonnet-4-6"  # misma familia Tino, mismo modelo que tinin_agent.py/extraccion.py
_META = ("anthropic", _MODEL)

_CONOCIMIENTO = """
Facturación tiene una sola cuenta de presupuesto para toda la empresa (por
ahora, no separada por cliente/campaña). Los movimientos (entradas/salidas)
y los canjes con marcas/proveedores nacen de facturas en PDF: la persona las
sube desde el botón "Subir factura" del dashboard, vos (DogTi) proponés los
datos leyendo el PDF, y recién se guardan cuando la persona revisa y
confirma lo que propusiste. Nunca generás ni confirmás un movimiento o
canje por chat -- si te piden crear uno, explicá que tienen que subir la
factura correspondiente desde esa pantalla.
"""

_SYSTEM_PROMPT = f"{DOGTI_BASE}\n\n{_CONOCIMIENTO}"


def _resumen_dashboard(resumen: dict | None) -> str:
    """Convierte el resumen que ya calcula obtener_dashboard() en un bloque
    de contexto compacto -- DogTi nunca consulta la base directamente."""
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

    response = await llm_call_with_retry(
        lambda: client.messages.create(model=_MODEL, max_tokens=800, system=system, messages=messages),
        label="dogti_agent.consultar",
    )
    await log_ai_usage(
        db, user_id, "facturacion_dogti", _META[0], _META[1],
        response.usage.input_tokens, response.usage.output_tokens,
    )
    texto = next((b.text for b in response.content if b.type == "text"), "")
    return {
        "respuesta": texto,
        "usage_items": [{
            "provider": _META[0], "model": _META[1],
            "input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens,
        }],
    }

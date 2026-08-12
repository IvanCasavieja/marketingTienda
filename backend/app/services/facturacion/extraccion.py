"""DogTi lee una factura PDF y extrae sus datos. Primer uso de bloques
`document` de Claude en este repo -- no había precedente de mandarle un PDF
directo al modelo. Se fuerza tool_choice a una sola tool para que la
respuesta sea siempre el JSON estructurado que espera el flujo de revisión
(ver facturacion/documentos.py), en vez de parsear texto libre."""
import base64

import anthropic

from app.core.config import settings
from app.services.ai_usage_service import log_ai_usage
from app.services.tino_personas import DOGTI_BASE

_MODEL = "claude-sonnet-4-6"  # misma familia Tino, mismo modelo que tinin_agent.py/debate_service.py
_META = ("anthropic", _MODEL)

_INSTRUCCION_EXTRACCION = """
Te paso una factura de un proveedor/marca en PDF. Extraé sus datos con la
tool registrar_extraccion_factura.

- tipo_sugerido: "canje" solo si el documento menciona explícitamente un
  trueque/canje/permuta (ej. "nota de canje", "canje publicitario", pago en
  especie). Si es una factura de compra/venta normal, es "movimiento".
- monto: el importe total de la factura, en número (sin separador de miles,
  punto como separador decimal).
- moneda: el símbolo tal cual aparece ("$", "UYU", "U$S", "USD", etc.) — si
  no lo encontrás, poné "UYU".
- fecha: la fecha de emisión de la factura, en formato YYYY-MM-DD.
- cuenta_sugerida: a cuál de las cuentas de la empresa pertenece esta
  factura (lista de opciones en la tool) — buscá cualquier señal en el
  documento que la identifique (razón social/RUT, local, código de compra,
  membrete, etc.). Si no hay ninguna señal clara, NO la completes — mejor
  dejarla sin definir que adivinar mal.
- confianza: "alta" si todos los campos clave (proveedor, monto, fecha)
  están claros y sin ambigüedad en el documento; "media" si tuviste que
  inferir alguno; "baja" si el PDF viene borroso, incompleto, o no parece
  una factura.
- notas: cualquier cosa que la persona que revise esto debería confirmar a
  mano (campo dudoso, texto ilegible, más de un monto posible, cuenta
  incierta, etc.) — dejalo vacío si no hay nada que aclarar.
- vigencia_desde/vigencia_hasta: completalos solo si el documento es un
  canje con un período de vigencia explícito.
""".strip()

_PROPERTIES_BASE = {
    "tipo_sugerido": {"type": "string", "enum": ["movimiento", "canje"]},
    "proveedor_marca": {"type": "string", "description": "Nombre del proveedor/marca que emite la factura"},
    "concepto": {"type": "string", "description": "Breve descripción de qué es la factura"},
    "monto": {"type": "number"},
    "moneda": {"type": "string"},
    "fecha": {"type": "string", "description": "YYYY-MM-DD"},
    "numero_factura": {"type": "string"},
    "vigencia_desde": {"type": "string", "description": "YYYY-MM-DD, solo si es un canje con vigencia"},
    "vigencia_hasta": {"type": "string", "description": "YYYY-MM-DD, solo si es un canje con vigencia"},
    "confianza": {"type": "string", "enum": ["alta", "media", "baja"]},
    "notas": {"type": "string"},
}
_REQUIRED_BASE = ["tipo_sugerido", "proveedor_marca", "concepto", "monto", "moneda", "fecha", "confianza"]


def _construir_tools(cuentas_activas: list[str]) -> list[dict]:
    """cuenta_sugerida como enum de las cuentas activas -- si no hay ninguna
    cuenta creada todavía, se omite el campo entero (un enum vacío no es
    válido). Nunca va en `required`: DogTi debe poder dejarla sin definir
    si no encuentra ninguna señal en el documento (ver instrucción)."""
    properties = dict(_PROPERTIES_BASE)
    if cuentas_activas:
        properties["cuenta_sugerida"] = {
            "type": "string",
            "enum": cuentas_activas,
            "description": "A cuál cuenta pertenece esta factura, solo si hay una señal clara en el documento.",
        }
    return [{
        "name": "registrar_extraccion_factura",
        "description": "Registra los datos extraídos de una factura de proveedor/marca en PDF.",
        "input_schema": {"type": "object", "properties": properties, "required": _REQUIRED_BASE},
    }]


async def extraer_factura_raw(pdf_bytes: bytes, cuentas_activas: list[str]) -> tuple[dict, int, int]:
    """La llamada a Claude en sí, sin tocar la base -- así el caller puede
    correr varias extracciones en paralelo (asyncio.gather, ver
    documentos.py::crear_documentos_y_extraer) sin compartir una AsyncSession
    entre corutinas concurrentes, algo que SQLAlchemy no soporta. Devuelve
    (campos_extraidos, input_tokens, output_tokens) -- el caller decide
    cuándo/cómo loguear el uso (ver registrar_uso_extraccion)."""
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY no configurado")

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    b64 = base64.standard_b64encode(pdf_bytes).decode()

    response = await client.messages.create(
        model=_MODEL,
        max_tokens=1500,
        system=f"{DOGTI_BASE}\n\n{_INSTRUCCION_EXTRACCION}",
        tools=_construir_tools(cuentas_activas),
        tool_choice={"type": "tool", "name": "registrar_extraccion_factura"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
                {"type": "text", "text": "Extraé los datos de esta factura."},
            ],
        }],
    )

    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_block is None:
        raise RuntimeError("DogTi no pudo leer el PDF")
    return tool_block.input, response.usage.input_tokens, response.usage.output_tokens


async def registrar_uso_extraccion(db, user_id: int, input_tokens: int, output_tokens: int) -> None:
    await log_ai_usage(db, user_id, "facturacion_extraccion", _META[0], _META[1], input_tokens, output_tokens)

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
- confianza: "alta" si todos los campos clave (proveedor, monto, fecha)
  están claros y sin ambigüedad en el documento; "media" si tuviste que
  inferir alguno; "baja" si el PDF viene borroso, incompleto, o no parece
  una factura.
- notas: cualquier cosa que la persona que revise esto debería confirmar a
  mano (campo dudoso, texto ilegible, más de un monto posible, etc.) — dejalo
  vacío si no hay nada que aclarar.
- vigencia_desde/vigencia_hasta: completalos solo si el documento es un
  canje con un período de vigencia explícito.
""".strip()

_TOOLS = [
    {
        "name": "registrar_extraccion_factura",
        "description": "Registra los datos extraídos de una factura de proveedor/marca en PDF.",
        "input_schema": {
            "type": "object",
            "properties": {
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
            },
            "required": ["tipo_sugerido", "proveedor_marca", "concepto", "monto", "moneda", "fecha", "confianza"],
        },
    },
]


async def extraer_factura(pdf_bytes: bytes, db, user_id: int) -> dict:
    """Devuelve el dict de campos que armó DogTi (tal cual el input de la
    tool). No commitea -- el caller (facturacion/documentos.py) es dueño de
    la transacción, igual que el resto de la familia Tino."""
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY no configurado")

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    b64 = base64.standard_b64encode(pdf_bytes).decode()

    response = await client.messages.create(
        model=_MODEL,
        max_tokens=1500,
        system=f"{DOGTI_BASE}\n\n{_INSTRUCCION_EXTRACCION}",
        tools=_TOOLS,
        tool_choice={"type": "tool", "name": "registrar_extraccion_factura"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
                {"type": "text", "text": "Extraé los datos de esta factura."},
            ],
        }],
    )
    await log_ai_usage(
        db, user_id, "facturacion_extraccion", _META[0], _META[1],
        response.usage.input_tokens, response.usage.output_tokens,
    )

    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_block is None:
        raise RuntimeError("DogTi no pudo leer el PDF")
    return tool_block.input

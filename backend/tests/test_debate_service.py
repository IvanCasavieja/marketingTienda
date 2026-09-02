"""Regresión: _ask_claude no debe romperse cuando Claude devuelve un
ThinkingBlock antes del texto (visto en producción: 'AttributeError:
'ThinkingBlock' object has no attribute 'text'' al usar el Convertidor de
Excel, que llama a esta función sin pedir `thinking` explícitamente -- la
familia 5 puede devolverlo igual)."""
import asyncio
from unittest.mock import MagicMock, patch

from app.services import debate_service


class _FakeBlock:
    def __init__(self, block_type: str, text: str | None = None, thinking: str | None = None):
        self.type = block_type
        if text is not None:
            self.text = text
        if thinking is not None:
            self.thinking = thinking


class _FakeUsage:
    input_tokens = 10
    output_tokens = 5


def _fake_response(content):
    resp = MagicMock()
    resp.content = content
    resp.usage = _FakeUsage()
    return resp


def test_ask_claude_ignora_thinking_block_adelante():
    respuesta = _fake_response([
        _FakeBlock("thinking", thinking="razonando..."),
        _FakeBlock("text", text="resultado final"),
    ])
    with patch.object(debate_service.anthropic, "Anthropic") as MockClient, \
         patch.object(debate_service.settings, "ANTHROPIC_API_KEY", "dummy"):
        MockClient.return_value.messages.create.return_value = respuesta
        texto, in_tok, out_tok = asyncio.run(debate_service._ask_claude("system", "prompt"))
    assert texto == "resultado final"
    assert (in_tok, out_tok) == (10, 5)


def test_ask_claude_solo_texto_sigue_funcionando():
    respuesta = _fake_response([_FakeBlock("text", text="respuesta directa")])
    with patch.object(debate_service.anthropic, "Anthropic") as MockClient, \
         patch.object(debate_service.settings, "ANTHROPIC_API_KEY", "dummy"):
        MockClient.return_value.messages.create.return_value = respuesta
        texto, _, _ = asyncio.run(debate_service._ask_claude("system", "prompt"))
    assert texto == "respuesta directa"

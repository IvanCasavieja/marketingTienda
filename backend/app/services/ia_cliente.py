"""El cliente de Anthropic que usan Don Tino y el ordenador de briefs.

Está en un solo lugar por una razón concreta: las pruebas (y el servidor de
prueba de `scripts/servidor_ia_simulada.py`) lo cambian por uno que contesta
respuestas grabadas, con la forma real de la API, sin salir a internet ni
gastar. Si cada ruta armara su propio `AsyncAnthropic`, habría que cambiarlo
en cada una y alguna se escaparía a la API de verdad.

En producción no hay nada que prender ni apagar acá: esta función siempre
devuelve el cliente real. El reemplazo lo hace solo quien la pisa desde afuera
(un test o ese script), nunca una variable de entorno.
"""
from __future__ import annotations

import anthropic

from app.core.config import settings


def cliente_anthropic() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

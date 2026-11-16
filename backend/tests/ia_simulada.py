"""La API de Anthropic, simulada: para probar sin clave, sin red y sin gastar.

Contesta con la forma real de la API (POST /v1/messages devuelve un Message en
JSON, con `content`, `stop_reason` y `usage`) a través de un transporte de
httpx. El SDK de verdad arma el pedido, lo "manda" y parsea la respuesta, así
que se prueba todo el camino menos el modelo mismo: lo que contesta acá está
grabado o armado con reglas simples, no es lo que diría Claude.

Dos usos:

- `ApiGrabada`: las pruebas le cargan las respuestas en orden y después miran
  qué pedidos le llegaron (modelo, herramientas, salida estructurada...).
- `SimuladorDeDonTino`: para levantar el servidor de prueba
  (scripts/servidor_ia_simulada.py) y ver las pantallas andando. Elige
  herramientas por palabras clave y arma la respuesta con lo que ellas
  devolvieron de la base de verdad. Sirve para probar permisos, links y
  pantallas; NO dice nada de la calidad de las respuestas del modelo real.

No es un test (no empieza con test_): pytest no lo junta solo.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Callable

import anthropic
import httpx

MODELO = "claude-sonnet-5"


# ---------------------------------------------------------------------------
# La forma de la API
# ---------------------------------------------------------------------------

def texto(t: str) -> dict:
    return {"type": "text", "text": t}


def herramienta(nombre: str, entrada: dict) -> dict:
    return {"type": "tool_use", "id": f"toolu_{uuid.uuid4().hex[:24]}", "name": nombre, "input": entrada}


def pensamiento() -> dict:
    # Con la familia 5 el razonamiento viene "omitido" por defecto: el bloque
    # llega con el texto vacío y una firma. Está para que el código que
    # devuelve `content` al historial lo pase tal cual, como con la API real.
    return {"type": "thinking", "thinking": "", "signature": "EqQBCkgIBxABGAIiQ" + uuid.uuid4().hex}


def mensaje(contenido: list[dict], stop_reason: str = "end_turn", *, entrada: int = 1_200,
            salida: int = 180, cache_leido: int = 0, cache_escrito: int = 0, modelo: str = MODELO) -> dict:
    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "model": modelo,
        "content": contenido,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": entrada,
            "output_tokens": salida,
            "cache_creation_input_tokens": cache_escrito,
            "cache_read_input_tokens": cache_leido,
            "service_tier": "standard",
        },
    }


def cliente_con(responder: Callable[[dict], dict]) -> anthropic.AsyncAnthropic:
    """Un AsyncAnthropic de verdad cuyo transporte contesta `responder(body)`."""
    def manejar(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/messages", request.url.path
        cuerpo = json.loads(request.content)
        return httpx.Response(200, json=responder(cuerpo), headers={"request-id": "req_simulado"})

    return anthropic.AsyncAnthropic(
        api_key="sk-ant-simulada-no-es-una-clave",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(manejar)),
        max_retries=0,
    )


class ApiGrabada:
    """Contesta en orden las respuestas cargadas y guarda los pedidos."""

    def __init__(self, respuestas: list[dict]):
        self.respuestas = list(respuestas)
        self.pedidos: list[dict] = []

    def __call__(self, cuerpo: dict) -> dict:
        self.pedidos.append(cuerpo)
        if not self.respuestas:
            raise AssertionError("La API simulada recibió más pedidos de los esperados")
        return self.respuestas.pop(0)

    def cliente(self) -> anthropic.AsyncAnthropic:
        return cliente_con(self)


# ---------------------------------------------------------------------------
# El simulador para el servidor de prueba
# ---------------------------------------------------------------------------

_NUMEROS = {
    "uno": "1", "dos": "2", "tres": "3", "cuatro": "4", "cinco": "5", "seis": "6", "siete": "7",
    "ocho": "8", "nueve": "9", "diez": "10", "veinte": "20", "treinta": "30", "cuarenta": "40",
    "cincuenta": "50", "sesenta": "60", "setenta": "70", "ochenta": "80", "noventa": "90",
    "cien": "100", "doscientas": "200", "trescientas": "300", "quinientas": "500",
}


def _norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").casefold()
    return "".join(c for c in s if not unicodedata.combining(c))


class SimuladorDeDonTino:
    """Reglas simples en lugar del modelo. Ver el docstring del módulo."""

    def __call__(self, cuerpo: dict) -> dict:
        formato = (cuerpo.get("output_config") or {}).get("format")
        if formato:
            return self._brief(cuerpo)
        return self._chat(cuerpo)

    # --- Don Tino ------------------------------------------------------------

    def _chat(self, cuerpo: dict) -> dict:
        ofrecidas = {t["name"] for t in cuerpo.get("tools") or []}
        ultimo = cuerpo["messages"][-1]
        if isinstance(ultimo["content"], str):
            return self._elegir_herramientas(ultimo["content"], ofrecidas)
        resultados = [b for b in ultimo["content"] if b.get("type") == "tool_result"]
        pregunta = next(
            (m["content"] for m in reversed(cuerpo["messages"]) if m["role"] == "user" and isinstance(m["content"], str)),
            "",
        )
        pedidas = {}
        for m in cuerpo["messages"]:
            if m["role"] == "assistant" and isinstance(m["content"], list):
                for b in m["content"]:
                    if b.get("type") == "tool_use":
                        pedidas[b["id"]] = b["name"]
        partes = [self._redactar(pedidas.get(r["tool_use_id"], ""), json.loads(r["content"]), pregunta)
                  for r in resultados]
        return mensaje([pensamiento(), texto("\n\n".join(p for p in partes if p))],
                       entrada=3_400, salida=420, cache_leido=11_000)

    def _elegir_herramientas(self, pregunta: str, ofrecidas: set[str]) -> dict:
        p = _norm(pregunta)
        llamadas: list[tuple[str, dict]] = []
        if "cargad" in p:
            periodo = "semana_que_viene" if "que viene" in p or "proxima" in p else "esta_semana"
            llamadas.append(("calendario_carga", {"periodo": periodo}))
        elif "pieza" in p:
            args: dict = {"periodo": "semana_que_viene" if "que viene" in p else "esta_semana"}
            if "sin aprobar" in p:
                args["estados"] = ["pendiente", "en-proceso"]
            if "express" in p:
                args["mundo"] = "tienda_express"
            llamadas.append(("calendario_piezas", args))
        elif "hacer hoy" in p or "tengo que hacer" in p:
            llamadas.append(("calendario_tareas", {"responsable": "yo", "periodo": "hoy"}))
            llamadas.append(("calendario_avisos", {"para": "yo", "periodo": "hoy"}))
        else:
            m = re.search(r"(?:estado|viene)\s+(?:del|de la|de|el|la)\s+([a-zA-ZáéíóúñÁÉÍÓÚÑ0-9 ]+?)(?:\s+para\b|\?|$)",
                          pregunta, re.IGNORECASE)
            if m and ("como viene" in p or "estado" in p):
                llamadas.append(("calendario_accion", {"texto": m.group(1).strip()}))
        llamadas = [(n, a) for n, a in llamadas if n in ofrecidas]
        if not llamadas:
            if any(k in p for k in ("pieza", "cargad", "hacer hoy", "como viene", "estado")):
                return mensaje([texto("No tengo acceso al calendario con tus permisos: pedile a un "
                                      "administrador el permiso de ver el calendario.")])
            return mensaje([texto("(Modo de prueba, sin IA real.) Preguntame por el calendario: "
                                  "\"¿cómo viene el Ciberlunes?\", \"¿qué tengo que hacer hoy?\"...")])
        return mensaje([pensamiento(), texto("Me fijo en el calendario.")] + [herramienta(n, a) for n, a in llamadas],
                       "tool_use", entrada=1_100, salida=90, cache_escrito=10_900)

    @staticmethod
    def _fecha(iso: str | None) -> str:
        return f"{iso[8:10]}/{iso[5:7]}" if iso else "sin fecha"

    def _redactar(self, nombre: str, datos: dict, pregunta: str) -> str:
        if "error" in datos:
            ajeno = re.search(r"no tiene acceso a ([^:]+):", datos["error"])
            if ajeno:
                return f"No tenés acceso a {ajeno.group(1)}, así que no te puedo contar nada de ese mundo."
            return f"No puedo contestarte eso: {datos['error']}"
        f = self._fecha
        if nombre == "calendario_accion":
            a = datos["accion"]
            link = f"[{a['nombre']}]({a['link']})"
            piezas = datos.get("piezas", [])
            tareas = datos.get("tareas", [])
            listas = [p for p in piezas if p["estado"] in ("aprobado", "publicado")]
            faltan = [p for p in piezas if p["estado"] not in ("aprobado", "publicado")]
            abiertas = [t for t in tareas if t["estado"] != "hecha"]
            hechas = [t for t in tareas if t["estado"] == "hecha"]
            riesgos = [p for p in faltan if p.get("atrasada")] + [t for t in abiertas if t.get("vencida")]
            if "gerencia" not in _norm(pregunta):
                return (f"{link} ({a.get('categoria', 'sin categoría')}) va del {f(a['desde'])} al {f(a['hasta'])}: "
                        f"{a['cuando']}. Piezas: {len(listas)} de {len(piezas)} aprobadas o publicadas. "
                        f"Tareas: {len(hechas)} de {len(tareas)} hechas.")
            renglones = [
                "**Resumen**",
                f"- {link}, del {f(a['desde'])} al {f(a['hasta'])} ({a['cuando']}). "
                f"{len(listas)} de {len(piezas)} piezas listas y {len(hechas)} de {len(tareas)} tareas hechas.",
                "**Listo**",
                *([f"- {p['area']}: {p['formato']} ({p['estado']})" for p in listas] + [f"- Tarea: {t['titulo']}" for t in hechas]
                  or ["- Nada todavía."]),
                "**Falta**",
                *([f"- {p['area']}: {p['formato']}, {p['estado']}, sale el {f(p.get('sale'))}" for p in faltan]
                  + [f"- {t['titulo']}: {t['responsable']}, vence el {f(t.get('vence'))}" for t in abiertas]
                  or ["- Nada."]),
                "**Riesgos**",
                *([f"- {r.get('titulo') or r.get('formato')}: atrasada o vencida" for r in riesgos] or ["- No hay riesgos a la vista."]),
                "**Próximos pasos**",
                *([f"- {t['responsable']}: {t['titulo']}" for t in abiertas[:4]] or ["- Seguir el plan."]),
            ]
            return "\n".join(renglones)
        if nombre == "calendario_piezas":
            piezas = datos.get("piezas", [])
            if not piezas:
                return "No hay piezas en ese período con esos estados."
            return "\n".join([f"Encontré {datos['total']} pieza(s):"] + [
                f"- [{p['accion']['nombre']}]({p['accion']['link']}) · {p['area']}: {p['formato']} — "
                f"{p['estado']}, sale el {f(p['sale'])}" for p in piezas])
        if nombre == "calendario_tareas":
            tareas = datos.get("tareas", [])
            if not tareas:
                return "No tenés tareas para hoy ni vencidas."
            return "\n".join(["Tus tareas:"] + [
                f"- {t['titulo']} ([{t['accion']['nombre']}]({t['accion']['link']})) — "
                f"{'venció' if t.get('vencida') else 'vence'} el {f(t.get('vence'))}" for t in tareas])
        if nombre == "calendario_avisos":
            avisos = datos.get("avisos", [])
            if not avisos:
                return "Hoy no te sale ningún aviso."
            return "\n".join(["Avisos:"] + [f"- [{a['accion']['nombre']}]({a['accion']['link']}) arranca el {f(a['arranca'])}"
                                            for a in avisos])
        if nombre == "calendario_carga":
            personas = datos.get("personas", [])
            if not personas:
                return "Nadie tiene tareas abiertas en ese período."
            return "\n".join([f"Del {f(datos['periodo']['desde'])} al {f(datos['periodo']['hasta'])}:"] + [
                f"- **{r['persona']}**: {r['vencen_en_el_periodo']} vencen en el período, {r['vencidas']} vencidas, "
                f"{r['abiertas']} abiertas en total" for r in personas])
        return json.dumps(datos, ensure_ascii=False)[:500]

    # --- Brief -----------------------------------------------------------------

    def _brief(self, cuerpo: dict) -> dict:
        contenido = cuerpo["messages"][-1]["content"]
        dictado = re.search(r"<dictado>\n(.*)\n</dictado>", contenido, re.S).group(1)
        tipo = re.search(r"Tipo de pieza: ([^.]+)\.", contenido).group(1)
        esquema = cuerpo["output_config"]["format"]["schema"]
        de_campos = esquema["properties"]["campos"]
        if "$ref" in de_campos:
            de_campos = esquema["$defs"][de_campos["$ref"].split("/")[-1]]
        claves = list(de_campos["properties"])
        d = _norm(dictado)
        # Lo mínimo para entender números dichos en palabras ("dos por uno",
        # "cuarenta locales"); el modelo de verdad entiende mucho más.
        for palabra, numero in _NUMEROS.items():
            d = re.sub(rf"\b{palabra}\b", numero, d)
        d = re.sub(r"\b(\d+) por (\d+)\b", r"\1x\2", d)
        campos: dict = {c: None for c in claves}
        dudas: list[str] = []

        def buscar(patron: str) -> re.Match | None:
            return re.search(patron, d)

        # Con unidad: "2x1" es una mecánica, no una medida.
        if "medidas" in campos and (m := buscar(r"(\d+\s*x\s*\d+\s*(?:cm|mm|px)|\ba[345]\b)")):
            campos["medidas"] = m.group(1).upper() if m.group(1).startswith("a") else m.group(1)
        if "cantidad" in campos and (m := buscar(r"(\d+)\s*(?:cenefas|unidades|piezas)")):
            campos["cantidad"] = m.group(1)
        if "precio_mecanica" in campos and (m := buscar(r"(\d+\s*x\s*\d+(?:\s+en\s+[a-z ]+?)?)(?:,|\.|$| del| para)")):
            campos["precio_mecanica"] = m.group(1).strip()
        if (m := buscar(r"del?\s+(\d{1,2})\s+al\s+(\d{1,2})(?:\s+de\s+([a-z]+))?")):
            valor = f"del {m.group(1)} al {m.group(2)}" + (f" de {m.group(3)}" if m.group(3) else "")
            for c in ("vigencia", "fechas", "fecha", "fecha_envio"):
                if c in campos:
                    campos[c] = valor
                    break
            if not m.group(3):
                dudas.append("¿De qué mes son las fechas?")
        if "locales" in campos and (m := buscar(r"(\d+)\s+locales")):
            campos["locales"] = f"{m.group(1)} locales"
        if "legales" in campos and ("sin legales" in d or "no lleva legales" in d):
            campos["legales"] = "No lleva"
        if "asunto" in campos and (m := re.search(r"asunto:?\s+([^,.]+)", dictado, re.I)):
            campos["asunto"] = m.group(1).strip()
        if "fecha_envio" in campos and (m := re.search(r"sale (?:el )?([^,.]+)", dictado, re.I)):
            campos["fecha_envio"] = m.group(1).strip()
        if "llamado_accion" in campos and (m := re.search(r"bot[oó]n:?\s+([^,.]+)", dictado, re.I)):
            campos["llamado_accion"] = m.group(1).strip()
        if "texto" in campos:
            campos["texto"] = dictado.strip()
        campana = re.search(r"para (?:el|la) ([A-Za-zÁÉÍÓÚáéíóúñ]+)", dictado)
        resumen = f"{tipo}" + (f" {campana.group(1)}" if campana else "")
        if campos.get("precio_mecanica"):
            resumen += f": {campos['precio_mecanica']}"
        salida = {"resumen": resumen, "campos": campos,
                  "notas": f"Para {campana.group(1)}." if campana else None, "dudas": dudas}
        return mensaje([texto(json.dumps(salida, ensure_ascii=False))], entrada=820, salida=160)

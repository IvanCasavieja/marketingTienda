# -*- coding: utf-8 -*-
"""Las reglas de medicion de las cenefas, leidas del UNICO lugar donde viven.

Una cenefa se dibuja dos veces: acá se arma el PPTX y en el navegador se
dibuja el preview. Cada regla de medición estaba escrita a mano en los dos
lados, y cada vez que alguien tocaba una y se olvidaba de la otra, la pantalla
dejaba de mostrar lo que salía impreso sin que nadie se enterara.

Pedido de Ivan (18/09/2026): "el archivo de reglas tiene que ser uno solo,
sino nos va a pasar de poner una regla en algún lado y luego olvidarnos de
cambiarla en el otro y eso es una mierda".

Ese archivo es ``app/data/reglas_de_medicion.json``. Este módulo lo lee para
el exportador; el preview lo pide por HTTP a
``GET /tools/cenefas/v2/reglas-de-medicion``, que devuelve ``CRUDO`` tal cual.

POR QUE ACA Y NO EN LA RAIZ DEL REPO: los dos despliegues están rooteados cada
uno en su carpeta. El contexto de Docker del backend es ``backend/``
(``docker build ... backend`` en ci.yml + ``COPY . .`` en el Dockerfile) y el
Root Directory de Vercel es ``frontend/``. Un archivo en ``<raiz>/shared/`` no
llegaría ni a la imagen del backend ni al build del frontend. Por eso el
archivo vive adentro del backend --como ``font_metrics.json``, mismo
precedente-- y el frontend lo pide por la red en vez de importarlo.

POR QUE ACA NO HAY VALOR DE RESERVA: ``font_metrics._cargar`` degrada a ``{}``
con un warning porque sin la tabla de anchos queda una aproximación
documentada. Acá no. Si falta el archivo o falta una clave, esto revienta al
importar. Una regla de medición que falta significa que el exportador mediría
con un número inventado, que es exactamente la mentira que este archivo viene
a matar. Que reviente en el arranque --el job "backend" de CI corre
``python -c "import app.main"``-- es el resultado bueno.
"""
from __future__ import annotations

import json
import pathlib
from types import SimpleNamespace

_RUTA = pathlib.Path(__file__).parent.parent.parent / "data" / "reglas_de_medicion.json"

# Las reglas que el código de acá consume. Si agregás una al JSON y la usás en
# Python, sumala a esta lista: así el arranque falla con un nombre concreto en
# vez de un AttributeError en medio de una generación.
_OBLIGATORIAS = (
    "factor_voladita",
    "alto_de_linea",
    "inset_cm",
    "pt_por_defecto",
    "factor_negrita",
    "em_fallback",
)


def _cargar() -> dict:
    try:
        crudo = json.loads(_RUTA.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - se ve en el arranque
        raise RuntimeError(
            f"no está {_RUTA}. Ese archivo es la ÚNICA fuente de las reglas de "
            f"medición de las cenefas; sin él el exportador mediría con números "
            f"inventados y el preview no tendría de dónde leerlos. No lo "
            f"reemplaces con valores por defecto: recuperá el archivo."
        ) from exc
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise RuntimeError(f"{_RUTA} no es JSON válido: {exc}") from exc

    faltan = [k for k in _OBLIGATORIAS if k not in crudo]
    if faltan:
        raise RuntimeError(
            f"a {_RUTA.name} le faltan reglas que el código usa: {', '.join(faltan)}. "
            f"Agregalas ahí con su 'valor', su 'que_es' y su 'porque' -- no las "
            f"escribas a mano en el .py."
        )
    for clave in _OBLIGATORIAS:
        valor = crudo[clave].get("valor") if isinstance(crudo[clave], dict) else None
        if not isinstance(valor, (int, float)) or isinstance(valor, bool):
            raise RuntimeError(
                f"la regla '{clave}' de {_RUTA.name} no trae un número en 'valor' "
                f"(trae {valor!r})."
            )
    return crudo


#: El JSON tal cual, con los porqués. Es lo que devuelve el endpoint, SIN
#: rearmar nada: si el endpoint reformateara, la forma pasaría a ser un segundo
#: lugar donde se puede desfasar.
CRUDO: dict = _cargar()

#: Los valores ya desenvueltos, para usar en el código: ``REGLAS.inset_cm``.
REGLAS = SimpleNamespace(**{k: CRUDO[k]["valor"] for k in _OBLIGATORIAS})

# -*- coding: utf-8 -*-
"""El tamano de hoja de las cenefas, leido del UNICO lugar donde vive.

Una cenefa se dibuja dos veces: aca se arma el PPTX y en el navegador se
dibuja el preview. El tamano de la hoja estaba escrito a mano en CINCO tablas
--``layout_engine.FORMATS``, ``component_renderer.FORMAT_SLIDES``,
``pptx_importer._FORMATS_DIM``, ``Canvas.FORMAT_DIMS`` y las etiquetas del
panel de importacion-- y tres de los seis formatos tenian numeros DISTINTOS
segun a quien se le preguntara. Encima habia una SEXTA decision, tomada en el
momento de dibujar: el preview agrandaba la hoja hasta que entrara el
contenido (``Math.max`` en Canvas.tsx), asi que un cuadro que se salia del
papel se veia adentro en pantalla y salia cortado de la impresora.

Pedido de Ivan (18/09/2026): "el archivo de reglas tiene que ser uno solo,
sino nos va a pasar de poner una regla en algun lado y luego olvidarnos de
cambiarla en el otro y eso es una mierda".

Ese archivo es ``app/data/formatos_de_hoja.json``. Este modulo lo lee para el
exportador, el importador y el motor de layout; el preview lo pide por HTTP a
``GET /tools/cenefas/v2/formatos-de-hoja``, que devuelve ``CRUDO`` tal cual.
Mismo patron exacto que ``reglas_medicion.py`` y ``font_metrics.py``: un JSON
en ``app/data/``, un modulo que lo lee, un endpoint que lo sirve sin rearmar
nada y un barrido que prohibe que vuelva a aparecer una copia.

PAPEL vs CELDA. Un formato dice dos cosas distintas que hasta hoy se llamaban
igual: el PAPEL que sale de la impresora y la CELDA que ocupa UNA cenefa
adentro de ese papel. Para a4/a3 son lo mismo; para 3xa4 son tres franjas
apiladas, para a5 dos cenefas una al lado de la otra y para pinchos/6xa4 una
grilla. Confundirlas es lo que hacia que el preview de un "3xa4" dibujara una
franja de 21x9,9 cm y la llamara "la hoja" mientras la impresora sacaba una A4
entera.

LA ORIENTACION LA DICE EL NOMBRE (Ivan, 22/09/2026): a4 y 3xa4 son una A4
VERTICAL, 6xa4 es una A4 HORIZONTAL y a5 es una A5 HORIZONTAL con DOS cenefas
("en realidad son 2xA5, no es una sola"). El codigo tenia la 6xa4 parada y la
a5 sola: por eso una A4 apaisada de 29,7 x 21 se detectaba como "a5"
(14,85 x 21) al importar. Los numeros, con su verificacion contra las 23
plantillas de produccion, estan en el JSON.

DE DONDE SALE EL PAPEL DE UNA PLANTILLA DE VERDAD. No de aca. El papel es el
que trae el PPTX que se importo (``prs.slide_width/height``), un numero exacto
que el sistema tenia en la mano y tiraba: se calculaba en ``import_pptx`` para
elegir la etiqueta del formato y despues no se guardaba en ningun lado. Desde
el 22/09/2026 se guarda en ``definition["hoja"]`` y ``hoja_de_definicion()``
--de este modulo-- es la puerta unica por la que los dos motores lo leen. Esta
tabla es el papel cuando no hay PPTX que preguntar (una plantilla armada a
mano en el editor) y nada mas.

POR QUE ACA Y NO EN LA RAIZ DEL REPO: mismo motivo que reglas_medicion.py --
los dos despliegues estan rooteados cada uno en su carpeta (Docker en
``backend/``, Vercel en ``frontend/``), asi que un archivo compartido en la
raiz no llegaria a ninguno de los dos builds. Por eso vive adentro del backend
y el frontend lo pide por la red.

POR QUE ACA NO HAY VALOR DE RESERVA: si falta el archivo o falta un formato,
esto revienta al importar el modulo. Un tamano de hoja que falta significa que
el exportador imprimiria sobre un papel inventado, que es exactamente la
mentira que este archivo viene a matar.
"""
from __future__ import annotations

import json
import pathlib

_RUTA = pathlib.Path(__file__).parent.parent.parent / "data" / "formatos_de_hoja.json"

# Los formatos que el codigo de aca consume. Si agregas uno al JSON y lo usas
# en Python, sumalo a esta lista: asi el arranque falla con un nombre concreto
# en vez de un KeyError en medio de una generacion.
_OBLIGATORIOS = ("a4", "a3", "3xa4", "pinchos", "a5", "6xa4")

_UMBRALES = ("tolerancia_deteccion_cm", "ruido_emu_cm", "tolerancia_desborde_cm")


def _cargar() -> dict:
    try:
        crudo = json.loads(_RUTA.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - se ve en el arranque
        raise RuntimeError(
            f"no esta {_RUTA}. Ese archivo es la UNICA fuente del tamano de hoja "
            f"de las cenefas; sin el el exportador imprimiria sobre un papel "
            f"inventado y el preview no tendria de donde leerlo. No lo "
            f"reemplaces con valores por defecto: recupera el archivo."
        ) from exc
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise RuntimeError(f"{_RUTA} no es JSON valido: {exc}") from exc

    formatos = crudo.get("formatos")
    if not isinstance(formatos, dict):
        raise RuntimeError(f"{_RUTA.name} no trae el diccionario 'formatos'.")

    faltan = [k for k in _OBLIGATORIOS if k not in formatos]
    if faltan:
        raise RuntimeError(
            f"a {_RUTA.name} le faltan formatos que el codigo usa: "
            f"{', '.join(faltan)}. Agregalos ahi con su papel, su celda y su "
            f"'porque' -- no los escribas a mano en el .py."
        )
    for fmt_id, fmt in formatos.items():
        for clave in ("papel_cm", "celda_cm"):
            medida = fmt.get(clave)
            if not isinstance(medida, dict):
                raise RuntimeError(f"el formato '{fmt_id}' de {_RUTA.name} no trae '{clave}'.")
            for eje in ("ancho", "alto"):
                v = medida.get(eje)
                if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
                    raise RuntimeError(
                        f"el formato '{fmt_id}' de {_RUTA.name} tiene "
                        f"{clave}.{eje} = {v!r}, que no es una medida."
                    )
    for clave in _UMBRALES:
        valor = crudo.get(clave, {}).get("valor") if isinstance(crudo.get(clave), dict) else None
        if not isinstance(valor, (int, float)) or isinstance(valor, bool):
            raise RuntimeError(
                f"{_RUTA.name} no trae un numero en '{clave}.valor' (trae {valor!r})."
            )
    return crudo


#: El JSON tal cual, con los porques. Es lo que devuelve el endpoint, SIN
#: rearmar nada: si el endpoint reformateara, la forma pasaria a ser un segundo
#: lugar donde el backend y el preview se pueden desfasar.
CRUDO: dict = _cargar()

#: fmt_id -> el bloque del JSON, tal cual.
FORMATOS: dict[str, dict] = CRUDO["formatos"]

#: Cuanto se puede apartar el slide de un PPTX de una medida conocida para que
#: el importador acepte esa etiqueta. Ver el 'porque' en el JSON.
TOLERANCIA_DETECCION_CM: float = CRUDO["tolerancia_deteccion_cm"]["valor"]

#: Por debajo de esto, dos hojas son la misma hoja (PowerPoint guarda EMU
#: enteros y 21 cm da 20,999). Ver el 'porque' en el JSON.
RUIDO_EMU_CM: float = CRUDO["ruido_emu_cm"]["valor"]

#: Cuanta TINTA se tiene que salir del papel para que se avise.
TOLERANCIA_DESBORDE_CM: float = CRUDO["tolerancia_desborde_cm"]["valor"]


def _formato(fmt_id: str | None) -> dict:
    """El bloque de un formato, o el de a4 si el id no existe.

    Cae en a4 y no revienta porque el id llega de la base (``master_format``
    de una plantilla vieja) y una etiqueta desconocida no tiene por que tumbar
    una generacion. El TAMANO igual no depende de esto cuando la plantilla
    trae su hoja: ver ``hoja_de_definicion``.
    """
    return FORMATOS.get(fmt_id or "", FORMATOS["a4"])


def papel_cm(fmt_id: str | None) -> tuple[float, float]:
    """El papel que sale de la impresora para ese formato, en cm."""
    p = _formato(fmt_id)["papel_cm"]
    return p["ancho"], p["alto"]


def celda_cm(fmt_id: str | None) -> tuple[float, float]:
    """Lo que ocupa UNA cenefa adentro del papel, en cm.

    Para a4/a3 es el papel entero; para 3xa4 una franja, para a5 una de las
    dos mitades y para pinchos/6xa4 una celda de la grilla.
    """
    c = _formato(fmt_id)["celda_cm"]
    return c["ancho"], c["alto"]


def slots(fmt_id: str | None) -> tuple[int, int, int]:
    """(cuantas cenefas entran, columnas, filas) de la grilla del formato."""
    f = _formato(fmt_id)
    return int(f["slots"]), int(f.get("slot_cols", 1)), int(f.get("slot_rows", 1))


def misma_hoja(a: tuple[float, float], b: tuple[float, float]) -> bool:
    """Si dos medidas de hoja son la misma hoja, salvando el ruido de EMU.

    PowerPoint guarda todo en EMU enteros y 21 cm no cae redondo: las 23
    plantillas de produccion declaran 20,999 x 29,699. Comparar con ``==``
    diria que ninguna es una A4.
    """
    return abs(a[0] - b[0]) <= RUIDO_EMU_CM and abs(a[1] - b[1]) <= RUIDO_EMU_CM


def hoja_de_definicion(definition: dict | None, fmt_id: str | None = None) -> dict:
    """EL PAPEL DE UNA PLANTILLA. La unica puerta: no hay otra cuenta.

    Devuelve ``{"ancho_cm", "alto_cm", "origen"}``.

    - ``origen = "pptx"``: la medida exacta del archivo que se importo
      (``prs.slide_width/height``). Es la verdad: es el papel sobre el que
      PowerPoint va a imprimir, porque el render reusa ese mismo archivo
      (``preserve_source`` en component_renderer).
    - ``origen = "formato"``: la plantilla no trae hoja --se armo a mano en el
      editor, o se importo antes del 22/09/2026 y todavia no se le corrio el
      backfill (``scripts/backfill_hoja_desde_pptx.py``)-- asi que se usa el
      papel del formato declarado. Se dice de donde salio para que el preview
      pueda mostrarlo y nadie confunda "medido" con "supuesto".

    ``fmt_id`` es el formato que se esta MIRANDO. Cuando no es el master, el
    diseno se esta viendo escalado a OTRA hoja, asi que la medida del PPTX
    original ya no aplica y manda el papel del formato destino.

    NO SE INFIERE DEL CONTENIDO. Ese era el bug: el preview hacia
    ``Math.max(hoja, ...bordes de los cuadros)``, o sea agrandaba el papel
    hasta que entrara el diseno. Un cuadro que se salia se veia adentro y
    salia cortado de la impresora. El papel es el papel.
    """
    definicion = definition or {}
    master = definicion.get("master_format")
    mirando_el_master = not fmt_id or fmt_id == master
    hoja = definicion.get("hoja")
    if mirando_el_master and isinstance(hoja, dict):
        ancho, alto = hoja.get("ancho_cm"), hoja.get("alto_cm")
        if isinstance(ancho, (int, float)) and isinstance(alto, (int, float)) \
                and ancho > 0 and alto > 0:
            return {
                "ancho_cm": float(ancho),
                "alto_cm": float(alto),
                "origen": hoja.get("origen") or "pptx",
            }
    ancho, alto = papel_cm(fmt_id or master)
    return {"ancho_cm": ancho, "alto_cm": alto, "origen": "formato"}

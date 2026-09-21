"""Orquesta la validación de redes sociales: leer el mailing una vez, y por
cada placa leerla, emparejarla con su producto, compararla y armar los
recortes que dejan ver cada diferencia sin abrir nada aparte.

No toca la base (el llamador guarda lo que devuelve) y no sabe de HTTP.

Todo el trabajo de imágenes va por `en_hilo` (ver hilos.py): es CPU sincrónico y
el servidor corre un solo proceso, así que hecho directo congelaba a todos.
Y la placa no se mantiene decodificada mientras se espera al modelo: se guardan
sus bytes y cada etapa que la necesita la reabre.
"""
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from PIL import Image

from app.services.rrss import catti, comparador, imagenes
from app.services.rrss.hilos import en_hilo

logger = logging.getLogger(__name__)

# Legales que se exigen en cada placa. `legal_alcohol` vacío = el que trae el
# propio mailing (ver comparador.comparar_elementos). Se pueden cambiar por
# corrida desde la pantalla de carga.
CONFIG_DEFECTO = {
    "legal_bases": "Bases y condiciones en tiendainglesa.com.uy",
    "legal_alcohol": "",
}

_ANCHO_RECORTE = 640
# Las cajas que da el modelo suelen quedar justas y a veces cortan el borde de
# un texto ("Lata 710 m"). Un recorte con algo del vecino se lee igual; uno que
# corta una letra no sirve para confirmar nada.
_MARGEN_PRODUCTO = 0.04
_MARGEN_CAMPO = 0.03
_LADO_VISTA = 800  # lado largo de la vista guardada de cada placa

CargarPaginas = Callable[[], Awaitable[list[Image.Image]]]


@dataclass
class ResultadoPlaca:
    resultado: dict
    vista: bytes | None
    ancho: int
    alto: int
    formato: str
    estado: str
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class MailingPreparado:
    mailing: dict
    paginas: list[Image.Image] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0


def _uri(im: Image.Image | None, calidad: int = 78) -> str | None:
    return imagenes.data_uri(imagenes.jpeg(im, calidad)) if im is not None else None


def _ms(desde: float) -> int:
    return round((time.perf_counter() - desde) * 1000)


# --------------------------------------------------------------------------
# Mailing
# --------------------------------------------------------------------------

def _recortes_de_productos(paginas: list[Image.Image], mailing: dict) -> None:
    for prod in mailing["productos"]:
        prod["recorte"] = _uri(
            imagenes.recortar(paginas[prod["pagina"]], prod["cajas"].get("producto"), margen=_MARGEN_PRODUCTO, ancho_max=520)
        )


async def preparar_mailing(datos: bytes, content_type: str, filename: str) -> MailingPreparado:
    """Renderiza el mailing, lo lee, ubica cada producto y deja el recorte de
    cada uno (el que se muestra al lado de la placa que le corresponde)."""
    paginas = await en_hilo(imagenes.paginas_del_mailing, datos, content_type, filename)
    mailing, t_in, t_out = await catti.leer_mailing(paginas)
    try:
        ti, to = await catti.localizar_mailing(paginas, mailing)
        t_in += ti
        t_out += to
    except Exception:
        # Sin cajas el mailing igual sirve para validar: solo se pierden los recortes.
        logger.warning("rrss: no se pudieron ubicar los productos del mailing", exc_info=True)
    await en_hilo(_recortes_de_productos, paginas, mailing)
    return MailingPreparado(mailing, paginas, t_in, t_out)


# --------------------------------------------------------------------------
# Placas
# --------------------------------------------------------------------------

def _vista(datos: bytes) -> bytes:
    """Vista chica de la placa, para guardarla y mostrarla junto al mailing."""
    return imagenes.jpeg(imagenes.reducir(imagenes.abrir_imagen(datos), _LADO_VISTA), 70)


def _recortes_de_las_filas(
    filas: list[dict], im: Image.Image, cajas_placa: dict, mailing: dict, idx: int | None,
    paginas: list[Image.Image],
) -> None:
    """Agrega a cada fila con diferencia `recorte_placa` y `recorte_mailing`
    (data URIs). Lo que no se puede recortar queda en None: la fila igual se
    muestra, con el texto de los dos lados."""
    item = mailing["productos"][idx] if idx is not None else None
    for fila in filas:
        fila["recorte_placa"] = fila["recorte_mailing"] = None
        if fila["severidad"] not in ("error", "aviso") or not fila["caja"]:
            continue
        clave_caja = fila["caja"]
        # Para lo que es del producto, si no se ubicó esa parte se muestra el
        # producto entero: mejor eso que nada.
        caja_placa = cajas_placa.get(clave_caja) or (cajas_placa.get("producto") if fila["grupo"] == "producto" else None)
        fila["recorte_placa"] = _uri(imagenes.recortar(im, caja_placa, margen=_MARGEN_CAMPO, ancho_max=_ANCHO_RECORTE))

        pagina = caja = None
        if item is not None and fila["grupo"] == "producto":
            pagina, caja = item["pagina"], item["cajas"].get(clave_caja) or item["cajas"].get("producto")
        elif fila["campo"] == "fecha" and mailing.get("fecha_pagina") is not None:
            pagina, caja = mailing["fecha_pagina"], mailing.get("fecha_caja")
        elif fila["campo"] == "legal_alcohol" and mailing.get("legal_alcohol_pagina") is not None:
            pagina, caja = mailing["legal_alcohol_pagina"], mailing.get("legal_alcohol_caja")
        if pagina is not None and caja:
            fila["recorte_mailing"] = _uri(
                imagenes.recortar(paginas[pagina], caja, margen=_MARGEN_CAMPO, ancho_max=_ANCHO_RECORTE)
            )


def _armar_recortes(datos: bytes, filas: list[dict], cajas: dict, mailing: dict, idx: int | None,
                    paginas: list[Image.Image]) -> None:
    _recortes_de_las_filas(filas, imagenes.abrir_imagen(datos), cajas, mailing, idx, paginas)


async def validar_placa(
    datos: bytes, nombre_archivo: str, mailing: dict, cargar_paginas: CargarPaginas, config: dict,
) -> ResultadoPlaca:
    """Valida UNA placa. Los errores de lectura no se propagan como excepción:
    devuelven una placa en estado 'error' con el motivo, para que un archivo
    roto en un lote de 30 no tire abajo a los otros 29.

    `cargar_paginas` trae las páginas del mailing SOLO si hacen falta (una placa
    sin diferencias no las necesita: no hay nada que recortar del mailing).

    Cada etapa queda medida en `resultado["tiempos_ms"]`: cuando una validación
    anda lenta hay que poder ver DÓNDE, en vez de suponerlo."""
    inicio = time.perf_counter()
    tiempos: dict[str, int] = {}

    try:
        t = time.perf_counter()
        prep = await en_hilo(catti.preparar_placa, datos)
        tiempos["preparar"] = _ms(t)
    except imagenes.ArchivoInvalido as exc:
        return await _con_error(str(exc), tiempos, inicio)

    formato = imagenes.clasificar_formato(prep.ancho, prep.alto)
    t_in = t_out = 0
    try:
        t = time.perf_counter()
        lectura, ti, to = await catti.leer_placa(prep)
        t_in, t_out = t_in + ti, t_out + to
        tiempos["lectura"] = _ms(t)

        idx, puntaje, filas = comparador.comparar_placa(lectura, mailing, config)

        # Un error de texto solo se sostiene si una segunda lectura lo repite:
        # acusar a una placa de un error que fue de lectura es peor que no ver nada.
        if any(f["severidad"] == "error" and f["campo"] in comparador.CAMPOS_DE_TEXTO for f in filas):
            t = time.perf_counter()
            segunda, ti, to = await catti.leer_placa(prep)
            t_in, t_out = t_in + ti, t_out + to
            filas = comparador.confirmar_con_segunda_lectura(filas, comparador.campos_leidos(segunda))
            tiempos["segunda_lectura"] = _ms(t)

        if any(f["severidad"] in ("error", "aviso") and f["caja"] for f in filas):
            t = time.perf_counter()
            try:
                cajas, ti, to = await catti.localizar_placa(datos, lectura)
                t_in, t_out = t_in + ti, t_out + to
            except Exception:
                logger.warning("rrss: no se pudo ubicar lo marcado en %s", nombre_archivo, exc_info=True)
                cajas = {}
            tiempos["ubicar"] = _ms(t)

            t = time.perf_counter()
            paginas = await cargar_paginas()
            tiempos["paginas"] = _ms(t)

            t = time.perf_counter()
            await en_hilo(_armar_recortes, datos, filas, cajas, mailing, idx, paginas)
            tiempos["recortes"] = _ms(t)
        else:
            for f in filas:
                f["recorte_placa"] = f["recorte_mailing"] = None
    except catti.LecturaFallida as exc:
        return await _con_error(str(exc), tiempos, inicio, datos, prep, formato, t_in, t_out)
    except Exception as exc:
        # RuntimeError de configuración (sin API key) o errores del API: se
        # dejan registrados y el usuario ve un motivo, no un 500 por placa.
        logger.error("rrss: error leyendo %s — %s", nombre_archivo, exc, exc_info=True)
        return await _con_error(
            "No pude leer esta placa ahora; probá de nuevo", tiempos, inicio, datos, prep, formato, t_in, t_out,
        )

    t = time.perf_counter()
    vista = await en_hilo(_vista, datos)
    tiempos["vista"] = _ms(t)
    tiempos["total"] = _ms(inicio)
    logger.info("rrss placa %s: %s ms=%s", nombre_archivo, comparador.estado_de_la_placa(filas, idx), tiempos)

    estado = comparador.estado_de_la_placa(filas, idx)
    resultado = {
        "match": {"indice": idx, "puntaje": round(puntaje, 1)} if idx is not None else None,
        "filas": filas,
        "lectura": lectura,
        "error": None,
        "tiempos_ms": tiempos,
    }
    return ResultadoPlaca(
        resultado=resultado, vista=vista, ancho=prep.ancho, alto=prep.alto, formato=formato, estado=estado,
        tokens_in=t_in, tokens_out=t_out,
    )


async def _con_error(motivo: str, tiempos: dict, inicio: float, datos: bytes | None = None,
                     prep: "catti.PlacaPreparada | None" = None, formato: str = "",
                     t_in: int = 0, t_out: int = 0) -> ResultadoPlaca:
    vista = None
    if datos is not None:
        try:
            vista = await en_hilo(_vista, datos)
        except Exception:
            vista = None
    tiempos["total"] = _ms(inicio)
    return ResultadoPlaca(
        resultado={"match": None, "filas": [], "lectura": None, "error": motivo, "tiempos_ms": tiempos},
        vista=vista,
        ancho=prep.ancho if prep else 0, alto=prep.alto if prep else 0,
        formato=formato, estado="error", tokens_in=t_in, tokens_out=t_out,
    )


def resumir_lote(estados: list[str], chequeos: dict) -> dict:
    """Contadores + los chequeos del lote, lo que se muestra arriba de todo."""
    cuenta = {e: estados.count(e) for e in ("ok", "avisos", "diferencias", "sin_match", "error")}
    return {"total": len(estados), **cuenta, **chequeos}

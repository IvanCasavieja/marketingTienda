"""Orquesta la validación de redes sociales: leer la fuente una vez, y por
cada placa leerla, emparejarla con su producto, compararla y armar los
recortes que dejan ver cada diferencia sin abrir nada aparte.

La fuente puede ser un MAILING (un PDF que CatTi mira y transcribe) o una
PLANILLA (un .xlsx/.csv que se lee como datos, sin IA -- ver planilla.py). Las
dos producen el MISMO dict, y de ahí para abajo el motor es uno solo.

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

import anthropic
from PIL import Image

from app.services.rrss import catti, comparador, imagenes, planilla
from app.services.rrss.hilos import en_hilo

logger = logging.getLogger(__name__)

# Lo que se exige en cada placa y no sale del producto. `legal_alcohol` y
# `fecha` vacíos = lo que traiga la propia fuente (ver
# comparador.comparar_elementos). Se pueden cambiar por corrida desde la
# pantalla de carga.
#
# `fecha` existe por las planillas: un mailing trae impreso el texto de
# vigencia ("DEL JUEVES 17 AL DOMINGO 20 DE SETIEMBRE") y una planilla trae dos
# fechas sueltas, que no es lo mismo. En vez de componer un texto que nadie
# escribió, lo escribe la persona -- y si no lo escribe, la fecha no se valida.
CONFIG_DEFECTO = {
    "legal_bases": "Bases y condiciones en tiendainglesa.com.uy",
    "legal_alcohol": "",
    "fecha": "",
}

_ANCHO_RECORTE = 640
# Las cajas que da el modelo suelen quedar justas y a veces cortan el borde de
# un texto ("Lata 710 m"). Un recorte con algo del vecino se lee igual; uno que
# corta una letra no sirve para confirmar nada.
_MARGEN_PRODUCTO = 0.04
_MARGEN_CAMPO = 0.03
# El ancho al que se le manda a CatTi el recorte del producto para RELEER el
# mailing (ver `_releer_producto_del_mailing`). La página se guarda a 1600 px y
# un producto ocupa un quinto de eso: el recorte sale de ~460 px y así CatTi
# leyó '$1.090' dos veces seguidas donde dice '$1090' (probado el 22/09/2026
# sobre la Jarra INHAUS); AMPLIADO a 1000 o 1400 px leyó '$1090' las cuatro
# veces. Ampliar no agrega información, pero el modelo lee mejor la letra chica
# cuando ocupa más píxeles, así que el recorte se agranda siempre a este ancho.
_ANCHO_RELECTURA = 1400
_CAMPOS_QUE_SE_RELEEN = comparador.CAMPOS_DE_PRECIO | {"precio_anterior_tachado"}
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
    mailing["origen"] = "mailing"
    await en_hilo(_recortes_de_productos, paginas, mailing)
    return MailingPreparado(mailing, paginas, t_in, t_out)


# --------------------------------------------------------------------------
# Planilla
# --------------------------------------------------------------------------

async def preparar_planilla(datos: bytes, filename: str, hoja: str | int | None = None) -> MailingPreparado:
    """La misma fuente, leída de una planilla, en dos pasos.

    1) CatTi mira la planilla y decide qué es cada columna (una llamada de
       texto, ver catti.interpretar_planilla). La planilla puede venir de
       cualquier forma -- pedido de Ivan del 22/09/2026, ver
       planilla.CAMPOS_DE_LA_PLANILLA -- y un listado real con la descripción en
       "NOMBRE ARTÍCULO" y la mecánica en "OFERTA" se rechazaba entero.
    2) Los valores se leen de las celdas, tal cual, con lo que decidió CatTi.
       Sin IA: la planilla es dato exacto y el modelo no reescribe contenido.

    Si CatTi no está disponible (sin clave, o la API caída) la planilla se lee
    por los NOMBRES de sus columnas, y se avisa: es peor que razonarla, pero
    un listado con los nombres de siempre se sigue pudiendo validar.

    Va a un hilo entero (openpyxl es CPU puro y sincrónico) por lo mismo que el
    resto del trabajo de píxeles: un solo proceso de uvicorn, ver hilos.py. Lo
    que ya NO hace es dibujar una tira por fila: eso se dibuja al emparejar cada
    placa, que es cuando se sabe qué fila hace falta (ver `validar_placa`).

    Lo que la lectura tuvo para decir (una hoja de más, una fila de pie, una
    columna en el vocabulario de gestión) viaja adentro del propio dict, en
    `mailing["planilla"]["avisos"]`, que es lo que se guarda en la base. Antes
    se armaba en un campo aparte del dataclass y acá se devolvía solo
    `pl.mailing`: los avisos no llegaban a ningún lado."""
    muestra = await en_hilo(planilla.muestra, datos, filename)
    try:
        mapeo, t_in, t_out = await catti.interpretar_planilla(muestra["texto"])
    except (RuntimeError, anthropic.APIError) as exc:
        # RuntimeError cubre "sin ANTHROPIC_API_KEY" y la LecturaFallida del
        # modelo; APIError, la API caída o saturada. En los dos casos hay una
        # forma peor pero útil de leer la planilla, y no hay por qué frenar la
        # validación entera.
        logger.warning("rrss: CatTi no pudo interpretar la planilla %s, leo por nombres de columna: %s", filename, exc)
        pl = await en_hilo(planilla.leer, datos, filename, hoja)
        pl.mailing["planilla"]["avisos"].insert(0, (
            "CatTi no pudo mirar la planilla en este momento, así que la leí por los nombres "
            "de las columnas. Revisá que la descripción y los precios hayan salido de la "
            "columna correcta."
        ))
        return MailingPreparado(pl.mailing, [], 0, 0)
    pl = await en_hilo(planilla.leer, datos, filename, hoja, mapeo)
    return MailingPreparado(pl.mailing, [], t_in, t_out)


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

        if mailing.get("origen") == "planilla":
            # No hay página de la que recortar: la evidencia es la fila de la
            # planilla dibujada, con la celda de ESTE campo encuadrada.
            if idx is not None and fila["grupo"] == "producto":
                fila["recorte_mailing"] = planilla.recorte_de_campo(mailing, idx, fila["campo"])
            continue

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
    paginas_relectura: list[Image.Image] = []
    try:
        t = time.perf_counter()
        lectura, ti, to = await catti.leer_placa(prep)
        t_in, t_out = t_in + ti, t_out + to
        tiempos["lectura"] = _ms(t)

        par = comparador.emparejamiento(lectura["producto"], mailing["productos"])
        idx, puntaje, filas = comparador.comparar_placa(lectura, mailing, config, par)

        # La evidencia del lado de la fuente. Con un mailing es el recorte del
        # producto, que ya quedó dibujado al leerlo; con una planilla es la tira
        # de la fila, y se dibuja ACÁ, cuando se sabe QUÉ fila hace falta: una
        # por placa emparejada en vez de una por fila del archivo (ver
        # planilla.evidencia). Va en el resultado de la placa porque es la
        # prueba de ESTE emparejamiento, y así viaja igual en vivo y al abrir la
        # validación del historial.
        recorte_fuente = None
        if idx is not None and mailing.get("origen") == "planilla":
            t = time.perf_counter()
            recorte_fuente = await en_hilo(planilla.evidencia, mailing, idx)
            tiempos["tira"] = _ms(t)

        # Un error de texto solo se sostiene si una segunda lectura lo repite:
        # acusar a una placa de un error que fue de lectura es peor que no ver nada.
        if any(f["severidad"] == "error" and f["campo"] in comparador.CAMPOS_CONFIRMABLES for f in filas):
            t = time.perf_counter()
            segunda, ti, to = await catti.leer_placa(prep)
            t_in, t_out = t_in + ti, t_out + to
            filas = comparador.confirmar_con_segunda_lectura(filas, comparador.campos_leidos(segunda))
            tiempos["segunda_lectura"] = _ms(t)

        # Y lo mismo del lado del MAILING, que hasta el 22/09/2026 se leía una
        # sola vez: si después de confirmar la placa queda un error de PRECIO (o
        # de tachado) contra un mailing, se relee el producto desde su recorte
        # ampliado. Solo la línea del precio y solo contra un mailing: es donde
        # se vio fallar la lectura de la página entera ('$1.090', '$7799'), y
        # una planilla no se lee, se abre. Cuesta una llamada por placa con
        # error de precio.
        if (
            mailing.get("origen") != "planilla" and idx is not None
            and any(f["severidad"] == "error" and f["campo"] in _CAMPOS_QUE_SE_RELEEN for f in filas)
        ):
            t = time.perf_counter()
            paginas_relectura = await cargar_paginas()
            tiempos["paginas"] = _ms(t)
            t = time.perf_counter()
            releido, ti, to = await _releer_producto_del_mailing(mailing["productos"][idx], paginas_relectura)
            t_in, t_out = t_in + ti, t_out + to
            if releido is not None:
                filas = comparador.confirmar_con_relectura_de_la_fuente(filas, comparador.campos_del_producto(releido))
            tiempos["relectura_mailing"] = _ms(t)

        if any(f["severidad"] in ("error", "aviso") and f["caja"] for f in filas):
            t = time.perf_counter()
            try:
                cajas, ti, to = await catti.localizar_placa(datos, lectura)
                t_in, t_out = t_in + ti, t_out + to
            except Exception:
                logger.warning("rrss: no se pudo ubicar lo marcado en %s", nombre_archivo, exc_info=True)
                cajas = {}
            tiempos["ubicar"] = _ms(t)

            # Con una planilla no hay páginas que traer de la base: el lado de
            # la fuente se dibuja, no se recorta.
            paginas: list[Image.Image] = []
            if mailing.get("origen") != "planilla":
                t = time.perf_counter()
                paginas = paginas_relectura if "paginas" in tiempos else await cargar_paginas()
                tiempos["paginas"] = tiempos.get("paginas", 0) + _ms(t)

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
    # Las filas que MÁS se parecieron, con su puntaje. Van cuando no hubo pareja
    # --sin esto, "no encontré este producto" es una acusación sin pruebas: la
    # persona no puede distinguir "esta placa no es de esta campaña" de "la
    # descripción está tan mal escrita que no la reconoció"-- y también cuando
    # SÍ hubo pero con duda: ahí son la prueba de que hay una segunda candidata
    # y por cuánto perdió.
    candidatas = (
        comparador.candidatos(lectura["producto"], mailing["productos"])
        if idx is None or par["duda"] else []
    )
    resultado = {
        "match": {
            "indice": idx, "puntaje": round(puntaje, 1),
            "segundo": round(par["segundo"], 1) if par["segundo"] is not None else None,
            "parecido": round(par["parecido"], 1),
            "duda": par["duda"], "motivo_duda": par["motivo_duda"],
        } if idx is not None else None,
        "candidatos": candidatas,
        # La tira de la fila de la planilla, o None si no se pudo dibujar. None
        # NO se esconde: la pantalla y el Excel dicen que la tira falta y
        # muestran la cita (archivo · hoja · fila) para ir a mirarla a mano.
        "recorte_fuente": recorte_fuente,
        "sin_pareja": par["motivo_sin_pareja"] if idx is None else None,
        "filas": filas,
        "lectura": lectura,
        "error": None,
        "tiempos_ms": tiempos,
    }
    return ResultadoPlaca(
        resultado=resultado, vista=vista, ancho=prep.ancho, alto=prep.alto, formato=formato, estado=estado,
        tokens_in=t_in, tokens_out=t_out,
    )


def _recorte_ampliado(pagina: Image.Image, caja) -> Image.Image | None:
    """SINCRÓNICO (va en un hilo): el recorte del producto llevado a
    _ANCHO_RELECTURA, agrandándolo si hace falta (ver el comentario de la
    constante). `imagenes.recortar` solo achica."""
    recorte = imagenes.recortar(pagina, caja, margen=_MARGEN_PRODUCTO, ancho_max=_ANCHO_RELECTURA)
    if recorte is None or recorte.width >= _ANCHO_RELECTURA:
        return recorte
    alto = max(1, round(recorte.height * _ANCHO_RELECTURA / recorte.width))
    return recorte.resize((_ANCHO_RELECTURA, alto), Image.LANCZOS)


async def _releer_producto_del_mailing(item: dict, paginas: list[Image.Image]) -> tuple[dict | None, int, int]:
    """La segunda lectura del mailing, de UN producto: su recorte ampliado de la
    página. None si no hay de dónde recortar (sin cajas, sin páginas): en ese
    caso el error queda como estaba, que es lo que pasaba hasta ahora."""
    caja = (item.get("cajas") or {}).get("producto")
    pagina = item.get("pagina")
    if not caja or pagina is None or not (0 <= pagina < len(paginas)):
        return None, 0, 0
    recorte = await en_hilo(_recorte_ampliado, paginas[pagina], caja)
    if recorte is None:
        return None, 0, 0
    try:
        return await catti.leer_producto_del_mailing(recorte)
    except Exception:
        # Es una confirmación, no la validación: si falla, la fila queda como
        # la dejó la primera lectura, y se registra.
        logger.warning("rrss: no se pudo releer el producto del mailing", exc_info=True)
        return None, 0, 0


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
        resultado={"match": None, "candidatos": [], "recorte_fuente": None, "sin_pareja": None,
                   "filas": [], "lectura": None, "error": motivo, "tiempos_ms": tiempos},
        vista=vista,
        ancho=prep.ancho if prep else 0, alto=prep.alto if prep else 0,
        formato=formato, estado="error", tokens_in=t_in, tokens_out=t_out,
    )


def resumir_lote(estados: list[str], chequeos: dict) -> dict:
    """Contadores + los chequeos del lote, lo que se muestra arriba de todo."""
    cuenta = {e: estados.count(e) for e in ("ok", "avisos", "diferencias", "sin_match", "error")}
    return {"total": len(estados), **cuenta, **chequeos}

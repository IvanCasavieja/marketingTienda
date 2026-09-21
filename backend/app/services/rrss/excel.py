"""El Excel de correcciones para el diseñador.

Salen SOLO las placas que tienen algo para corregir. La idea es que se entienda
sin explicación:

- Un bloque por ARREGLO, no por placa. Las adaptaciones de un mismo producto
  (1:1, 4:5, 9:16) casi siempre traen el mismo error: van juntas, así se corrige
  una vez y se exportan las tres. Si una tiene algo distinto a sus hermanas, va
  en su propio bloque y lo avisa.
- Placa y mailing lado a lado, y al costado solo lo que está mal: lo que dice
  (en rojo), lo que tiene que decir (en verde) y qué hacer, en una frase.

Diseño aprobado por Ivan el 2026-09-21 sobre la campaña del 17 al 20 de
setiembre. Es CPU puro y sincrónico (decodifica y arma imágenes): el que lo llame
desde una corrutina tiene que mandarlo a un hilo (ver hilos.py).
"""
import base64
import io

from openpyxl import Workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.drawing.image import Image as XLImage
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from PIL import Image, ImageDraw, ImageFont

from app.services.rrss import correccion as c

_EMU = 9525  # EMU por píxel

# ── Paleta ────────────────────────────────────────────────────────────────
AZUL, AZUL_2 = "1B3A6B", "2C5490"
GRIS_OSC, GRIS, GRIS_TXT, GRIS_SUAVE = "44546A", "F2F4F7", "32404F", "6B7686"
ROJO, ROJO_F = "C0392B", "FDECEA"
VERDE, VERDE_F = "1E8449", "E8F6EC"
AMBAR, AMBAR_F = "9A6400", "FFF4D6"

_linea = Side(style="thin", color="D7DCE3")
_grueso = Side(style="medium", color="9AA4B2")
_caja = Border(left=_linea, right=_linea, top=_linea, bottom=_linea)

_ORDEN_FORMATO = {"1:1": 0, "4:5": 1, "9:16": 2}

# Fuentes para el pie de las miniaturas (lo único que se dibuja con PIL; el resto
# del texto lo dibuja Excel). El servidor es Linux sin fuentes instaladas: ahí
# queda la que trae Pillow adentro, sin negrita. NO se simula la negrita con un
# trazo: con esa fuente el trazo rellena el hueco del 9 y "9:16" se leía "8:16".
_FUENTES = ("C:/Windows/Fonts/segoeui.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
_FUENTES_NEGRITA = ("C:/Windows/Fonts/segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


class NadaParaCorregir(ValueError):
    """Todas las placas están bien: no hay Excel que armar."""


def _fuente(tam: int, negrita: bool = False) -> ImageFont.ImageFont:
    for ruta in (_FUENTES_NEGRITA if negrita else _FUENTES):
        try:
            return ImageFont.truetype(ruta, tam)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:  # Pillow viejo, sin tamaño de fuente
        return ImageFont.load_default()


def _fill(color: str) -> PatternFill:
    return PatternFill("solid", fgColor=color)


def _px_col(ancho_chars: float) -> int:
    return round(ancho_chars * 7) + 5


def _pil(valor) -> Image.Image | None:
    """Una imagen desde bytes o desde un data URI."""
    if not valor:
        return None
    if isinstance(valor, str):
        valor = base64.b64decode(valor.split(",", 1)[1])
    return Image.open(io.BytesIO(valor)).convert("RGB")


def _jpeg(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=86)
    return buf.getvalue()


# ── Imágenes ancladas a celdas ────────────────────────────────────────────

def _poner(ws, jpg: bytes, ancho: int, alto: int, col0: int, fila0: int, dx: float = 0, dy: float = 0) -> None:
    """Imagen anclada a una celda (col0/fila0 en base 0), corrida dx/dy px."""
    img = XLImage(io.BytesIO(jpg))
    img.width, img.height = ancho, alto
    img.anchor = OneCellAnchor(
        _from=AnchorMarker(col=col0, row=fila0, colOff=int(dx * _EMU), rowOff=int(dy * _EMU)),
        ext=XDRPositiveSize2D(int(ancho * _EMU), int(alto * _EMU)),
    )
    ws.add_image(img)


def _centrada(ws, valor, col0: int, fila0: int, ancho_celda: int, alto_celda: float,
              margen_arriba: int = 0, margen: int = 8) -> None:
    im = _pil(valor)
    if im is None:
        return
    escala = min((ancho_celda - 2 * margen) / im.width, (alto_celda - margen_arriba - 2 * margen) / im.height, 1.0)
    w, h = max(1, round(im.width * escala)), max(1, round(im.height * escala))
    im = im.resize((w, h), Image.LANCZOS)
    _poner(ws, _jpeg(im), w, h, col0, fila0, (ancho_celda - w) / 2, margen_arriba + (alto_celda - margen_arriba - h) / 2)


def _tira_de_placas(placas: list[dict], etiquetas: dict[str, str], alto: int = 130) -> tuple[bytes, int, int]:
    """Las placas de un bloque, una al lado de la otra, con su formato y su nombre
    abajo. Va como UNA imagen: en Excel no hay forma confiable de poner texto
    debajo de cada foto dentro de una misma celda."""
    f_formato = _fuente(16, negrita=True)
    f_nombre = _fuente(12)
    fotos = []
    for im in placas:
        pil = _pil(im.get("vista"))
        if pil is None:  # la placa no se pudo abrir: un hueco gris del tamaño de una cuadrada
            pil = Image.new("RGB", (alto, alto), (226, 230, 236))
        fotos.append((pil.resize((max(1, round(pil.width * alto / pil.height)), alto), Image.LANCZOS), im))
    hueco, pie = 12, 38
    lienzo = Image.new("RGB", (sum(f.width for f, _ in fotos) + hueco * (len(fotos) - 1), alto + pie), "white")
    dib = ImageDraw.Draw(lienzo)
    x = 0
    for foto, im in fotos:
        lienzo.paste(foto, (x, 0))
        lineas = (
            (im.get("formato") or "", f_formato, alto + 1, (32, 42, 54)),
            (etiquetas.get(im["nombre_archivo"], im["nombre_archivo"]), f_nombre, alto + 21, (107, 118, 134)),
        )
        for texto, fuente, y, color in lineas:
            ancho = dib.textlength(texto, font=fuente)
            dib.text((x + (foto.width - ancho) / 2, y), texto, font=fuente, fill=color)
        x += foto.width + hueco
    return _jpeg(lienzo), lienzo.width, lienzo.height


# ── Texto con lo que cambia resaltado ─────────────────────────────────────

def _rico(texto: str, contra: str, lado: str, tam: int = 14) -> CellRichText:
    """Del lado de la placa se resalta en rojo lo que está mal; del lado del
    mailing, en verde lo que tiene que ir. Por palabra entera (ver correccion)."""
    base = InlineFont(sz=tam, color=GRIS_TXT, rFont="Calibri")
    if not texto:
        vacio = "(no está)" if lado == "placa" else "(no va nada)"
        return CellRichText([TextBlock(InlineFont(sz=tam - 1, i=True, color="8792A2", rFont="Calibri"), vacio)])
    color = ROJO if lado == "placa" else VERDE
    resalte = InlineFont(sz=tam, b=True, u="single", color=color, rFont="Calibri")
    if not contra:  # el otro lado está vacío: todo este texto es la diferencia
        return CellRichText([TextBlock(resalte, texto)])
    seg_p, seg_m = c.diferenciar_palabras(texto, contra) if lado == "placa" else c.diferenciar_palabras(contra, texto)
    segmentos = seg_p if lado == "placa" else seg_m
    return CellRichText([TextBlock(resalte if distinto else base, t) for t, distinto in segmentos])


# ── Qué entra al Excel ────────────────────────────────────────────────────

def _problemas(im: dict) -> list[dict]:
    probs = [f for f in im.get("filas") or [] if f.get("severidad") in ("error", "aviso")]
    if probs:
        return probs
    if im.get("error"):
        return [dict(campo="lectura", estado="revisar", placa=im["error"], mailing="")]
    return [dict(campo="sin_match", estado="revisar", placa="No encontré este producto en el mailing", mailing="")]


def _producto(mailing: dict, im: dict) -> dict | None:
    idx = (im.get("match") or {}).get("indice")
    productos = mailing.get("productos") or []
    return productos[idx] if idx is not None and 0 <= idx < len(productos) else None


def _agrupar(placas: list[dict]) -> list[dict]:
    """Las placas del MISMO producto con EXACTAMENTE los mismos errores van en un
    solo bloque. Una placa sin producto en el mailing no se junta con nada."""
    grupos: dict[tuple, dict] = {}
    for im in placas:
        probs = _problemas(im)
        idx = (im.get("match") or {}).get("indice")
        clave = (
            idx if idx is not None else f"sola-{im['nombre_archivo']}",
            tuple(sorted((f["campo"], f.get("placa") or "", f.get("mailing") or "") for f in probs)),
        )
        grupos.setdefault(clave, {"placas": [], "problemas": probs})["placas"].append(im)
    for g in grupos.values():
        g["placas"].sort(key=lambda im: (_ORDEN_FORMATO.get(im.get("formato"), 9), im.get("orden", 0)))
    return list(grupos.values())


# ── Hojas ─────────────────────────────────────────────────────────────────

def _banner(ws, validacion: dict, hasta_col: str, arreglos: int | None = None) -> None:
    imagenes = validacion["imagenes"]
    total = len(imagenes)
    con_algo = sum(1 for i in imagenes if i["estado"] != "ok")
    ws.merge_cells(f"A1:{hasta_col}1")
    ws["A1"] = "CORRECCIONES DE PLACAS  ·  REDES SOCIALES"
    ws["A1"].font = Font(size=18, bold=True, color="FFFFFF")
    ws["A1"].fill = _fill(AZUL)
    ws["A1"].alignment = Alignment(vertical="center", indent=1)
    ws.row_dimensions[1].height = 36
    ws.merge_cells(f"A2:{hasta_col}2")
    que = (f"{arreglos} cosas para corregir, en {con_algo} de las {total} placas" if arreglos
           else f"Hay que corregir {con_algo} de las {total} placas")
    fecha = (validacion.get("mailing") or {}).get("fecha") or ""
    campana = f"Campaña: {fecha}      " if fecha else ""
    ws["A2"] = f"{campana}{que}.  Las otras {total - con_algo} están bien: no las toques."
    ws["A2"].font = Font(size=12, color="FFFFFF")
    ws["A2"].fill = _fill(AZUL_2)
    ws["A2"].alignment = Alignment(vertical="center", indent=1)
    ws.row_dimensions[2].height = 26


def _encabezado(ws, fila: int, columnas: list[tuple[str, str, str]]) -> None:
    for letra, texto, color in columnas:
        cel = ws[f"{letra}{fila}"]
        cel.value = texto
        cel.font = Font(size=11, bold=True, color="FFFFFF")
        cel.fill = _fill(color)
        cel.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cel.border = _caja
    ws.row_dimensions[fila].height = 30


def _hoja_correcciones(wb, validacion: dict, etiquetas: dict[str, str]) -> None:
    ws = wb.active
    ws.title = "Correcciones"
    anchos = {"A": 49, "B": 28, "C": 17, "D": 31, "E": 31, "F": 33}
    for col, a in anchos.items():
        ws.column_dimensions[col].width = a

    mailing = validacion.get("mailing") or {}
    placas = [i for i in sorted(validacion["imagenes"], key=lambda x: x.get("orden", 0)) if i["estado"] != "ok"]
    grupos = _agrupar(placas)
    _banner(ws, validacion, "F", arreglos=len(grupos))
    _encabezado(ws, 3, [
        ("A", "LAS PLACAS", GRIS_OSC), ("B", "EL MAILING", GRIS_OSC), ("C", "QUÉ REVISAR", GRIS_OSC),
        ("D", "DICE LA PLACA", ROJO), ("E", "TIENE QUE DECIR", VERDE), ("F", "QUÉ HACER", AMBAR),
    ])

    # un producto en más de un bloque: sus adaptaciones no tienen todas el mismo error
    bloques_por_producto: dict = {}
    for g in grupos:
        idx = (g["placas"][0].get("match") or {}).get("indice")
        if idx is not None:
            bloques_por_producto[idx] = bloques_por_producto.get(idx, 0) + 1

    alto_minimo = 236  # px por bloque, para que se vean las fotos
    alto_error = 74    # px mínimos por error
    arriba = 46        # px del título del bloque, arriba de las fotos
    fila = 4
    for g in grupos:
        placas_g, probs = g["placas"], g["problemas"]
        n = len(probs)
        alto_bloque = max(alto_minimo, n * alto_error)
        alto_fila = alto_bloque / n
        ini, fin = fila, fila + n - 1
        prod = _producto(mailing, placas_g[0])

        for letra in "AB":
            ws.merge_cells(f"{letra}{ini}:{letra}{fin}")
            ws[f"{letra}{ini}"].border = _caja
            ws[f"{letra}{ini}"].alignment = Alignment(horizontal="center", vertical="top", wrap_text=True)

        lectura = placas_g[0].get("lectura") or {}
        nombre = (prod or {}).get("descripcion") or (lectura.get("producto") or {}).get("descripcion") \
            or etiquetas.get(placas_g[0]["nombre_archivo"], placas_g[0]["nombre_archivo"])
        if len(nombre) > 46:
            nombre = nombre[:44].rstrip(" ,.") + "…"
        cuantas = "1 placa" if len(placas_g) == 1 else f"{len(placas_g)} placas, el mismo arreglo"
        idx = (placas_g[0].get("match") or {}).get("indice")
        if len(placas_g) == 1 and bloques_por_producto.get(idx, 0) > 1:
            cuantas += " · ojo: distinta de sus otras adaptaciones"
        ws[f"A{ini}"] = CellRichText([
            TextBlock(InlineFont(sz=12, b=True, color=GRIS_TXT, rFont="Calibri"), nombre + "\n"),
            TextBlock(InlineFont(sz=10, i=True, color=GRIS_SUAVE, rFont="Calibri"), cuantas),
        ])
        jpg, w, h = _tira_de_placas(placas_g, etiquetas)
        ancho_a = _px_col(anchos["A"])
        # si la tira no entra en la columna, se muestra más chica (el archivo es el mismo)
        escala = min(1.0, (ancho_a - 16) / w, (alto_bloque - arriba - 10) / h)
        w, h = round(w * escala), round(h * escala)
        _poner(ws, jpg, w, h, 0, ini - 1, (ancho_a - w) / 2, arriba + (alto_bloque - arriba - h) / 2)

        ws[f"B{ini}"] = "Así está en el mailing" if prod else "No está en el mailing"
        ws[f"B{ini}"].font = Font(size=10, italic=True, color=GRIS_SUAVE)
        if prod:
            _centrada(ws, prod.get("recorte"), 1, ini - 1, _px_col(anchos["B"]), alto_bloque, margen_arriba=24)

        for k, f in enumerate(probs):
            r = fila + k
            ws.row_dimensions[r].height = alto_fila * 0.75  # px -> puntos
            placa_txt, mailing_txt = f.get("placa") or "", f.get("mailing") or ""
            ws[f"C{r}"] = c.nombre_campo(f["campo"])
            ws[f"C{r}"].font = Font(size=11, bold=True, color=GRIS_TXT)
            ws[f"C{r}"].fill = _fill(GRIS)
            ws[f"D{r}"] = _rico(placa_txt, mailing_txt, "placa")
            ws[f"D{r}"].fill = _fill(ROJO_F)
            ws[f"E{r}"] = _rico(mailing_txt, placa_txt, "mailing")
            ws[f"E{r}"].fill = _fill(VERDE_F)
            ws[f"F{r}"] = c.instruccion(f.get("estado", ""), placa_txt, mailing_txt)
            ws[f"F{r}"].font = Font(size=13, bold=True, color=AMBAR)
            ws[f"F{r}"].fill = _fill(AMBAR_F)
            for letra in "CDEF":
                ws[f"{letra}{r}"].alignment = Alignment(vertical="center", wrap_text=True, indent=1)
                ws[f"{letra}{r}"].border = _caja
        # línea más gruesa entre bloque y bloque, para que se lea como una tarjeta
        for letra in "ABCDEF":
            b = ws[f"{letra}{fin}"].border
            ws[f"{letra}{fin}"].border = Border(left=b.left, right=b.right, top=b.top, bottom=_grueso)
        fila = fin + 1

    ws.freeze_panes = "C4"
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 90
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.print_title_rows = "3:3"


def _hoja_todas(wb, validacion: dict, etiquetas: dict[str, str]) -> None:
    ws = wb.create_sheet("Todas las placas")
    for col, a in zip("ABCDE", (16, 46, 10, 22, 50)):
        ws.column_dimensions[col].width = a
    ws.merge_cells("A1:E1")
    ws["A1"] = "TODAS LAS PLACAS DE LA CAMPAÑA"
    ws["A1"].font = Font(size=16, bold=True, color="FFFFFF")
    ws["A1"].fill = _fill(AZUL)
    ws["A1"].alignment = Alignment(vertical="center", indent=1)
    ws.row_dimensions[1].height = 32
    _encabezado(ws, 2, [("A", "PLACA", GRIS_OSC), ("B", "PRODUCTO", GRIS_OSC), ("C", "FORMATO", GRIS_OSC),
                        ("D", "ESTADO", GRIS_OSC), ("E", "QUÉ TIENE", GRIS_OSC)])
    etiqueta_estado = {"ok": "Está bien", "diferencias": "Hay que corregirla", "avisos": "Para revisar",
                       "sin_match": "No está en el mailing", "error": "No se pudo leer"}
    color_estado = {"ok": "E8F6EC", "diferencias": "FDECEA", "avisos": "FFF4D6", "sin_match": "F1EEFF", "error": "F2F4F7"}
    mailing = validacion.get("mailing") or {}
    fila = 3
    for im in sorted(validacion["imagenes"], key=lambda x: x.get("orden", 0)):
        prod = _producto(mailing, im)
        probs = [f for f in im.get("filas") or [] if f.get("severidad") in ("error", "aviso")]
        valores = [
            etiquetas.get(im["nombre_archivo"], im["nombre_archivo"]),
            prod["descripcion"] if prod else "—",
            im.get("formato") or "",
            etiqueta_estado.get(im["estado"], im["estado"]),
            ", ".join(dict.fromkeys(c.nombre_campo(f["campo"]) for f in probs)) or "—",
        ]
        for letra, v in zip("ABCDE", valores):
            cel = ws[f"{letra}{fila}"]
            cel.value = v
            cel.fill = _fill(color_estado.get(im["estado"], "FFFFFF"))
            cel.border = _caja
            cel.font = Font(size=11, bold=(letra == "D"), color=GRIS_TXT)
            centrada = letra in "ACD"
            cel.alignment = Alignment(vertical="center", wrap_text=True,
                                      horizontal="center" if centrada else "left", indent=0 if centrada else 1)
        # un nombre largo (el vino) ocupa dos renglones: con la fila baja quedaba cortado
        ws.row_dimensions[fila].height = 36 if len(valores[1]) > 44 else 22
        fila += 1
    ws.freeze_panes = "A3"
    ws.sheet_view.showGridLines = False


def construir(validacion: dict) -> bytes:
    """El .xlsx de una validación.

    `validacion` tiene la forma del detalle de la API: {"mailing": {...},
    "imagenes": [{nombre_archivo, formato, estado, orden, filas, lectura, match,
    error, vista}]}. La vista puede venir en bytes o como data URI.
    NadaParaCorregir si todas las placas están bien."""
    if not any(i["estado"] != "ok" for i in validacion["imagenes"]):
        raise NadaParaCorregir("No hay nada para corregir: todas las placas están bien")
    etiquetas = c.etiquetas([i["nombre_archivo"] for i in validacion["imagenes"]])
    wb = Workbook()
    _hoja_correcciones(wb, validacion, etiquetas)
    _hoja_todas(wb, validacion, etiquetas)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

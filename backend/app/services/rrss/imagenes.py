"""Todo lo que toca píxeles en la validación de redes sociales: abrir las
placas, renderizar el mailing, recortar la zona donde CatTi vio algo y
achicar para guardar.

Está separado de catti.py a propósito: acá no hay IA ni base, así que se
puede probar con imágenes sintéticas. Y las cajas (`[x0, y0, x1, y1]` como
fracción 0..1 de la imagen) son un dato que devuelve el modelo: no hay que
confiar en ellas, `caja_valida` las revisa antes de que alguien recorte.
"""
import base64
import io

from PIL import Image, ImageDraw, ImageFont, ImageOps

# Proporciones que usan las redes. Se compara ancho/alto con tolerancia: una
# placa de 2250x2813 es "4:5" aunque 2250/2813 no dé exactamente 0.8.
FORMATOS: list[tuple[str, float]] = [("1:1", 1.0), ("4:5", 0.8), ("9:16", 9 / 16)]
_TOLERANCIA_FORMATO = 0.03

MAX_PAGINAS_MAILING = 12
_ANCHO_PAGINA_PX = 1600  # ancho al que se renderiza cada página del mailing


class ArchivoInvalido(ValueError):
    """El archivo no se pudo abrir como imagen o PDF -- mensaje apto para el usuario."""


def clasificar_formato(ancho: int, alto: int) -> str:
    """'1:1' | '4:5' | '9:16', o '<ancho>x<alto>' si no es ninguno de los tres
    (una placa con una proporción rara es algo que hay que mostrar, no ocultar)."""
    if alto <= 0:
        return f"{ancho}x{alto}"
    ratio = ancho / alto
    for nombre, esperado in FORMATOS:
        if abs(ratio - esperado) <= _TOLERANCIA_FORMATO:
            return nombre
    return f"{ancho}x{alto}"


def abrir_imagen(data: bytes) -> Image.Image:
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as exc:
        raise ArchivoInvalido("No pude abrir el archivo como imagen") from exc
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        fondo = Image.new("RGB", im.size, (255, 255, 255))
        fondo.paste(im, mask=im.split()[-1])
        return fondo
    return im.convert("RGB")


def jpeg(im: Image.Image, calidad: int = 85) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=calidad, optimize=True)
    return buf.getvalue()


def data_uri(jpeg_bytes: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode()


def base64_jpeg(im: Image.Image, calidad: int = 88) -> str:
    return base64.standard_b64encode(jpeg(im, calidad)).decode()


def reducir(im: Image.Image, lado_largo: int) -> Image.Image:
    """Achica sin agrandar nunca. Devuelve una copia."""
    mayor = max(im.size)
    if mayor <= lado_largo:
        return im.copy()
    escala = lado_largo / mayor
    return im.resize((max(1, round(im.width * escala)), max(1, round(im.height * escala))), Image.LANCZOS)


def ajustar_ancho(im: Image.Image, ancho: int) -> Image.Image:
    """Lleva la imagen a `ancho` px (achica o agranda) -- para leer letra chica."""
    if im.width == ancho:
        return im.copy()
    return im.resize((ancho, max(1, round(im.height * ancho / im.width))), Image.LANCZOS)


# --------------------------------------------------------------------------
# Cajas
# --------------------------------------------------------------------------

def caja_valida(caja) -> list[float] | None:
    """Una caja `[x0, y0, x1, y1]` en fracciones 0..1, o None si no sirve.

    El modelo a veces devuelve cajas en píxeles, invertidas o de área cero.
    Un recorte de basura es peor que no tener recorte: el usuario creería que
    ahí está el texto que se comparó."""
    try:
        x0, y0, x1, y1 = (float(v) for v in caja)
    except (TypeError, ValueError):
        return None
    if max(x0, y0, x1, y1) > 1.5:  # vino en píxeles o en otra escala
        return None
    x0, y0, x1, y1 = (min(1.0, max(0.0, v)) for v in (x0, y0, x1, y1))
    if x1 - x0 < 0.02 or y1 - y0 < 0.01:
        return None
    return [x0, y0, x1, y1]


def recortar(im: Image.Image, caja, margen: float = 0.015, ancho_max: int = 720) -> Image.Image | None:
    """Recorta `caja` (con un margen para no cortar letras) y la deja a
    `ancho_max` como mucho. None si la caja no es utilizable."""
    caja = caja_valida(caja)
    if caja is None:
        return None
    x0, y0, x1, y1 = caja
    izq = max(0, int((x0 - margen) * im.width))
    arr = max(0, int((y0 - margen) * im.height))
    der = min(im.width, int((x1 + margen) * im.width) + 1)
    aba = min(im.height, int((y1 + margen) * im.height) + 1)
    if der - izq < 8 or aba - arr < 8:
        return None
    recorte = im.crop((izq, arr, der, aba))
    if recorte.width > ancho_max:
        recorte = ajustar_ancho(recorte, ancho_max)
    return recorte


def marcar_caja(im: Image.Image, caja, color=(255, 45, 85), grosor: int = 6) -> Image.Image:
    """Copia de `im` con la caja dibujada -- para mostrar dónde está el
    producto dentro de la página entera del mailing."""
    salida = im.copy()
    caja = caja_valida(caja)
    if caja is None:
        return salida
    dib = ImageDraw.Draw(salida)
    x0, y0, x1, y1 = caja
    dib.rectangle(
        [x0 * im.width, y0 * im.height, x1 * im.width, y1 * im.height],
        outline=color, width=grosor,
    )
    return salida


# --------------------------------------------------------------------------
# Mailing
# --------------------------------------------------------------------------

def paginas_del_mailing(data: bytes, content_type: str, filename: str) -> list[Image.Image]:
    """Las páginas del mailing como imágenes de ~1600 px de ancho.

    Un PDF se renderiza con PyMuPDF (los textos del mailing van en curvas, así
    que no hay capa de texto que leer: hay que mirarlo). Una imagen suelta se
    toma como un mailing de una sola página."""
    nombre = (filename or "").lower()
    es_pdf = content_type == "application/pdf" or nombre.endswith(".pdf") or data[:5] == b"%PDF-"
    if not es_pdf:
        return [reducir(abrir_imagen(data), 2400)]

    import pymupdf  # import tardío: es una dependencia pesada que solo usa esta función

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ArchivoInvalido("No pude abrir el PDF del mailing") from exc
    try:
        if doc.page_count == 0:
            raise ArchivoInvalido("El PDF del mailing no tiene páginas")
        if doc.page_count > MAX_PAGINAS_MAILING:
            raise ArchivoInvalido(
                f"El mailing tiene {doc.page_count} páginas; el máximo es {MAX_PAGINAS_MAILING}"
            )
        paginas = []
        for pagina in doc:
            zoom = _ANCHO_PAGINA_PX / pagina.rect.width
            pix = pagina.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            paginas.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
        return paginas
    finally:
        doc.close()


def mitades_con_solape(im: Image.Image, solape: float = 0.04) -> list[tuple[Image.Image, float, float]]:
    """La mitad de arriba y la de abajo de una página, con un poco de solape
    para no partir un producto por el medio. Devuelve (imagen, y0, y1) con y
    como fracción de la página."""
    corte = im.height // 2
    margen = int(im.height * solape)
    return [
        (im.crop((0, 0, im.width, corte + margen)), 0.0, (corte + margen) / im.height),
        (im.crop((0, corte - margen, im.width, im.height)), (corte - margen) / im.height, 1.0),
    ]


def tira_inferior(im: Image.Image, fraccion: float = 0.12) -> Image.Image:
    """La franja de abajo, donde van los legales -- es letra chica y el modelo
    la lee mal si solo la ve dentro de la imagen entera."""
    return im.crop((0, int(im.height * (1 - fraccion)), im.width, im.height))


def con_grilla(im: Image.Image, paso: float = 0.1) -> Image.Image:
    """Copia de `im` con una grilla rotulada encima, para que el modelo pueda
    LEER coordenadas en vez de estimarlas a ojo (ver catti.localizar).

    Líneas fuertes cada `paso` y finas a la mitad; los valores se escriben en
    los cuatro bordes y en el medio, así en una página alta no hace falta
    seguir una línea durante 2000 px para saber a qué altura está."""
    base = im.convert("RGBA")
    capa = Image.new("RGBA", base.size, (0, 0, 0, 0))
    dib = ImageDraw.Draw(capa)
    ancho, alto = base.size
    try:
        fuente = ImageFont.load_default(size=max(14, ancho // 55))
    except TypeError:  # Pillow viejo, sin tamaño de fuente
        fuente = ImageFont.load_default()
    tam = getattr(fuente, "size", 12)
    magenta = (255, 0, 200)

    pasos = round(1 / paso)
    for i in range(1, pasos * 2):
        v = i * paso / 2
        fuerte = i % 2 == 0
        color = magenta + ((150,) if fuerte else (70,))
        x, y = round(v * ancho), round(v * alto)
        dib.line([(x, 0), (x, alto)], fill=color, width=2 if fuerte else 1)
        dib.line([(0, y), (ancho, y)], fill=color, width=2 if fuerte else 1)

    def rotulo(pos, texto):
        caja = dib.textbbox(pos, texto, font=fuente)
        dib.rectangle([caja[0] - 2, caja[1] - 1, caja[2] + 2, caja[3] + 1], fill=(255, 255, 255, 215))
        dib.text(pos, texto, font=fuente, fill=(200, 0, 150, 255))

    for i in range(1, pasos):
        v = i * paso
        texto = f"{v:.1f}"
        x, y = round(v * ancho), round(v * alto)
        for yy in (3, alto // 2 + 4, alto - tam - 6):
            rotulo((x + 3, yy), texto)
        for xx in (3, ancho // 2 + 4, ancho - tam * 2 - 6):
            rotulo((xx, y + 2), texto)
    return Image.alpha_composite(base, capa).convert("RGB")

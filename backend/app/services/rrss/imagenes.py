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

# Fuentes para lo que se dibuja con PIL (el pie de las miniaturas del Excel, la
# tira de la planilla). El servidor es Linux sin fuentes instaladas: ahí queda
# la que trae Pillow adentro, sin negrita. NO se simula la negrita con un trazo:
# con esa fuente el trazo rellena el hueco del 9 y "9:16" se leía "8:16".
_FUENTES = ("C:/Windows/Fonts/segoeui.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
_FUENTES_NEGRITA = ("C:/Windows/Fonts/segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


class ArchivoInvalido(ValueError):
    """El archivo no se pudo abrir como imagen o PDF -- mensaje apto para el usuario."""


def fuente(tam: int, negrita: bool = False) -> ImageFont.ImageFont:
    """La fuente para dibujar texto con PIL, en el tamaño pedido. Vive acá y no
    en quien dibuja porque la dibujan dos módulos (excel.py y planilla.py) y la
    lista de rutas es distinta en Windows que en el servidor."""
    for ruta in (_FUENTES_NEGRITA if negrita else _FUENTES):
        try:
            return ImageFont.truetype(ruta, tam)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:  # Pillow viejo, sin tamaño de fuente
        return ImageFont.load_default()


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

# Proporción de una carilla vertical suelta: A4, A5, carta y oficio andan todas
# entre 0,64 y 0,77, así que 0,71 sirve de patrón para cualquiera.
_PROPORCION_CARILLA = 0.707
# Cuántas carillas se aceptan en una hoja. Más que esto y lo que hay no es un
# pliego: es un banner largo o algo que no sabemos leer, y se deja entero.
_MAX_CARILLAS = 4


def carillas_en(ancho: float, alto: float) -> int:
    """Cuántas carillas verticales entran, a lo ancho, en una hoja.

    Un mailing se diseña en carillas verticales, pero se entrega impuesto: dos,
    tres o cuatro juntas en una misma hoja. En vez de preguntarse "¿es
    apaisada?", se mide cuántas carillas de proporción normal entran a lo
    ancho. Así funciona igual con un díptico, un tríptico o lo que venga, sin
    una regla por cada mailing.

    Una hoja vertical da 1 y no se toca nunca.
    """
    if alto <= 0 or ancho <= 0:
        return 1
    cuantas = round((ancho / alto) / _PROPORCION_CARILLA)
    return min(max(cuantas, 1), _MAX_CARILLAS)


def carillas_de(hoja: Image.Image, cuantas: int = 2) -> list[Image.Image]:
    """Parte una hoja impuesta en sus carillas, de izquierda a derecha.

    SIN solape, a propósito: entre dos carillas hay un pliegue y nada lo cruza,
    y un solape acá duplicaría productos -- cada carilla se lee por separado y
    sus productos se suman, no se deduplican (a diferencia de las mitades de
    una misma carilla, que las junta el propio modelo en una sola lectura).

    El caso que lo motivó: el mailing del 24 al 27 de setiembre de 2026 vino en
    hojas de 44 x 32 cm con DOS carillas al lado -- la izquierda "Rompe
    Precios" del 23 al 30 y la derecha "Los Rompe del Finde" del 24 al 27.
    Leídas como una sola página, con una sola campaña y una sola fecha, el
    modelo se quedaba con una y descartaba la otra: ninguna placa del finde
    encontraba su fila.
    """
    if cuantas <= 1:
        return [hoja]
    paso = hoja.width / cuantas
    return [
        hoja.crop((round(i * paso), 0, round((i + 1) * paso) if i < cuantas - 1 else hoja.width, hoja.height))
        for i in range(cuantas)
    ]


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
        # Se cuentan CARILLAS, no hojas: una hoja impuesta rinde varias, y cada
        # una es una lectura aparte.
        carillas_totales = sum(carillas_en(p.rect.width, p.rect.height) for p in doc)
        if carillas_totales > MAX_PAGINAS_MAILING:
            raise ArchivoInvalido(
                f"El mailing tiene {carillas_totales} páginas; el máximo es {MAX_PAGINAS_MAILING}"
            )
        paginas = []
        for pagina in doc:
            # El ancho se aplica por CARILLA, no por hoja: con un ancho fijo por
            # hoja, un pliego de dos quedaba a la mitad de resolución que un
            # mailing normal y la letra chica no se leía.
            cuantas = carillas_en(pagina.rect.width, pagina.rect.height)
            zoom = (_ANCHO_PAGINA_PX * cuantas) / pagina.rect.width
            pix = pagina.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            hoja = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            paginas.extend(carillas_de(hoja, cuantas))
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

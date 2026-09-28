"""Arma el Excel del informe semanal de pricing a partir de los JSONL que deja
scrapeo_total.py.

UNA FILA = un producto en UNA sucursal, para poder filtrar por sucursal con el
filtro de Excel. El JSONL guarda juntas las sucursales que comparten precio (así
ocupa 187 MB en vez de ~1 GB); acá se expanden de nuevo, una fila por sucursal.

Una hoja por CADENA, no por archivo: GDU trae Disco, Devoto y Géant, y cada una
va a su propia hoja. Si una cadena no entra en una hoja se parte en "(2)", "(3)"…
— Excel corta en 1.048.576 filas por hoja y Devoto sola son 1,98 millones.

Se escribe en modo write_only: las filas van al archivo a medida que se leen, sin
armar el libro entero en memoria.
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

log = logging.getLogger("scrapeo.excel")

COLUMNAS = [
    ("cadena", "Cadena", 14), ("sucursal", "Sucursal", 26),
    ("sku", "SKU", 14), ("barcode", "Código de barras", 17),
    ("nombre", "Producto", 60), ("marca", "Marca", 18), ("categoria", "Categoría", 24),
    ("precio", "Precio", 12), ("precio_lista", "Precio de lista", 14), ("moneda", "Moneda", 9),
    ("url", "Link", 46), ("bajado", "Bajado", 19),
]

MAX_FILAS_POR_HOJA = 1_000_000  # Excel corta en 1.048.576; se deja aire

AZUL = "1B3A6B"
GRIS = "F2F4F7"

# Notas fijas por cadena: el CONTEXTO que los números no dicen. Los números
# (cuántos con precio, de cuántos publicados) salen de lo bajado y de
# resumen.json — antes estaban escritos a mano acá y quedaban viejos: la hoja
# del 28/09 decía los totales del 21/09, y de FarmaShop afirmaba que "los que
# faltan no traen precio" cuando en realidad el corte era el timeout.
NOTAS = {
    "Disco": "Parte de GDU. 31 sucursales.",
    "Devoto": "Parte de GDU. 39 sucursales.",
    "Geant": "Parte de GDU. 2 sucursales.",
    "Ta-Ta": "Su API deja de devolver resultados pasadas unas páginas por sucursal. 15 sucursales.",
    "ElDorado": "Su API corta en la posición 2.499 de cada tienda; se juntan las 17.",
    "LOi": "Sin sucursales: precio único.",
    "FarmaShop": "Sin sucursales. Sus páginas tardan hasta 25 segundos: se baja con reintentos.",
    "Pigalle": "Sin sucursales.",
    "BlackDog": "Sin sucursales. Publica en DÓLARES: mirá la columna Moneda.",
    "Electrohogar": "Sin sucursales.",
    "CoverCompany": "Sin sucursales. Una fila por variante.",
}

# Hoja del Excel -> cadena tal como la baja scrapeo_total (para resumen.json).
_CADENA_FUENTE = {"Disco": "GDU", "Devoto": "GDU", "Geant": "GDU"}

# Cadenas cuyo tope lo pone SU sistema: aunque los números digan menos que el
# total, no es un corte nuestro. Se explican en NOTAS.
_PARCIALES_POR_SU_API = {"Ta-Ta", "ElDorado"}


def _miles(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _alcance(cadena: str, productos: dict, resumen: dict) -> str:
    """El texto de la columna Alcance, calculado con lo que se bajó."""
    n = len(productos.get(cadena) or ())
    fuente = _CADENA_FUENTE.get(cadena, cadena)
    total = (resumen.get(fuente) or {}).get("total_reportado")
    if fuente == "GDU":
        base = f"{_miles(n)} productos con precio"
        return f"Catálogo completo — {base} (GDU publica {_miles(total)})" if total else base
    if total:
        estado = "Catálogo completo" if n >= total * 0.97 else "PARCIAL"
        return f"{estado}: {_miles(n)} de {_miles(total)} publicados"
    if cadena in _PARCIALES_POR_SU_API:
        return f"PARCIAL: {_miles(n)} productos (el total real no lo dice su API)"
    return f"{_miles(n)} productos con precio"

# Por qué no está cada una de las que faltan. Un informe de precios que no dice
# qué NO mira se lee como si fuera todo el mercado.
SIN_CATALOGO = [
    ("Botiga", "Su catálogo sale del mismo Magento que FarmaShop y devuelve exactamente lo mismo: "
               "separarlas exige abrir producto por producto. Se deja afuera para no contar dos veces."),
    ("DIMM", "Su buscador exige un término; no expone forma de listar el catálogo."),
    ("Stienda", "Igual que DIMM (misma plataforma)."),
    ("Zona Tecno", "Igual que DIMM (misma plataforma)."),
    ("AMV", "Igual que DIMM (misma plataforma)."),
    ("Fama", "Buscador PHP propio: sin término no devuelve nada."),
    ("Estación Hogar", "Igual que Fama (misma plataforma)."),
]

# Solo productos activos: los inactivos son los que el sitio no muestra (sin
# stock, discontinuados). Confirmado con Ivan el 21/09/2026.
NOTA_ACTIVOS = ("Solo productos ACTIVOS: los que el sitio muestra a la venta. GDU además publica "
                "17.420 inactivos (sin stock o discontinuados) que quedan afuera a propósito.")


def _limpiar(valor):
    """Excel no acepta caracteres de control en una celda, y openpyxl levanta
    IllegalCharacterError al guardar -- con el libro entero ya armado. Pasó de
    verdad con un producto de CoverCompany."""
    if isinstance(valor, str):
        return ILLEGAL_CHARACTERS_RE.sub("", valor)
    return valor


def _sucursales_gdu() -> dict:
    """{(cadena, nombre_sucursal): branch_id} — para rearmar el link de GDU, que
    lleva la sucursal adentro (?sc=<id>). Verificado: ningún nombre se repite
    dentro de su cadena."""
    try:
        from app.services.scraper import gdu_rest as gdu
        return {(m["cadena"], m["nombre"]): bid for bid, m in gdu._load_branch_meta().items()}
    except Exception as exc:
        log.warning("No pude leer las sucursales de GDU (%s): los links de GDU van sin ?sc=", exc)
        return {}


def _expandir(reg: dict, sucursales_gdu: dict) -> list:
    """Una fila por sucursal. Sin sucursales (LOi, FarmaShop…), una sola fila."""
    detalle = (reg.get("sucursales_detalle") or "").strip()
    if not detalle:
        return [{**reg, "sucursal": ""}]
    filas = []
    for nombre in detalle.split(", "):
        nombre = nombre.strip()
        if not nombre:
            continue
        fila = {**reg, "sucursal": nombre}
        bid = sucursales_gdu.get((reg.get("cadena"), nombre))
        if bid and reg.get("url"):
            # el link de GDU apunta a UNA sucursal: se reescribe para que sea la de esta fila
            fila["url"] = reg["url"].split("?sc=")[0] + f"?sc={bid}"
        filas.append(fila)
    return filas


def _leer(ruta: Path):
    """Las filas de un JSONL, sin repetidas.

    El catálogo de una cadena puede reordenarse mientras se pagina y repetir un
    producto (580 repetidos en FarmaShop el 28/09). El scraper ya no los deja
    pasar, pero los archivos bajados con la versión anterior los traen: acá se
    filtran igual, así --solo-excel también sale limpio."""
    vistos: set = set()
    with ruta.open(encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            try:
                reg = json.loads(linea)
            except json.JSONDecodeError:
                continue  # última línea a medio escribir si se cortó el proceso
            clave = (reg.get("cadena"), reg.get("sku"), reg.get("precio"), reg.get("sucursales_detalle"))
            if clave in vistos:
                continue
            vistos.add(clave)
            yield reg


def _encabezado(ws) -> None:
    from openpyxl.cell import WriteOnlyCell
    fila = []
    for _, titulo, _ancho in COLUMNAS:
        cel = WriteOnlyCell(ws, value=titulo)
        cel.font = Font(bold=True, color="FFFFFF")
        cel.fill = PatternFill("solid", fgColor=AZUL)
        cel.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
        fila.append(cel)
    ws.append(fila)
    ws.freeze_panes = "A2"
    for i, (_, _, ancho) in enumerate(COLUMNAS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = ancho


class HojasDeCadena:
    """Las hojas de una cadena: abre una nueva cada MAX_FILAS_POR_HOJA."""

    def __init__(self, wb: Workbook, cadena: str):
        self.wb, self.cadena = wb, cadena
        self.parte, self.en_hoja, self.total = 0, MAX_FILAS_POR_HOJA, 0
        self.ws = None

    def append(self, valores: list) -> None:
        if self.en_hoja >= MAX_FILAS_POR_HOJA:
            self.parte += 1
            nombre = self.cadena[:31] if self.parte == 1 else f"{self.cadena[:26]} ({self.parte})"
            self.ws = self.wb.create_sheet(nombre)
            _encabezado(self.ws)
            self.en_hoja = 0
        self.ws.append(valores)
        self.en_hoja += 1
        self.total += 1


def armar(carpeta: Path, destino: Path) -> Path:
    jsonls = sorted(carpeta.glob("*.jsonl"))
    if not jsonls:
        raise SystemExit(f"No hay nada bajado en {carpeta}")
    sucursales_gdu = _sucursales_gdu()

    # Lo que reportó la corrida (cuántos publica cada cadena): para la Cobertura.
    resumen: dict = {}
    if (carpeta / "resumen.json").exists():
        try:
            resumen = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("resumen.json ilegible (%s): la Cobertura sale sin totales", exc)

    # Primera pasada: cuántas filas por cadena, para ordenar las hojas de mayor a
    # menor y que el resumen salga con los números antes de escribir nada.
    log.info("Contando…")
    cuenta: dict = {}
    productos: dict = {}
    for ruta in jsonls:
        for reg in _leer(ruta):
            if reg.get("precio") is None:
                continue
            cadena = reg.get("cadena") or ruta.stem
            cuenta[cadena] = cuenta.get(cadena, 0) + max(1, reg.get("sucursales") or 1)
            productos.setdefault(cadena, set()).add(reg.get("sku"))
    orden = sorted(cuenta, key=lambda c: -cuenta[c])
    for c in orden:
        log.info("  %-14s %10s filas  %8s productos", c, f"{cuenta[c]:,}", f"{len(productos[c]):,}")

    wb = Workbook(write_only=True)
    hoja_resumen = wb.create_sheet("Resumen")
    hojas = {c: HojasDeCadena(wb, c) for c in orden}

    for ruta in jsonls:
        for reg in _leer(ruta):
            if reg.get("precio") is None:
                continue
            for fila in _expandir(reg, sucursales_gdu):
                cadena = fila.get("cadena") or ruta.stem
                hojas[cadena].append([_limpiar(fila.get(c)) for c, _, _ in COLUMNAS])
        log.info("Escrito: %s", ruta.stem)

    for c in orden:
        log.info("Excel: %-14s %10s filas en %d hoja(s)", c, f"{hojas[c].total:,}", hojas[c].parte)

    _llenar_resumen(hoja_resumen, orden, cuenta, productos, hojas)
    _hoja_cobertura(wb, orden, productos, resumen)
    destino.parent.mkdir(parents=True, exist_ok=True)
    log.info("Guardando…")
    wb.save(destino)
    log.info("Excel listo: %s (%.0f MB)", destino, destino.stat().st_size / 1e6)
    return destino


def _llenar_resumen(ws, orden, cuenta, productos, hojas) -> None:
    from openpyxl.cell import WriteOnlyCell

    def titulo(texto):
        cel = WriteOnlyCell(ws, value=texto)
        cel.font = Font(bold=True, size=14, color="FFFFFF")
        cel.fill = PatternFill("solid", fgColor=AZUL)
        return cel

    def cabecera(texto):
        cel = WriteOnlyCell(ws, value=texto)
        cel.font = Font(bold=True)
        cel.fill = PatternFill("solid", fgColor=GRIS)
        return cel

    for i, ancho in enumerate((24, 16, 18, 10), start=1):
        ws.column_dimensions[get_column_letter(i)].width = ancho
    ws.append([titulo("PRECIOS DE LA COMPETENCIA — SCRAPEO TOTAL")])
    ws.append([f"Bajado el {datetime.now():%d/%m/%Y a las %H:%M}"])
    ws.append([])
    ws.append([cabecera(x) for x in ("Cadena", "Filas", "Productos", "Hojas")])
    for c in orden:
        ws.append([c, cuenta[c], len(productos[c]), hojas[c].parte])
    ws.append([])
    ws.append([cabecera("TOTAL"), sum(cuenta.values()), sum(len(p) for p in productos.values()), ""])
    ws.append([])
    ws.append(["UNA FILA = un producto en UNA sucursal. Se filtra por la columna Sucursal."])
    ws.append(["Disco, Devoto y Géant van en hojas separadas: son tres cadenas distintas."])
    ws.append([f"Una cadena que pasa el millón de filas se parte en (2), (3)… ({MAX_FILAS_POR_HOJA:,} por hoja)."])
    ws.append([NOTA_ACTIVOS])
    ws.append(["Mirá la hoja Cobertura: no todas las cadenas se pueden bajar enteras."])


def _hoja_cobertura(wb, orden, productos: dict, resumen: dict) -> None:
    from openpyxl.cell import WriteOnlyCell
    ws = wb.create_sheet("Cobertura")
    for i, ancho in enumerate((20, 42, 76), start=1):
        ws.column_dimensions[get_column_letter(i)].width = ancho

    def cabecera(texto):
        cel = WriteOnlyCell(ws, value=texto)
        cel.font = Font(bold=True, color="FFFFFF")
        cel.fill = PatternFill("solid", fgColor=AZUL)
        return cel

    ws.append([cabecera(x) for x in ("Cadena", "Alcance", "Aclaración")])
    for c in orden:
        ws.append([c, _alcance(c, productos, resumen), NOTAS.get(c, "")])
    ws.append([])
    ws.append([cabecera("Qué productos se incluyen")])
    ws.append(["", NOTA_ACTIVOS])
    ws.append([])
    ws.append([cabecera("Cadenas que NO están"), cabecera(""), cabecera("Por qué")])
    for nombre, motivo in SIN_CATALOGO:
        ws.append([nombre, "", motivo])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    carpeta = Path(sys.argv[1] if len(sys.argv) > 1 else Path.home() / "scrapeo_total")
    destino = Path(sys.argv[2]) if len(sys.argv) > 2 else carpeta / f"Precios competencia {datetime.now():%Y-%m-%d}.xlsx"
    armar(carpeta, destino)

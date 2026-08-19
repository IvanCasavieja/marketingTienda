"""Parseo de Excel/CSV — motor de datos para cenefas v2."""
import io
import re
import unicodedata

import openpyxl

from app.services.cenefas.formatters import (
    fmt_price,
    parse_price_raw,
    parse_combo,
    DELI_SUBCATS,
    NO_UNIDAD_SUBCATS,
)

# ---------------------------------------------------------------------------
# Variables canónicas del sistema — nomenclatura estándar camelCase
# ---------------------------------------------------------------------------
#
# Estas son TODAS las variables que el sistema reconoce.
# En el Excel, usar estos nombres como títulos de columna.
# En los PPTX, usar <<variableName>> con el mismo nombre.
# Todas son opcionales — se usa lo que el Excel contenga.
#
CANONICAL_VARS: frozenset[str] = frozenset({
    "precioActual",       # precio principal formateado ("$1.234")
    "precioAnterior",     # precio tachado / anterior ("$1.500")
    "precioBanco",        # precio con beneficio bancario ("$1.000")
    "banco",              # nombre o logo del banco (texto o imagen)
    "descripcion",        # nombre del producto
    "mecanica",           # mecánica / tipo de oferta ("Precio Final", "2X$X"...)
    "aclaracion",         # texto de aclaración por producto (= "aclaracion1", ver alias abajo)
    "aclaracion2",        # segunda aclaración (alias Excel-friendly de segundaAclaracion)
    "aclaracion3",        # tercera aclaración — plantillas "Rompe Precios" con 3 slots de legales
    "segundaAclaracion",  # segunda aclaración (ej: aviso de alcohol)
    "vigencia",           # texto de vigencia
    "codigoSKU",          # código de artículo
    "dia",                # día de la semana
    "mes",                # mes
    "año",                # año
    "moneda",             # prefijo de moneda ("$" o "U$S")
    "categoria",          # categoría del producto
    "subCategoria",       # subcategoría del producto
    "descuento",          # TRUE/FALSE para reglas de visibilidad
    "precioP",            # Parrilla y Vinos: precio principal -- crudo, SIN auto-formato de
                          # "$" (el "$" ya está fijo como texto estático en el PPTX; si
                          # este también llevara "$" quedaría duplicado -- "$$399").
    "precio4x3",          # Parrilla y Vinos: nivel de precio por cantidad 4x3 -- entero/decimal
    "precio5x3",          # se separan en dos placeholders del PPTX vía transform
    "precio6x3",          # price_integer/price_decimal (ver pptx_importer.py), no acá.

    # ── Sistema unificado (Rompe Precios + Parrilla y Vinos, desde 08/2026) ──
    # A pedido explícito: de acá en más el nombre de columna en el Excel, el
    # placeholder en el PPTX y la variable canónica son SIEMPRE el mismo
    # string -- sin alias ni traducción de un nombre a otro (a diferencia del
    # resto de este archivo). No reemplazan nada de lo que Parrilla y Vinos
    # ya tenía (precioP/precio4x3/5x3/6x3 arriba siguen andando igual) --son
    # variables ADICIONALES, opcionales, pensadas para diseños nuevos.
    "precioOferta",        # precio de oferta, sin "$" (mismo criterio que precioP -- el
                          # "$" va fijo como texto estático en el diseño)
    "oferta1",             # niveles de oferta genéricos (reemplazan conceptualmente a
    "oferta2",             # precio4x3/5x3/6x3 para diseños que no atan la oferta a una
    "oferta3",             # cantidad fija tipo "4x3")
    "decimalPrecioP",      # parte decimal de precioP/precioOferta/ofertaN como columna
    "decimalPrecioOferta", # PROPIA del Excel (no un transform sobre la misma columna,
    "decimalOferta1",      # a diferencia de <<decimal4x3>> con precio4x3 arriba) -- para
    "decimalOferta2",      # diseños que ya traen el entero y el decimal en columnas
    "decimalOferta3",      # separadas.
})

# Variables que contienen precios — los números se auto-formatean con prefix de moneda
_PRICE_VARS: frozenset[str] = frozenset({"precioActual", "precioAnterior", "precioBanco"})

# Igual que _PRICE_VARS (se normalizan con parse_price_raw/fmt_price al
# formato uruguayo "1.234,56"), pero SIN el prefijo "$"/"U$S " -- Parrilla y
# Vinos ya tiene el "$" fijo como texto estático en el PPTX. Sin este paso,
# una celda de Excel cargada como NÚMERO (no texto) le llega a Python como
# float y el "," se convierte en "." (101.5 en vez de 101,50) -- el split
# entero/decimal de component_renderer.py::apply_transform busca una coma,
# así que sin normalizar acá el precio no se partía nunca (confirmado
# renderizando la plantilla real con datos de prueba).
_PRICE_VARS_SIN_PREFIJO: frozenset[str] = frozenset({
    "precioP", "precio4x3", "precio5x3", "precio6x3",
    "precioOferta", "oferta1", "oferta2", "oferta3",
    "decimalPrecioP", "decimalPrecioOferta", "decimalOferta1", "decimalOferta2", "decimalOferta3",
})

# ---------------------------------------------------------------------------
# Normalización de headers Excel
# ---------------------------------------------------------------------------

def _norm(name: str) -> str:
    """Normaliza para lookup: sin acentos, sin espacios/guiones, minúsculas."""
    s = unicodedata.normalize("NFD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"[\s_\-]+", "", s).lower()


# Mapa: header normalizado → nombre canónico de variable
# Soporta tanto nombres nuevos como legacy para backward compat
_ALIASES: dict[str, str] = {
    # ── Nuevos nombres canónicos (pasan directo) ──────────────────────────
    "precioactual":       "precioActual",
    "precioanterior":     "precioAnterior",
    "preciobanco":        "precioBanco",
    "banco":              "banco",
    "descripcion":        "descripcion",
    "nombredearticulo":   "descripcion",  # excel real de Parrilla y Vinos — sin colisión con otro destino
    "nombredelarticulo":  "descripcion",  # variantes probables de la misma columna real -- no hay forma
    "nombrearticulo":     "descripcion",  # de confirmar el texto exacto del excel sin verlo, así que se
    "nombredeproducto":   "descripcion",  # cubren las más probables en vez de una sola apuesta.
    "nombreproducto":     "descripcion",
    "titulo":             "mecanica",    # backward compat: columna "titulo" → var "mecanica"
    "mecanica":           "mecanica",
    "aclaracion":         "aclaracion",
    "aclaracion1":        "aclaracion",   # alias amigable — misma variable que "aclaracion"
    "aclaracion2":        "aclaracion2",
    "aclaracion3":        "aclaracion3",
    "segundaaclaracion":  "segundaAclaracion",
    "vigencia":           "vigencia",
    "codigosku":          "codigoSKU",
    "dia":                "dia",
    "mes":                "mes",
    "ano":                "año",        # ñ → n tras strip de acentos
    "moneda":             "moneda",
    "categoria":          "categoria",
    "subcategoria":       "subCategoria",
    "descuento":          "descuento",

    # ── Sistema unificado (Rompe Precios + Parrilla y Vinos) -- mapeo directo,
    # el nombre de columna del Excel es siempre igual a la variable canónica.
    "preciop":             "precioP",
    "preciooferta":        "precioOferta",
    "oferta1":             "oferta1",
    "oferta2":             "oferta2",
    "oferta3":             "oferta3",
    "decimalpreciop":      "decimalPrecioP",
    "decimalpreciooferta": "decimalPrecioOferta",
    "decimaloferta1":      "decimalOferta1",
    "decimaloferta2":      "decimalOferta2",
    "decimaloferta3":      "decimalOferta3",

    # ── Legacy Excel → canónico ───────────────────────────────────────────
    "precio":             "precioActual",
    "precios":            "precioActual",
    "regular":            "precioAnterior",   # excel de "rompe precios del finde"
    "scotland20%":        "precioBanco",
    "scotia20%":          "precioBanco",
    "pbanco":             "precioBanco",
    "preciobanco":        "precioBanco",
    "codigo":             "codigoSKU",
    "diasemana":          "dia",
    "diasemana":          "dia",
    "platodia":           "dia",
    "platodeldia":        "dia",
    "otraaclaracion":     "segundaAclaracion",

    # ── Triggers internos para compatibilidad con lógica legacy ───────────
    # (las columnas OFERTADET y OFERTA activan el compute de mecanica/titulo)
    "ofertadet":          "_ofertadet",
    "oferta":             "_oferta",
    "subcategoria":       "_subcategoria_legacy",  # needed for DELI logic
    "comprador":          "_comprador",
}

# Override de alias solo para Parrilla y Vinos (ver load_products_from_bytes,
# parámetro `destino`) -- "regular" y "oferta" ya significan otra cosa en el
# excel de Rompe Precios/Redexpres (arriba), así que no se puede resolver
# con un solo diccionario global. Acá "regular" es el precio PRINCIPAL (no
# el anterior) y "oferta" es el nivel de precio 4x3 (nombre real de la
# columna en el excel de Parrilla y Vinos, aunque confunda con el trigger
# de combos de arriba -- nada que ver, es solo coincidencia de nombre).
# "regular" mapea a precioP (NO precioActual) a propósito: precioActual se
# auto-formatea con "$" en el passthrough de abajo, y el "$" de esta
# plantilla ya es texto fijo en el PPTX -- si el valor también trajera "$"
# quedaría duplicado ("$$399"), verificado renderizando la plantilla real.
#
# "ofertadet"/"comprador"/"subcategoria" también se desactivan acá: el Excel
# real de Parrilla y Vinos no es una planilla armada a medida para cenefas,
# es una exportación más amplia de gestión de categorías (tiene columnas
# como COMPRADOR/PROVEEDOR/VENTA $/FORECASTUNI/OBJETIVO ajenas a esto) que
# arrastra columnas con estos mismos nombres pero un significado total y
# confirmadamente distinto (ver caso real: "OFERTADET"="M x N" en una fila
# que no tiene NADA que ver con la mecánica de combos de Redexpres). Sin
# este bloqueo, esas columnas disparaban la lógica legacy de
# combos/fiambrería pensada para Redexpres, pisando precios de Parrilla y
# Vinos que ya se resuelven solos con precioP/precio4x3/5x3/6x3.
_ALIASES_PARRILLA_VINOS_OVERRIDE: dict[str, str] = {
    "regular":      "precioP",
    "oferta":       "precio4x3",
    "4x3":          "precio4x3",  # alias adicional -- misma columna, el export a veces la nombra "4x3" en vez de "oferta"
    "5x3":          "precio5x3",
    "6x3":          "precio6x3",
    "ofertadet":    "_ignoradoParrillaOfertadet",
    "comprador":    "_ignoradoParrillaComprador",
    "subcategoria": "_ignoradoParrillaSubcategoria",
    # La columna de código de SKU en el export real de gestión varía entre
    # descargas -- a veces "Codigo" (ya cubierto por el alias global de
    # abajo), a veces "Articulo" a secas (sin "Nombre" adelante, que ya
    # significa otra cosa -- ver "nombrearticulo"→descripcion). Confirmado
    # con el usuario: cualquiera de las dos puede aparecer, tienen que
    # resolver las dos al mismo código.
    "articulo":     "codigoSKU",
}

# Columnas que, si están presentes, sirven para detectar la fila de headers
_DETECTION_NORMS = {"ofertadet", "descripcion", "precios", "precio", "precioactual", "codigo", "moneda", "dia"}

# El export real de gestión para Parrilla y Vinos no siempre trae "regular"
# como nombre de columna del precio principal -- a veces sale directo de
# gestión sin renombrar, con el nombre de pantalla de ese sistema, "PVP
# GESTION" seguido de la fecha de la semana (ej. "PVP GESTION 14/08"), que
# cambia en cada descarga. Un alias exacto en el diccionario no alcanza acá
# porque la fecha nunca es la misma -- se matchea por prefijo, y solo para
# este destino (ver load_products_from_bytes).
_RE_PVP_GESTION = re.compile(r"^pvpgestion")


# ---------------------------------------------------------------------------
# Procesamiento de fila
# ---------------------------------------------------------------------------

def process_row(
    row:         tuple,
    h:           dict,       # var_name → col_idx
    vigencia:    str = "",
    aclaracion:  str = "",
    otra_alcohol:str = "",
    banco:       str = "",
) -> dict:
    """Convierte una fila de Excel en un dict de variables para el renderer."""

    # Leer moneda primero (necesaria para formatear precios)
    moneda  = "$"
    if "moneda" in h:
        m = h["moneda"]
        if m < len(row) and row[m]:
            moneda = str(row[m]).strip()
    prefix = "U$S " if moneda == "U$S" else "$"

    result: dict[str, str] = {}

    # ── Passthrough + auto-formato para columnas canónicas ─────────────────
    for var_name, col_idx in h.items():
        if var_name.startswith("_"):
            continue  # columna interna — se procesa abajo
        if col_idx >= len(row):
            continue
        val = row[col_idx]
        if val is None or (isinstance(val, str) and not val.strip()):
            result[var_name] = ""
        elif var_name in _PRICE_VARS:
            pv = parse_price_raw(val)
            result[var_name] = (prefix + fmt_price(pv)) if pv > 0 else str(val).strip()
        elif var_name in _PRICE_VARS_SIN_PREFIJO:
            # parse_price_raw() solo matchea el run de dígitos inicial e
            # ignora en silencio lo que venga después (ej. "4x350" -> 4.0) --
            # inofensivo en los demás usos de parse_price_raw (siempre reciben
            # la parte ya separada de un combo tipo "Nx$precio"), pero acá el
            # valor crudo de la celda todavía puede traer esa notación:
            # "oferta" es históricamente la columna de combos de Redexpres
            # (ver _ALIASES/"_oferta" arriba), así que una fila cargada con el
            # hábito viejo ("4x350" en vez de un precio limpio "350") se
            # truncaba a "$4" sin ningún indicio de que estaba mal. Si el
            # valor crudo no es un precio limpio de punta a punta, se deja tal
            # cual (mismo fallback que ya existía para pv<=0) para que el
            # error quede visible en vez de mostrar un precio falso.
            val_str = str(val).strip()
            looks_like_price = isinstance(val, (int, float)) or bool(re.fullmatch(r"\d[\d.,]*", val_str))
            pv = parse_price_raw(val) if looks_like_price else 0.0
            result[var_name] = fmt_price(pv) if pv > 0 else val_str
        else:
            result[var_name] = str(val).strip()

    # ── Lógica de oferta según OFERTADET ─────────────────────────────────
    _nx_applied = False

    _ofertadet_raw = ""
    if "_ofertadet" in h and h["_ofertadet"] < len(row):
        _ofertadet_raw = str(row[h["_ofertadet"]] or "").strip()

    _oferta_raw = ""
    if "_oferta" in h and h["_oferta"] < len(row):
        _oferta_raw = str(row[h["_oferta"]] or "").strip()

    if "_ofertadet" in h:
        if _ofertadet_raw.lower() == "combo":
            # Combo: OFERTA "6x160" → precio grande=160 (de OFERTA), mecanica usa columna precio
            _m_nx = re.match(r"^(\d+)\s*[xX]\s*\$?\s*([\d.,]+)\s*$", _oferta_raw)
            if _m_nx:
                _cantidad        = _m_nx.group(1)
                _precio_oferta   = parse_price_raw(_m_nx.group(2))   # 160 — precio grande
                _precio_columna  = result.get("precioActual", "")    # $53 — para mecanica
                result["oferta"]       = f"{_cantidad}x"
                result["precioActual"] = prefix + fmt_price(_precio_oferta)
                result["mecanica"]     = f"Comprando {_cantidad}, {_precio_columna} la unidad."
                _nx_applied = True

        elif re.search(r"m\s*[xX×]\s*n", _ofertadet_raw, re.IGNORECASE):
            # M x N: "3x2"/"2x1" va en el slot de precio; oferta queda vacío
            _precio_original  = result.get("precioActual", "")
            result["oferta"]       = ""
            result["precioActual"] = _oferta_raw   # "3x2" ocupa el lugar del precio
            _m_first = re.match(r"^(\d+)", _oferta_raw)
            if _m_first:
                _cantidad = _m_first.group(1)
                result["mecanica"] = f"Comprando {_cantidad}, {_precio_original} la unidad."
            _nx_applied = True

        elif not _ofertadet_raw:
            # Vacío: solo precio de columna, sin oferta ni mecanica
            result["oferta"]   = ""
            result["mecanica"] = ""
            _nx_applied = True

        if result.get("categoria") == "BEBIDAS CON ALCOHOL" and _nx_applied:
            result["segundaAclaracion"] = result.get("segundaAclaracion") or otra_alcohol

    elif "_oferta" in h:
        # Sin OFERTADET: backward compat — intentar Nx$precio en OFERTA
        _m_nx = re.match(r"^(\d+)\s*[xX]\s*\$?\s*([\d.,]+)\s*$", _oferta_raw)
        if _m_nx:
            _cantidad   = _m_nx.group(1)
            _unit_price = parse_price_raw(_m_nx.group(2))
            if not result.get("precioActual"):
                result["precioActual"] = prefix + fmt_price(_unit_price)
            result["oferta"]   = f"{_cantidad}x"
            result["mecanica"] = f"Comprando {_cantidad}, {result['precioActual']} la unidad."
            if result.get("categoria") == "BEBIDAS CON ALCOHOL":
                result["segundaAclaracion"] = result.get("segundaAclaracion") or otra_alcohol
            _nx_applied = True

    # ── Otros valores de OFERTADET → lógica legacy ────────────────────────
    if "_ofertadet" in h and not _nx_applied:
        _apply_legacy_compute(row, h, result, prefix, moneda, otra_alcohol)

    # ── Fallback a parámetros globales ────────────────────────────────────
    if not result.get("vigencia"):
        result["vigencia"] = vigencia
    if not result.get("aclaracion"):
        result["aclaracion"] = aclaracion
    if not result.get("banco"):
        result["banco"] = banco

    # ── COMPRADOR: fiambrería + 100g → precio ÷ 10 (kg → por 100g) ──────────
    _comprador_raw = ""
    if "_comprador" in h and h["_comprador"] < len(row):
        _comprador_raw = str(row[h["_comprador"]] or "").strip()
    if re.search(r"fiambr", _comprador_raw, re.IGNORECASE):
        desc = result.get("descripcion", "")
        if re.search(r"100\s*g", desc, re.IGNORECASE):
            for price_key in ("precioActual", "precioAnterior"):
                pv_str = result.get(price_key, "")
                if pv_str:
                    # precioActual ya está formateado como "$390"; quitar prefijo antes de parsear
                    clean = re.sub(r"^[^\d]*", "", pv_str)
                    pv = parse_price_raw(clean)
                    if pv > 0:
                        result[price_key] = prefix + fmt_price(round(pv / 10, 2))

    # ── Aliases backward compat (para templates ya importados con nombres viejos) ──
    _backfill_legacy_keys(result)

    return result


def _apply_legacy_compute(
    row: tuple, h: dict, result: dict, prefix: str, moneda: str, otra_alcohol: str
) -> None:
    """Computa título y mecánica de oferta a partir de OFERTADET/OFERTA/PRECIO."""
    ofertadet     = str(row[h["_ofertadet"]] or "").strip() if h["_ofertadet"] < len(row) else "Precio fijo"
    precio_raw    = row[h.get("precioActual", -1)] if "precioActual" in h and h["precioActual"] < len(row) else 0
    oferta_raw    = str(row[h["_oferta"]] or "").strip() if "_oferta" in h and h["_oferta"] < len(row) else ""
    precio        = parse_price_raw(precio_raw)
    desc          = result.get("descripcion", "")
    cat           = result.get("categoria", "")
    subcat        = result.get("subCategoria", "") or (
        str(row[h["_subcategoria_legacy"]] or "").strip() if "_subcategoria_legacy" in h else ""
    )
    cod           = result.get("codigoSKU", "")

    titulo_val  = ""
    mecanica    = ""
    unidad      = ""

    if ofertadet == "Combo":
        p1_str, amount = parse_combo(oferta_raw)
        result["precioActual"] = prefix + fmt_price(amount)
        qty = p1_str[:-1] if p1_str.endswith("X") else "2"
        mecanica = f"Comprando {qty}, {prefix}{fmt_price(precio)} c/u"
        titulo_val = p1_str

    elif ofertadet == "M x N":
        result["precioActual"] = prefix + fmt_price(precio)
        mecanica = f"Comprando 2, {prefix}{fmt_price(precio)} c/u"
        titulo_val = "M x N"

    elif re.search(r"2da\s+al\s+50|2da\s+50", ofertadet, re.IGNORECASE):
        result["precioActual"] = prefix + fmt_price(precio)
        mecanica = "Comprando 2, la 2da al 50% OFF"
        titulo_val = "2DA AL 50%"

    else:
        precio_val = precio
        if subcat in DELI_SUBCATS:
            dl = desc.lower()
            has_kg = ". kg" in dl or " kg" in dl or dl.endswith("kg") or "100g" in dl
            if has_kg or subcat == "FIAMBRES":
                precio_val = precio / 10
                if has_kg:
                    desc = re.sub(r"\.\s*[Kk]g\b", ". 100g", desc)
                    desc = re.sub(r"\s+[Kk]g\b", " 100g", desc)
                    result["descripcion"] = desc
        result["precioActual"] = prefix + fmt_price(precio_val)
        titulo_val = "Precio Final"

    is_multi_sku = bool(cod and ("/" in cod or re.search(r"\d\s*[-–—]\s*\d", cod)))
    if is_multi_sku and ofertadet in ("Precio fijo", "% descuento"):
        if subcat not in NO_UNIDAD_SUBCATS:
            unidad = "unidad"

    if not result.get("mecanica"):
        result["mecanica"] = titulo_val
    result["unidadPrecio"]    = unidad
    result["unidadPBanco"]    = "unidad" if is_multi_sku else ""
    if cat == "BEBIDAS CON ALCOHOL":
        result["segundaAclaracion"] = result.get("segundaAclaracion") or "Prohibida la venta de bebidas alcohólicas a menores de 18 años"


def _backfill_legacy_keys(result: dict) -> None:
    """Agrega claves con nombres legacy para que templates viejos sigan funcionando."""
    _map = {
        # old key          canonical key
        "precio":          "precioActual",
        "precio_banco":    "precioBanco",
        "p1":              "mecanica",    # legacy P1 → mecanica
        "titulo":          "mecanica",   # legacy titulo → mecanica
        "code":            "codigoSKU",
        "otra_aclaracion": "segundaAclaracion",
        "unidad":          "unidadPrecio",
        "unidad_precio":   "unidadPrecio",
        "unidad_pbanco":   "unidadPBanco",
    }
    for old, new in _map.items():
        if old not in result:
            result[old] = result.get(new, "")


# ---------------------------------------------------------------------------
# Carga desde Excel
# ---------------------------------------------------------------------------

def load_products_from_bytes(
    excel_bytes:  bytes,
    vigencia:     str = "",
    aclaracion:   str = "",
    otra_alcohol: str = "",
    banco:        str = "",
    destino:      str | None = None,
) -> list[dict]:
    # destino solo importa para Parrilla y Vinos hoy -- ver
    # _ALIASES_PARRILLA_VINOS_OVERRIDE arriba. Cualquier otro valor (o None)
    # usa el diccionario global de siempre, sin cambios de comportamiento.
    aliases = {**_ALIASES, **_ALIASES_PARRILLA_VINOS_OVERRIDE} if destino == "parrilla_y_vinos" else _ALIASES

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), data_only=True)
    ws = wb["Cenefas"] if "Cenefas" in wb.sheetnames else wb.active

    # ── Detectar fila de encabezados ──────────────────────────────────────
    header_row = None
    for i, row in enumerate(ws.iter_rows(max_row=10, values_only=True), start=1):
        norms = {_norm(str(c)) for c in row if c is not None}
        if len(norms & _DETECTION_NORMS) >= 1 or "ofertadet" in norms:
            header_row = i
            break
    if header_row is None:
        header_row = 1

    # ── Mapear columnas ───────────────────────────────────────────────────
    raw_headers = [cell.value for cell in ws[header_row]]
    h: dict[str, int] = {}
    for idx, raw in enumerate(raw_headers):
        if not raw:
            continue
        norm = _norm(str(raw))
        canonical = aliases.get(norm)
        if canonical is None and destino == "parrilla_y_vinos" and _RE_PVP_GESTION.match(norm):
            canonical = "precioP"
        key = canonical if canonical else str(raw)  # pass through unknown columns as-is
        if key in h:
            continue  # primera columna con este nombre gana -- ver caso real:
            # el excel de Parrilla y Vinos trae "OFERTA" DOS veces (precio
            # real en una posición, un código de mecánica interno sin
            # relación en otra) -- sin esto, la última pisaba a la primera
            # en silencio y el precio se perdía.
        h[key] = idx

    # ── Detectar columna de descripción para skip de filas vacías ─────────
    desc_col = h.get("descripcion")
    titulo_col = h.get("_ofertadet")

    products: list[dict] = []
    seen: set[str | tuple] = set()

    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        # Saltar filas sin descripción
        if desc_col is not None and (desc_col >= len(row) or not row[desc_col]):
            continue

        data = process_row(row, h, vigencia, aclaracion, otra_alcohol, banco)

        # Deduplicación: codigoSKU es la clave PRINCIPAL y suficiente por sí
        # sola cuando está presente -- es el identificador real de un
        # producto, no hace falta que descripción/mecanica/precioActual/dia
        # también coincidan (esos campos ni siquiera se popultan en Parrilla
        # y Vinos). Comparar por combinación de campos era demasiado
        # estricto: bastaba con que la descripción viniera escrita distinto
        # entre filas del mismo código para NO deduplicar filas repetidas.
        # Sin codigoSKU (destinos/excels que no lo traen) cae al criterio
        # viejo por combinación de campos, único identificador disponible.
        sku = (data.get("codigoSKU") or "").strip()
        key = sku or (
            data.get("mecanica", ""),
            data.get("precioActual", ""),
            (data.get("descripcion") or "").lower().strip(),
            data.get("dia", ""),
        )
        if key not in seen:
            seen.add(key)
            products.append(data)

    return products


# ---------------------------------------------------------------------------
# Generación de plantilla Excel de descarga
# ---------------------------------------------------------------------------
#
# Tres plantillas, una por destino de Cenefas — comparten estilo pero tienen
# columnas distintas porque cada destino soporta variables distintas
# (Rompe Precios explícitamente no tiene mecánica de combo/M x N).
#
# Parrilla y Vinos tiene su PROPIO esquema, calcado del Excel real que ya
# usa el equipo (no el de Rompe Precios): "regular" es el precio principal,
# "oferta"/"5x3"/"6x3" son tres niveles de precio por cantidad que en el
# PPTX aparecen partidos en entero+decimal (ver _ALIASES_PARRILLA_VINOS_OVERRIDE
# y pptx_importer.py). vigencia/aclaraciones quedan como columnas opcionales
# al final por si una plantilla futura (ej. la versión A4) las necesita —
# process_row ya trata todo como opcional, no molestan si quedan vacías.

def generate_template_bytes(destino: str = "redexpres") -> bytes:
    if destino == "rompe_precios":
        return _build_template_workbook(
            headers=["descripcion", "precio", "precioAnterior", "vigencia", "aclaracion1", "aclaracion2", "aclaracion3"],
            col_widths=[36, 12, 14, 30, 30, 30, 30],
            examples=[
                ("ACEITE GIRASOL FAMILIA 1.5L",  139, 169, "Válido viernes 17 a domingo 19 de julio", "Precio válido en todos los locales.", "Stock limitado.",                                                ""),
                ("ARROZ BLUE PATNA 1KG",          55,  69, "Válido viernes 17 a domingo 19 de julio", "Precio válido en todos los locales.", "",                                                                ""),
                ("CERVEZA PILSEN LATA 473ML",     59,  75, "Válido viernes 17 a domingo 19 de julio", "Precio válido en todos los locales.", "Stock limitado.", "Prohibida la venta de bebidas alcohólicas a menores de 18 años"),
                ("YOGUR CONAPROLE FRUTILLA 1KG",  89, 109, "Válido viernes 17 a domingo 19 de julio", "Precio válido en todos los locales.", "",                                                                ""),
                ("DETERGENTE OMO LÍQUIDO 3L",    229, 279, "Válido viernes 17 a domingo 19 de julio", "Precio válido en todos los locales.", "Stock limitado.",                                                ""),
            ],
            var_docs=[
                ("descripcion",    "Nombre del producto",                       "Texto",  "Corresponde a <<Descripcion>> en la plantilla PPTX. Palabras en MAYÚSCULAS se ven en negrita."),
                ("precio",         "Precio actual (el que se muestra grande)",  "Precio", "Corresponde a <<Precio>>. Número (139) o texto ($139) — con número se auto-formatea con $."),
                ("precioAnterior", "Precio anterior — se muestra tachado",      "Precio", "Corresponde a <<precioAnterior>>. Dejar vacío si el producto no tenía un precio previo."),
                ("vigencia",       "Texto de vigencia de la oferta",            "Texto",  "Corresponde a <<Vigencia>>. Si se deja vacío acá, usa la vigencia general de la pantalla de este destino."),
                ("aclaracion1",    "Primera aclaración / legal",                "Texto",  "Corresponde a <<Aclaracion1>>."),
                ("aclaracion2",    "Segunda aclaración",                        "Texto",  "Corresponde a <<Aclaracion2>>. Dejar vacío si no aplica."),
                ("aclaracion3",    "Tercera aclaración (ej. alcohol)",          "Texto",  "Corresponde a <<Aclaracion3>>. Dejar vacío si no aplica."),
                ("imagen (cocarda)", "Sello/badge de la promo",                 "Imagen — NO es columna", "Se sube UNA sola vez desde la pantalla de este destino (no por producto) — no hace falta agregarla acá."),
            ],
        )

    if destino == "parrilla_y_vinos":
        return _build_template_workbook(
            headers=["codigo", "nombre de articulo", "regular", "oferta", "5x3", "6x3", "vigencia", "aclaracion1", "aclaracion2", "aclaracion3"],
            col_widths=[14, 36, 12, 12, 12, 12, 30, 30, 30, 30],
            examples=[
                ("84512", "ASADO DE TIRA KG",          399, "379,50", "365,50", "349,50", "Válido viernes 17 a domingo 19 de julio", "Precio válido en todos los locales.", "Stock limitado.", ""),
                ("63321", "VINO TANNAT RESERVA 750ML", 349, "329,50", "319,50", "299,50", "Válido viernes 17 a domingo 19 de julio", "Precio válido en todos los locales.", "", "Prohibida la venta de bebidas alcohólicas a menores de 18 años"),
                ("41207", "CHORIZO PARRILLERO KG",     289, "269,50", "259,50", "249,50", "Válido viernes 17 a domingo 19 de julio", "Precio válido en todos los locales.", "Stock limitado.", ""),
                ("55890", "CARBÓN VEGETAL 3KG",         99,       "",       "",       "", "Válido viernes 17 a domingo 19 de julio", "Precio válido en todos los locales.", "", ""),
                ("67788", "ESPUMANTE BRUT 750ML",      259, "239,50", "229,50", "219,50", "Válido viernes 17 a domingo 19 de julio", "Precio válido en todos los locales.", "Stock limitado.", "Prohibida la venta de bebidas alcohólicas a menores de 18 años"),
            ],
            var_docs=[
                ("codigo",              "Código de artículo",                          "Texto",  "Corresponde a <<codigo>> en la plantilla PPTX."),
                ("nombre de articulo",  "Nombre del producto",                         "Texto",  "Corresponde a <<descripcion>>."),
                ("regular",             "Precio principal (el que se muestra grande)", "Precio", "Corresponde a <<precioP>>. El signo $ ya está fijo en la plantilla, no hace falta incluirlo acá."),
                ("oferta",              "Precio del nivel 4x3",                        "Precio", "Corresponde a <<4x3P>> (entero) y <<decimal4x3>> (decimal, con la coma) — se parte automáticamente. Dejar vacío si el producto no tiene este nivel."),
                ("5x3",                 "Precio del nivel 5x3",                        "Precio", "Corresponde a <<5x3P>>/<<decimal5x3>>, igual que la columna oferta. Dejar vacío si no aplica."),
                ("6x3",                 "Precio del nivel 6x3",                        "Precio", "Corresponde a <<6x3P>>/<<decimal6x3>>, igual que la columna oferta. Dejar vacío si no aplica."),
                ("vigencia",            "Texto de vigencia de la oferta",              "Texto",  "Corresponde a <<Vigencia>>, si la plantilla la usa. Opcional."),
                ("aclaracion1",         "Primera aclaración / legal",                  "Texto",  "Corresponde a <<Aclaracion1>>, si la plantilla la usa. Opcional."),
                ("aclaracion2",         "Segunda aclaración",                          "Texto",  "Opcional."),
                ("aclaracion3",         "Tercera aclaración (ej. alcohol)",            "Texto",  "Opcional."),
            ],
        )

    # Redexpres — columnas y ejemplos extraídos del Excel real de referencia
    # (planilla ya usada con la plantilla A4 REDEX.pptx), no inventados.
    return _build_template_workbook(
        headers=["DESCRIPCION", "precioActual", "OFERTADET", "OFERTA", "ACLARACION", "OTRA ACLARACION", "VIGENCIA", "CODIGO"],
        col_widths=[36, 14, 14, 14, 32, 40, 30, 16],
        examples=[
            ("ACEITE GIRASOL FAMILIA 1.5L",   139, "",      "",      "Precio válido en todos los locales.", "",                                                                "Válido del 10 al 16 de julio", "84512"),
            ("ARROZ BLUE PATNA 1KG",           59, "Combo", "3x150", "Descuento aplicado en caja.",         "",                                                                "Válido del 10 al 16 de julio", "63321"),
            ("GASEOSA COCA-COLA 1.5L",         89, "M x N", "3x2",   "Llevando 3 pagás 2.",                 "",                                                                "Válido del 10 al 16 de julio", "41207"),
            ("CERVEZA PILSEN LATA 473ML",      69, "Combo", "6x360", "Descuento aplicado en caja.",         "Prohibida la venta de bebidas alcohólicas a menores de 18 años", "Válido del 10 al 16 de julio", "55890/55891"),
            ("YOGUR CONAPROLE FRUTILLA 1KG",   99, "",      "",      "Precio válido en todos los locales.", "",                                                                "Válido del 10 al 16 de julio", "72190"),
            ("PAPEL HIGIÉNICO SCOTT X4",      119, "M x N", "2x1",   "Llevando 2 pagás 1.",                 "",                                                                "Válido del 10 al 16 de julio", "30044"),
            ("JAMÓN COOK FUD FETEADO 200G",   149, "",      "",      "Descuento aplicado en caja.",         "",                                                                "Válido del 10 al 16 de julio", "18765-18770"),
            ("DETERGENTE OMO LÍQUIDO 3L",     259, "Combo", "2x460", "Descuento aplicado en caja.",         "",                                                                "Válido del 10 al 16 de julio", "91002"),
            ("VINO TANNAT RESERVA 750ML",     349, "",      "",      "Precio válido en todos los locales.", "Prohibida la venta de bebidas alcohólicas a menores de 18 años", "Válido del 10 al 16 de julio", "67788"),
            ("GALLETITAS TITA CHOCOLATE X6",   79, "M x N", "3x2",   "Llevando 3 pagás 2.",                 "",                                                                "Válido del 10 al 16 de julio", "20456"),
        ],
        var_docs=[
            ("DESCRIPCION",     "Nombre del producto",                                     "Texto",  "Corresponde a <<Descripcion>>. Palabras en MAYÚSCULAS se ven en negrita."),
            ("precioActual",    "Precio unitario del producto",                            "Precio", "Corresponde a <<Precio>>. Si OFERTADET=Combo o M x N, se usa como precio 'la unidad' en la mecánica, y el precio grande final sale de OFERTA."),
            ("OFERTADET",       "Tipo de mecánica: 'Combo', 'M x N', o vacío = precio fijo","Lista",  "Vacío = OFERTA y la mecánica quedan en blanco (solo precio)."),
            ("OFERTA",          "Detalle de la mecánica según OFERTADET",                  "Texto",  "Combo: 'CANTIDADxPRECIO_TOTAL' (ej. '3x150'). M x N: 'CANTIDADxPAGADAS' (ej. '3x2')."),
            ("ACLARACION",      "Aclaración principal debajo del producto",                "Texto",  "Corresponde a <<Aclaracion1>>. Ej: 'Descuento aplicado en caja.'"),
            ("OTRA ACLARACION", "Segunda aclaración (legales, restricciones)",             "Texto",  "Corresponde a <<OtraAclaracion1>>. Usar para el disclaimer de alcohol en bebidas."),
            ("VIGENCIA",        "Texto de vigencia de la oferta",                          "Texto",  "Corresponde a <<Vigencia1>>. Ej: 'Válido del 10 al 16 de julio'."),
            ("CODIGO",          "Código de artículo",                                      "Texto",  "No se muestra directo, pero si tiene '/' o un rango ('123-456') activa el texto 'unidad' junto al precio."),
        ],
        dropdown={"OFERTADET": ["Combo", "M x N", ""]},
    )


def _build_template_workbook(
    headers:    list[str],
    col_widths: list[int],
    examples:   list[tuple],
    var_docs:   list[tuple],
    dropdown:   dict[str, list[str]] | None = None,
) -> bytes:
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cenefas"

    header_fill = PatternFill("solid", fgColor="1E3A5F")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    even_fill   = PatternFill("solid", fgColor="EEF2F7")

    for col, name in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=name)
        cell.fill      = header_fill
        cell.font      = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row_idx, data in enumerate(examples, 2):
        fill = even_fill if row_idx % 2 == 0 else None
        for col_idx, value in enumerate(data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = Alignment(vertical="center")
            if fill:
                cell.fill = fill

    for col, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.row_dimensions[1].height = 26
    ws.freeze_panes = "A2"

    for header_name, options in (dropdown or {}).items():
        col_idx = headers.index(header_name) + 1
        col_letter = get_column_letter(col_idx)
        dv = DataValidation(type="list", formula1=f'"{",".join(options)}"', allow_blank=True)
        dv.sqref = f"{col_letter}2:{col_letter}5000"
        ws.add_data_validation(dv)

    # ── Hoja de referencia de variables ──────────────────────────────────────
    ws2 = wb.create_sheet("Variables")
    ws2.column_dimensions["A"].width = 20
    ws2.column_dimensions["B"].width = 42
    ws2.column_dimensions["C"].width = 20
    ws2.column_dimensions["D"].width = 46

    inst_font = Font(bold=True, color="FFFFFF", size=11)
    inst_fill = PatternFill("solid", fgColor="1E3A5F")

    for col, name in enumerate(["Variable", "Descripción", "Tipo", "Notas"], 1):
        cell = ws2.cell(row=1, column=col, value=name)
        cell.fill = inst_fill; cell.font = inst_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[1].height = 24

    for row_idx, data in enumerate(var_docs, 2):
        for col_idx, value in enumerate(data, 1):
            cell = ws2.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if row_idx % 2 == 0:
                cell.fill = PatternFill("solid", fgColor="EEF2F7")
        ws2.row_dimensions[row_idx].height = 36

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

"""La descarga dividida: una carpeta por sucursal, un Excel por categoría.

Ivan, 15/09/2026: "el resultado esperado es una carpeta mayor que tendrá sub
carpetas por sucursales de tienda inglesa que tendrán adentro diferentes excels
por cada categoría que correspondan a un stock mayor o igual a 1 para esa
sucursal".

Casi todo lo que se prueba acá es puro, y no por comodidad: `armar_zip_dividido`
y `juntar_filas_por_producto` se escribieron sin `db` justamente para que el
reparto de filas --qué fila va a qué archivo, qué filas son un solo producto y
cuál queda afuera-- se pueda fijar en un test. Es la decisión que le importa a
la persona que baja el ZIP.

Las dos excepciones son `parse_input_excel` y `match_rows`, que son async y
piden una AsyncSession. Se las llama con `_BaseVacia` (ver más abajo), que
contesta "no hay nada guardado" a las tres consultas de lectura que hacen: sigue
sin haber base ni red, que es lo que conftest.py prohíbe, y a cambio los tests
de la ingesta recorren el camino de verdad en vez de empezar con las filas ya
parseadas a mano.

Los tres agujeros que estos tests tapan, en orden de qué tan caro sale cada uno:

1. De cuántos productos habla el archivo. El export real --el primero de
   verdad, que Ivan pasó el 15/09/2026-- viene en FORMATO LARGO: una fila por
   producto y POR SUCURSAL, con el nombre de la sucursal como VALOR de la
   columna `sucursal` y no como encabezado. Sin juntar esas filas, el
   Convertidor arma 4.773 cenefas en vez de 274: la misma repetida hasta 18
   veces, y el que la revisa corrige 18 veces la misma descripción.

   Antes de ver el archivo dimos por hecho lo contrario --una columna por
   sucursal, reconocida por el nombre del encabezado contra una lista fija-- y
   se implementó entero. Ese día se borró todo (SUCURSALES,
   es_columna_de_sucursal, detectar_columnas_stock) junto con los siete tests
   que lo sostenían, así que acá no quedó nada de aquello: lo que hay que
   sostener ahora es que las filas se junten bien y --sobre todo-- que un
   listado que NO trae la columna `sucursal`, que son casi todos, pase intacto.

2. Las filas que se pierden en silencio. Partir una descarga en N archivos es
   justo el momento en que una fila de menos no se nota: por eso lo que queda
   afuera por falta de stock y lo que cae en "Sin categoría" se cuenta, y el
   resumen es lo que la pantalla muestra ANTES de descargar.

3. Los nombres. La sucursal y la categoría son texto que escribe gestión --una
   celda del listado cada una-- y terminan siendo el nombre de una carpeta y de
   un archivo. Un "/" o un punto final ahí adentro es un ZIP que no se puede
   descomprimir en Windows, y eso se descubre en la góndola.
"""
import asyncio
import io
import zipfile

import openpyxl
import pytest

from app.services.cenefas.convertidor import (
    _STOCK_MINIMO,
    _mapear_columnas,
    _nombre_para_zip,
    _parse_stock_or_none,
    ConvertidorParseError,
    armar_zip_dividido,
    build_output_workbook,
    detectar_fila_headers,
    juntar_filas_por_producto,
    leer_filas,
    match_rows,
    parse_input_excel,
)


# ---------------------------------------------------------------------------
# Herramientas: el Excel de entrada y el ZIP de salida, los dos en memoria
# ---------------------------------------------------------------------------

# La fila de encabezados del export REAL con stock por sucursal, copiada a mano
# de "ac corp 30agosto (1).xlsx" (hoja "Export", 4.773 filas, 271 productos, 18
# sucursales). Ese .xlsx vive en la carpeta de Descargas y NO se copia al repo:
# un test que dependa de un binario sin versionar no se puede correr en el CI.
# Lo que importa de ese archivo es la FORMA --los nombres exactos de las diez
# columnas y una fila por producto y POR SUCURSAL-- y eso se copia sin el
# archivo.
#
# Los nombres no son decorado. `id_producto` es el que entra por el alias sin el
# cual el archivo no se abre; `sucursal` es lo único que enciende el juntado;
# `dsc_subfamilia` es la categoría que después nombra cada Excel del ZIP. Las
# otras siete viajan igual para que estos tests lean un export de verdad y no
# una versión de laboratorio con exactamente las columnas que le convienen: son
# justo las que en el archivo real no se leen, y tienen que seguir sin leerse.
_HEADERS_EXPORT_LARGO = (
    "id_producto", "descripcion", "proveedor", "sucursal", "stock",
    "cantidad_vendida", "dsc_categoria", "dsc_subcategoria", "dsc_familia",
    "dsc_subfamilia",
)


def _fila_export(codigo, descripcion, sucursal, stock, subfamilia):
    """Una fila del export real, con las diez columnas en su lugar."""
    return (codigo, descripcion, "AC CORP URUGUAY SRL", sucursal, stock, None,
            "TECNOLOGIA", "AUDIO, TV Y VIDEO", "AUDIO", subfamilia)


def _xlsx(*filas) -> bytes:
    """Un .xlsx armado en memoria, con la primera fila de encabezados.

    Molde de _pptx_con_textos (test_importer_y_render.py) pasado a openpyxl: no
    hay binarios en el repo ni dependencia del archivo real de Ivan.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Export"
    for fila in filas:
        ws.append(list(fila))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _hoja(*filas):
    """Las filas de ese .xlsx tal como las lee el Convertidor.

    Se pasa por `leer_filas` a propósito en vez de armar las tuplas a mano: es
    el camino de verdad --el mismo que corre /columnas-- y el único que deja las
    celdas como openpyxl las devuelve. Un encabezado puede volver con espacios
    de más y un stock como número con coma, y armando las tuplas a mano el test
    probaría otra cosa.
    """
    return leer_filas(_xlsx(*filas), "listado.xlsx")


class _ResultadoVacio:
    """Lo que devuelve un SELECT contra una base que no tiene nada guardado."""

    def all(self):
        return []

    def scalars(self):
        return self


class _BaseVacia:
    """La `db` de parse_input_excel y match_rows, sin base y sin red.

    conftest.py prohíbe las dos cosas y las dos funciones piden una
    AsyncSession, pero la usan para tres consultas de LECTURA y nada más: los
    alias de encabezado que Tinín aprendió en imports anteriores, el catálogo de
    descripciones por SKU, y las familias de OFERTADET confirmadas a mano. Con
    las tres vacías el resultado es exactamente el de un import hecho en una
    instalación limpia, que es justo el caso que hay que probar acá: lo que
    llega a la grilla tiene que salir del ARCHIVO y no de lo que alguien guardó
    antes.

    La alternativa era escribir las filas parseadas a mano y arrancar el test
    después del parser. No sirve para lo que hay que sostener: el día que
    parse_input_excel deje de juntar --o que alguien le saque el alias de
    id_producto-- esos asserts seguirían todos en verde.
    """

    async def execute(self, *args, **kwargs):
        return _ResultadoVacio()


def _parsear(file_bytes):
    """parse_input_excel entero: (filas, aliases_aprendidos, headers, juntado)."""
    return asyncio.run(parse_input_excel(
        file_bytes, "export.xlsx", db=_BaseVacia(), current_user_id=1))


def _a_la_grilla(parsed):
    """Las filas como las ve la persona.

    El paso importa: es match_rows el que pasa el "_stock" del parser a
    `stockPorSucursal`, que es la clave con la que armar_zip_dividido decide la
    carpeta. Entre las dos no hay nada más, y ese hilo es el que estos tests
    tienen que recorrer entero.
    """
    rows, _ma_pairs = asyncio.run(match_rows(parsed, _BaseVacia()))
    return rows


def _larga(codigo, sucursal, stock, **extra):
    """Una fila parseada de un listado en formato largo, como la deja el parser.

    Los datos del producto vienen repetidos en TODAS las filas de ese código
    --así es el export-- y `extra` es para pisar el campo que el caso mire.
    """
    fila = {
        "codigo":            codigo,
        "nombreArticulo":    "AURICULAR PHILIPS INALAM. UPBEAT NEGRO",
        "descripcionExcel":  "",
        "precio":            1290.0,
        "categoriaProducto": "AURICULARES",
        "sucursal":          sucursal,
        "stock":             stock,
    }
    fila.update(extra)
    return fila


def _fila(codigo, descripcion, categoria="", stock=None, **extra):
    """Una fila como la manda la grilla a /export-dividido.

    Lo mínimo para que build_output_workbook la escriba, más los dos campos de
    contexto nuevos. `extra` es para las columnas que solo tiene ALGUNA fila
    (banco, típicamente): es el caso que hace falta para probar que todos los
    libros salen iguales.
    """
    fila = {
        "codigo": codigo,
        "descripcion": descripcion,
        "mecanica": "Precio Final",
        "precioOferta": "1.290",
        "categoriaProducto": categoria,
        "stockPorSucursal": stock or {},
    }
    fila.update(extra)
    return fila


def _filas_de_prueba():
    """El listado chico que usan los tests de los tres modos.

    Tiene a propósito una de cada: una fila en dos sucursales, una en una sola,
    una sin categoría, y una que no tiene stock en ninguna parte.
    """
    return [
        _fila("580735", "Heladera James 300 L",    "Heladeras",         {"suc1": 3, "suc2": 0, "suc3": 2}),
        _fila("580736", "Microondas Philco 20 L",  "Microondas",        {"suc1": 1, "suc2": 0, "suc3": 0}),
        _fila("580737", "Cosa que nadie conoce",   "",                  {"suc1": 0, "suc2": 4, "suc3": 0}),
        _fila("580738", "Freidora de aire 5 L",    "Freidoras de aire", {"suc1": 0, "suc2": 0, "suc3": 0}),
    ]


def _rutas(zip_bytes):
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        return sorted(zf.namelist())


def _hoja_del_zip(zip_bytes, ruta):
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        return openpyxl.load_workbook(io.BytesIO(zf.read(ruta))).active


def _encabezados(zip_bytes, ruta):
    return [celda.value for celda in _hoja_del_zip(zip_bytes, ruta)[1]]


def _codigos(zip_bytes, ruta):
    ws = _hoja_del_zip(zip_bytes, ruta)
    col = _encabezados(zip_bytes, ruta).index("codigo")
    return [fila[col].value for fila in ws.iter_rows(min_row=2)]


def _todos_los_codigos(zip_bytes):
    """Qué filas sobrevivieron al reparto, sin importar en qué archivo cayeron."""
    return {cod for ruta in _rutas(zip_bytes) for cod in _codigos(zip_bytes, ruta)}


# ---------------------------------------------------------------------------
# La ingesta del formato largo: de 4.773 filas a 274 productos
# ---------------------------------------------------------------------------

def test_sin_el_alias_de_id_producto_el_archivo_no_se_podia_ni_abrir():
    # El alias más barato de todos y el único sin el cual no hay nada más que
    # probar. detectar_fila_headers busca la fila de encabezados por UNA señal:
    # que alguna columna normalice a `codigo`. El export de gestión llama a la
    # suya "id_producto", que no estaba en _INPUT_ALIASES, así que no encontraba
    # encabezados en ninguna de las diez primeras filas y el archivo se
    # rechazaba ENTERO con "No encontré una columna 'CODIGO' reconocible". No es
    # que saliera mal dividido: no se abría.
    filas = _hoja(
        _HEADERS_EXPORT_LARGO,
        _fila_export("503996", "AURICULAR PHILIPS INALAM.", "Central", 5, "AURICULARES"),
    )
    assert detectar_fila_headers(filas) == 0
    col_map, encontro_codigo = _mapear_columnas(filas[0])
    assert encontro_codigo
    # Las cinco columnas que el Convertidor lee de este export, cada una en su
    # lugar (la 1, `descripcion`, entra por el alias de siempre). Las otras
    # cinco --proveedor, cantidad_vendida y los tres niveles de categoría más
    # gruesos que dsc_subfamilia-- no se mapean a propósito: son demasiado
    # gruesas para nombrar una carpeta (decisión de Ivan, 15/09/2026).
    assert col_map[0] == "codigo"
    assert col_map[3] == "sucursal"
    assert col_map[4] == "stock"
    assert col_map[9] == "categoriaProducto"
    assert sorted(col_map) == [0, 1, 3, 4, 9]

    # Y el otro lado, para que quede claro que el alias resolvió ESTE export y
    # no apagó el chequeo: una columna de código que nadie reconoce sigue siendo
    # un rechazo con motivo, que es lo que tiene que pasar.
    with pytest.raises(ConvertidorParseError) as exc:
        _parsear(_xlsx(
            ("articulo", "sucursal", "stock"),
            ("503996",   "Central",  5),
        ))
    assert "CODIGO" in str(exc.value)


def test_tres_productos_en_cuatro_sucursales_son_tres_filas():
    # La forma del archivo real en chiquito: 3 x 4 = 12 filas que son 3
    # productos. Esa cuenta es cuántas cenefas se imprimen, así que es la que
    # tiene que dar bien antes que ninguna otra.
    filas = [
        _larga(codigo, sucursal, unidades)
        for codigo, stocks in (
            ("503996", (5, 0, 2, 1)),
            ("610220", (0, 3, 0, 0)),
            ("707311", (7, 7, 7, 7)),
        )
        for sucursal, unidades in zip(("Central", "Arocena", "Unión", "Pocitos"), stocks)
    ]
    assert len(filas) == 12

    juntadas, resumen = juntar_filas_por_producto(filas)
    # En el orden del archivo: la grilla se lee comparándola contra el Excel que
    # la persona tiene abierto al lado.
    assert [f["codigo"] for f in juntadas] == ["503996", "610220", "707311"]
    assert resumen == {
        "filas": 12, "productos": 3,
        "sucursales": ["Central", "Arocena", "Unión", "Pocitos"],
        "con_diferencias": 0,
    }
    # Las cuatro sucursales de cada producto adentro de _stock, ceros incluidos:
    # "informó que no tiene" es un dato y se ve en la grilla.
    assert juntadas[0]["_stock"] == {"Central": 5, "Arocena": 0, "Unión": 2, "Pocitos": 1}
    assert juntadas[1]["_stock"] == {"Central": 0, "Arocena": 3, "Unión": 0, "Pocitos": 0}
    assert all(len(f["_stock"]) == 4 for f in juntadas)
    # `sucursal` y `stock` ya no cuelgan de la fila. Son datos de UNA de las
    # doce filas que se juntaron, no del producto, y sueltos ahí son una
    # invitación a leerlos como si lo fueran ("este auricular es de Central").
    assert all("sucursal" not in f and "stock" not in f for f in juntadas)


def test_el_stock_ilegible_no_entra_en_stock_y_no_cuenta_como_cero():
    # La misma distinción que ya cuida _parse_stock_or_none, un paso más
    # adelante: la sucursal que no informó no deja rastro en _stock, la que
    # informó 0 sí. Las dos dejan la fila afuera de esa carpeta, pero un listado
    # incompleto no puede tener la misma cara que una góndola vacía.
    juntadas, _resumen = juntar_filas_por_producto([
        _larga("503996", "Central", 5),
        _larga("503996", "Arocena", None),
        _larga("503996", "Unión",   0),
    ])
    assert juntadas[0]["_stock"] == {"Central": 5, "Unión": 0}

    # Y desde el archivo, que es donde se decide qué es ilegible: "12,5" no es
    # una cantidad de unidades --devolver 12 sería inventar la mitad que falta--
    # y la celda vacía tampoco es un 0. Las dos quedan fuera de _stock sin
    # romper nada: la sucursal sigue existiendo para los demás productos, que es
    # lo que antes no pasaba (una celda rara descalificaba la columna entera).
    parsed, _aliases, _headers, _juntado = _parsear(_xlsx(
        _HEADERS_EXPORT_LARGO,
        _fila_export("503996", "AURICULAR PHILIPS", "Central", 5,      "AURICULARES"),
        _fila_export("503996", "AURICULAR PHILIPS", "Arocena", None,   "AURICULARES"),
        _fila_export("503996", "AURICULAR PHILIPS", "Unión",   "12,5", "AURICULARES"),
        _fila_export("503996", "AURICULAR PHILIPS", "Pocitos", 0,      "AURICULARES"),
    ))
    assert parsed[0]["_stock"] == {"Central": 5, "Pocitos": 0}


def test_la_misma_sucursal_repetida_para_un_producto_se_suma():
    # Un export puede traer el stock físico y el que está en tránsito en dos
    # filas de la misma sucursal. Son unidades de la MISMA góndola: quedarse con
    # una de las dos deja media carga sin cartel, y lo peor es que no falla
    # nada, simplemente sale un número más chico.
    juntadas, resumen = juntar_filas_por_producto([
        _larga("503996", "Central", 5),
        _larga("503996", "Central", 3),
        _larga("503996", "Arocena", 0),
    ])
    assert juntadas[0]["_stock"] == {"Central": 8, "Arocena": 0}
    # Y en el resumen la sucursal repetida se nombra una sola vez: es una
    # carpeta, no dos.
    assert resumen == {"filas": 3, "productos": 1,
                       "sucursales": ["Central", "Arocena"], "con_diferencias": 0}


def test_gana_el_primer_valor_no_vacio_y_el_producto_que_difiere_se_cuenta():
    # Las 18 filas de un producto traen los mismos datos repetidos, así que
    # quedarse ciegamente con la primera parece gratis. No lo es: basta que la
    # primera venga con el nombre en blanco para que el producto entero salga
    # sin nombre teniéndolo diecisiete veces más abajo, y una cenefa sin nombre
    # de artículo ni siquiera se puede redactar con IA.
    juntadas, resumen = juntar_filas_por_producto([
        _larga("503996", "Central", 5, nombreArticulo=""),
        _larga("503996", "Arocena", 0, nombreArticulo="AURICULAR PHILIPS UPBEAT"),
        _larga("610220", "Central", 2, precio=200.0),
        _larga("610220", "Arocena", 1, precio=999.0),
    ])
    assert juntadas[0]["nombreArticulo"] == "AURICULAR PHILIPS UPBEAT"
    # Gana el PRIMERO no vacío, no el último ni el más grande: el 999 de la
    # segunda fila no pisa al 200 de la primera.
    assert juntadas[1]["precio"] == 200.0
    # Y se cuenta UN producto, no dos filas ni tres campos: lo que la pantalla
    # tiene que poder decir es "1 producto viene con datos distintos entre sus
    # filas". El primero no cuenta --venir en blanco y después con dato no es
    # una diferencia, es el archivo completándose-- y el segundo sí.
    assert resumen["con_diferencias"] == 1

    # Un 0 NO es un valor vacío. Con un `if not valor` el precio 0 de la primera
    # fila lo pisaría el de la segunda, y el producto saldría con un precio que
    # nadie escribió ahí.
    juntadas, _resumen = juntar_filas_por_producto([
        _larga("707311", "Central", 1, precio=0.0),
        _larga("707311", "Arocena", 1, precio=999.0),
    ])
    assert juntadas[0]["precio"] == 0.0


def test_el_resumen_lista_las_sucursales_en_orden_de_aparicion_y_sin_repetir():
    # El orden es el del archivo y no el alfabético: es el que la persona ve al
    # abrir el Excel, y el aviso de la pantalla de mapeo se lee al lado. Salen
    # TODAS las que traiga el archivo, sin lista blanca ni negra --"Deposito
    # A.Saravia", "Propios" y "Central" incluidas (Ivan, 15/09/2026)-- así que
    # el día que abra un local nuevo aparece solo y no hay nada que actualizar.
    _juntadas, resumen = juntar_filas_por_producto([
        _larga("503996", "Central",            5),
        _larga("503996", "Arocena",            0),
        _larga("610220", "Arocena",            3),
        _larga("610220", "Central",            0),
        _larga("610220", "Deposito A.Saravia", 9),
    ])
    assert resumen["filas"] == 5
    assert resumen["productos"] == 2
    assert resumen["sucursales"] == ["Central", "Arocena", "Deposito A.Saravia"]


def test_las_filas_de_pie_del_reporte_no_llegan_a_la_grilla_y_se_cuentan():
    # El export real termina con dos filas que no son productos: una que dice
    # "Total" --con el total de unidades en la columna de stock-- y otra que
    # arranca "Filtros aplicados:", las dos con texto en la primera columna y
    # todo lo demás vacío. Como esa primera columna es `id_producto`, llegaban a
    # la grilla como dos artículos más: dos cenefas para imprimir que dicen
    # "Total" y "Filtros aplicados: Date el o después del...".
    #
    # Se reconocen por la FORMA y no por el texto: en este formato toda fila de
    # producto trae sucursal --es la razón de ser del formato--, así que la que
    # no la trae no es una. Comparar contra "Total" se cae el día que el reporte
    # diga "Totales"; esto no.
    parsed, _aliases, _headers, juntado = _parsear(_xlsx(
        _HEADERS_EXPORT_LARGO,
        _fila_export("610220", "FREIDORA DE AIRE ATMA 5L", "Central", 4, "FREIDORA"),
        _fila_export("610220", "FREIDORA DE AIRE ATMA 5L", "Arocena", 0, "FREIDORA"),
        _fila_export("503996", "AURICULAR PHILIPS INALAM.", "Central", 0, "AURICULARES"),
        # Las dos de pie, tal como vienen: "Total" TRAE stock (1.837 unidades,
        # la suma de la columna) y no trae sucursal, y la de los filtros no trae
        # nada. Por eso el criterio mira la sucursal y no "la fila vacía".
        ("Total", None, None, None, 1837, None, None, None, None, None),
        ("Filtros aplicados: \nDate el o después del 24/08/2026 0:00:00",
         None, None, None, None, None, None, None, None, None),
    ))
    assert [f["codigo"] for f in parsed] == ["610220", "503996"]
    assert juntado["filas_sin_sucursal"] == 2
    # Y no dejaron rastro en ninguna otra cuenta: las 3 filas del juntado son
    # las de producto, y las 1.837 unidades del "Total" no inventaron una
    # sucursal --que habría salido como una carpeta más en el ZIP.
    assert juntado["filas"] == 3
    assert juntado["productos"] == 2
    assert juntado["sucursales"] == ["Central", "Arocena"]
    assert [r["codigo"] for r in _a_la_grilla(parsed)] == ["610220", "503996"]

    # Ivan, 15/09/2026: "no siempre va a venir así pero es una posibilidad, no
    # lo hagas como fila obligatoria". El MISMO archivo sin el pie tiene que
    # salir igual y sin quejarse: nada acá espera esas dos filas.
    parsed, _aliases, _headers, juntado = _parsear(_xlsx(
        _HEADERS_EXPORT_LARGO,
        _fila_export("610220", "FREIDORA DE AIRE ATMA 5L", "Central", 4, "FREIDORA"),
        _fila_export("610220", "FREIDORA DE AIRE ATMA 5L", "Arocena", 0, "FREIDORA"),
        _fila_export("503996", "AURICULAR PHILIPS INALAM.", "Central", 0, "AURICULARES"),
    ))
    assert [f["codigo"] for f in parsed] == ["610220", "503996"]
    assert juntado["filas_sin_sucursal"] == 0


def test_sin_columna_sucursal_la_fila_con_solo_el_codigo_igual_llega_a_la_grilla():
    # El test que más importa de este archivo, y el que dice qué NO puede hacer
    # la regla del pie de reporte. Saltear "la fila sin sucursal" es correcto en
    # el formato largo y sería un desastre en los listados de siempre, que son
    # casi todos: ahí la fila que trae el código y nada más ES un producto --el
    # que entró al listado antes de que gestión le cargara la descripción-- y la
    # persona la completa a mano en la grilla. Descartarla sería hacerle perder
    # una cenefa sin decirle nada y sin un solo error a la vista: el listado
    # entraría, saldría con una fila menos, y nadie se entera hasta que falta el
    # cartel en la góndola.
    #
    # Por eso la regla se enciende SOLO si la hoja trae sucursal. Acá no la
    # trae, así que la 580736 llega entera.
    parsed, _aliases, _headers, juntado = _parsear(_xlsx(
        ("CODIGO", "NOMBREARTICULO", "DESCRIPCION", "MONEDA", "PVPREGULAR",
         "PVPOFERTA", "OFERTA", "OFERTADET"),
        ("580735", "HELADERA JAMES RJ32 FRIO SECO 300L", "Heladera JAMES RJ32 Frío Seco 300 L",
         "$", 28990, 23990, "20%", "20% de descuento"),
        ("580736", None, None, None, None, None, None, None),
        ("580737", "MICROONDAS PHILCO 20L", "Microondas PHILCO 20 L",
         "$", 44990, 37990, "20%", "20% de descuento"),
    ))
    assert [f["codigo"] for f in parsed] == ["580735", "580736", "580737"]
    assert juntado["filas_sin_sucursal"] == 0

    rows = _a_la_grilla(parsed)
    assert [r["codigo"] for r in rows] == ["580735", "580736", "580737"]
    # Y llega como lo que es: una fila a completar, no una fila descartada. El
    # warning es el que la pinta de rojo en la grilla, que es el aviso que la
    # persona tiene que ver en vez de la fila ausente.
    assert "missing_description" in rows[1]["warnings"]


def test_una_hoja_sin_columna_sucursal_pasa_intacta():
    # EL test de todo esto. Los listados con stock por sucursal son la
    # excepción: el Convertidor procesa todos los días listados de oferta que no
    # traen la columna `sucursal` y que tienen que salir exactamente igual que
    # antes de que el formato largo existiera. Si esto se cae, se rompió el uso
    # normal de la herramienta para arreglar un caso raro.
    parsed = [
        {"codigo": "580735", "nombreArticulo": "HELADERA JAMES RJ32 FRIO SECO 300L",
         "precio": 28990.0},
        {"codigo": "580736", "nombreArticulo": "MICROONDAS PHILCO 20L",
         "precio": 44990.0},
    ]
    copia = [dict(f) for f in parsed]
    juntadas, resumen = juntar_filas_por_producto(parsed)
    # La MISMA lista, no una copia con los mismos valores: no se armó ninguna
    # fila nueva ni se tocó una clave. Ni siquiera se agrega un "_stock" vacío.
    assert juntadas is parsed
    assert juntadas == copia
    assert resumen == {"filas": 0, "productos": 0, "sucursales": [], "con_diferencias": 0}

    # La columna presente pero toda en blanco es lo mismo que no tenerla: hay
    # exports que la traen vacía y no por eso son formato largo.
    vacias = [dict(f, sucursal="") for f in copia]
    juntadas, resumen = juntar_filas_por_producto(vacias)
    assert juntadas is vacias
    assert resumen["productos"] == 0

    # Y el mismo listado de siempre por el camino completo, desde el .xlsx. La
    # tercera fila REPITE el código de la primera a propósito: sin columna
    # `sucursal` no hay nada que juntar, así que dos filas con el mismo código
    # siguen siendo dos filas --dos cenefas-- y no una. Agrupar por código a
    # espaldas de nadie es justo la forma en que esto se rompería en silencio.
    parsed, _aliases, _headers, juntado = _parsear(_xlsx(
        ("CODIGO", "NOMBREARTICULO", "DESCRIPCION", "MONEDA", "PVPREGULAR",
         "PVPOFERTA", "OFERTA", "OFERTADET"),
        ("580735", "HELADERA JAMES RJ32 FRIO SECO 300L", "Heladera JAMES RJ32 Frío Seco 300 L",
         "$", 28990, 23990, "20%", "20% de descuento"),
        ("580736", "MICROONDAS PHILCO 20L", "Microondas PHILCO 20 L",
         "$", 44990, 37990, "20%", "20% de descuento"),
        ("580735", "HELADERA JAMES RJ32 FRIO SECO 300L", "Heladera JAMES RJ32, la otra fila",
         "$", 28990, 23990, "20%", "20% de descuento"),
    ))
    assert [f["codigo"] for f in parsed] == ["580735", "580736", "580735"]
    # `filas_sin_sucursal` en 0 y no ausente: la clave va siempre, y acá vale 0
    # porque sin columna `sucursal` no se saltea ninguna fila (ver más abajo).
    assert juntado == {"filas": 0, "productos": 0, "sucursales": [],
                       "con_diferencias": 0, "filas_sin_sucursal": 0}

    rows = _a_la_grilla(parsed)
    # Sin stock por sucursal no hay nada que ofrecer en "dividir por
    # sucursales", y ese vacío es exactamente lo que lo deja apagado.
    assert [r["stockPorSucursal"] for r in rows] == [{}, {}, {}]
    # Y sin columna de categoría, no hay categoría: la tabla de palabras clave
    # que antes la deducía del nombre se borró el 15/09/2026. Estas tres filas
    # caen en "Sin categoría.xlsx" y se corrigen a mano en la grilla.
    assert [r["categoriaProducto"] for r in rows] == ["", "", ""]


# ---------------------------------------------------------------------------
# 2 y 3. El umbral: el 1 entra, el 0 no, y el vacío no es un 0
# ---------------------------------------------------------------------------

def test_el_stock_uno_entra_porque_con_una_unidad_ya_hay_que_poner_el_cartel():
    # Ivan lo dijo primero como "mayor a 1" y lo corrigió el mismo día a "mayor
    # o igual a 1". El número vive en UN solo lado: si alguien lo sube a 2, este
    # test se cae y hay que venir a cambiarlo a mano, que es exactamente lo que
    # se quiere cuando cambia un acuerdo.
    assert _STOCK_MINIMO == 1
    rows = [_fila("580735", "Heladera James", "Heladeras", {"suc1": 1, "suc2": 0})]
    zip_bytes, resumen = armar_zip_dividido(
        rows, por_categoria=False, por_sucursal=True, nombre_base="cenefas")
    assert _rutas(zip_bytes) == ["suc1.xlsx"]
    assert resumen["sucursales"] == ["suc1"]
    assert resumen["filas_sin_stock"] == 0


def test_la_celda_vacia_no_es_un_cero():
    # La diferencia que sostiene todo: vacío es "esta sucursal no informó" y 0 es
    # "informó que no tiene". Las dos dejan la fila afuera de esa carpeta, pero
    # el 0 se ve en la grilla y el vacío no existe -- si el vacío se leyera como
    # 0, un listado incompleto tendría la misma cara que una góndola vacía.
    #
    # Desde que el formato es LARGO, esta función es el ÚNICO lugar donde se
    # miran los valores del stock: no hay ninguna columna que aceptar ni
    # descartar por su forma --la sucursal es un valor de la columna
    # `sucursal`-- así que una celda rara no descalifica a la sucursal, solo
    # deja esa fila sin dato ahí.
    assert _parse_stock_or_none("") is None
    assert _parse_stock_or_none(None) is None
    assert _parse_stock_or_none("   ") is None
    assert _parse_stock_or_none(0) == 0
    assert _parse_stock_or_none("0") == 0
    # Lo que openpyxl deja cuando la columna está formateada como número.
    assert _parse_stock_or_none(12.0) == 12
    assert _parse_stock_or_none("12,0") == 12
    # Nada de inventar la mitad que falta: 12,5 no es una cantidad de unidades.
    assert _parse_stock_or_none("12,5") is None
    assert _parse_stock_or_none("-1") is None
    assert _parse_stock_or_none("$1.290") is None
    assert _parse_stock_or_none("SI") is None


def test_una_celda_ilegible_deja_afuera_la_fila_y_no_la_sucursal():
    # El corolario del cambio de criterio, adentro del ZIP. Cuando la sucursal
    # era una COLUMNA, un "12,5" en cualquiera de sus celdas la descalificaba
    # entera y esa sucursal desaparecía del ZIP con todas sus filas. Ahora la
    # sucursal es un VALOR que viene en su propia fila: existe igual, y lo único
    # que pasa es que la fila de la celda ilegible no entra ahí.
    rows = [
        _fila("580735", "Heladera James",   "Heladeras",  {"suc1": "12,5", "suc2": 3}),
        _fila("580736", "Microondas Philco", "Microondas", {"suc1": 2,      "suc2": 1}),
    ]
    zip_bytes, resumen = armar_zip_dividido(
        rows, por_categoria=False, por_sucursal=True, nombre_base="cenefas")
    assert _rutas(zip_bytes) == ["suc1.xlsx", "suc2.xlsx"]
    assert _codigos(zip_bytes, "suc1.xlsx") == ["580736"]
    assert _codigos(zip_bytes, "suc2.xlsx") == ["580735", "580736"]
    assert resumen["filas_sin_stock"] == 0


def test_la_sucursal_que_no_informo_no_recibe_la_fila():
    # Corolario de lo de arriba dentro del ZIP: _stock solo trae las sucursales
    # con valor legible, así que "no hay dato" llega como una clave ausente y no
    # como un 0. El resultado es el mismo --la fila no entra-- y tiene que serlo.
    rows = [_fila("580735", "Heladera James", "Heladeras", {"suc1": 2})]
    zip_bytes, _resumen = armar_zip_dividido(
        rows, por_categoria=False, por_sucursal=True, nombre_base="cenefas")
    assert _rutas(zip_bytes) == ["suc1.xlsx"]


# ---------------------------------------------------------------------------
# 4 y 5. Lo que no sale: la fila sin stock y la sucursal sin filas
# ---------------------------------------------------------------------------

def test_la_fila_sin_stock_en_ninguna_sucursal_no_sale_y_se_cuenta():
    # Es la fila que más fácil se pierde: no falla nada, simplemente no está en
    # ningún archivo. Por eso `filas_sin_stock` existe y por eso la pantalla lo
    # muestra antes de descargar.
    rows = [
        _fila("580735", "Heladera James",  "Heladeras",  {"suc1": 3, "suc2": 0}),
        _fila("580736", "Microondas Philco", "Microondas", {"suc1": 0, "suc2": 0}),
    ]
    zip_bytes, resumen = armar_zip_dividido(
        rows, por_categoria=True, por_sucursal=True, nombre_base="cenefas")
    assert resumen["filas_sin_stock"] == 1
    assert _todos_los_codigos(zip_bytes) == {"580735"}


def test_el_zip_sin_ningun_archivo_devuelve_archivos_cero():
    # El caso que la ruta traduce a 400 (cenefas_convertidor.py): si nadie tiene
    # stock en ninguna sucursal --o si en la pantalla de mapeo se destildaron
    # TODAS las columnas de stock, que es lo que de verdad pasa-- no queda ni un
    # archivo. Acá abajo no es un error: la función arma lo que le piden y
    # devuelve archivos=0. El que habla con una persona es el que avisa.
    #
    # Antes de este acuerdo salía un ZIP de 22 bytes con HTTP 200 y el toast
    # decía "ZIP descargado": el mismo agujero que ya tenía resuelto
    # download_lote contando ENTRADAS y no bytes.
    rows = [
        _fila("580735", "Heladera James",   "Heladeras",  {"suc1": 0, "suc2": 0}),
        _fila("580736", "Microondas Philco", "Microondas", {}),
    ]
    zip_bytes, resumen = armar_zip_dividido(
        rows, por_categoria=True, por_sucursal=True, nombre_base="cenefas")
    assert resumen["archivos"] == 0
    assert _rutas(zip_bytes) == []
    assert resumen["filas_sin_stock"] == 2
    # Y el ZIP igual es un ZIP válido, solo que sin entradas: es exactamente el
    # archivo de 22 bytes que la ruta NO tiene que mandar.
    assert len(zip_bytes) > 0


def test_la_sucursal_sin_ninguna_fila_no_aparece_en_el_zip():
    # No hay forma de "crear la carpeta vacía": las entradas del ZIP son rutas
    # de archivo y la carpeta la inventa el descompresor. suc2 y suc3 existen
    # como columna del Excel y no existen como carpeta, y está bien.
    rows = [
        _fila("580735", "Heladera James",   "Heladeras",  {"suc1": 5, "suc2": 0, "suc3": 0}),
        _fila("580736", "Microondas Philco", "Microondas", {"suc1": 1, "suc2": 0, "suc3": 0}),
    ]
    zip_bytes, resumen = armar_zip_dividido(
        rows, por_categoria=True, por_sucursal=True, nombre_base="cenefas")
    assert resumen["sucursales"] == ["suc1"]
    assert _rutas(zip_bytes) == ["suc1/Heladeras.xlsx", "suc1/Microondas.xlsx"]


# ---------------------------------------------------------------------------
# 6. Sin categoría: visible y contado, nunca perdido
# ---------------------------------------------------------------------------

def test_la_categoria_sale_de_la_columna_y_es_el_nombre_del_excel():
    # De punta a punta, la decisión de Ivan del 15/09/2026: "no hace falta tinín
    # ni nada de detectar automáticamente". La categoría es el valor de
    # `dsc_subfamilia` y de ningún otro lado -- la escribió quien carga el
    # producto, y viaja tal cual desde la celda hasta el nombre del archivo del
    # ZIP. Nada la interpreta: "FREIDORA" no se vuelve "Freidoras de aire", que
    # es lo que hacía la tabla de palabras clave que se borró ese día.
    parsed, _aliases, _headers, _juntado = _parsear(_xlsx(
        _HEADERS_EXPORT_LARGO,
        _fila_export("610220", "FREIDORA DE AIRE ATMA 5L", "Central", 4, "FREIDORA"),
        # Y la contracara: la fila cuya celda vino vacía (2 de los 273 productos
        # del export real). Antes la tabla le adivinaba una categoría por el
        # nombre; ahora no se adivina nada y cae en "Sin categoría.xlsx",
        # visible y contada, para corregirla a mano en la grilla -- para eso la
        # columna es editable.
        _fila_export("503996", "AURICULAR PHILIPS INALAM.", "Central", 2, ""),
    ))
    rows = _a_la_grilla(parsed)
    assert [r["categoriaProducto"] for r in rows] == ["FREIDORA", ""]

    zip_bytes, resumen = armar_zip_dividido(
        rows, por_categoria=True, por_sucursal=False, nombre_base="cenefas")
    assert _rutas(zip_bytes) == ["FREIDORA.xlsx", "Sin categoría.xlsx"]
    assert _codigos(zip_bytes, "FREIDORA.xlsx") == ["610220"]
    assert _codigos(zip_bytes, "Sin categoría.xlsx") == ["503996"]
    assert resumen["categorias"] == ["FREIDORA", "Sin categoría"]
    assert resumen["filas_sin_categoria"] == 1


def test_la_fila_sin_categoria_cae_en_sin_categoria_y_se_cuenta():
    rows = [
        _fila("580735", "Heladera James",       "Heladeras", {"suc1": 2}),
        _fila("580737", "Cosa que nadie conoce", "",          {"suc1": 2}),
    ]
    zip_bytes, resumen = armar_zip_dividido(
        rows, por_categoria=True, por_sucursal=False, nombre_base="cenefas")
    assert _rutas(zip_bytes) == ["Heladeras.xlsx", "Sin categoría.xlsx"]
    assert _codigos(zip_bytes, "Sin categoría.xlsx") == ["580737"]
    assert resumen["filas_sin_categoria"] == 1
    # "Sin categoría" es una categoría más en el resumen: la pantalla tiene que
    # poder decir a dónde fue a parar cada fila.
    assert resumen["categorias"] == ["Heladeras", "Sin categoría"]


def test_la_misma_fila_sin_categoria_en_ocho_sucursales_se_cuenta_una_sola_vez():
    # El número del resumen es "cuántas filas hay que clasificar", no "cuántas
    # veces se escribió una fila sin clasificar". Con los dos interruptores
    # prendidos la misma fila sale repetida en todas sus sucursales --es correcto,
    # está en varias góndolas-- pero para clasificar sigue siendo una sola.
    rows = [_fila("580737", "Cosa que nadie conoce", "", {f"suc{i}": 4 for i in range(1, 9)})]
    zip_bytes, resumen = armar_zip_dividido(
        rows, por_categoria=True, por_sucursal=True, nombre_base="cenefas")
    assert resumen["archivos"] == 8
    assert resumen["filas_sin_categoria"] == 1


# ---------------------------------------------------------------------------
# 7 y 8. Los tres modos, y el cuarto que no existe
# ---------------------------------------------------------------------------

def test_solo_por_categoria_no_filtra_por_stock():
    # Con "dividir por sucursales" apagado no hay eje de sucursal, así que no hay
    # contra qué comparar el stock: entran TODAS las filas, incluida la 580738
    # que no tiene stock en ninguna parte. El filtro por stock es parte de
    # dividir por sucursal, no una regla suelta.
    zip_bytes, resumen = armar_zip_dividido(
        _filas_de_prueba(), por_categoria=True, por_sucursal=False, nombre_base="cenefas")
    assert _rutas(zip_bytes) == [
        "Freidoras de aire.xlsx", "Heladeras.xlsx", "Microondas.xlsx", "Sin categoría.xlsx",
    ]
    assert resumen["filas_sin_stock"] == 0
    assert resumen["sucursales"] == []
    assert len(_todos_los_codigos(zip_bytes)) == 4


def test_solo_por_sucursal_deja_el_zip_plano():
    # Un solo eje, un solo nivel: "suc1.xlsx" suelto y ninguna carpeta. La
    # carpeta aparece únicamente cuando hay dos ejes que cruzar.
    zip_bytes, resumen = armar_zip_dividido(
        _filas_de_prueba(), por_categoria=False, por_sucursal=True, nombre_base="cenefas")
    assert _rutas(zip_bytes) == ["suc1.xlsx", "suc2.xlsx", "suc3.xlsx"]
    assert resumen["sucursales"] == ["suc1", "suc2", "suc3"]
    assert resumen["filas_sin_stock"] == 1          # la 580738
    assert resumen["filas_sin_categoria"] == 0      # no existe ningún "Sin categoría"
    assert _codigos(zip_bytes, "suc1.xlsx") == ["580735", "580736"]
    assert _codigos(zip_bytes, "suc3.xlsx") == ["580735"]


def test_las_dos_prendidas_es_una_carpeta_por_sucursal_con_un_excel_por_categoria():
    # El pedido textual de Ivan. La 580735 sale DOS veces (suc1 y suc3) porque
    # está en dos góndolas, y la 580738 no sale ninguna.
    zip_bytes, resumen = armar_zip_dividido(
        _filas_de_prueba(), por_categoria=True, por_sucursal=True, nombre_base="cenefas")
    assert _rutas(zip_bytes) == [
        "suc1/Heladeras.xlsx",
        "suc1/Microondas.xlsx",
        "suc2/Sin categoría.xlsx",
        "suc3/Heladeras.xlsx",
    ]
    assert resumen["archivos"] == 4
    assert resumen["filas_sin_stock"] == 1
    assert resumen["filas_sin_categoria"] == 1
    assert _codigos(zip_bytes, "suc1/Heladeras.xlsx") == ["580735"]
    assert _codigos(zip_bytes, "suc3/Heladeras.xlsx") == ["580735"]


def test_los_dos_interruptores_apagados_es_un_error_y_no_una_descarga_entera():
    # No es "bajá el Excel completo": para eso está /export, que devuelve un xlsx
    # y no un zip. El cliente hardcodea la extensión, así que devolver un ZIP por
    # esta puerta le rompe la descarga a quien lo pidió. La ruta lo traduce a 400.
    with pytest.raises(ValueError) as exc:
        armar_zip_dividido(
            _filas_de_prueba(), por_categoria=False, por_sucursal=False, nombre_base="cenefas")
    assert "dividir" in str(exc.value)


# ---------------------------------------------------------------------------
# 9. Todos los libros de la tanda, con las mismas columnas
# ---------------------------------------------------------------------------

def test_todos_los_libros_del_zip_salen_con_las_mismas_columnas():
    # Son archivos que se abren uno al lado del otro para compararlos. Si cada
    # libro dedujera sus columnas, la sucursal que ese día no tuviera ninguna
    # fila con banco saldría sin las columnas de banco y la de al lado con ellas.
    rows = [
        _fila("580735", "Heladera James",   "Heladeras",  {"suc1": 2}),
        _fila("580736", "Microondas Philco", "Microondas", {"suc2": 2},
              banco="ITAU", precioBanco="999"),
    ]
    zip_bytes, _resumen = armar_zip_dividido(
        rows, por_categoria=True, por_sucursal=True, nombre_base="cenefas")
    encabezados = {ruta: _encabezados(zip_bytes, ruta) for ruta in _rutas(zip_bytes)}
    assert len(encabezados) == 2
    assert len({tuple(cols) for cols in encabezados.values()}) == 1
    # Y la columna que tiene UNA sola fila está en los dos libros.
    assert "banco" in encabezados["suc1/Heladeras.xlsx"]


def test_el_contexto_nuevo_no_se_convierte_en_columna_del_excel():
    # La regla de nombres del contrato: ninguna clave nueva puede llamarse como
    # una variable de ORDEN_EXPORT o se cuela como columna del xlsx sin querer
    # (es lo que pasó con `tipoOferta`). stockPorSucursal y categoriaProducto son
    # contexto: se ven en la grilla, deciden el archivo, y no se exportan.
    rows = [_fila("580735", "Heladera James", "Heladeras", {"suc1": 2})]
    zip_bytes, _resumen = armar_zip_dividido(
        rows, por_categoria=True, por_sucursal=False, nombre_base="cenefas")
    columnas = _encabezados(zip_bytes, "Heladeras.xlsx")
    assert "stockPorSucursal" not in columnas
    assert "categoriaProducto" not in columnas


def test_build_output_workbook_respeta_las_columnas_que_le_pasan():
    # El parámetro que hace posible lo de arriba. Sin `columnas`, el
    # comportamiento de siempre queda intacto: lo deduce de estas filas.
    fila = _fila("580735", "Heladera James", "Heladeras", {"suc1": 2})
    fijas = openpyxl.load_workbook(
        io.BytesIO(build_output_workbook([fila], ["codigo", "banco"]))).active
    assert [c.value for c in fijas[1]] == ["codigo", "banco"]
    deducidas = openpyxl.load_workbook(io.BytesIO(build_output_workbook([fila]))).active
    assert [c.value for c in deducidas[1]][0] == "codigo"
    assert "banco" not in [c.value for c in deducidas[1]]


# Acá vivían los seis tests de categoria_de_producto --el orden de la tabla, la plancha de pelo, los tres textos--: se borraron el 15/09/2026 con la función, porque la categoría sale de la columna dsc_subfamilia y ya no se deduce de nada.


# ---------------------------------------------------------------------------
# 11 y 12. Los nombres: los escribe una persona, celda por celda
# ---------------------------------------------------------------------------

def test_nombre_para_zip_deja_algo_que_windows_pueda_escribir():
    # _nombre_archivo de cenefas_v2.py no sirve tal cual: no toca los puntos, ni
    # el "..", ni el punto/espacio final, que es lo que hace fallar la extracción.
    assert _nombre_para_zip("Punta Carretas/Centro") == "Punta CarretasCentro"
    assert _nombre_para_zip("Tienda Inglesa S.A.") == "Tienda Inglesa S.A"
    assert _nombre_para_zip("Suc 3 ") == "Suc 3"
    assert _nombre_para_zip("..") == "SIN NOMBRE"
    assert _nombre_para_zip("") == "SIN NOMBRE"
    assert _nombre_para_zip("   ") == "SIN NOMBRE"


def test_nombre_para_zip_no_devuelve_un_nombre_reservado_de_windows():
    # Regresión del 15/09/2026. "CON", "AUX", "NUL", "PRN", "COM1".."COM9" y
    # "LPT1".."LPT9" son DISPOSITIVOS del DOS, no archivos: no se pueden crear
    # con ese nombre ni como archivo ni como carpeta, y el que descomprime se
    # queda sin ese archivo o sin el ZIP entero según con qué lo abra. No tienen
    # ningún caracter prohibido que sacar, así que pasaban enteros. Una
    # categoría "Aux" o una sucursal escrita "Con" alcanzan para romperlo.
    assert _nombre_para_zip("CON") == "CON_"
    assert _nombre_para_zip("AUX") == "AUX_"
    assert _nombre_para_zip("con") == "con_"
    assert _nombre_para_zip("Aux") == "Aux_"
    assert _nombre_para_zip("COM1") == "COM1_"
    assert _nombre_para_zip("LPT9") == "LPT9_"
    # Windows mira el nombre ANTES del primer punto: "NUL.xlsx" sigue siendo el
    # dispositivo, así que el "_" va pegado a esa parte y no al final.
    assert _nombre_para_zip("NUL.xlsx") == "NUL_.xlsx"
    # Y lo que solo EMPIEZA como un reservado es un nombre normal: no se toca.
    assert _nombre_para_zip("CONSUR") == "CONSUR"
    assert _nombre_para_zip("COM0") == "COM0"


def test_una_sucursal_con_nombre_reservado_sale_en_el_zip():
    # El mismo caso, ya adentro del ZIP: la carpeta y el archivo salen con el
    # "_" y el ZIP se puede descomprimir entero.
    rows = [_fila("580735", "Heladera James", "Aux", {"CON": 2})]
    zip_bytes, resumen = armar_zip_dividido(
        rows, por_categoria=True, por_sucursal=True, nombre_base="cenefas")
    assert _rutas(zip_bytes) == ["CON_/Aux_.xlsx"]
    assert resumen["archivos"] == 1


def test_los_nombres_raros_de_sucursal_no_rompen_el_zip():
    # El encabezado de la columna ES el nombre de la sucursal, o sea texto que
    # escribe gestión: nadie le va a avisar al Convertidor antes de poner una
    # barra ahí adentro. Perder el archivo es peor que un nombre feo.
    rows = [
        _fila("1", "Heladera James", "Heladeras", {"Punta Carretas/Centro": 2}),
        _fila("2", "Heladera James", "Heladeras", {"..": 2}),
        _fila("3", "Heladera James", "Heladeras", {"Tienda Inglesa S.A.": 2}),
        _fila("4", "Heladera James", "Heladeras", {"   ": 2}),
    ]
    zip_bytes, resumen = armar_zip_dividido(
        rows, por_categoria=True, por_sucursal=True, nombre_base="cenefas")
    rutas = _rutas(zip_bytes)
    # Ninguna fila se perdió y ninguna ruta anidó de más: la barra del nombre no
    # creó un nivel de carpeta que nadie pidió.
    assert len(rutas) == 4
    assert resumen["archivos"] == 4
    assert _todos_los_codigos(zip_bytes) == {"1", "2", "3", "4"}
    assert all(ruta.count("/") == 1 for ruta in rutas)
    carpetas = [ruta.split("/")[0] for ruta in rutas]
    assert ".." not in carpetas
    assert "Punta CarretasCentro" in carpetas
    assert "Tienda Inglesa S.A" in carpetas
    # Las dos que no dejan nada usable ("   " y "..") son DOS tiendas distintas
    # y quedan en DOS carpetas: el sufijo va en la carpeta, no en el archivo.
    assert sorted(ruta for ruta in rutas if ruta.startswith("SIN NOMBRE")) == [
        "SIN NOMBRE (2)/Heladeras.xlsx", "SIN NOMBRE/Heladeras.xlsx",
    ]
    # El resumen muestra los nombres LÓGICOS, los que la persona ve en la grilla:
    # el saneado es cosa del nombre del archivo. El "   " llega con los espacios
    # ya sacados porque el nombre de sucursal se limpia antes de agrupar.
    assert resumen["sucursales"] == ["", "..", "Punta Carretas/Centro", "Tienda Inglesa S.A."]


def test_dos_sucursales_que_sanean_al_mismo_nombre_quedan_en_dos_carpetas():
    # Regresión del 15/09/2026, y es el arreglo más caro de todos. "Suc/1" y
    # "Suc1" son DOS tiendas y los dos nombres sanean a "Suc1" (la barra se
    # saca). Antes el saneado se hacía al armar cada ruta, así que las dos
    # tiendas terminaban compartiendo UNA carpeta con las filas mezcladas:
    # salía "Suc1/Heladeras.xlsx" y "Suc1/Heladeras (2).xlsx" y el que repone
    # góndola no tenía cómo saber cuál archivo era de cuál tienda, porque el
    # sufijo se lo comía el archivo en vez de la carpeta.
    rows = [
        _fila("580735", "Heladera James",   "Heladeras", {"Suc/1": 2}),
        _fila("580736", "Microondas Philco", "Heladeras", {"Suc1": 2}),
    ]
    zip_bytes, resumen = armar_zip_dividido(
        rows, por_categoria=True, por_sucursal=True, nombre_base="cenefas")
    assert _rutas(zip_bytes) == ["Suc1 (2)/Heladeras.xlsx", "Suc1/Heladeras.xlsx"]
    assert resumen["archivos"] == 2
    # Y cada archivo con las filas de SU tienda, que es lo que se perdía.
    assert _codigos(zip_bytes, "Suc1/Heladeras.xlsx") == ["580735"]
    assert _codigos(zip_bytes, "Suc1 (2)/Heladeras.xlsx") == ["580736"]
    assert resumen["sucursales"] == ["Suc/1", "Suc1"]


def test_la_misma_categoria_escrita_distinto_es_un_solo_archivo():
    # Regresión del 15/09/2026. La categoría se corrige A MANO en la grilla, así
    # que una fila arreglada como "heladeras" y otra como "Heladeras" son el
    # mismo tipo de producto. Agrupadas por el string exacto salían DOS archivos
    # que para Windows tienen el mismo nombre: al descomprimir uno pisaba al
    # otro y esas filas desaparecían sin un solo error. Ahora se agrupa por _norm
    # y se muestra la primera grafía que apareció.
    rows = [
        _fila("580735", "Heladera James",   "Heladeras", {"suc1": 2}),
        _fila("580736", "Freezer James",    "heladeras", {"suc1": 2}),
        _fila("580737", "Heladera Samsung", "HELADERAS", {"suc1": 2}),
    ]
    zip_bytes, resumen = armar_zip_dividido(
        rows, por_categoria=True, por_sucursal=True, nombre_base="cenefas")
    assert _rutas(zip_bytes) == ["suc1/Heladeras.xlsx"]
    assert resumen["archivos"] == 1
    assert resumen["categorias"] == ["Heladeras"]
    assert _codigos(zip_bytes, "suc1/Heladeras.xlsx") == ["580735", "580736", "580737"]


def test_la_misma_sucursal_escrita_distinto_es_una_sola_carpeta():
    # El mismo arreglo del lado de las sucursales: "suc1" y "SUC1" armaban dos
    # carpetas con el mismo nombre para Windows. Y ahora hace MÁS falta que
    # antes: el nombre de la sucursal es texto que gestión escribe celda por
    # celda, sin ninguna lista contra la cual canonizarlo, así que dos grafías
    # del mismo local en el mismo archivo son perfectamente posibles.
    rows = [
        _fila("580735", "Heladera James",   "Heladeras",  {"suc1": 2}),
        _fila("580736", "Microondas Philco", "Microondas", {"SUC1": 2}),
    ]
    zip_bytes, resumen = armar_zip_dividido(
        rows, por_categoria=True, por_sucursal=True, nombre_base="cenefas")
    assert _rutas(zip_bytes) == ["suc1/Heladeras.xlsx", "suc1/Microondas.xlsx"]
    assert resumen["sucursales"] == ["suc1"]


def test_dos_categorias_que_sanean_al_mismo_nombre_no_se_pisan():
    # "Heladeras/Freezers" y "HeladerasFreezers" quedan idénticas después de
    # sacar la barra, y ahí una se comía a la otra adentro del ZIP sin que nadie
    # se enterara -- el mismo problema que ya tiene resuelto download_lote.
    rows = [
        _fila("580735", "Heladera James", "Heladeras/Freezers", {"suc1": 2}),
        _fila("580736", "Freezer James",  "HeladerasFreezers",  {"suc1": 2}),
    ]
    zip_bytes, resumen = armar_zip_dividido(
        rows, por_categoria=True, por_sucursal=False, nombre_base="cenefas")
    assert _rutas(zip_bytes) == ["HeladerasFreezers (2).xlsx", "HeladerasFreezers.xlsx"]
    assert resumen["archivos"] == 2
    assert _todos_los_codigos(zip_bytes) == {"580735", "580736"}
    # Cada una con su fila: el sufijo resuelve el nombre, no junta el contenido.
    assert _codigos(zip_bytes, "HeladerasFreezers.xlsx") == ["580735"]
    assert _codigos(zip_bytes, "HeladerasFreezers (2).xlsx") == ["580736"]


# ---------------------------------------------------------------------------
# Punta a punta: del .xlsx de gestión al ZIP
# ---------------------------------------------------------------------------

def test_punta_a_punta_el_export_largo_sale_como_una_carpeta_por_sucursal():
    # El pedido de Ivan entero, sobre un archivo con la forma REAL: se lee, se
    # junta, se arma el ZIP. Cada test de arriba mira una pieza; este mira el
    # hilo, que es donde se rompen estas cosas. Si alguien saca el juntado del
    # parser y lo deja en la ruta, acá salen NUEVE cenefas en vez de tres y
    # todos los demás tests siguen en verde.
    datos = _xlsx(
        _HEADERS_EXPORT_LARGO,
        _fila_export("503996", "AURICULAR PHILIPS INALAM. UPBEAT NEGRO", "Central", 5, "AURICULARES"),
        _fila_export("503996", "AURICULAR PHILIPS INALAM. UPBEAT NEGRO", "Arocena", 0, "AURICULARES"),
        _fila_export("503996", "AURICULAR PHILIPS INALAM. UPBEAT NEGRO", "Pocitos", 2, "AURICULARES"),
        _fila_export("610220", "FREIDORA DE AIRE ATMA 5L",              "Central", 0, "FREIDORA"),
        _fila_export("610220", "FREIDORA DE AIRE ATMA 5L",              "Arocena", 3, "FREIDORA"),
        _fila_export("610220", "FREIDORA DE AIRE ATMA 5L",              "Pocitos", 0, "FREIDORA"),
        _fila_export("707311", "PARLANTE JBL GO 3",                     "Central", 0, "PARLANTES CHICOS"),
        _fila_export("707311", "PARLANTE JBL GO 3",                     "Arocena", 0, "PARLANTES CHICOS"),
        _fila_export("707311", "PARLANTE JBL GO 3",                     "Pocitos", 0, "PARLANTES CHICOS"),
    )

    parsed, _aliases, headers, juntado = _parsear(datos)
    # Los headers crudos vuelven para poder re-abrir la pantalla de mapeo, y son
    # los del export de gestión y no los del Convertidor.
    assert headers[0] == "id_producto"
    assert len(parsed) == 3
    assert juntado == {"filas": 9, "productos": 3,
                       "sucursales": ["Central", "Arocena", "Pocitos"],
                       "con_diferencias": 0, "filas_sin_sucursal": 0}

    rows = _a_la_grilla(parsed)
    # La categoría sale de dsc_subfamilia y de ningún otro lado: la escribió
    # quien carga el producto. Se nota en la freidora, que sale "FREIDORA" tal
    # cual --la tabla de palabras clave, que decía "Freidoras de aire", se borró.
    assert [r["categoriaProducto"] for r in rows] == [
        "AURICULARES", "FREIDORA", "PARLANTES CHICOS",
    ]
    # Y el stock llegó hasta acá: es match_rows el que pasa "_stock" del parser
    # a `stockPorSucursal`, la clave con la que se decide la carpeta.
    assert rows[0]["stockPorSucursal"] == {"Central": 5, "Arocena": 0, "Pocitos": 2}

    zip_bytes, resumen = armar_zip_dividido(
        rows, por_categoria=True, por_sucursal=True, nombre_base="cenefas")
    # Una carpeta por sucursal y adentro un Excel por subfamilia, con lo que esa
    # sucursal tiene para vender. Arocena solo tiene la freidora; el auricular
    # está en Central y en Pocitos y sale en las dos, que es correcto: está en
    # las dos góndolas.
    assert _rutas(zip_bytes) == [
        "Arocena/FREIDORA.xlsx",
        "Central/AURICULARES.xlsx",
        "Pocitos/AURICULARES.xlsx",
    ]
    assert resumen["archivos"] == 3
    assert resumen["sucursales"] == ["Arocena", "Central", "Pocitos"]
    assert resumen["categorias"] == ["AURICULARES", "FREIDORA"]
    # El parlante no tiene stock en ninguna parte: no sale en ningún archivo y
    # se cuenta, que es lo que la pantalla muestra antes de descargar.
    assert resumen["filas_sin_stock"] == 1
    assert _todos_los_codigos(zip_bytes) == {"503996", "610220"}
    # Ninguna sucursal vacía y ningún "Sin categoría": el export las trae todas.
    assert resumen["filas_sin_categoria"] == 0

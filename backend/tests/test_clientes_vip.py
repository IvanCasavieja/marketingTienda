"""Clientes VIP (0091, 25/11/2026) y lo que usa Valentina desde la nube (0092).

Ivan: "un dashboard con un agente que analice… prever el comportamiento futuro
de los clientes VIP… tengo acceso yo y Emi Perdomo". Lo puro (segmentos,
riesgo, predicción) corre siempre; la carga de punta a punta con la
API usa la base de TEST_DATABASE_URL, con las ayudas de
test_tablero_agencia_api.py.
"""
import os
from datetime import date

import pytest

from app.models.role import ALL_PERMISSIONS, DEFAULT_ROLES
from app.services import clientes_vip as vip

URL = os.environ.get("TEST_DATABASE_URL")
OCT = date(2026, 10, 1)


def _hist(ventas: dict[int, int], tickets: int = 4) -> dict:
    """{meses para atrás desde octubre: venta} → historial."""
    return {vip.sumar_meses(OCT, -k): (v, tickets if v else 0) for k, v in ventas.items()}


# ---------------------------------------------------------------------------
# Los permisos
# ---------------------------------------------------------------------------

def test_los_permisos_existen_y_no_vienen_con_ningun_rol_salvo_superadmin():
    assert vip.PERMISO_VER in ALL_PERMISSIONS and vip.PERMISO_CARGAR in ALL_PERMISSIONS
    for rol in DEFAULT_ROLES:
        if rol["name"] != "Superadmin":
            assert vip.PERMISO_VER not in rol["permissions"], rol["name"]
            assert vip.PERMISO_CARGAR not in rol["permissions"], rol["name"]


# ---------------------------------------------------------------------------
# Meses
# ---------------------------------------------------------------------------

def test_meses():
    assert vip.sumar_meses(date(2026, 1, 1), -1) == date(2025, 12, 1)
    assert vip.sumar_meses(date(2025, 11, 1), 3) == date(2026, 2, 1)
    assert vip.meses_entre(date(2025, 11, 1), date(2026, 2, 1)) == 3
    assert vip.mes_de("2026-03") == date(2026, 3, 1)
    for malo in ("2026-13", "26-03", "2026/03", "", "1999-01"):
        with pytest.raises(ValueError):
            vip.mes_de(malo)


# ---------------------------------------------------------------------------
# La foto de cada cliente
# ---------------------------------------------------------------------------

DESDE = date(2025, 1, 1)


def test_estable_creciendo_bajando():
    estable = vip.perfil(_hist({k: 10_000 for k in range(12)}), OCT, DESDE)
    assert estable["segmento"] == "Estable" and estable["riesgo"] == 0
    assert estable["venta_esperada"] == 10_000

    crece = vip.perfil(_hist({0: 15_000, 1: 15_000, 2: 15_000, 3: 10_000, 4: 10_000, 5: 10_000}), OCT, DESDE)
    assert crece["segmento"] == "Creciendo"

    baja = vip.perfil(_hist({0: 8_000, 1: 8_000, 2: 8_000, 3: 10_000, 4: 10_000, 5: 10_000}), OCT, DESDE)
    assert baja["segmento"] == "Bajando" and 0 < baja["riesgo"] < 50


def test_el_que_no_compro_el_ultimo_mes_esta_en_riesgo_y_a_los_3_se_perdio():
    sin_octubre = vip.perfil(_hist({1: 10_000, 2: 10_000, 3: 10_000, 4: 10_000, 5: 10_000}), OCT, DESDE)
    assert sin_octubre["segmento"] == "En riesgo"
    cae_fuerte = vip.perfil(_hist({0: 3_000, 1: 3_000, 2: 3_000, 3: 10_000, 4: 10_000, 5: 10_000}), OCT, DESDE)
    assert cae_fuerte["segmento"] == "En riesgo"
    perdido = vip.perfil(_hist({3: 10_000, 4: 10_000, 5: 10_000}), OCT, DESDE)
    assert perdido == {"segmento": "Perdido", "riesgo": 100, "venta_esperada": 0}
    # Más riesgo cuanto más tiempo sin comprar
    dos_meses = vip.perfil(_hist({2: 10_000, 3: 10_000, 4: 10_000, 5: 10_000}), OCT, DESDE)
    assert sin_octubre["riesgo"] < dos_meses["riesgo"] < 100


def test_nuevo_solo_si_hay_datos_de_antes_para_saberlo():
    assert vip.perfil(_hist({0: 5_000, 1: 5_000}), OCT, DESDE)["segmento"] == "Nuevo"
    # Si los datos arrancan en septiembre, no se sabe si es nuevo.
    assert vip.perfil(_hist({0: 5_000, 1: 5_000}), OCT, date(2026, 9, 1))["segmento"] != "Nuevo"


def test_la_venta_esperada_sigue_a_los_ultimos_meses_y_a_la_estacion():
    p = vip.perfil(_hist({0: 10_000, 1: 20_000, 2: 30_000}), OCT, DESDE, estacional=1.2)
    assert p["venta_esperada"] == round((0.5 * 10_000 + 0.3 * 20_000 + 0.2 * 30_000) * 1.2)


def test_factor_estacional_con_tope_y_sin_historia():
    assert vip.factor_estacional({}, OCT) == 1.0
    serie = {vip.sumar_meses(OCT, -12 - k): 100 for k in range(3)}
    serie[vip.sumar_meses(OCT, -11)] = 130  # noviembre del año pasado
    assert vip.factor_estacional(serie, OCT) == pytest.approx(1.3)
    serie[vip.sumar_meses(OCT, -11)] = 1000
    assert vip.factor_estacional(serie, OCT) == 1.4


def test_ficha_suma_12_meses_y_elige_sucursal_y_categoria():
    filas = [
        (vip.sumar_meses(OCT, -k), 10_000, 2_000, 4, 1_000, "Carrasco" if k < 6 else "Punta Carretas",
         "Almacén=6000;Bebidas=3000;Lácteos=1000")
        for k in range(14)
    ]
    f = vip.ficha(7, filas, OCT, DESDE, 1.0)
    assert f["venta_12m"] == 120_000 and f["margen_12m"] == 24_000 and f["tickets_12m"] == 48
    assert f["meses_con_compra"] == 12 and f["ultimo_mes"] == OCT
    assert f["categoria"] == "Almacén" and f["parte_ecommerce"] == 10
    assert f["sucursal"] == "Carrasco"  # 6 meses contra 6: gana la primera que llegó a ese total


# ---------------------------------------------------------------------------
# Valentina
# ---------------------------------------------------------------------------

def _serie(meses: int, base: int = 280_000_000, crecimiento: float = 0.0) -> dict:
    return {vip.sumar_meses(OCT, -k): round(base * (1 + crecimiento) ** (-k)) for k in range(meses)}


def test_prediccion_sin_un_anio_usa_lo_de_cada_cliente():
    p = vip.prediccion_global(_serie(10), OCT, 270_000_000)
    assert p["mes"] == "2026-11" and p["venta"] == 270_000_000
    assert p["margen_error"] == 10.0 and p["desde"] < p["venta"] < p["hasta"]
    assert "cada cliente" in p["como"]


def test_prediccion_con_dos_anios_promedia_y_mide_su_error():
    serie = _serie(22, crecimiento=0.01)
    p = vip.prediccion_global(serie, OCT, 0)
    assert p["como"] == "el mismo mes del año pasado con la tendencia de hoy"
    # Con un crecimiento parejo el camino del año anterior acierta: el margen queda en el mínimo.
    assert p["margen_error"] == 3.0
    assert p["venta"] == pytest.approx(serie[OCT] * 1.01, rel=0.001)
    ambos = vip.prediccion_global(serie, OCT, 250_000_000)
    assert ambos["venta"] == round((p["venta"] + 250_000_000) / 2)


# ---------------------------------------------------------------------------
# De punta a punta, con la API y una base de verdad
# ---------------------------------------------------------------------------

if URL:
    from sqlalchemy import func, select

    from app.models.clientes_vip import VipCarga, VipClienteMes, VipMesDimension
    from test_tablero_agencia_api import Cliente, _persona, correr

_con_base = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: estas pruebas necesitan una base Postgres")


def _fila(cliente: int, mes: str, venta: int, sucursal="Carrasco") -> list:
    return [cliente, mes, venta, venta // 3, 10, 3, 3, 0, 0, venta // 10, sucursal, f"Almacén={venta}"]


async def _cargar(cliente, archivo: str, filas: list[list], dims: list[dict] | None = None) -> dict:
    meses = sorted({f[1] for f in filas})
    r = await cliente.post("/clientes-vip/cargas", json={"archivo": archivo, "meses": meses, "filas": len(filas)})
    assert r.status_code == 200, r.text
    carga_id = r.json()["id"]
    for i in range(0, len(filas), 2):  # en tandas, como el navegador
        r = await cliente.post(f"/clientes-vip/cargas/{carga_id}/filas", json={"filas": filas[i:i + 2]})
        assert r.status_code == 200, r.text
    r = await cliente.post(f"/clientes-vip/cargas/{carga_id}/terminar", json={"dimensiones": dims or []})
    assert r.status_code == 200, r.text
    return r.json()


@_con_base
def test_emi_carga_dos_archivos_ve_el_tablero_y_los_demas_no():

    async def prueba(d):
        emi = Cliente(d.http, await _persona(d, "Emi VIP", permisos=(vip.PERMISO_VER, vip.PERMISO_CARGAR)))
        mira = Cliente(d.http, await _persona(d, "Mira VIP", permisos=(vip.PERMISO_VER,)))
        nadie = Cliente(d.http, await _persona(d, "Sin VIP"))
        agencia = Cliente(d.http, d.a1)

        # 2025: el cliente 1 compra todo el año, el 2 deja en octubre.
        filas = [_fila(1, f"2025-{m:02d}", 10_000) for m in range(1, 13)]
        filas += [_fila(2, f"2025-{m:02d}", 8_000) for m in range(1, 10)]
        dims = [{"mes": "2025-12", "dimension": "categoria", "valor": "Almacén", "venta": 10_000, "margen": 3_000,
                 "unidades": 10, "tickets": 3, "clientes": 1}]
        r = await _cargar(emi, "compras_2025.zip", filas, dims)
        assert r["clientes"] == 2

        t = (await mira.get("/clientes-vip/tablero")).json()
        assert t["ultimo_mes"] == "2025-12" and t["clientes"] == 2
        assert [m["mes"] for m in t["meses"]][:2] == ["2025-01", "2025-02"]
        assert {s["segmento"]: s["clientes"] for s in t["segmentos"]} == {"Estable": 1, "Perdido": 1}
        assert t["dimensiones"]["categoria"][0]["valor"] == "Almacén"
        assert t["cargas"][0]["archivo"] == "compras_2025.zip" and t["cargas"][0]["estado"] == "lista"
        assert t["prediccion"]["mes"] == "2026-01"

        lista = (await mira.get("/clientes-vip/clientes", params={"orden": "riesgo"})).json()
        assert lista["total"] == 2 and lista["filas"][0]["id_cliente"] == 2
        det = (await mira.get("/clientes-vip/clientes/1")).json()
        assert len(det["meses"]) == 12 and det["meses"][0]["categorias"] == [{"nombre": "Almacén", "venta": 10_000}]

        # Cargar de nuevo diciembre lo reemplaza: el cliente 1 ya no está en diciembre, el 3 sí.
        await _cargar(emi, "diciembre_corregido.csv", [_fila(3, "2025-12", 5_000)])
        async with d.Sesion() as s:
            dic = (await s.execute(select(VipClienteMes.id_cliente).where(VipClienteMes.mes == date(2025, 12, 1)))).scalars().all()
            assert dic == [3]
            assert (await s.scalar(select(func.count()).select_from(VipMesDimension))) == 0
            assert (await s.scalar(select(func.count()).select_from(VipClienteMes).where(
                VipClienteMes.mes == date(2025, 11, 1)))) == 1

        # Quien solo ve no carga; sin permiso, nada; la agencia, nada.
        r = await mira.post("/clientes-vip/cargas", json={"archivo": "x.csv", "meses": ["2026-01"], "filas": 1})
        assert r.status_code == 403
        for c in (nadie, agencia):
            assert (await c.get("/clientes-vip/tablero")).status_code in (403, 404)
            assert (await c.get("/clientes-vip/clientes/1")).status_code in (403, 404)

        # Una fila de un mes que no es de la carga, o rota, no entra.
        r = await emi.post("/clientes-vip/cargas", json={"archivo": "x.csv", "meses": ["2026-01"], "filas": 1})
        carga_id = r.json()["id"]
        r = await emi.post(f"/clientes-vip/cargas/{carga_id}/filas", json={"filas": [_fila(9, "2026-02", 1)]})
        assert r.status_code == 400
        r = await emi.post(f"/clientes-vip/cargas/{carga_id}/filas", json={"filas": [[9, "2026-01"]]})
        assert r.status_code == 400
        async with d.Sesion() as s:
            assert (await s.get(VipCarga, carga_id)).estado == "cargando"
    correr(prueba)


@_con_base
def test_valentina_baja_los_datos_publica_su_informe_y_anota_lo_que_aprende():
    """Valentina (Escuadrón Lechuza, en la nube) con su cuenta: ver y cargar."""

    async def prueba(d):
        emi = Cliente(d.http, await _persona(d, "Emi Datos", permisos=(vip.PERMISO_VER, vip.PERMISO_CARGAR)))
        valentina = Cliente(d.http, await _persona(d, "Valentina Agente", permisos=(vip.PERMISO_VER, vip.PERMISO_CARGAR)))
        mira = Cliente(d.http, await _persona(d, "Mira Datos", permisos=(vip.PERMISO_VER,)))
        nadie = Cliente(d.http, await _persona(d, "Sin Datos"))
        filas = [_fila(1, f"2026-{m:02d}", 10_000) for m in range(1, 11)] + [_fila(2, "2026-10", 7_000, 'La "Barra";')]
        dims = [{"mes": "2026-10", "dimension": "canal", "valor": "Tienda Inglesa", "venta": 17_000, "margen": 5_000,
                 "unidades": 20, "tickets": 6, "clientes": 2}]
        await _cargar(emi, "2026.csv", filas, dims)

        # Antes de que ella publique: el tablero no tiene informe ni predicción suya.
        t = (await mira.get("/clientes-vip/tablero")).json()
        assert t["informe"] is None and t["prediccion_valentina"] is None and t["prediccion"]["mes"] == "2026-11"

        # Baja los datos en CSV (las comillas y el punto y coma de un nombre no rompen nada).
        r = await valentina.get("/clientes-vip/datos", params={"tabla": "clientes_mes"})
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
        lineas = r.text.strip().split("\n")
        assert lineas[0] == ";".join(vip.COLUMNAS_CLIENTES_MES) and len(lineas) == 1 + len(filas)
        assert '"La ""Barra"";"' in r.text
        assert (await valentina.get("/clientes-vip/datos", params={"tabla": "dimensiones"})).text.count("\n") == 2
        assert (await valentina.get("/clientes-vip/datos", params={"tabla": "clientes"})).status_code == 200
        assert (await valentina.get("/clientes-vip/datos", params={"tabla": "users"})).status_code == 400
        n = (await valentina.get("/clientes-vip/numeros")).json()
        assert n["ultimo_mes"] == "octubre 2026" and n["clientes_vip"] == 2

        # Anota lo que aprendió; lo puede ver cualquiera con el permiso.
        r = await valentina.post("/clientes-vip/memoria", json={
            "tema": "Calendario comercial", "texto": "Noviembre trae Black Friday y CyberLunes: no compararlo con octubre a secas.",
            "fuente": "mail de Ivan del 26/11"})
        assert r.status_code == 200, r.text
        nota = r.json()
        assert [x["tema"] for x in (await mira.get("/clientes-vip/memoria")).json()] == ["Calendario comercial"]
        # Se corrige y se retira, sin borrar: queda en el historial.
        r = await valentina.patch(f"/clientes-vip/memoria/{nota['id']}", json={"activo": False})
        assert r.status_code == 200 and r.json()["activo"] is False
        assert (await mira.get("/clientes-vip/memoria")).json() == []
        assert len((await mira.get("/clientes-vip/memoria", params={"retiradas": True})).json()) == 1

        # Publica su informe con su predicción: el tablero muestra los dos.
        r = await valentina.post("/clientes-vip/informes", json={
            "mes": "2026-10", "autor": "Valentina",
            "analisis": "### 📊 Cómo cerró octubre 2026\n- Lo que pasó, explicado con calma y con los datos.",
            "prediccion": {"mes": "2026-11", "venta": 18_000, "desde": 16_000, "hasta": 20_000, "como": "cohortes + calendario"}})
        assert r.status_code == 200, r.text
        t = (await mira.get("/clientes-vip/tablero")).json()
        assert t["informe"]["autor"] == "Valentina" and t["prediccion_valentina"]["venta"] == 18_000

        # Quien solo ve no publica ni escribe la memoria; sin permiso, nada de nada.
        assert (await mira.post("/clientes-vip/memoria", json={"tema": "x y", "texto": "algo que no"})).status_code == 403
        assert (await mira.post("/clientes-vip/informes", json={"mes": "2026-10", "analisis": "x" * 60})).status_code == 403
        for ruta in ("/clientes-vip/datos", "/clientes-vip/numeros", "/clientes-vip/memoria"):
            assert (await nadie.get(ruta)).status_code in (403, 404), ruta
            assert (await Cliente(d.http, d.a1).get(ruta)).status_code in (403, 404), ruta
    correr(prueba)


@_con_base
def test_el_detalle_comprimido_va_y_vuelve_entero_y_valentina_publica_cada_cliente():
    import gzip

    async def prueba(d):
        emi = Cliente(d.http, await _persona(d, "Emi Detalle", permisos=(vip.PERMISO_VER, vip.PERMISO_CARGAR)))
        mira = Cliente(d.http, await _persona(d, "Mira Detalle", permisos=(vip.PERMISO_VER,)))

        async def cargar_con_detalle(archivo: str) -> int:
            r = await emi.post("/clientes-vip/cargas", json={"archivo": archivo, "meses": ["2026-09", "2026-10"], "filas": 2})
            carga_id = r.json()["id"]
            await emi.post(f"/clientes-vip/cargas/{carga_id}/filas",
                           json={"filas": [_fila(1, "2026-09", 9_000), _fila(1, "2026-10", 10_000)]})
            # Dos partes, cada una un gzip completo: pegadas forman un gzip válido.
            partes = ["id_cliente;mes;categoria;venta\n1;2026-09;ALMACEN;9000\n", "1;2026-10;BEBIDAS;10000\n"]
            for i, texto in enumerate(partes):
                r = await emi.post(f"/clientes-vip/cargas/{carga_id}/detalle",
                                   params={"nombre": "cliente_mes_categoria", "parte": i, "filas": 1},
                                   content=gzip.compress(texto.encode()))
                assert r.status_code == 200, r.text
            # Sin comprimir, o con un nombre raro, no entra.
            r = await emi.post(f"/clientes-vip/cargas/{carga_id}/detalle", params={"nombre": "cliente_mes_categoria", "parte": 9},
                               content=b"texto plano")
            assert r.status_code == 400
            r = await emi.post(f"/clientes-vip/cargas/{carga_id}/detalle", params={"nombre": "usuarios", "parte": 0},
                               content=gzip.compress(b"x"))
            assert r.status_code == 400
            assert (await emi.post(f"/clientes-vip/cargas/{carga_id}/terminar", json={"dimensiones": []})).status_code == 200
            return carga_id

        primera = await cargar_con_detalle("sep-oct.csv")
        indice = (await mira.get("/clientes-vip/detalle")).json()
        assert [(x["carga_id"], x["nombre"], x["partes"], x["filas"]) for x in indice] == [(primera, "cliente_mes_categoria", 2, 2)]
        r = await mira.get(f"/clientes-vip/detalle/{primera}/cliente_mes_categoria")
        assert r.status_code == 200
        assert gzip.decompress(r.content).decode() == (
            "id_cliente;mes;categoria;venta\n1;2026-09;ALMACEN;9000\n1;2026-10;BEBIDAS;10000\n")
        assert (await mira.get(f"/clientes-vip/detalle/{primera}/productos")).status_code == 404

        # Una carga nueva de los mismos meses reemplaza el detalle viejo: no se acumula.
        segunda = await cargar_con_detalle("sep-oct-corregido.csv")
        assert [x["carga_id"] for x in (await mira.get("/clientes-vip/detalle")).json()] == [segunda]

        # Valentina publica lo que ve de cada cliente y aparece en su ficha.
        r = await emi.post("/clientes-vip/valentina/clientes", json={"mes": "2026-10", "filas": [{
            "id_cliente": 1, "riesgo_abandono": 0.12, "proxima_categoria": "BEBIDAS", "probabilidad_proxima": 0.64,
            "potencial_mensual": 2500, "descubrio": "BEBIDAS (octubre)", "dejo": "ALMACEN", "frecuencia": "estable",
            "mix": "más bebidas, menos almacén", "accion": "Ofrecerle bebidas en el próximo mailing"}]})
        assert r.status_code == 200, r.text
        ficha = (await mira.get("/clientes-vip/clientes/1")).json()
        assert ficha["valentina"]["proxima_categoria"] == "BEBIDAS" and ficha["valentina"]["mes"] == "2026-10"
        # Republica: se actualiza, no se duplica.
        await emi.post("/clientes-vip/valentina/clientes", json={"mes": "2026-10", "filas": [{"id_cliente": 1, "riesgo_abandono": 0.3}]})
        ficha = (await mira.get("/clientes-vip/clientes/1")).json()
        assert ficha["valentina"]["riesgo_abandono"] == 0.3 and ficha["valentina"]["proxima_categoria"] is None
        # Quien solo ve no publica nada.
        r = await mira.post("/clientes-vip/valentina/clientes", json={"mes": "2026-10", "filas": [{"id_cliente": 1}]})
        assert r.status_code == 403
    correr(prueba)

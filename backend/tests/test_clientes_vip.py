"""Clientes VIP (0091, 25/11/2026).

Ivan: "un dashboard con un agente que analice… prever el comportamiento futuro
de los clientes VIP… tengo acceso yo y Emi Perdomo". Lo puro (segmentos,
riesgo, predicción, el mail) corre siempre; la carga de punta a punta con la
API usa la base de TEST_DATABASE_URL, con las ayudas de
test_tablero_agencia_api.py.
"""
import asyncio
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
# El informe y el mail
# ---------------------------------------------------------------------------

NUMEROS = {
    "ultimo_mes": "octubre 2026", "meses_cargados": "enero 2025 a octubre 2026", "clientes_vip": 9949,
    "el_mes": {"venta": 281_000_000, "margen_pct": 33.9, "clientes_que_compraron": 9100, "tickets": 120_000,
               "ticket_promedio": 2340, "compras_por_cliente": 13.2, "parte_ecommerce_pct": 8.0,
               "parte_marca_propia_pct": 12.0},
    "el_mes_anterior": {"venta": 275_000_000},
    "el_mismo_mes_del_anio_anterior": {"venta": 260_000_000},
    "venta_por_mes": {}, "categorias_ultimos_3_meses": [],
    "categorias_movimientos": {"los_que_mas_bajan": [{"valor": "Bebidas", "contra_3m_antes": -7.5}],
                               "los_que_mas_suben": []},
    "sucursales_movimientos": {"los_que_mas_bajan": [], "los_que_mas_suben": []}, "canales": [],
    "segmentos": [{"segmento": "En riesgo", "clientes": 412, "venta_3m": 20_000_000, "venta_3m_antes": 55_000_000,
                   "venta_esperada": 6_000_000}],
    "clientes_a_mirar": [],
    "prediccion_de_valentina": {"mes": "2026-11", "venta": 290_000_000, "desde": 275_000_000, "hasta": 305_000_000,
                                "como": "el mismo mes del año pasado con la tendencia de hoy"},
}


def test_sin_clave_de_ia_el_informe_sale_igual_con_los_numeros():
    texto = vip.informe_con_reglas(NUMEROS)
    for parte in ("### 📊 Cómo cerró octubre 2026", "### 🔎 Lo que hay que mirar", "### 🔮 Lo que viene",
                  "### ✅ Qué haríamos"):
        assert parte in texto
    assert "$ 281,0 millones" in texto and "(+2,2%)" in texto
    assert "Bebidas" in texto and "412 clientes en riesgo" in texto
    assert "noviembre 2026" in texto


class _ClienteFalso:
    """Lo que devuelve messages.create: un bloque de razonamiento y el texto."""

    def __init__(self, texto: str, stop_reason: str):
        from types import SimpleNamespace as N
        self.pedidos = []
        respuesta = N(stop_reason=stop_reason, usage=N(input_tokens=10, output_tokens=20),
                      content=[N(type="thinking", thinking=""), N(type="text", text=texto)])

        async def crear(**kw):
            self.pedidos.append(kw)
            return respuesta
        self.messages = N(create=crear)


def _con_ia(monkeypatch, cliente):
    from app.services import ia_cliente
    monkeypatch.setattr(vip.settings, "ANTHROPIC_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(ia_cliente, "cliente_anthropic", lambda: cliente)


def test_el_informe_con_ia_completo_se_queda_con_el_texto_y_tiene_lugar(monkeypatch):
    cliente = _ClienteFalso("### 📊 Cómo cerró octubre 2026\n- Todo bien.", "end_turn")
    _con_ia(monkeypatch, cliente)
    texto, con_ia, usage = asyncio.run(vip.escribir_analisis(NUMEROS))
    assert con_ia and texto == "### 📊 Cómo cerró octubre 2026\n- Todo bien." and usage.output_tokens == 20
    # El razonamiento cuenta dentro de max_tokens: con 2.000 se cortó (25/11/2026).
    assert cliente.pedidos[0]["max_tokens"] >= 16_000
    assert cliente.pedidos[0]["output_config"] == {"effort": "medium"}


def test_el_informe_cortado_no_se_guarda_va_el_de_reglas(monkeypatch):
    _con_ia(monkeypatch, _ClienteFalso("### 📊 Cómo cerró\n- Vendimos $ 285 millones, entre $ 277 y", "max_tokens"))
    texto, con_ia, usage = asyncio.run(vip.escribir_analisis(NUMEROS))
    assert not con_ia and usage is None
    assert "### ✅ Qué haríamos" in texto  # el de reglas, entero


def test_escribir_analisis_sin_clave_no_llama_a_la_ia(monkeypatch):
    monkeypatch.setattr(vip.settings, "ANTHROPIC_API_KEY", "")
    texto, con_ia, usage = asyncio.run(vip.escribir_analisis(NUMEROS))
    assert not con_ia and usage is None and texto.startswith("### 📊")


def test_el_mail_es_html_limpio_con_el_link_y_el_aviso_de_confidencial():
    informe = vip.VipInforme(mes=OCT, analisis="### 📊 Cómo cerró\n- Venta: **$ 281 millones** <script>\n\nFin.",
                             prediccion={}, con_ia=True)
    asunto, html, texto = vip.armar_mail(informe, "https://core.example/clientes-vip")
    assert asunto == "⭐ Clientes VIP · octubre 2026"
    assert "<strong>$ 281 millones</strong>" in html and "<script>" not in html and "&lt;script&gt;" in html
    assert "<ul" in html and "<h3" in html and "https://core.example/clientes-vip" in html
    assert "confidencial" in html and "Ver el tablero" in texto


def test_el_mail_sale_solo_si_los_datos_son_recientes():
    hoy = date(2026, 11, 25)
    assert vip.es_reciente(date(2026, 10, 1), hoy)
    assert vip.es_reciente(date(2026, 8, 1), hoy)
    assert not vip.es_reciente(date(2026, 7, 1), hoy)
    assert not vip.es_reciente(date(2025, 12, 1), hoy)
    assert not vip.es_reciente(None, hoy)


def test_las_cuentas_internas_y_de_prueba_no_reciben_mails():
    assert vip.destinatario_real("emi@tiendainglesa.com.uy")
    for no in ("agente-claude@internal.marketingtienda", "equipo-nocturno@example.com", "", None, "x@y.invalid"):
        assert not vip.destinatario_real(no)


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
def test_emi_carga_dos_archivos_ve_el_tablero_y_los_demas_no(monkeypatch):
    informes = []
    monkeypatch.setattr(vip, "informe_en_segundo_plano", lambda carga_id, user_id: informes.append(carga_id))

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
        assert r["clientes"] == 2 and len(informes) == 1

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
def test_el_informe_se_guarda_sin_ia_y_no_le_llega_a_las_cuentas_internas(monkeypatch):
    monkeypatch.setattr(vip, "informe_en_segundo_plano", lambda *a: None)
    monkeypatch.setattr(vip.settings, "ANTHROPIC_API_KEY", "")
    from datetime import datetime, timezone
    monkeypatch.setattr(vip, "ahora", lambda: datetime(2026, 11, 25, tzinfo=timezone.utc))  # octubre es reciente
    enviados = []

    async def falso_envio(to, subject, html, plain, de=None):
        enviados.append((to, subject, de))

    from app.services import email_service
    monkeypatch.setattr(email_service, "send_email", falso_envio)
    monkeypatch.setattr(email_service, "email_configurado", lambda: True)
    dormir = asyncio.sleep
    monkeypatch.setattr(vip.asyncio, "sleep", lambda *_: dormir(0))

    async def prueba(d):
        emi_u = await _persona(d, "Emi Informe", permisos=(vip.PERMISO_VER, vip.PERMISO_CARGAR))
        lector = await _persona(d, "Lector VIP", permisos=(vip.PERMISO_VER,))
        sin_permiso = await _persona(d, "Otro Sin VIP")
        async with d.Sesion() as s:
            for u, mail in ((lector, "lector.vip@ejemplo.uy"), (sin_permiso, "otro.sin.vip@ejemplo.uy")):
                (await s.get(type(u), u.id)).email = mail
            await s.commit()
        await _cargar(Cliente(d.http, emi_u), "2026.csv", [_fila(1, f"2026-{m:02d}", 10_000) for m in range(1, 11)])
        async with d.Sesion() as s:
            informe = await vip.armar_informe(s, None, emi_u.id)
        assert informe and not informe.con_ia and "octubre 2026" in informe.analisis
        assert informe.prediccion["mes"] == "2026-11" and informe.enviado_a == len(enviados)
        para = [e[0] for e in enviados]
        assert "lector.vip@ejemplo.uy" in para  # tiene el permiso
        assert "otro.sin.vip@ejemplo.uy" not in para  # no lo tiene
        assert not any(p.endswith(".test") for p in para)  # las cuentas de prueba, nunca
        assert all(e[1] == "⭐ Clientes VIP · octubre 2026" and e[2].startswith("Sofía y Valentina · ") for e in enviados)
    correr(prueba)

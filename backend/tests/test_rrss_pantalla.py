"""Lo que tiene que cumplir la PANTALLA de la validación de RRSS.

Se lee el fuente del frontend como texto, igual que hace test_factor_voladita
con las reglas de medición, y por el mismo motivo: no necesita Node, ni build,
ni que el frontend esté instalado, y corre con el resto de la suite del backend
(el frontend no tiene suite de JS).

Los cuatro casos que fija:
  - la zona de arrastrar la FUENTE valida, como la de las placas;
  - ningún texto que se muestra en las dos fuentes nombra al mailing;
  - la punta de la cola de CatTi contrasta también sobre fondo claro;
  - el progreso dice el mismo número que marca la barra, y no llega a 100 %
    antes de que el cierre conteste.

SI UN TEST DE ACÁ FALLA no hay que "arreglar el test": volvió el bug.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

# backend/tests/ -> backend/ -> raíz del repo
_RAIZ = pathlib.Path(__file__).resolve().parents[2]
_FRONT = _RAIZ / "frontend"
_RRSS = _FRONT / "components" / "rrss"
_LOCALES = _FRONT / "lib" / "locales"

_UPLOAD = _RRSS / "UploadStep.tsx"
_REVIEW = _RRSS / "ReviewStep.tsx"
_MASCOTA = _RRSS / "CatTiMascota.tsx"
_PAGINA = _FRONT / "app" / "(dashboard)" / "redes-sociales" / "validacion" / "page.tsx"

_IDIOMAS = ("es", "en", "pt")


def _texto(ruta: pathlib.Path) -> str:
    assert ruta.exists(), f"se movió {ruta}"
    return ruta.read_text(encoding="utf-8")


def _rrss(idioma: str) -> dict:
    return json.loads(_texto(_LOCALES / f"{idioma}.json"))["rrss"]


# ---------------------------------------------------------------- (7) la zona de arrastre

def test_la_zona_de_arrastrar_la_fuente_valida_el_archivo():
    """Arrastrabas un .docx, entraba, se habilitaba Validar y el backend
    contestaba "No pude abrir el archivo como imagen" — un mensaje sobre
    imágenes, para un Word, en un panel que se llama "Mailing o planilla". Era
    el único lugar donde la lista única de tipos no se aplicaba."""
    src = _texto(_UPLOAD)
    assert "export function aceptaFuente" in src
    assert "elegirFuente(e.dataTransfer.files?.[0])" in src
    # La fuente entra por UNA sola puerta: si aparece un segundo `onMailing(...)`
    # es que alguien volvió a saltearse la validación.
    assert src.count("onMailing(") == 1, "hay más de un camino para cargar la fuente"
    assert "onMailing(f);" in src.split("const elegirFuente")[1].split("};")[0]


def test_el_tamano_maximo_no_esta_escrito_en_la_pantalla():
    """Los MB salen del mismo JSON que usa el backend para rechazar
    (app/data/rrss_archivos.json), igual que los tipos de archivo. Escritos a
    mano de este lado vuelve el bug de aceptar en un lado lo que el otro
    rechaza."""
    visto = False
    for ruta in (_UPLOAD, _REVIEW, _PAGINA):
        for linea in _texto(ruta).splitlines():
            if not re.search(r"1024\s*\*\s*1024|\bMB\b", linea):
                continue
            visto = True
            assert "max_mb" in linea or "{{max}}" in linea, f"{ruta.name}: {linea.strip()}"
    assert visto, "el barrido no encontró dónde se mira el tamaño: se movió el código?"


# ---------------------------------------------------------------- (8) hablar del mailing

def test_ninguna_frase_de_catti_nombra_al_mailing():
    """Las frases rotan en las DOS fuentes: "CatTi está revisando el mailing sin
    apurarse" aparecía mientras leía una planilla."""
    for idioma in _IDIOMAS:
        for frase in _rrss(idioma)["catti"]["frases"]:
            assert "mailing" not in frase.lower(), (idioma, frase)


def test_los_textos_que_valen_para_las_dos_fuentes_no_nombran_al_mailing():
    """El nombre de la fuente se pasa como variable ({{fuente}}) y sale de
    correccion.nombre_de_la_fuente del otro lado: "la planilla" o "el mailing",
    escrito en UN solo lugar por lado."""
    for idioma in _IDIOMAS:
        rrss = _rrss(idioma)
        assert "{{fuente}}" in rrss["todoCoincide"]
        assert "{{fuente}}" in rrss["coincideLoQueDicta"]
        # el que mandaba a mirar un mailing que no existe cuando falla una planilla
        assert "errorMailing" not in rrss
        assert "mailing" not in rrss["errorFuente"].lower()
        assert "mailing" not in rrss["legalAlcoholVacio"].lower()


def test_los_tres_idiomas_dicen_las_mismas_claves():
    """Una clave que existe en es y no en en/pt sale en pantalla como el nombre
    de la clave."""
    claves = {idioma: set(_rrss(idioma)) for idioma in _IDIOMAS}
    assert claves["en"] == claves["es"] and claves["pt"] == claves["es"]


def test_la_columna_de_la_fuente_se_llama_como_la_fuente():
    """En el panel de una placa en espera decía "El mailing" fijo, aunque se
    estuviera validando contra una planilla."""
    src = _texto(_REVIEW)
    assert src.count('t("rrss.elMailing")') == 0
    assert src.count('fuenteEsPlanilla(v) ? "rrss.laPlanilla" : "rrss.elMailing"') >= 2


# ---------------------------------------------------------------- (14) la punta de la cola

def test_la_punta_de_la_cola_se_ve_sobre_fondo_claro():
    """#ede9fe sin contorno, sobre la tarjeta blanca, no contrastaba con nada:
    de lejos parecía un mordisco en la cola. En oscuro se veía bien, y por eso
    no saltaba a la vista."""
    src = _texto(_MASCOTA)
    punta = next(ln for ln in src.splitlines() if 'cx="14"' in ln and 'cy="45"' in ln)
    assert "stroke=" in punta, "la punta de la cola volvió a quedar sin contorno"
    assert "#ede9fe" not in punta


# ---------------------------------------------------------------- (15) el progreso

def test_el_texto_del_progreso_dice_el_mismo_numero_que_la_barra():
    """Decía "revisando la placa 4 de 10" con la barra en 3/10. Y con PARALELO=3
    en realidad estaba revisando la 4, la 5 y la 6."""
    src = _texto(_REVIEW)
    assert "progreso.hechas + 1" not in src
    assert 't("rrss.revisando", { hechas: progreso.hechas, total: progreso.total })' in src
    assert "rrss.revisandoAhora" in src and "enVuelo" in src
    for idioma in _IDIOMAS:
        assert "{{hechas}}" in _rrss(idioma)["revisando"]
        assert "{{count}}" in _rrss(idioma)["revisandoAhora"]


def test_la_barra_no_llega_a_cien_antes_de_que_el_cierre_conteste():
    """El cierre (adaptaciones y CTA del lote) es un paso más, y puede fallar:
    marcar 100 % mientras todavía no contestó es decir que terminó algo que no
    terminó."""
    src = _texto(_REVIEW)
    assert "progreso.total + 1" in src
    assert "<BarraCatTi hechas={pasosHechos} total={pasosTotales}" in src
    assert "<BarraCatTi hechas={progreso.hechas} total={progreso.total}" not in src


@pytest.mark.parametrize("fase, hechas, total, tope", [
    ("validando", 3, 10, 30.0),   # 3 de 11 pasos
    ("cerrando", 10, 10, 95.0),   # todas las placas, pero el cierre no contestó
])
def test_el_porcentaje_de_la_barra(fase, hechas, total, tope):
    """La misma cuenta que hace la pantalla, para que el número quede fijado acá
    y no solo en un .tsx que nadie corre."""
    pct = hechas / (total + 1) * 100
    assert pct <= tope
    assert (fase == "cerrando") == (pct > 90)


# ---------------------------------------------------------------- (D) la regla del archivo único, entera

def test_las_placas_tambien_tienen_tamano_maximo():
    """El JSON trae max_mb para las placas y la pantalla lo recibía en
    GET /rrss/config, pero el navegador no lo miraba: solo chequeaba el tamaño
    de la FUENTE. Arrastrabas una carpeta con placas de 40 MB, la pantalla las
    aceptaba todas y el backend las tiraba de a una con la barra corriendo."""
    src = _texto(_UPLOAD)
    filtro = src.split("export function crearPlacasLocales")[1].split("\n}")[0]
    assert "tipo.max_mb * 1024 * 1024" in filtro, "las placas no miran el tamaño máximo"
    # y lo que queda afuera se DICE, con nombre y apellido: no se descarta en silencio
    assert "pesadas.push(file.name)" in filtro
    assert 't("rrss.placasMuyPesadas"' in src and "{errorPlacas}" in src


def test_el_tope_de_filas_de_la_planilla_se_muestra_y_no_se_escribe():
    """Mismo criterio que los MB y los tipos: el número vive en
    app/data/rrss_archivos.json y la pantalla lo muestra desde ahí."""
    src = _texto(_UPLOAD)
    assert "tipos.fuentes.planilla.max_filas" in src
    for idioma in _IDIOMAS:
        assert "{{max}}" in _rrss(idioma)["planillaTope"]


# ---------------------------------------------------------------- (E) la tira que no se pudo dibujar

def test_la_tira_de_la_planilla_no_se_pide_prestada_del_mailing():
    """Con planilla la evidencia es la tira de la fila, y viaja con la placa
    (`recorte_fuente`): se dibuja al emparejar y no una por fila del archivo.
    Si no se pudo dibujar se dice ahí mismo, con un texto que no habla de
    recortar un mailing que no existe."""
    src = _texto(_REVIEW)
    planilla_branch = src.split("if (fuenteEsPlanilla(v)) {")[1].split("\n  }")[0]
    assert "img.recorte_fuente ?? item.recorte" in planilla_branch
    assert 't("rrss.sinTira")' in planilla_branch
    assert "rrss.sinRecorte" not in planilla_branch
    for idioma in _IDIOMAS:
        assert "mailing" not in _rrss(idioma)["sinTira"].lower()


# ---------------------------------------------------------------- (F) los tres contadores de la lectura

def test_la_pantalla_muestra_las_filas_juntadas():
    """`filas_juntadas` viajaba en la API y estaba tipado en api.ts, pero no se
    pintaba en ningún lado: la pantalla mostraba filas_leidas y filas_ignoradas
    nada más. Es el contador que delata que el motor entendió el archivo de otra
    manera que la persona ("30 filas con producto" en un archivo de 90), así que
    va al lado de los otros dos."""
    src = _texto(_REVIEW)
    assert "filas_juntadas" in src, "la pantalla no muestra filas_juntadas"
    assert 't("rrss.planillaJuntadas"' in src
    for idioma in _IDIOMAS:
        assert "{{count}}" in _rrss(idioma)["planillaJuntadas"]


def test_el_tope_de_la_pantalla_habla_de_lo_mismo_que_el_backend():
    """El tope cuenta PRODUCTOS (un listado en formato largo trae varias filas
    por producto): la pantalla no puede seguir prometiendo "hasta 1000 filas"
    mientras el backend acepta 1.050 filas de 350 productos."""
    for idioma in _IDIOMAS:
        texto = _rrss(idioma)["planillaTope"].lower()
        assert "filas" not in texto and "rows" not in texto and "linhas" not in texto, texto

"""Las rutas por-job comprueban de quién es el job, y el ZIP de lote no sale vacío.

Los dos casos que fijan estos tests aparecieron en una pasada de QA contra la
base real y son fáciles de reintroducir, porque los dos "parecen" bien escritos.
"""
import io
import os
import re
import zipfile

import pytest


RUTA_CENEFAS_V2 = os.path.join(
    os.path.dirname(__file__), "..", "app", "api", "routes", "cenefas_v2.py"
)


def _fuente() -> str:
    with open(RUTA_CENEFAS_V2, encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Pertenencia: ninguna ruta por-job puede usar db.get(CenefaJob, ...) pelado
# ---------------------------------------------------------------------------

def test_ninguna_ruta_saca_un_job_sin_chequear_dueño():
    """db.get(CenefaJob, job_id) devuelve el job de cualquiera.

    Fue el agujero de PATCH /informe/{job_id}/verificar: un usuario con solo
    cenefas.view podía DESverificar la corrida de otro, y desverificar mete la
    fila en el WHERE de purgar_archivos_vencidos — a los CENEFAS_RETENCION_DIAS
    el PPTX ajeno se borraba sin vuelta atrás. Los ids se los servía el propio
    listado. _get_job (que filtra por created_by o is_superuser) es el único
    camino permitido.
    """
    fuente = _fuente()
    sospechosas = re.findall(r"db\.get\(\s*CenefaJob\s*,", fuente)
    assert not sospechosas, (
        f"{len(sospechosas)} uso(s) de db.get(CenefaJob, ...) sin chequeo de "
        f"pertenencia — usá await _get_job(job_id, current_user, db)"
    )


def test_verificar_corrida_pasa_por_get_job():
    fuente = _fuente()
    i = fuente.index('@router.patch("/informe/{job_id}/verificar")')
    cuerpo = fuente[i:i + 2000]
    assert "_get_job(job_id, current_user, db)" in cuerpo, (
        "verificar_corrida tiene que resolver el job con _get_job"
    )


# ---------------------------------------------------------------------------
# El ZIP de un lote
# ---------------------------------------------------------------------------

def test_un_zip_vacio_no_pesa_cero():
    """La razón por la que `if not buffer.tell()` no servía como guarda."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED):
        pass
    assert buf.tell() == 22, "un ZIP sin entradas igual trae el End Of Central Directory"
    assert not (not buf.tell()), "por eso el 404 era código muerto"


def test_download_lote_cuenta_entradas_y_no_bytes():
    fuente = _fuente()
    i = fuente.index("async def download_lote(")
    cuerpo = fuente[i:i + 3000]
    # Solo código: el comentario que explica el bug menciona la expresión vieja
    # a propósito, así que se buscan los dos puntos que la vuelven un `if`.
    codigo = "\n".join(
        l for l in cuerpo.splitlines() if not l.lstrip().startswith("#")
    )
    assert "buffer.tell():" not in codigo, (
        "medir bytes deja pasar el ZIP vacío: un ZIP sin entradas pesa 22"
    )
    assert "escritas = 0" in cuerpo and "escritas += 1" in cuerpo, (
        "hay que contar las entradas efectivamente escritas"
    )
    assert "if not escritas" in cuerpo, (
        "sin esa guarda se sirve un .zip vacío con HTTP 200"
    )

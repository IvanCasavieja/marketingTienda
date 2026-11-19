"""La contraseña: de 6 a 20 caracteres, de cualquier tipo (Ivan, 19/11/2026).

Antes pedía al menos 12 caracteres, una mayúscula, un número y un símbolo. Para
una plataforma interna era demasiado: "de 6 a 20 caracteres está bárbara". La
regla vale para todo lo que pone una contraseña nueva: el alta desde el panel,
el cambio de contraseña y la recuperación.
"""
import pytest
from pydantic import BaseModel, ValidationError

from app.schemas import auth
from app.schemas.auth import CLAVE_MAXIMO, CLAVE_MINIMO, _validate_password_strength


def test_el_largo_es_de_6_a_20():
    assert (CLAVE_MINIMO, CLAVE_MAXIMO) == (6, 20)


@pytest.mark.parametrize("clave", ["abcdef", "prueba 123", "solo minusculas", "123456", "a" * 20])
def test_pasa_cualquier_clave_de_6_a_20(clave):
    # Sin mayúscula, sin número, sin símbolo, con espacios: da igual.
    assert _validate_password_strength(clave) == clave


@pytest.mark.parametrize("clave,mensaje", [
    ("", "al menos 6"),
    ("abcde", "al menos 6"),
    ("a" * 21, "hasta 20"),
])
def test_rechaza_las_cortas_y_las_largas(clave, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        _validate_password_strength(clave)


def test_los_schemas_que_piden_una_clave_nueva_usan_la_misma_regla():
    """Cada schema de auth con un campo de contraseña nueva acepta una de 6 y
    rechaza una de 5: si alguno tuviera su propio mínimo, esto lo frena."""
    probados = 0
    for nombre in dir(auth):
        modelo = getattr(auth, nombre)
        if not (isinstance(modelo, type) and issubclass(modelo, BaseModel)) or modelo is BaseModel:
            continue
        campos = [c for c in modelo.model_fields if c in ("password", "new_password")]
        if not campos or nombre == "UserLogin":
            continue
        campo = campos[0]
        base = {}
        for c, info in modelo.model_fields.items():
            if c == campo or not info.is_required():
                continue
            base[c] = "persona@prueba.test" if "email" in c else "valor-de-prueba"
        try:
            modelo(**base, **{campo: "abcdef"})
        except ValidationError as e:
            assert not any(err["loc"] == (campo,) for err in e.errors()), f"{nombre} rechaza una clave de 6"
        with pytest.raises(ValidationError):
            modelo(**base, **{campo: "abcde"})
        probados += 1
    assert probados >= 2, "no se encontraron los schemas con contraseña nueva"

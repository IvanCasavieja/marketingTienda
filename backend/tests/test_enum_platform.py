"""El tipo `platform` de la base se guarda con los NOMBRES del enum de Python.

La columna se declara como Enum(Platform) y SQLAlchemy persiste el NOMBRE del
miembro (META), no su valor. La migracion inicial creaba el tipo con los
valores, asi que una base creada desde cero con Alembic tenia etiquetas que la
aplicacion nunca emitia: /dashboard y /campaigns morian con 500
('invalid input value for enum platform: "META"'). Produccion no lo sufria
porque su tipo se creo por fuera de Alembic. Detectado el 10/09/2026 levantando
la plataforma entera desde cero contra una base vacia.
"""
import os

from app.models.platform_connection import Platform

# GOOGLE_ANALYTICS no esta en la migracion inicial: se agrega en la 0010 y la
# 0012 la pasa a mayuscula.
_EN_LA_INICIAL = [m for m in Platform if m.name != "GOOGLE_ANALYTICS"]


def _codigo(nombre_archivo: str) -> str:
    ruta = os.path.join(os.path.dirname(__file__), "..", "migrations", "versions", nombre_archivo)
    with open(ruta, encoding="utf-8") as fh:
        return "\n".join(l for l in fh.read().splitlines() if not l.lstrip().startswith("#"))


def test_la_migracion_inicial_usa_los_nombres_del_enum():
    codigo = _codigo("0001_initial_schema.py")
    for miembro in _EN_LA_INICIAL:
        assert f'"{miembro.name}"' in codigo, (
            f"la migracion 0001 no crea la etiqueta {miembro.name}: una base nueva "
            f"quedaria sin el valor que la aplicacion emite"
        )


def test_la_migracion_inicial_no_usa_los_valores():
    codigo = _codigo("0001_initial_schema.py")
    for miembro in _EN_LA_INICIAL:
        assert f'"{miembro.value}"' not in codigo, (
            f"la migracion 0001 crea la etiqueta con el valor {miembro.value!r} en vez "
            f"del nombre {miembro.name!r} — es el bug que rompia el modulo de Medios"
        )


def test_existe_la_migracion_que_normaliza_bases_ya_creadas():
    codigo = _codigo("0054_platform_enum_mayusculas.py")
    for miembro in Platform:
        assert f'"{miembro.value}", "{miembro.name}"' in codigo, (
            f"falta el par {miembro.value} -> {miembro.name} en la normalizacion"
        )

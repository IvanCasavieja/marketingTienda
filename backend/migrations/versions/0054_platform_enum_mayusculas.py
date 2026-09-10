"""normaliza las etiquetas del tipo platform a los nombres del enum

La aplicacion declara la columna como Enum(Platform) y SQLAlchemy persiste el
NOMBRE del miembro (META), no su valor ("meta"). Hasta el 10/09/2026 la
migracion 0001 creaba el tipo con los valores, asi que TODA base creada desde
cero con Alembic quedaba con etiquetas en minuscula y el modulo de Medios
arrancaba roto: /dashboard y /campaigns devolvian 500 con
'invalid input value for enum platform: "META"'.

Produccion no esta en ese estado: su tipo se creo por fuera de Alembic y ya
tiene las etiquetas en mayuscula (la migracion 0012 lo dice explicitamente al
renombrar la de Google Analytics "para coincidir con la convencion existente").

Por eso esta migracion es IDEMPOTENTE y solo renombra lo que haga falta: no
hace nada donde las etiquetas ya son correctas, y arregla las bases que se
hayan creado con la 0001 vieja. Renombrar una etiqueta es un cambio de
metadatos: las filas existentes no se tocan.

Revision ID: 0054
Revises: 0053
Create Date: 2026-09-10
"""
from alembic import op

revision      = "0054"
down_revision = "0053"
branch_labels = None
depends_on    = None

_PARES = [
    ("meta", "META"),
    ("google_ads", "GOOGLE_ADS"),
    ("tiktok", "TIKTOK"),
    ("dv360", "DV360"),
    ("sfmc", "SFMC"),
    ("google_analytics", "GOOGLE_ANALYTICS"),
]

_RENOMBRAR = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
               WHERE t.typname = 'platform' AND e.enumlabel = '{desde}')
       AND NOT EXISTS (SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
               WHERE t.typname = 'platform' AND e.enumlabel = '{hacia}')
    THEN
        ALTER TYPE platform RENAME VALUE '{desde}' TO '{hacia}';
    END IF;
END $$;
"""


def upgrade() -> None:
    for minuscula, mayuscula in _PARES:
        op.execute(_RENOMBRAR.format(desde=minuscula, hacia=mayuscula))


def downgrade() -> None:
    for minuscula, mayuscula in _PARES:
        op.execute(_RENOMBRAR.format(desde=mayuscula, hacia=minuscula))

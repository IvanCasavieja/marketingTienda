"""
store.py — SQLite intermedio para el scraper.

Misma lógica que el scraper standalone, pero el path de la DB
se lee de SCRAPER_DATA_DIR (default: /tmp/scraper).
El SQLite es efímero: después de cada run se vuelca a PostgreSQL
vía scraper_sync._sync_to_postgres().
"""

import os
import sqlite3
import time
from pathlib import Path
from .adapters import ProductRecord

_DATA_DIR = Path(os.environ.get("SCRAPER_DATA_DIR", "/tmp/scraper"))
_DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = _DATA_DIR / "productos.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS productos (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    tienda           TEXT    NOT NULL,
    url              TEXT    NOT NULL,
    nombre           TEXT,
    precio           REAL,
    precio_lista     REAL,
    sku              TEXT,
    barcode          TEXT,
    marca            TEXT,
    categoria        TEXT,
    sucursal_id      TEXT,
    sucursal_nombre  TEXT,
    actualizado_en   TEXT
)
"""

_INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_url_suc ON productos(url, COALESCE(sucursal_id, ''))",
    "CREATE INDEX IF NOT EXISTS idx_sc_barcode  ON productos(barcode)",
    "CREATE INDEX IF NOT EXISTS idx_sc_sku      ON productos(sku)",
    "CREATE INDEX IF NOT EXISTS idx_sc_tienda   ON productos(tienda)",
    "CREATE INDEX IF NOT EXISTS idx_sc_sucursal ON productos(sucursal_id)",
]

# Mantener _SCHEMA como alias para limpiar() y código externo que pueda usarlo
_SCHEMA = _CREATE_TABLE + ";\n" + ";\n".join(_INDEXES)


def _tiene_url_unique(con: sqlite3.Connection) -> bool:
    """Detecta el schema viejo donde url era UNIQUE en la tabla (no en índice separado)."""
    row = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='productos'"
    ).fetchone()
    return bool(row and "UNIQUE" in (row[0] or "").upper() and "url" in (row[0] or "").lower())


def _crear_indexes(con: sqlite3.Connection) -> None:
    for sql in _INDEXES:
        con.execute(sql)


def conectar() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA busy_timeout=5000")

    # Migración: schema viejo tenía url UNIQUE inline → recrear tabla
    if _tiene_url_unique(con):
        con.execute("ALTER TABLE productos RENAME TO _productos_old")
        con.execute(_CREATE_TABLE)
        _crear_indexes(con)
        con.execute("""
            INSERT OR IGNORE INTO productos
                (tienda, url, nombre, precio, precio_lista, sku, barcode, marca,
                 categoria, sucursal_id, sucursal_nombre, actualizado_en)
            SELECT tienda, url, nombre, precio, precio_lista, sku, barcode, marca,
                   categoria, sucursal_id, sucursal_nombre, actualizado_en
            FROM _productos_old
        """)
        con.execute("DROP TABLE _productos_old")
    else:
        con.execute(_CREATE_TABLE)
        _crear_indexes(con)

    # Migraciones de columnas para DBs muy antiguas
    cols = {r[1] for r in con.execute("PRAGMA table_info(productos)")}
    for col, typedef in [("precio_lista", "REAL"), ("sucursal_id", "TEXT"), ("sucursal_nombre", "TEXT")]:
        if col not in cols:
            con.execute(f"ALTER TABLE productos ADD COLUMN {col} {typedef}")
    con.commit()
    return con


def guardar_bulk(records: list) -> int:
    validos = [r for r in records if not r.error]
    if not validos:
        return 0
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    rows = [
        (r.tienda, r.url, r.nombre, r.precio,
         getattr(r, "precio_lista", None),
         r.sku, r.barcode, r.marca, r.categoria,
         getattr(r, "sucursal_id", None),
         getattr(r, "sucursal_nombre", None),
         ts)
        for r in validos
    ]
    con = conectar()
    con.executemany("""
        INSERT INTO productos
            (tienda, url, nombre, precio, precio_lista, sku, barcode, marca, categoria,
             sucursal_id, sucursal_nombre, actualizado_en)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url, COALESCE(sucursal_id, '')) DO UPDATE SET
            nombre          = excluded.nombre,
            precio          = excluded.precio,
            precio_lista    = excluded.precio_lista,
            sku             = excluded.sku,
            barcode         = excluded.barcode,
            marca           = excluded.marca,
            categoria       = excluded.categoria,
            sucursal_id     = excluded.sucursal_id,
            sucursal_nombre = excluded.sucursal_nombre,
            actualizado_en  = excluded.actualizado_en
    """, rows)
    con.commit()
    con.close()
    return len(validos)


def todos() -> list[dict]:
    con = conectar()
    cols = ["id","tienda","url","nombre","precio","precio_lista","sku","barcode","marca",
            "categoria","sucursal_id","sucursal_nombre"]
    sql  = f"SELECT {','.join(cols)} FROM productos"
    filas = [dict(zip(cols, r)) for r in con.execute(sql).fetchall()]
    con.close()
    return filas


def contar() -> dict:
    con = conectar()
    rows = con.execute("SELECT tienda, COUNT(*) FROM productos GROUP BY tienda").fetchall()
    con.close()
    return dict(rows)


def limpiar() -> None:
    """Vacía la DB intermedia recreando el schema (garantiza schema actualizado)."""
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("DROP TABLE IF EXISTS productos")
    con.execute(_CREATE_TABLE)
    _crear_indexes(con)
    con.commit()
    con.close()

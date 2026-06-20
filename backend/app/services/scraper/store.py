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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS productos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tienda          TEXT    NOT NULL,
    url             TEXT    NOT NULL UNIQUE,
    nombre          TEXT,
    precio          REAL,
    precio_lista    REAL,
    sku             TEXT,
    barcode         TEXT,
    marca           TEXT,
    categoria       TEXT,
    actualizado_en  TEXT
);
CREATE INDEX IF NOT EXISTS idx_sc_barcode ON productos(barcode);
CREATE INDEX IF NOT EXISTS idx_sc_sku     ON productos(sku);
CREATE INDEX IF NOT EXISTS idx_sc_tienda  ON productos(tienda);
"""


def conectar() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript(_SCHEMA)
    # migración: agregar columna si la DB viene de versión anterior
    cols = {r[1] for r in con.execute("PRAGMA table_info(productos)")}
    if "precio_lista" not in cols:
        con.execute("ALTER TABLE productos ADD COLUMN precio_lista REAL")
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
         r.sku, r.barcode, r.marca, r.categoria, ts)
        for r in validos
    ]
    con = conectar()
    con.executemany("""
        INSERT INTO productos
            (tienda, url, nombre, precio, precio_lista, sku, barcode, marca, categoria, actualizado_en)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            nombre       = excluded.nombre,
            precio       = excluded.precio,
            precio_lista = excluded.precio_lista,
            sku          = excluded.sku,
            barcode      = excluded.barcode,
            marca        = excluded.marca,
            categoria    = excluded.categoria,
            actualizado_en = excluded.actualizado_en
    """, rows)
    con.commit()
    con.close()
    return len(validos)


def todos() -> list[dict]:
    con = conectar()
    cols = ["id","tienda","url","nombre","precio","precio_lista","sku","barcode","marca","categoria"]
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
    """Vacía la DB intermedia (útil al inicio de cada run nocturno)."""
    con = conectar()
    con.execute("DELETE FROM productos")
    con.commit()
    con.close()

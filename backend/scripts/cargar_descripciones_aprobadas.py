"""
Carga en el Diccionario las descripciones aprobadas FUERA de la plataforma.

Por que existe: el 29/09/2026 se quedo sin saldo la API key de Anthropic, asi que
Tinin no podia generar las descripciones del listado de la Fiesta Alemania fase 2.
Claude las redacto con las mismas reglas (_STYLE_RULES) en un artifact de
aprobacion, Ivan las aprobo ahi, y este script las pasa al catalogo singular
(sku_descripciones) por el MISMO PATCH /descripciones/{sku} que usa la pantalla
del Diccionario -- asi queda el updated_by del usuario que corre esto y pasa por
las mismas validaciones (clave plural, largo del SKU, 300 caracteres).

Va por la API y no por asyncpg a proposito: no necesita DATABASE_URL en la PC,
solo un usuario con permiso cenefas.diccionario.

SOLO AGREGA, NO PISA -- mismo criterio que seed_sku_descripciones_desde_stock.py.
Un SKU que ya tiene descripcion se saltea y se lista; --pisar-existentes lo
reemplaza igual, dejando antes un backup JSON con el texto anterior.

Entrada: un JSON con una lista de {"sku": "...", "texto": "..."} (el export de la
coleccion `descripciones` del artifact).

Uso:
  MKTG_EMAIL=... MKTG_PASSWORD=... python backend/scripts/cargar_descripciones_aprobadas.py aprobadas.json --dry-run
  MKTG_EMAIL=... MKTG_PASSWORD=... python backend/scripts/cargar_descripciones_aprobadas.py aprobadas.json --yes
  (MKTG_API_URL opcional, por defecto produccion)
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

_API = os.environ.get("MKTG_API_URL", "https://marketingtienda.onrender.com/api/v1").rstrip("/")
_RUTA = "/tools/cenefas/convertidor/descripciones"


def _pedir(metodo: str, path: str, token: str | None = None, cuerpo=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(cuerpo).encode() if cuerpo is not None else None
    rq = urllib.request.Request(_API + path, data=data, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(rq, timeout=120) as resp:
            texto = resp.read()
            return json.loads(texto) if texto else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{metodo} {path} -> {e.code}: {e.read()[:300].decode(errors='replace')}")


def _login() -> str:
    email, password = os.environ.get("MKTG_EMAIL"), os.environ.get("MKTG_PASSWORD")
    if not email or not password:
        print("ERROR: faltan MKTG_EMAIL y MKTG_PASSWORD")
        sys.exit(1)
    return _pedir("POST", "/auth/login", cuerpo={"email": email, "password": password})["access_token"]


def _existente(token: str, sku: str) -> str | None:
    """La busqueda es ilike: '1234' trae tambien '51234'. Se filtra exacto."""
    r = _pedir("GET", f"{_RUTA}?limit=50&q={urllib.parse.quote(sku)}", token)
    return next((i["descripcion"] for i in r["items"] if i["sku"] == sku), None)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("archivo")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--pisar-existentes", action="store_true")
    args = ap.parse_args()

    with open(args.archivo, encoding="utf-8") as f:
        filas = [(str(d["sku"]).strip(), " ".join(str(d["texto"]).split())) for d in json.load(f)]
    filas = [(s, t) for s, t in filas if s and t]

    token = _login()
    nuevas, iguales, distintas = [], [], []
    for sku, texto in filas:
        actual = _existente(token, sku)
        if actual is None:
            nuevas.append((sku, texto))
        elif actual == texto:
            iguales.append(sku)
        else:
            distintas.append((sku, actual, texto))

    print(f"{len(filas)} aprobadas: {len(nuevas)} nuevas, {len(iguales)} ya iguales, "
          f"{len(distintas)} con otra descripcion en el Diccionario")
    for sku, actual, texto in distintas:
        print(f"  {sku}: '{actual}' -> '{texto}'")

    a_escribir = nuevas + ([(s, t) for s, _, t in distintas] if args.pisar_existentes else [])
    if args.dry_run or not a_escribir:
        return
    if not args.yes and input(f"Escribir {len(a_escribir)} en {_API}? [s/N] ").lower() != "s":
        return

    if args.pisar_existentes and distintas:
        os.makedirs("backend/backups", exist_ok=True)
        ruta = f"backend/backups/sku_descripciones_pre_aprobadas_{datetime.now():%Y-%m-%d_%H%M%S}.json"
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump([{"sku": s, "descripcion": a} for s, a, _ in distintas], f, ensure_ascii=False, indent=1)
        print(f"Backup: {ruta}")

    errores = 0
    for sku, texto in a_escribir:
        try:
            _pedir("PATCH", f"{_RUTA}/{urllib.parse.quote(sku)}", token, {"descripcion": texto})
        except RuntimeError as e:
            errores += 1
            print(f"  ERROR {sku}: {e}")
    print(f"Escritas {len(a_escribir) - errores}, errores {errores}")


if __name__ == "__main__":
    main()

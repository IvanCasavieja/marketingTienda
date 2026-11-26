#!/usr/bin/env python3
"""Valentina y la plataforma: bajar los datos de Clientes VIP, publicar, y su memoria.

Valentina (Escuadrón Lechuza) trabaja desde la nube con su propia cuenta de Core
Tienda (permisos `clientes_vip.view` y `clientes_vip.cargar`). Las credenciales
las pone la rutina en variables de entorno; no van en el repo (es público).

    export VIP_API=https://core-tienda-api.onrender.com/api/v1
    export VIP_EMAIL=...  VIP_CLAVE=...

    python3 vip_api.py estado                          # último mes cargado, último informe, cargas
    python3 vip_api.py bajar $S/vip                    # todo para analizar (CSV, detalle .gz, números, memoria)
    python3 vip_api.py memoria                         # lo que aprendió (JSON)
    python3 vip_api.py anotar --tema "..." --texto "..." --fuente "mail de Ivan del 26/11"
    python3 vip_api.py retirar 12                      # una nota que dejó de valer (queda en el historial)
    python3 vip_api.py publicar --mes 2026-10 --informe informe.md --prediccion prediccion.json
    python3 vip_api.py clientes --mes 2026-10 --csv clientes.csv
    python3 vip_api.py procesados $S/procesados.txt     # bajar los ids de mails ya contestados
    python3 vip_api.py guardar-procesados $S/procesados.txt  # guardarlos de vuelta

`clientes.csv` (separado por ;): id_cliente;riesgo_abandono;proxima_categoria;
probabilidad_proxima;potencial_mensual;descubrio;dejo;frecuencia;mix;accion
(riesgo y probabilidad de 0 a 1; potencial en pesos por mes; lo demás, texto corto).

Sin dependencias: solo la biblioteca estándar.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = os.environ.get("VIP_API", "https://core-tienda-api.onrender.com/api/v1").rstrip("/")
# Uruguay no tiene horario de verano desde 2015.
MONTEVIDEO = dt.timezone(dt.timedelta(hours=-3))
TANDA = 2000
_token: str | None = None


def _pedir(metodo: str, ruta: str, cuerpo=None, crudo: bool = False, timeout: int = 300):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(API + ruta, data=datos, method=metodo)
    req.add_header("User-Agent", "escuadron-lechuza-valentina")
    if datos is not None:
        req.add_header("Content-Type", "application/json")
    if _token:
        req.add_header("Authorization", f"Bearer {_token}")
    for intento in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                contenido = r.read()
                return contenido if crudo else (json.loads(contenido) if contenido else {})
        except urllib.error.HTTPError as e:
            texto = e.read().decode(errors="replace")[:400]
            if e.code >= 500 and intento < 2:
                continue
            raise SystemExit(f"La plataforma respondió {e.code} en {ruta}: {texto}")
        except urllib.error.URLError as e:
            if intento < 2:
                continue
            raise SystemExit(f"No se pudo llegar a la plataforma ({API}): {e.reason}. "
                             "¿La red del entorno deja entrar a ese dominio?")


def entrar() -> None:
    global _token
    email, clave = os.environ.get("VIP_EMAIL"), os.environ.get("VIP_CLAVE")
    if not email or not clave:
        raise SystemExit("Faltan VIP_EMAIL y VIP_CLAVE (están en las instrucciones de la rutina).")
    r = _pedir("POST", "/auth/login", {"email": email, "password": clave}, timeout=120)
    _token = r.get("access_token")
    if not _token:
        raise SystemExit(f"No se pudo entrar a Core Tienda: {str(r)[:200]}")


def estado() -> dict:
    t = _pedir("GET", "/clientes-vip/tablero")
    inf = t.get("informe") or {}
    ultimo = t.get("ultimo_mes")
    hecho = inf.get("mes") == ultimo and inf.get("autor") == "Valentina"
    # El informe sale el día después de la carga (Ivan, 25/11/2026: «al
    # siguiente día… entrar a la plataforma y verificar»): cuenta el día, en
    # Montevideo, de la carga lista más nueva que trae el último mes.
    fechas = [c["fecha"] for c in t.get("cargas", [])
              if c.get("estado") == "lista" and c.get("fecha") and ultimo in (c.get("meses") or [])]
    dia = None
    if fechas:
        f = dt.datetime.fromisoformat(max(fechas))
        dia = (f if f.tzinfo else f.replace(tzinfo=dt.timezone.utc)).astimezone(MONTEVIDEO).date()
    return {
        "ultimo_mes": ultimo,
        "clientes": t.get("clientes"),
        "ultimo_informe": {"mes": inf.get("mes"), "autor": inf.get("autor"), "fecha": inf.get("fecha")} if inf else None,
        "cargado_el": dia.isoformat() if dia else None,
        "falta_analizar": bool(ultimo) and not hecho and dia is not None
                          and dia < dt.datetime.now(MONTEVIDEO).date(),
        "cargas": [{k: c.get(k) for k in ("id", "archivo", "meses", "estado", "fecha")} for c in t.get("cargas", [])],
        "memoria": t.get("memoria"),
    }


def bajar(destino: str) -> None:
    d = Path(destino)
    (d / "detalle").mkdir(parents=True, exist_ok=True)
    for tabla in ("clientes_mes", "dimensiones", "clientes"):
        (d / f"{tabla}.csv").write_bytes(_pedir("GET", f"/clientes-vip/datos?tabla={tabla}", crudo=True, timeout=600))
    (d / "numeros.json").write_text(json.dumps(_pedir("GET", "/clientes-vip/numeros"), ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "tablero.json").write_text(json.dumps(_pedir("GET", "/clientes-vip/tablero"), ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "memoria.json").write_text(json.dumps(_pedir("GET", "/clientes-vip/memoria"), ensure_ascii=False, indent=1), encoding="utf-8")
    indice = _pedir("GET", "/clientes-vip/detalle")
    (d / "detalle" / "indice.json").write_text(json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf-8")
    for x in indice:
        nombre = f"{x['nombre']}_carga{x['carga_id']}.csv.gz"
        (d / "detalle" / nombre).write_bytes(
            _pedir("GET", f"/clientes-vip/detalle/{x['carga_id']}/{x['nombre']}", crudo=True, timeout=600))
    print(f"Listo en {d}: clientes_mes.csv, dimensiones.csv, clientes.csv, numeros.json, tablero.json, "
          f"memoria.json y {len(indice)} archivos de detalle (ver detalle/indice.json: qué meses trae cada carga).")


def publicar(mes: str, informe: str, prediccion: str | None, autor: str) -> dict:
    cuerpo = {"mes": mes, "analisis": Path(informe).read_text(encoding="utf-8"), "autor": autor,
              "prediccion": json.loads(Path(prediccion).read_text(encoding="utf-8")) if prediccion else {}}
    return _pedir("POST", "/clientes-vip/informes", cuerpo)


def _num(v: str, tipo):
    v = (v or "").strip()
    return tipo(float(v)) if v else None


def clientes(mes: str, ruta: str) -> int:
    filas = []
    with open(ruta, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            filas.append({
                "id_cliente": int(r["id_cliente"]),
                "riesgo_abandono": _num(r.get("riesgo_abandono"), float),
                "proxima_categoria": (r.get("proxima_categoria") or None),
                "probabilidad_proxima": _num(r.get("probabilidad_proxima"), float),
                "potencial_mensual": _num(r.get("potencial_mensual"), int),
                **{k: ((r.get(k) or "").strip()[:400] or None) for k in ("descubrio", "dejo", "frecuencia", "mix", "accion")},
            })
    for i in range(0, len(filas), TANDA):
        _pedir("POST", "/clientes-vip/valentina/clientes", {"mes": mes, "filas": filas[i:i + TANDA]})
    return len(filas)


TEMA_PROCESADOS = "_correo_procesado"


def _nota_procesados() -> dict | None:
    return next((m for m in _pedir("GET", "/clientes-vip/memoria") if m["tema"] == TEMA_PROCESADOS), None)


def procesados(ruta: str) -> int:
    nota = _nota_procesados()
    ids = (nota["texto"].split() if nota else [])
    Path(ruta).write_text("\n".join(ids) + ("\n" if ids else ""), encoding="utf-8")
    return len(ids)


def guardar_procesados(ruta: str) -> int:
    ids = sorted(set(Path(ruta).read_text(encoding="utf-8").split())) if Path(ruta).exists() else []
    if not ids:
        return 0
    texto = " ".join(ids[-300:])  # los últimos alcanzan: leer mira 14 días
    nota = _nota_procesados()
    if nota:
        _pedir("PATCH", f"/clientes-vip/memoria/{nota['id']}", {"texto": texto})
    else:
        _pedir("POST", "/clientes-vip/memoria", {"tema": TEMA_PROCESADOS, "texto": texto,
                                                 "fuente": "lista técnica: mails ya contestados"})
    return len(ids)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("estado")
    b = sub.add_parser("bajar"); b.add_argument("destino")
    sub.add_parser("memoria")
    a = sub.add_parser("anotar"); a.add_argument("--tema", required=True); a.add_argument("--texto", required=True)
    a.add_argument("--fuente", default="")
    r = sub.add_parser("retirar"); r.add_argument("id", type=int)
    p = sub.add_parser("publicar"); p.add_argument("--mes", required=True); p.add_argument("--informe", required=True)
    p.add_argument("--prediccion"); p.add_argument("--autor", default="Valentina")
    c = sub.add_parser("clientes"); c.add_argument("--mes", required=True); c.add_argument("--csv", required=True)
    pr = sub.add_parser("procesados"); pr.add_argument("archivo")
    gp = sub.add_parser("guardar-procesados"); gp.add_argument("archivo")
    args = ap.parse_args()

    entrar()
    if args.cmd == "estado":
        print(json.dumps(estado(), ensure_ascii=False, indent=1))
    elif args.cmd == "bajar":
        bajar(args.destino)
    elif args.cmd == "memoria":
        print(json.dumps(_pedir("GET", "/clientes-vip/memoria"), ensure_ascii=False, indent=1))
    elif args.cmd == "anotar":
        print(json.dumps(_pedir("POST", "/clientes-vip/memoria", {"tema": args.tema, "texto": args.texto,
                                                                   "fuente": args.fuente}), ensure_ascii=False))
    elif args.cmd == "retirar":
        print(json.dumps(_pedir("PATCH", f"/clientes-vip/memoria/{args.id}", {"activo": False}), ensure_ascii=False))
    elif args.cmd == "publicar":
        print(json.dumps(publicar(args.mes, args.informe, args.prediccion, args.autor), ensure_ascii=False)[:300])
    elif args.cmd == "clientes":
        print(f"{clientes(args.mes, args.csv)} clientes publicados")
    elif args.cmd == "procesados":
        print(f"{procesados(args.archivo)} mails ya contestados")
    elif args.cmd == "guardar-procesados":
        print(f"{guardar_procesados(args.archivo)} guardados")


if __name__ == "__main__":
    sys.exit(main())

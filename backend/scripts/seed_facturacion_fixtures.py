"""
Script standalone de seed -- usa asyncpg directo, sin dependencias de la app
(mismo patrón que seed_sku_descripciones_standalone.py). Carga datos de
prueba (fixture) en facturacion_movimientos y facturacion_canjes: 6 meses
de presupuesto (una entrada mensual + varias salidas a proveedores reales
de medios/marketing) y un puñado de canjes con marcas, para poder ver el
dashboard de Facturación funcionando con datos con forma real mientras no
existe todavía la conexión en vivo con las ventas.

Semántica de re-corrida: identifica las filas que generó una corrida
anterior de este mismo script por documento_id IS NULL (todo movimiento o
canje "real" nace de una factura subida, así que siempre tiene un
documento_id -- ver facturacion/documentos.py). Con --reset, borra esas
filas fixture antes de insertar las nuevas, sin tocar ninguna fila real que
haya cargado un usuario. Toca la base de PRODUCCIÓN directamente -- por eso
pide confirmación explícita salvo que se pase --yes.

Uso:
  DATABASE_URL=postgresql+asyncpg://... python backend/scripts/seed_facturacion_fixtures.py [--reset] [--dry-run] [--yes]
"""
import os
import re
import random
import sys
import asyncio
import argparse
from datetime import date, timedelta
from decimal import Decimal

try:
    import asyncpg
except ImportError:
    print("ERROR: pip install asyncpg")
    sys.exit(1)

random.seed(42)

# Últimos 6 meses incluyendo el actual (hardcodeado a la fecha de creación
# del fixture, no date.today(), para que la data no vaya quedando "vieja"
# silenciosamente si el script no se vuelve a correr -- si hace falta data
# más reciente, se corre de nuevo con --reset).
_HOY = date(2026, 8, 11)


def _primeros_dias_de_mes(hoy: date, cantidad: int) -> list[date]:
    meses = []
    y, m = hoy.year, hoy.month
    for _ in range(cantidad):
        meses.append(date(y, m, 1))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return list(reversed(meses))


MESES_NOMBRE = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

# Proveedores de medios/marketing -- generan SALIDAS del presupuesto.
PROVEEDORES_SALIDA = [
    "Medios Impresos S.A.",
    "Radiomundo",
    "Canal 10 - SAETA TV",
    "El Observador",
    "Google Uruguay",
    "Meta Platforms",
    "Imprenta Rápida SRL",
    "BTL Punto de Venta SRL",
    "Producciones Eventos SRL",
]

_CONCEPTOS_SALIDA = {
    "Medios Impresos S.A.": "Impresión de cenefas y folletos",
    "Radiomundo": "Pauta radial mensual",
    "Canal 10 - SAETA TV": "Pauta TV — tanda comercial",
    "El Observador": "Pauta digital + prensa",
    "Google Uruguay": "Google Ads — búsqueda y display",
    "Meta Platforms": "Meta Ads — Facebook e Instagram",
    "Imprenta Rápida SRL": "Impresión de material POP",
    "BTL Punto de Venta SRL": "Activación en punto de venta",
    "Producciones Eventos SRL": "Producción de evento promocional",
}

# Marcas/proveedores de canjes (trueque) -- entregan producto/espacio a
# cambio de exhibición o pauta, no pagan en efectivo.
MARCAS_CANJE = [
    "Coca-Cola Uruguay",
    "PepsiCo Uruguay",
    "Unilever Uruguay",
    "Nestlé Uruguay",
    "Bimbo Uruguay",
    "Danone Uruguay",
    "Conaprole",
    "AjeGroup Uruguay",
]

# Asignación fija (no random.choice) -- con solo 6 canjes de muestra, dejar
# el estado a la suerte del RNG podía darle 0 representantes a un estado
# entero (ej. ningún "activo"), y el punto de esta data es justamente
# mostrar la torta de canjes por estado con los 3 valores presentes.
_ESTADOS_CANJE = ["activo", "activo", "pendiente", "pendiente", "cerrado", "cerrado"]


def _redondear(monto: float) -> Decimal:
    return Decimal(round(monto / 1000) * 1000)


def generar_movimientos() -> list[dict]:
    movimientos: list[dict] = []
    meses = _primeros_dias_de_mes(_HOY, 6)

    for mes in meses:
        nombre_mes = MESES_NOMBRE[mes.month - 1]
        # Entrada mensual -- "presupuesto asignado", simula el % de ventas
        # del mes que todavía se carga a mano (ver plan: la conexión en vivo
        # con ventas queda para más adelante).
        monto_entrada = _redondear(random.uniform(850_000, 1_350_000))
        movimientos.append({
            "tipo": "entrada",
            "monto": monto_entrada,
            "moneda": "UYU",
            "concepto": f"Presupuesto asignado — {nombre_mes.capitalize()} {mes.year}",
            "proveedor_marca": None,
            "numero_factura": None,
            "fecha": mes,
        })

        # 3 a 6 salidas del mes, a proveedores random del pool.
        n_salidas = random.randint(3, 6)
        proveedores_mes = random.sample(PROVEEDORES_SALIDA, k=n_salidas)
        for proveedor in proveedores_mes:
            dia = random.randint(1, 27)
            monto_salida = _redondear(random.uniform(40_000, 220_000))
            movimientos.append({
                "tipo": "salida",
                "monto": monto_salida,
                "moneda": "UYU",
                "concepto": _CONCEPTOS_SALIDA[proveedor],
                "proveedor_marca": proveedor,
                "numero_factura": f"A-{mes.month:02d}{mes.year % 100}-{random.randint(1000, 9999)}",
                "fecha": date(mes.year, mes.month, dia),
            })

    return movimientos


def generar_canjes() -> list[dict]:
    canjes: list[dict] = []
    inicio_ventana = _HOY - timedelta(days=150)
    marcas = random.sample(MARCAS_CANJE, k=len(_ESTADOS_CANJE))
    estados = list(_ESTADOS_CANJE)
    random.shuffle(estados)
    for marca, estado in zip(marcas, estados):
        vigencia_desde = inicio_ventana + timedelta(days=random.randint(0, 90))
        vigencia_hasta = vigencia_desde + timedelta(days=random.randint(30, 60))
        # Un canje "cerrado" ya venció -- corre la ventana hacia atrás para
        # que la fecha cuente una historia consistente, no solo el estado.
        if estado == "cerrado":
            vigencia_hasta = min(vigencia_hasta, _HOY - timedelta(days=5))
            vigencia_desde = min(vigencia_desde, vigencia_hasta - timedelta(days=30))
        canjes.append({
            "marca_proveedor": marca,
            "valor": _redondear(random.uniform(80_000, 400_000)),
            "moneda": "UYU",
            "estado": estado,
            "vigencia_desde": vigencia_desde,
            "vigencia_hasta": vigencia_hasta,
            "descripcion": f"Canje de exhibición y pauta con {marca}",
        })
    return canjes


async def run_seed(reset: bool, dry_run: bool) -> None:
    raw_url = os.environ.get("DATABASE_URL", "")
    if not raw_url:
        print("ERROR: DATABASE_URL no definida")
        sys.exit(1)

    dsn = re.sub(r"^postgresql\+asyncpg://", "postgresql://", raw_url)
    dsn = re.sub(r"^postgres://", "postgresql://", dsn)

    movimientos = generar_movimientos()
    canjes = generar_canjes()
    print(f"Generados {len(movimientos)} movimientos y {len(canjes)} canjes de prueba")

    conn = await asyncpg.connect(dsn)
    try:
        if reset and not dry_run:
            borrados_mov = await conn.execute(
                "DELETE FROM facturacion_movimientos WHERE documento_id IS NULL"
            )
            borrados_canje = await conn.execute(
                "DELETE FROM facturacion_canjes WHERE documento_id IS NULL"
            )
            print(f"--reset: {borrados_mov} · {borrados_canje} (movimientos/canjes fixture anteriores borrados)")

        if not dry_run:
            await conn.executemany(
                """
                INSERT INTO facturacion_movimientos
                    (tipo, monto, moneda, concepto, proveedor_marca, numero_factura, fecha)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                [
                    (m["tipo"], m["monto"], m["moneda"], m["concepto"],
                     m["proveedor_marca"], m["numero_factura"], m["fecha"])
                    for m in movimientos
                ],
            )
            await conn.executemany(
                """
                INSERT INTO facturacion_canjes
                    (marca_proveedor, valor, moneda, estado, vigencia_desde, vigencia_hasta, descripcion)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                [
                    (c["marca_proveedor"], c["valor"], c["moneda"], c["estado"],
                     c["vigencia_desde"], c["vigencia_hasta"], c["descripcion"])
                    for c in canjes
                ],
            )
    finally:
        await conn.close()

    prefix = "[DRY RUN] " if dry_run else ""
    print(f"\n{prefix}Listo — {len(movimientos)} movimientos y {len(canjes)} canjes insertados")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="Borra la data fixture de una corrida anterior antes de insertar (no toca filas reales, con documento_id)")
    parser.add_argument("--dry-run", action="store_true", help="Solo simula, no escribe nada en la base")
    parser.add_argument("--yes", action="store_true", help="Saltea la confirmación interactiva")
    args = parser.parse_args()

    if not args.dry_run and not args.yes:
        print("Esto va a insertar movimientos y canjes de PRUEBA en la base de PRODUCCIÓN de Facturación.")
        if args.reset:
            print("Con --reset: antes borra cualquier movimiento/canje fixture (sin documento_id) de una corrida anterior.")
        confirm = input("Escribí CONFIRMAR para continuar: ")
        if confirm.strip() != "CONFIRMAR":
            print("Cancelado.")
            sys.exit(0)

    asyncio.run(run_seed(args.reset, args.dry_run))


if __name__ == "__main__":
    main()

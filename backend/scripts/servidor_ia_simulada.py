"""Levanta el backend con la API de Anthropic SIMULADA, para ver andando a Don
Tino con el calendario, el dictado de briefs y la revisión de piezas de las
entregas sin una clave y sin gastar.

Solo para una PC de trabajo. Se niega a arrancar:
- en el servidor desplegado (Render o Azure: `settings.es_servidor_desplegado`);
- con APP_ENV=production (el valor por defecto: hay que pedirlo a propósito
  con APP_ENV=development).

En producción este camino no existe: `app/services/ia_cliente.py` arma
siempre el cliente real, y no hay ninguna variable de entorno que lo cambie.
Este script lo pisa desde afuera, en su propio proceso y en ningún otro.

Las respuestas las arma `tests/ia_simulada.py` con reglas simples (no es el
modelo): sirve para probar permisos, links y pantallas, no la calidad de lo
que contestaría Claude.

Uso, desde backend/:
    APP_ENV=development DATABASE_URL=... APP_SECRET_KEY=... ENCRYPTION_KEY=... \\
        python scripts/servidor_ia_simulada.py --port 8025
"""
import argparse
import os
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

# Una clave de mentira, puesta a propósito encima de cualquier otra: aunque en
# la máquina hubiera una de verdad, este proceso no la usa.
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-simulada-no-es-una-clave"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8025)
    args = parser.parse_args()

    from app.core.config import settings
    if settings.es_servidor_desplegado:
        sys.exit("Esto es para una PC de trabajo: no corre en el servidor desplegado.")
    if settings.APP_ENV == "production":
        sys.exit("Con APP_ENV=production no: poné APP_ENV=development para usar la IA simulada.")

    import ia_simulada
    from app.services import ia_cliente

    ia_cliente.cliente_anthropic = lambda: ia_simulada.cliente_con(ia_simulada.SimuladorDeDonTino())
    print("IA SIMULADA: Don Tino, el dictado y la revisión de piezas contestan con reglas, sin la API real.",
          flush=True)

    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()

"""
Fitea un modelo de Marketing Mix Modeling con Google Meridian sobre
data/weekly_metrics.csv (generado por
backend/scripts/export_metrics_for_meridian.py) y guarda un reporte HTML.

Corre con .venv-meridian, no con el venv del backend — este entorno no
necesita ni tiene acceso a la base de datos, solo lee el CSV.

Uso:
  ../.venv-meridian/Scripts/python.exe fit_model.py

Con pocas semanas de datos (fixtures: ~13-14) esto es una prueba de que el
pipeline funciona de punta a punta, no un insight de negocio — Meridian
idealmente quiere 1+ año de historia semanal para resultados confiables. Los
n_chains/n_adapt/n_burnin/n_keep de abajo son valores reducidos a propósito
para que una primera corrida no tarde una eternidad; subirlos una vez que
haya más semanas de datos reales.
"""
import sys
from pathlib import Path

import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from meridian import constants
from meridian.analysis.summarizer import Summarizer
from meridian.data.data_frame_input_data_builder import DataFrameInputDataBuilder
from meridian.model.model import Meridian
from meridian.model.spec import ModelSpec

HERE = Path(__file__).resolve().parent
DATA_PATH = HERE / "data" / "weekly_metrics.csv"
OUTPUT_DIR = HERE / "output"
REPORT_FILENAME = "meridian_summary.html"

# Reducidos para una corrida rapida con pocas semanas de datos. Subir una vez
# que haya suficiente historia real (ver docstring arriba).
N_CHAINS = 2
N_ADAPT = 200
N_BURNIN = 200
N_KEEP = 300


def load_input_data():
    df = pd.read_csv(DATA_PATH)
    spend_cols = sorted(c for c in df.columns if c.endswith("_spend"))
    channels = [c.removesuffix("_spend") for c in spend_cols]
    media_cols = [f"{c}_impressions" for c in channels]

    missing = [c for c in media_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas de impresiones en el CSV: {missing}")

    builder = DataFrameInputDataBuilder(kpi_type=constants.REVENUE)
    builder = builder.with_kpi(df, kpi_col="kpi", time_col="time")
    builder = builder.with_media(
        df,
        media_cols=media_cols,
        media_spend_cols=spend_cols,
        media_channels=channels,
        time_col="time",
    )
    return builder.build(), channels


def main() -> None:
    if not DATA_PATH.exists():
        raise SystemExit(
            f"No existe {DATA_PATH}. Corre primero "
            "backend/scripts/export_metrics_for_meridian.py con el venv del backend."
        )

    input_data, channels = load_input_data()
    n_weeks = len(input_data.time)
    print(f"Cargadas {n_weeks} semanas, canales: {', '.join(channels)}")
    if n_weeks < 52:
        print(
            f"AVISO: solo {n_weeks} semanas de datos (Meridian recomienda 1+ año). "
            "Tratar este resultado como prueba de pipeline, no como insight."
        )

    mmm = Meridian(input_data=input_data, model_spec=ModelSpec())

    print("Muestreando el prior...")
    mmm.sample_prior(n_draws=500)

    print(f"Muestreando el posterior (MCMC, {N_CHAINS} cadenas)... puede tardar unos minutos.")
    mmm.sample_posterior(
        n_chains=N_CHAINS, n_adapt=N_ADAPT, n_burnin=N_BURNIN, n_keep=N_KEEP
    )

    print("Generando reporte HTML...")
    Summarizer(mmm).output_model_results_summary(
        filename=REPORT_FILENAME,
        filepath=str(OUTPUT_DIR),
    )
    print(f"Listo -> {OUTPUT_DIR / REPORT_FILENAME}")
    if n_weeks < 52:
        print(
            f"Recordatorio: {n_weeks} semanas de datos — revisar los intervalos de "
            "confianza en el reporte, van a ser anchos."
        )


if __name__ == "__main__":
    main()

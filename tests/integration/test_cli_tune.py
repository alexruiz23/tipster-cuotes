"""`tipster tune`: malla de hiperparámetros sobre una base temporal (ADR 009)."""

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from tipster.cli.app import app


def test_tune_muestra_la_malla_y_la_mejor_combinacion(db: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "tune",
            "--db",
            str(db),
            "--train-from",
            "2022-01-01",
            "--train-to",
            "2022-12-31",
            "--test-to",
            "2023-02-28",
            "--half-life",
            "90",
            "--l2",
            "0",
            "--l2",
            "1",
        ],
        env={"COLUMNS": "160"},
    )
    assert result.exit_code == 0, result.output
    for text in (
        "log-loss",
        "Brier",
        "sin decaimiento",
        "Mejor combinación",
        "entrenamiento",
        "prueba",
        "Diferencia pareada de log-loss mejor − base",
    ):
        assert text in result.output
    assert (
        sqlite3.connect(db).execute("SELECT COUNT(*) FROM historical_matches").fetchone()[0] == 720
    )

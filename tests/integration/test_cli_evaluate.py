"""`tipster evaluate`: walk-forward estricto sobre una base temporal (ADR 011)."""

from pathlib import Path

from typer.testing import CliRunner

from tipster.cli.app import app


def test_evaluate_muestra_las_tablas_del_walk_forward(db: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "evaluate",
            "--db", str(db),
            "--league", "premier",
            "--train-from", "2022-01-01",
            "--test-from", "2022-12-01",
            "--test-to", "2023-02-28",
            "--scored-after", "2022-04-01",
            "--block-days", "7",
        ],
        env={"COLUMNS": "200"},
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    for text in (
        "Walk-forward estricto",
        "Hiperparámetros del Elo",
        "log-loss (Brier)",
        "Elo − Dixon-Coles",
        "Dixon-Coles reajustado − sin reajuste",
        "tasa de empates",
        "Cómputo: Dixon-Coles",
    ):
        assert text in result.output


def test_evaluate_rechaza_una_liga_desconocida(db: Path) -> None:
    result = CliRunner().invoke(app, ["evaluate", "--db", str(db), "--league", "no_existe"])
    assert result.exit_code == 2
    assert "no_existe" in result.output

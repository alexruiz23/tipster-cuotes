"""`tipster select-blend`: solo la validación, nunca 2024/25 (ADR 012)."""

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tipster.cli.app import app


@pytest.fixture
def db_with_odds(db: Path) -> Path:
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE historical_matches SET pinnacle_home = 2.0, pinnacle_draw = 3.5,"
        " pinnacle_away = 4.0, odds_source = 'API-Football-closing'"
    )
    conn.commit()
    conn.close()
    return db


ARGS = ["--league", "premier", "--train-from", "2022-01-01", "--val-from", "2022-09-01",
        "--val-to", "2023-02-28", "--block-days", "7"]  # fmt: skip


def test_select_blend_muestra_las_decisiones_y_guarda_la_configuracion(db_with_odds: Path) -> None:
    result = CliRunner().invoke(
        app, ["select-blend", "--db", str(db_with_odds), *ARGS], env={"COLUMNS": "120"}
    )
    assert result.exit_code == 0, result.output
    for text in ("1. devig", "Elegido:", "2. calibrador", "3. mezcla", "peso del mercado",
                 "REVISIÓN MANUAL", "Configuración guardada con id 1"):  # fmt: skip
        assert text in result.output
    row = (
        sqlite3.connect(db_with_odds).execute("SELECT settings_json FROM blend_configs").fetchone()
    )
    assert '"w_market"' in row[0] and '"validation"' in row[0]


def test_la_validacion_no_puede_tocar_2024_25(db_with_odds: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "select-blend",
            "--db",
            str(db_with_odds),
            "--league",
            "premier",
            "--val-to",
            "2024-08-01",
        ],
    )
    assert result.exit_code == 1
    assert "test ciego" in result.output
    assert (
        sqlite3.connect(db_with_odds).execute("SELECT COUNT(*) FROM blend_configs").fetchone()[0]
        == 0
    )

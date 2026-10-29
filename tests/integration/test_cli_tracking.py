"""Comandos `close`, `settle` y `clv` (ADR 012) sin red."""

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.factories import NOW
from tests.integration.test_tracking import _make_pick
from tipster.cli.app import app
from tipster.storage.db import connect
from tipster.storage.tracking import SqliteTrackingRepository


@pytest.fixture(autouse=True)
def _aislado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)  # sin .env del repositorio
    monkeypatch.delenv("ODDS_API_KEY", raising=False)


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "tipster.sqlite"
    conn = connect(path)
    pick_id, quote_id, run_id = _make_pick(conn, "e1")
    SqliteTrackingRepository(conn).set_stakes(run_id, {quote_id: 20.0})
    SqliteTrackingRepository(conn).set_closing(
        pick_id, closing_odds=1.8, closing_fair_odds=2.0, captured_at=NOW, last_update=NOW,
        reliable=True, clv=0.10,
    )  # fmt: skip
    conn.close()
    return path


def test_close_sin_clave_falla_con_el_codigo_de_configuracion(db: Path) -> None:
    result = CliRunner().invoke(app, ["close", "--db", str(db)])
    assert result.exit_code == 2
    assert "ODDS_API_KEY" in result.output


def test_settle_manual_liquida_sin_clave_y_actualiza_el_bankroll(db: Path) -> None:
    result = CliRunner().invoke(app, ["settle", "--db", str(db), "--result", "e1=2-1"])
    assert result.exit_code == 0, result.output
    assert "1 pick liquidado" in result.output
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT status, profit FROM picks").fetchone() == (
        "ganado",
        pytest.approx(24.0),
    )
    assert (
        conn.execute("SELECT balance_after FROM bankroll_entries ORDER BY id DESC").fetchone()[0]
        == 1024.0
    )


def test_settle_rechaza_un_resultado_mal_escrito(db: Path) -> None:
    result = CliRunner().invoke(app, ["settle", "--db", str(db), "--result", "e1:dos-uno"])
    assert result.exit_code == 2
    assert "EVENTO=GL-GV" in result.output


def test_clv_resume_los_picks_con_cierre_fiable(db: Path) -> None:
    result = CliRunner().invoke(app, ["clv", "--db", str(db)], env={"COLUMNS": "120"})
    assert result.exit_code == 0, result.output
    assert "Picks con CLV: 1" in result.output
    assert "+10.00 %" in result.output

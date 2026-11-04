"""`tipster status`: bankroll, abiertos, ROI y CLV del paper trading (ADR 012)."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.integration.test_close_settle import FakeScores, _open, _settle
from tipster.cli.app import app
from tipster.providers.base import MatchScore
from tipster.services.status import paper_status
from tipster.storage.db import MEMORY, connect


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    connection = connect(MEMORY)
    yield connection
    connection.close()


def test_estado_con_abiertos_liquidados_ingresos_y_retiros(conn: sqlite3.Connection) -> None:
    _open(conn, "e1", minutes_to_kickoff=-180, stake=1.0, price=2.0)  # gana: +1,00
    _open(conn, "e2", minutes_to_kickoff=-200, stake=2.0, price=2.0)  # pierde: −2,00
    _open(conn, "e3", minutes_to_kickoff=600, stake=1.5)  # abierto con stake
    _open(conn, "e4", minutes_to_kickoff=600, stake=0.0)  # abierto sin stake: no cuenta
    scores = FakeScores([MatchScore("xe1", True, 2, 1), MatchScore("xe2", True, 0, 0)])
    _, bank = _settle(conn, scores)  # depósito inicial de 1 000
    bank.deposit(50.0)
    bank.withdraw(30.0)
    st = paper_status(conn)
    assert (st.balance, st.deposits, st.withdrawals) == (1019.0, 1050.0, 30.0)
    assert st.profit == pytest.approx(-1.0)
    assert (st.open_picks, st.open_exposure) == (1, 1.5)
    assert (st.won, st.lost, st.void, st.settled) == (1, 1, 0, 2)
    assert st.roi == pytest.approx(-1.0 / 3.0)
    assert st.clv.n == 0


def test_el_comando_avisa_de_muestra_insuficiente_y_de_clv_sin_datos(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    connect(db).close()
    result = CliRunner().invoke(app, ["status", "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert "Bankroll:" in result.output and "100.00" in result.output
    assert "Muestra insuficiente: 0 < 50" in result.output
    assert "sin datos de cierre fiable" in result.output

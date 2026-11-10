"""`tipster status`: bankroll, abiertos, ROI y CLV del paper trading (ADR 012)."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

from tests.integration.test_close_settle import NOW, FakeScores, _open, _settle, clock
from tipster.cli.app import app
from tipster.providers.base import MatchScore
from tipster.services.settle import SettleService
from tipster.services.status import paper_status, status_lines
from tipster.storage.db import MEMORY, connect
from tipster.storage.sqlite import SqliteRunRepository
from tipster.storage.tracking import SqliteTrackingRepository


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
    st = paper_status(conn, NOW)
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


def test_los_nulos_no_cuentan_como_apostado_en_el_roi(conn: sqlite3.Connection) -> None:
    _open(conn, "e1", minutes_to_kickoff=-180, stake=1.0, price=2.0)  # gana: +1,00
    _open(conn, "e2", minutes_to_kickoff=-200, stake=5.0, price=2.0)  # anulado
    _, bank = _settle(conn, FakeScores([MatchScore("xe1", True, 2, 1)]))
    SettleService(
        provider=None, tracking=SqliteTrackingRepository(conn), bankroll=bank,
        runs=SqliteRunRepository(conn, clock), clock=clock,
    ).run({}, void={"e2"})  # fmt: skip
    st = paper_status(conn, NOW)
    assert (st.won, st.void, st.staked_settled) == (1, 1, 1.0)
    assert st.roi == pytest.approx(1.0)


def test_status_muestra_error_tipico_y_cobertura_del_clv(conn: sqlite3.Connection) -> None:
    ids = [_open(conn, f"e{i}", minutes_to_kickoff=-60 - i, stake=1.0) for i in range(3)]
    _open(conn, "futuro", minutes_to_kickoff=600, stake=1.0)  # aún no jugado: no cuenta
    for i, pick_id in enumerate(ids[:2]):
        conn.execute(
            "UPDATE picks SET closing_reliable = 1, clv = ? WHERE id = ?", (0.02 * (i + 1), pick_id)
        )
    st = paper_status(conn, NOW)
    assert (st.clv.n, st.clv_eligible) == (2, 3)
    text = "\n".join(status_lines(st, ZoneInfo("Europe/Madrid")))
    assert "error típico" in text and "Cobertura CLV: 2 de 3" in text
    assert "Muestra insuficiente: 2 < 30" in text

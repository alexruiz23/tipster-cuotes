"""Stake como porcentaje del bankroll, ingresos y retiros (ADR 012)."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.integration.test_close_settle import FakeScores, _open, _settle
from tests.integration.test_scan_service import CAPTURED, FIXTURES, _service, _settings
from tipster.cli.app import app
from tipster.pricing.classify import Label
from tipster.providers.base import MatchScore
from tipster.providers.the_odds_api.client import TheOddsApiProvider
from tipster.providers.the_odds_api.offline import OfflineFetcher
from tipster.services.scan import ScanResult
from tipster.staking.flat import flat_stake
from tipster.storage.db import MEMORY, connect
from tipster.storage.tracking import SqliteBankrollRepository


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    connection = connect(MEMORY)
    yield connection
    connection.close()


def _bank(conn: sqlite3.Connection, initial: float = 100.0) -> SqliteBankrollRepository:
    bank = SqliteBankrollRepository(conn, lambda: CAPTURED)
    bank.ensure_initial(initial)
    return bank


def _flat_scan(conn: sqlite3.Connection) -> ScanResult:
    provider = TheOddsApiProvider(OfflineFetcher(FIXTURES))
    return _service(conn, provider, _settings(sizing_strategy="flat", min_stake=0.0)).run()


def _stakes(result: ScanResult) -> set[float]:
    return {
        p.opportunity.stake
        for p in result.picks
        if p.opportunity.label is Label.VALUE and p.opportunity.stake
    }


@pytest.mark.parametrize(
    ("bankroll", "stake"), [(100.0, 1.0), (200.0, 2.0), (500.0, 5.0), (50.0, 0.5), (1000.0, 5.0)]
)
def test_el_stake_es_el_1_por_ciento_con_minimo_y_maximo(bankroll: float, stake: float) -> None:
    assert flat_stake(bankroll, pct=0.01, min_abs=0.5, max_abs=5.0) == stake


def test_depositar_50_sobre_100_da_150_y_un_stake_de_1_50(conn: sqlite3.Connection) -> None:
    bank = _bank(conn)
    assert bank.deposit(50.0) == 150.0
    assert _stakes(_flat_scan(conn)) == {1.5}


def test_retirar_30_sobre_100_da_70_y_un_stake_de_0_70(conn: sqlite3.Connection) -> None:
    bank = _bank(conn)
    assert bank.withdraw(30.0) == 70.0
    assert _stakes(_flat_scan(conn)) == {0.7}


def test_no_se_puede_retirar_mas_de_lo_que_hay(conn: sqlite3.Connection) -> None:
    bank = _bank(conn)
    with pytest.raises(ValueError, match=r"no se puede retirar 200\.00"):
        bank.withdraw(200.0)
    assert (
        bank.balance() == 100.0
        and conn.execute("SELECT COUNT(*) FROM bankroll_entries").fetchone()[0] == 1
    )


def test_el_saldo_es_la_suma_de_los_movimientos(conn: sqlite3.Connection) -> None:
    bank = _bank(conn)
    bank.deposit(50.0)
    bank.withdraw(30.0)
    bank.settle(_open(conn, "e1", minutes_to_kickoff=-180), -4.0)
    total = conn.execute("SELECT SUM(amount) FROM bankroll_entries").fetchone()[0]
    assert bank.balance() == total == 116.0
    kinds = [r[0] for r in conn.execute("SELECT kind FROM bankroll_entries ORDER BY id")]
    assert kinds == ["deposito", "deposito", "retiro", "liquidacion"]


def test_un_pick_ganado_de_1_euro_a_cuota_2_sube_el_bankroll_1_euro(
    conn: sqlite3.Connection,
) -> None:
    pick_id = _open(conn, "e1", minutes_to_kickoff=-180, stake=1.0, price=2.0)
    result, bank = _settle(conn, FakeScores([MatchScore("xe1", True, 2, 1)]))
    assert [s.pick_id for s in result.settled] == [pick_id]
    assert conn.execute("SELECT profit FROM picks").fetchone()[0] == pytest.approx(1.0)
    assert bank.balance() == 1001.0  # _settle parte de 1 000


def test_cli_deposit_withdraw_y_error_al_retirar_de_mas(tmp_path: Path) -> None:
    db = str(tmp_path / "t.sqlite")
    run = CliRunner()
    assert "bankroll 150.00" in run.invoke(app, ["bankroll", "deposit", "50", "--db", db]).output
    assert "bankroll 120.00" in run.invoke(app, ["bankroll", "withdraw", "30", "--db", db]).output
    result = run.invoke(app, ["bankroll", "withdraw", "500", "--db", db])
    assert result.exit_code == 2 and "no se puede retirar" in result.output
    assert "retiro" in run.invoke(app, ["bankroll", "show", "--db", db]).output

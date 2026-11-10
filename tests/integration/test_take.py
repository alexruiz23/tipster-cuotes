"""`tipster take`: la cuota real de la web .es manda sobre la del feed (BACKLOG 45)."""

import sqlite3
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

from tests.integration.test_close_settle import (
    NOW,
    FakeOdds,
    FakeScores,
    _close,
    _open,
    _pinnacle,
    _settle,
    clock,
)
from tipster.cli import app as cli
from tipster.providers.base import MatchScore
from tipster.services.status import paper_status, status_lines
from tipster.storage.db import connect
from tipster.storage.tracking import SqliteTrackingRepository


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(tmp_path / "t.sqlite")
    yield connection
    connection.close()


def _take(conn: sqlite3.Connection, pick_id: int, price: float) -> bool:
    return SqliteTrackingRepository(conn).set_taken(
        pick_id, price=price, bookmaker="bwin.es", at=NOW
    )


def test_registrar_la_cuota_real_guarda_precio_casa_y_hora(conn: sqlite3.Connection) -> None:
    pick_id = _open(conn, "e1", minutes_to_kickoff=600, price=2.20)
    assert _take(conn, pick_id, 2.05)
    row = conn.execute(
        "SELECT taken_price, taken_bookmaker, taken_at, clv_taken FROM picks"
    ).fetchone()
    assert (row[0], row[1], row[3]) == (2.05, "bwin.es", None)  # aún sin cierre: sin CLV real
    assert row[2] is not None


@pytest.mark.parametrize("stake", [None, 0.0])
def test_no_se_registra_en_un_pick_sin_stake(conn: sqlite3.Connection, stake: float | None) -> None:
    pick_id = _open(conn, "e1", minutes_to_kickoff=600, stake=stake)
    assert not _take(conn, pick_id, 2.0)
    assert not _take(conn, 999, 2.0)  # inexistente


def test_no_se_registra_en_un_pick_ya_liquidado(conn: sqlite3.Connection) -> None:
    pick_id = _open(conn, "e1", minutes_to_kickoff=-180)
    _settle(conn, FakeScores([MatchScore("xe1", True, 2, 1)]))
    assert not _take(conn, pick_id, 2.0)


def test_el_cierre_calcula_el_clv_real_y_el_del_feed_a_la_vez(conn: sqlite3.Connection) -> None:
    pick_id = _open(conn, "e1", minutes_to_kickoff=10, price=2.20)
    _take(conn, pick_id, 2.00)
    _close(conn, FakeOdds(_pinnacle("e1", (1.80, 3.60, 3.60))))  # cuota justa de cierre 2,00
    row = conn.execute("SELECT clv, clv_taken FROM picks").fetchone()
    assert row["clv"] == pytest.approx(0.10)  # feed: 2,20 / 2,00 − 1
    assert row["clv_taken"] == pytest.approx(0.0)  # real: 2,00 / 2,00 − 1


def test_registrar_despues_del_cierre_calcula_el_clv_real_al_momento(
    conn: sqlite3.Connection,
) -> None:
    pick_id = _open(conn, "e1", minutes_to_kickoff=10, price=2.20)
    _close(conn, FakeOdds(_pinnacle("e1", (1.80, 3.60, 3.60))))
    _take(conn, pick_id, 2.10)
    assert conn.execute("SELECT clv_taken FROM picks").fetchone()[0] == pytest.approx(0.05)
    [(real, feed, stake)] = SqliteTrackingRepository(conn).clv_taken_values()
    assert real == pytest.approx(0.05)
    assert feed == pytest.approx(0.10)
    assert stake == 20.0


def test_un_cierre_no_fiable_no_da_clv_real(conn: sqlite3.Connection) -> None:
    pick_id = _open(conn, "e1", minutes_to_kickoff=10)
    _take(conn, pick_id, 2.0)
    early = _pinnacle("e1", (1.80, 3.60, 3.60), captured=NOW - timedelta(minutes=10))
    _close(conn, FakeOdds(early))
    assert conn.execute("SELECT clv_taken FROM picks").fetchone()[0] is None


def test_la_liquidacion_usa_la_cuota_real(conn: sqlite3.Connection) -> None:
    won = _open(conn, "e1", minutes_to_kickoff=-180, stake=10.0, price=2.20)
    plain = _open(conn, "e2", minutes_to_kickoff=-200, stake=10.0, price=2.20)
    _take(conn, won, 2.00)
    _, bank = _settle(
        conn, FakeScores([MatchScore("xe1", True, 2, 1), MatchScore("xe2", True, 2, 1)])
    )
    profits = {r["id"]: r["profit"] for r in conn.execute("SELECT id, profit FROM picks")}
    assert profits[won] == pytest.approx(10.0)  # 10 × (2,00 − 1), no 12,00
    assert profits[plain] == pytest.approx(12.0)  # sin cuota real: la del feed
    assert bank.balance() == pytest.approx(1022.0)


def test_status_compara_el_clv_real_con_el_del_feed(conn: sqlite3.Connection) -> None:
    a = _open(conn, "e1", minutes_to_kickoff=10, price=2.20)
    _open(conn, "e2", minutes_to_kickoff=600)  # sin cuota real
    _take(conn, a, 2.00)
    _close(conn, FakeOdds(_pinnacle("e1", (1.80, 3.60, 3.60))))
    st = paper_status(conn, NOW)
    assert (st.taken_picks, st.stake_picks) == (1, 2)
    text = "\n".join(status_lines(st, ZoneInfo("Europe/Madrid")))
    assert "Cuota real registrada: 1 de 2" in text
    assert "CLV real:   +0.00 % en 1 picks · el feed daba +10.00 %" in text


def test_status_avisa_si_no_hay_ninguna_cuota_real(conn: sqlite3.Connection) -> None:
    _open(conn, "e1", minutes_to_kickoff=600)
    text = "\n".join(status_lines(paper_status(conn, NOW), ZoneInfo("Europe/Madrid")))
    assert "Cuota real registrada: 0 de 1" in text and "tipster take" in text


# -- CLI ---------------------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_now", clock)
    path = tmp_path / "t.sqlite"
    c = connect(path)
    _open(c, "e1", minutes_to_kickoff=600, price=2.20)
    c.commit()
    c.close()
    return path


def test_cli_take_registra_y_muestra_la_desviacion(db: Path) -> None:
    result = CliRunner().invoke(
        cli.app, ["take", "1", "--price", "2.0", "--bookmaker", "bwin.es", "--db", str(db)]
    )
    assert result.exit_code == 0, result.output
    assert "cuota real 2 (feed 2.2, -9.1%)" in result.output and "mucho peor" in result.output
    listing = CliRunner().invoke(cli.app, ["take", "--list", "--db", str(db)])
    assert "#1" in listing.output and "real 2" in listing.output


def test_cli_take_rechaza_pick_inexistente_o_cuota_invalida(db: Path) -> None:
    bad_pick = CliRunner().invoke(cli.app, ["take", "99", "--price", "2.0", "--db", str(db)])
    assert bad_pick.exit_code == 2 and "no existe" in bad_pick.output
    bad_price = CliRunner().invoke(cli.app, ["take", "1", "--price", "1.0", "--db", str(db)])
    assert bad_price.exit_code == 2
    missing = CliRunner().invoke(cli.app, ["take", "1", "--db", str(db)])
    assert missing.exit_code == 2 and "--price" in missing.output

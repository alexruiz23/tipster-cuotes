"""Bankroll de papel y seguimiento de picks (ADR 012) sobre SQLite."""

import sqlite3
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

from tests.factories import NOW, make_event, make_opportunity, make_quote
from tipster.domain.models import Pick
from tipster.pricing.classify import Label
from tipster.storage.db import connect
from tipster.storage.sqlite import (
    SqliteEventRepository,
    SqliteOddsRepository,
    SqlitePickRepository,
    SqliteRunRepository,
)
from tipster.storage.tracking import (
    SqliteBankrollRepository,
    SqliteBlendConfigRepository,
    SqliteTrackingRepository,
)


def clock():  # type: ignore[no-untyped-def]
    return NOW


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(tmp_path / "tipster.sqlite")
    yield connection
    connection.close()


def _make_pick(
    conn: sqlite3.Connection,
    event_id: str = "e1",
    *,
    selection: str = "local",
    price: float = 2.20,
    label: Label = Label.VALUE,
    market_id: str = "1x2",
) -> tuple[int, int, int]:
    """Guarda un pick y devuelve (id del pick, id de la cuota, id de la ejecución)."""
    run_id = SqliteRunRepository(conn, clock).start("scan", {})
    cursor = conn.execute(
        "INSERT INTO provider_requests (run_id, provider, endpoint, params_key, from_cache,"
        " requested_at) VALUES (?, 'the_odds_api', '/x', '', 0, ?)",
        (run_id, NOW.isoformat()),
    )
    request_id = cursor.lastrowid
    assert request_id is not None
    SqliteEventRepository(conn, clock).upsert(make_event(event_id), "the_odds_api", "x" + event_id)
    quote = make_quote(event_id=event_id, selection=selection, price=price, market_id=market_id)
    quote_id = SqliteOddsRepository(conn).add_batch(request_id, [quote])[0]
    SqlitePickRepository(conn).add(
        run_id,
        [Pick(quote_id=quote_id, opportunity=make_opportunity(label, quote), created_at=NOW)],
    )
    pick_id = conn.execute("SELECT id FROM picks WHERE quote_id = ?", (quote_id,)).fetchone()[0]
    return pick_id, quote_id, run_id


# -- Bankroll ----------------------------------------------------------------------------------


def test_el_bankroll_empieza_con_el_deposito_inicial_una_sola_vez(conn: sqlite3.Connection) -> None:
    bank = SqliteBankrollRepository(conn, clock)
    assert bank.balance() == 0.0
    bank.ensure_initial(1000.0)
    bank.ensure_initial(5000.0)  # no vuelve a depositar
    assert bank.balance() == 1000.0
    assert conn.execute("SELECT COUNT(*) FROM bankroll_entries").fetchone()[0] == 1


def test_las_liquidaciones_actualizan_el_saldo_y_son_idempotentes(conn: sqlite3.Connection) -> None:
    bank = SqliteBankrollRepository(conn, clock)
    bank.ensure_initial(1000.0)
    won, _, _ = _make_pick(conn, "e1")
    lost, _, _ = _make_pick(conn, "e2")
    assert bank.settle(won, 24.0) == 1024.0  # 20 a cuota 2,20 ganado: +20·1,20
    assert bank.settle(lost, -20.0) == 1004.0
    assert bank.settle(won, 24.0) == 1004.0  # repetir no duplica
    assert conn.execute("SELECT COUNT(*) FROM bankroll_entries").fetchone()[0] == 3


def test_pnl_de_un_tramo_de_tiempo(conn: sqlite3.Connection) -> None:
    bank = SqliteBankrollRepository(conn, clock)
    bank.ensure_initial(1000.0)
    a, _, _ = _make_pick(conn, "e1")
    b, _, _ = _make_pick(conn, "e2")
    bank.settle(a, 24.0)
    bank.settle(b, -20.0)
    assert bank.pnl_between(NOW - timedelta(hours=1), NOW + timedelta(hours=1)) == 4.0
    assert bank.pnl_between(NOW + timedelta(hours=1), NOW + timedelta(hours=2)) == 0.0
    # el depósito inicial no cuenta como resultado
    assert bank.pnl_between(NOW - timedelta(hours=1), NOW + timedelta(hours=1)) != 1004.0


# -- Seguimiento de picks ----------------------------------------------------------------------


def test_stakes_y_picks_abiertos(conn: sqlite3.Connection) -> None:
    track = SqliteTrackingRepository(conn)
    pick_id, quote_id, run_id = _make_pick(conn, "e1")
    track.set_stakes(run_id, {quote_id: 20.0})
    [open_pick] = track.open_picks()
    assert (open_pick.id, open_pick.event_id, open_pick.stake, open_pick.price) == (
        pick_id,
        "e1",
        20.0,
        2.20,
    )
    assert (open_pick.market_id, open_pick.selection) == ("1x2", "local")
    assert open_pick.kickoff == make_event("e1").kickoff
    assert track.stake_by_open_event() == {"e1": 20.0}


def test_un_pick_sin_stake_no_cuenta_como_exposicion(conn: sqlite3.Connection) -> None:
    track = SqliteTrackingRepository(conn)
    _make_pick(conn, "e1")  # stake NULL
    assert track.stake_by_open_event() == {}
    assert track.exposure(NOW, NOW + timedelta(days=10)) == 0.0


def test_la_exposicion_cuenta_los_stakes_abiertos_con_inicio_en_el_tramo(
    conn: sqlite3.Connection,
) -> None:
    track = SqliteTrackingRepository(conn)
    _, q1, r1 = _make_pick(conn, "e1")
    _, q2, r2 = _make_pick(conn, "e2")
    track.set_stakes(r1, {q1: 20.0})
    track.set_stakes(r2, {q2: 15.0})
    kickoff = make_event("e1").kickoff  # los dos eventos empiezan a la vez
    assert track.exposure(kickoff - timedelta(hours=1), kickoff + timedelta(hours=1)) == 35.0
    assert track.exposure(kickoff + timedelta(hours=1), kickoff + timedelta(hours=2)) == 0.0


def test_liquidar_cierra_el_pick_y_guarda_resultado_y_beneficio(conn: sqlite3.Connection) -> None:
    track = SqliteTrackingRepository(conn)
    pick_id, quote_id, run_id = _make_pick(conn)
    track.set_stakes(run_id, {quote_id: 20.0})
    track.settle(pick_id, result="local", status="ganado", profit=24.0, settled_at=NOW)
    assert track.open_picks() == []
    row = conn.execute("SELECT status, result, profit, settled_at FROM picks").fetchone()
    assert tuple(row) == ("ganado", "local", 24.0, NOW.isoformat())
    assert track.stake_by_open_event() == {}


def test_el_cierre_fiable_alimenta_el_clv_y_el_no_fiable_no(conn: sqlite3.Connection) -> None:
    track = SqliteTrackingRepository(conn)
    good, q1, r1 = _make_pick(conn, "e1")
    bad, q2, r2 = _make_pick(conn, "e2")
    track.set_stakes(r1, {q1: 10.0})
    track.set_stakes(r2, {q2: 10.0})
    track.set_closing(
        good, closing_odds=1.80, closing_fair_odds=2.00, captured_at=NOW, last_update=NOW,
        reliable=True, clv=0.10,
    )  # fmt: skip
    track.set_closing(
        bad, closing_odds=1.80, closing_fair_odds=2.00, captured_at=NOW, last_update=None,
        reliable=False, clv=None,
    )  # fmt: skip
    assert track.clv_values() == [(0.10, 10.0)]
    row = conn.execute("SELECT closing_reliable, clv FROM picks WHERE id = ?", (bad,)).fetchone()
    assert tuple(row) == (0, None)


def test_las_columnas_de_mezcla_se_guardan_y_se_leen(conn: sqlite3.Connection) -> None:
    pick_id, quote_id, run_id = _make_pick(conn)
    opportunity = make_opportunity(Label.VALUE).model_copy(
        update={
            "p_model": 0.5,
            "p_model_raw": 0.48,
            "w_market": 0.8,
            "model_name": "dixon_coles",
            "model_version": "3",
        }
    )
    conn2 = conn
    conn2.execute("DELETE FROM picks")
    SqlitePickRepository(conn2).add(
        run_id, [Pick(quote_id=quote_id, opportunity=opportunity, created_at=NOW)]
    )
    [stored] = SqlitePickRepository(conn2).for_run(run_id)
    assert (stored.opportunity.p_model_raw, stored.opportunity.w_market) == (0.48, 0.8)
    assert (stored.opportunity.model_name, stored.opportunity.model_version) == ("dixon_coles", "3")
    assert pick_id > 0


def test_la_configuracion_de_mezcla_se_guarda_y_se_recupera(conn: sqlite3.Connection) -> None:
    configs = SqliteBlendConfigRepository(conn, clock)
    assert configs.latest() is None
    first = configs.save({"w_market": 1.0, "devig": "multiplicativo"})
    second = configs.save({"w_market": 0.8, "calibrator": {"beta": 0.9}})
    assert second == first + 1
    assert configs.latest() == (second, {"w_market": 0.8, "calibrator": {"beta": 0.9}})

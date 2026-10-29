"""Stakes de `tipster scan` (ADR 012): Kelly, un pick por evento, exposición y pérdida diarias."""

import sqlite3
from collections.abc import Iterator

import pytest

from tests.integration.test_scan_service import (
    CAPTURED,
    FIXTURES,
    KEY,
    _offline_scan,
    _service,
    _settings,
)
from tests.integration.test_tracking import _make_pick
from tipster.config import Settings
from tipster.pricing.classify import Label
from tipster.providers.the_odds_api.client import TheOddsApiProvider
from tipster.providers.the_odds_api.offline import OfflineFetcher
from tipster.services.scan import ScanResult
from tipster.staking.kelly import kelly_stake
from tipster.storage.db import MEMORY, connect
from tipster.storage.tracking import SqliteBankrollRepository, SqliteTrackingRepository

assert KEY
EXTRA_ONE_PER_EVENT = "otro pick de este partido tiene más EV"
EXTRA_OPEN = "ya hay un pick abierto con stake en este partido"
EXTRA_LOSS = "límite de pérdida diaria alcanzado"


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    connection = connect(MEMORY)
    yield connection
    connection.close()


def _scan(conn: sqlite3.Connection, settings: Settings | None = None) -> ScanResult:
    provider = TheOddsApiProvider(OfflineFetcher(FIXTURES))
    return _service(conn, provider, settings or _settings()).run()


def _value(result: ScanResult) -> list:  # type: ignore[type-arg]
    return [p.opportunity for p in result.picks if p.opportunity.label is Label.VALUE]


def test_los_value_llevan_un_cuarto_de_kelly_con_tope_y_solo_el_mejor_de_cada_partido(
    conn: sqlite3.Connection,
) -> None:
    result = _offline_scan(conn)
    values = _value(result)
    assert len(values) == 3  # dos del partido 1 (888sport y Winamax O2.5) y uno del partido 2
    staked = [o for o in values if o.stake]
    assert len({o.event.id for o in staked}) == len(staked) == 2  # un pick por evento
    for o in staked:
        assert o.stake == pytest.approx(kelly_stake(1000.0, o.p_final, o.quote.price), abs=0.005)
        assert 0 < o.stake <= 20.0
    best = max((o for o in values if o.event.id == staked[0].event.id), key=lambda o: o.ev)
    assert best.stake == staked[0].stake or best in staked
    unstaked = [o for o in values if not o.stake]
    assert len(unstaked) == 1
    assert unstaked[0].stake == 0.0 and EXTRA_ONE_PER_EVENT in unstaked[0].reasons[-1]


def test_el_posible_error_no_lleva_stake(conn: sqlite3.Connection) -> None:
    result = _offline_scan(conn)
    errors = [p.opportunity for p in result.picks if p.opportunity.label is Label.POSIBLE_ERROR]
    assert errors and all(o.stake is None for o in errors)


def test_los_stakes_quedan_en_la_base_y_el_bankroll_arranca_en_1000(
    conn: sqlite3.Connection,
) -> None:
    result = _offline_scan(conn)
    rows = conn.execute("SELECT stake, reasons_json FROM picks WHERE label = 'VALUE'").fetchall()
    assert sorted(r["stake"] for r in rows) == sorted(o.stake for o in _value(result))
    assert SqliteBankrollRepository(conn, lambda: CAPTURED).balance() == 1000.0


def test_repetir_el_escaneo_no_duplica_stake(conn: sqlite3.Connection) -> None:
    first = _offline_scan(conn)
    total = SqliteTrackingRepository(conn).stake_by_open_event()
    second = _offline_scan(conn)
    assert all(o.stake == 0.0 for o in _value(second))
    assert all(EXTRA_OPEN in o.reasons[-1] for o in _value(second))
    assert SqliteTrackingRepository(conn).stake_by_open_event() == total
    assert sum(total.values()) == pytest.approx(sum(o.stake or 0.0 for o in _value(first)))


def test_la_exposicion_diaria_recorta_los_stakes(conn: sqlite3.Connection) -> None:
    result = _scan(conn, _settings(daily_exposure=0.005))  # 5,00 por día de partido
    staked = [o.stake for o in _value(result) if o.stake]
    assert staked == [5.0, 5.0]


def test_la_exposicion_ya_abierta_del_dia_reduce_el_hueco(conn: sqlite3.Connection) -> None:
    # Un pick abierto con stake 3,00 de otro partido del 26/10 (hora local); tope diario 7,00
    _, quote_id, run_id = _make_pick(conn, "ya-abierto")
    conn.execute(
        "UPDATE events SET kickoff_utc = '2026-10-26T12:00:00+00:00' WHERE id = 'ya-abierto'"
    )
    SqliteTrackingRepository(conn).set_stakes(run_id, {quote_id: 3.0})
    result = _scan(conn, _settings(daily_exposure=0.007))
    stakes = {o.event.home_team: o.stake for o in _value(result) if o.stake}
    # el partido del 25/10 tiene el hueco entero (7,00); el del 26/10, solo 7,00 − 3,00 = 4,00
    assert stakes == {"Local Prueba FC": 7.0, "Ciudad Ficticia CF": 4.0}


def test_el_limite_de_perdida_diaria_apaga_las_recomendaciones(conn: sqlite3.Connection) -> None:
    _offline_scan(conn)
    pick_id = conn.execute("SELECT id FROM picks ORDER BY id LIMIT 1").fetchone()[0]
    SqliteBankrollRepository(conn, lambda: CAPTURED).settle(pick_id, -60.0)  # 6 % de 1 000
    second = _offline_scan(conn)
    values = _value(second)
    assert values and all(o.stake == 0.0 for o in values)
    assert all(EXTRA_LOSS in o.reasons[-1] for o in values)


def test_los_picks_guardan_la_version_de_la_mezcla_y_w_1_sin_modelo(
    conn: sqlite3.Connection,
) -> None:
    provider = TheOddsApiProvider(OfflineFetcher(FIXTURES))
    result = _service(conn, provider, _settings(), blend_version="7").run()
    assert result.picks
    assert {(p.opportunity.model_version, p.opportunity.w_market, p.opportunity.model_name)
            for p in result.picks} == {("7", 1.0, None)}  # fmt: skip
    rows = conn.execute("SELECT DISTINCT model_version, w_market, model_name FROM picks").fetchall()
    assert [tuple(r) for r in rows] == [("7", 1.0, None)]

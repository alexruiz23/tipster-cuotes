"""Repositorios SQLite (D7: sqlite3 de la librería estándar) contra una base temporal."""

import json
import sqlite3
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tests.factories import NOW, make_event, make_opportunity, make_quote
from tipster.domain.markets import get_market
from tipster.domain.models import Pick
from tipster.pricing.classify import Label
from tipster.pricing.devig import devig
from tipster.providers.base import RequestRecord
from tipster.storage.db import connect, schema_versions
from tipster.storage.sqlite import (
    SqliteEventRepository,
    SqliteOddsRepository,
    SqlitePickRepository,
    SqliteResponseCache,
    SqliteRunRepository,
)


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(tmp_path / "tipster.sqlite")
    yield connection
    connection.close()


def clock() -> datetime:
    return NOW


def _record(
    *,
    params_key: str = "bookmakers=pinnacle&markets=h2h",
    status: int | None = 200,
    from_cache: bool = False,
    requested_at: datetime = NOW,
    raw_path: str | None = "data/raw/r1.json",
) -> RequestRecord:
    return RequestRecord(
        provider="the_odds_api",
        endpoint="/v4/sports/soccer_spain_la_liga/odds",
        params_key=params_key,
        http_status=status,
        from_cache=from_cache,
        cost=2,
        credits_used=10,
        credits_remaining=490,
        requested_at=requested_at,
        duration_ms=120,
        raw_path=raw_path,
    )


def _run_with_request(conn: sqlite3.Connection, **kwargs: object) -> tuple[int, int]:
    runs = SqliteRunRepository(conn, clock)
    run_id = runs.start("scan", {"ev_min": 0.03})
    return run_id, runs.record_request(run_id, _record(**kwargs))  # type: ignore[arg-type]


def _store_quote(conn: sqlite3.Connection, request_id: int, **kwargs: object) -> int:
    quote = make_quote(**kwargs)  # type: ignore[arg-type]
    SqliteEventRepository(conn, clock).upsert(make_event(quote.event_id), "the_odds_api", "ext1")
    return SqliteOddsRepository(conn).add_batch(request_id, [quote])[0]


def test_las_migraciones_se_aplican_una_sola_vez(tmp_path: Path) -> None:
    path = tmp_path / "tipster.sqlite"
    connect(path).close()
    again = connect(path)
    assert schema_versions(again) == [1]
    tables = {r[0] for r in again.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    expected = {"runs", "provider_requests", "events", "event_external_ids", "odds_quotes", "picks"}
    assert expected <= tables
    again.close()


def test_ejecucion_y_peticiones(conn: sqlite3.Connection) -> None:
    runs = SqliteRunRepository(conn, clock)
    run_id = runs.start("scan", {"ev_min": 0.03})
    request_id = runs.record_request(run_id, _record())
    runs.finish(run_id, "parcial")
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    assert row["status"] == "parcial"
    assert json.loads(row["settings_json"]) == {"ev_min": 0.03}
    assert datetime.fromisoformat(row["finished_at"]) == NOW
    req = conn.execute("SELECT * FROM provider_requests WHERE id = ?", (request_id,)).fetchone()
    assert (req["cost"], req["credits_remaining"], req["from_cache"]) == (2, 490, 0)


def test_upsert_de_evento_es_idempotente(conn: sqlite3.Connection) -> None:
    events = SqliteEventRepository(conn, clock)
    event = make_event()
    events.upsert(event, "the_odds_api", "ext1")
    events.upsert(event, "the_odds_api", "ext1")
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM event_external_ids").fetchone()[0] == 1
    stored = events.get(event.id)
    assert stored == event
    assert stored is not None
    assert stored.kickoff.utcoffset() == timedelta(0)


def test_cuotas_ida_y_vuelta_y_ultima_por_seleccion(conn: sqlite3.Connection) -> None:
    _, request_id = _run_with_request(conn)
    SqliteEventRepository(conn, clock).upsert(make_event(), "the_odds_api", "ext1")
    odds = SqliteOddsRepository(conn)
    old = make_quote(price=2.10, captured_at=NOW - timedelta(minutes=5))
    new = make_quote(price=2.20)
    other = make_quote(selection="empate", price=3.40)
    ids = odds.add_batch(request_id, [old, new, other])
    assert len(set(ids)) == 3
    latest = odds.latest("e1", "1x2")
    assert sorted(latest, key=lambda q: q.selection) == [other, new]


def test_toda_cuota_guarda_hora_de_captura_y_origen(conn: sqlite3.Connection) -> None:
    _, request_id = _run_with_request(conn)
    quote_id = _store_quote(conn, request_id)
    row = conn.execute("SELECT * FROM odds_quotes WHERE id = ?", (quote_id,)).fetchone()
    assert row["captured_at"] == NOW.isoformat()
    assert row["source"] == "the_odds_api"
    assert row["request_id"] == request_id


def test_restricciones_del_esquema(conn: sqlite3.Connection) -> None:
    _, request_id = _run_with_request(conn)
    _store_quote(conn, request_id)
    insert = (
        "INSERT INTO odds_quotes (request_id, event_id, bookmaker_id, market_id, selection,"
        " price, captured_at, provider_last_update, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    base = [request_id, "e1", "pinnacle", "1x2", "local", 2.0, NOW.isoformat(), None, "x"]
    for column, value in ((5, 1.0), (6, None), (8, None)):  # cuota ≤ 1, sin captura, sin origen
        bad = list(base)
        bad[column] = value
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(insert, bad)
    conn.execute(insert, base)
    with pytest.raises(sqlite3.IntegrityError):  # UNIQUE por petición, evento, casa y selección
        conn.execute(insert, base)
    with pytest.raises(sqlite3.IntegrityError):  # clave foránea: evento inexistente
        conn.execute(insert, [*base[:1], "no_existe", *base[2:]])


def test_picks_guardan_las_cuotas_de_referencia_reproducibles(conn: sqlite3.Connection) -> None:
    run_id, request_id = _run_with_request(conn)
    quote_id = _store_quote(conn, request_id)
    opportunity = make_opportunity(Label.VALUE)
    pick = Pick(quote_id=quote_id, opportunity=opportunity, created_at=NOW)
    picks = SqlitePickRepository(conn)
    picks.add(run_id, [pick])

    row = conn.execute("SELECT * FROM picks WHERE run_id = ?", (run_id,)).fetchone()
    stored = json.loads(row["reference_odds_json"])
    assert stored == [["local", 2.0], ["empate", 3.5], ["visitante", 4.0]]
    # Exactamente las cuotas de entrada del devig, y reproducen p_mercado.
    assert [tuple(x) for x in stored] == list(opportunity.reference_odds)
    selections = get_market("1x2").selections
    p = devig([price for _, price in stored], opportunity.devig_method)
    assert p[selections.index(opportunity.quote.selection)] == pytest.approx(row["p_market"])
    assert row["stake"] is None

    assert picks.for_run(run_id) == [pick]


def test_el_esquema_rechaza_picks_que_no_son_value_ni_error(conn: sqlite3.Connection) -> None:
    run_id, request_id = _run_with_request(conn)
    quote_id = _store_quote(conn, request_id)
    row = SqlitePickRepository(conn)
    row.add(run_id, [Pick(quote_id=quote_id, opportunity=make_opportunity(), created_at=NOW)])
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE picks SET label = 'SIN_VALOR'")


def test_cache_por_ttl(conn: sqlite3.Connection) -> None:
    runs = SqliteRunRepository(conn, clock)
    run_id = runs.start("scan", {})
    fresh_id = runs.record_request(run_id, _record(requested_at=NOW - timedelta(seconds=30)))
    runs.record_request(run_id, _record(params_key="otro", status=500))
    runs.record_request(run_id, _record(from_cache=True, requested_at=NOW))
    cache = SqliteResponseCache(conn)
    ttl = timedelta(seconds=60)
    endpoint = "/v4/sports/soccer_spain_la_liga/odds"

    key = "bookmakers=pinnacle&markets=h2h"
    hit = cache.lookup("the_odds_api", endpoint, key, ttl, NOW)
    assert hit is not None
    assert hit.request_id == fresh_id
    assert hit.requested_at == NOW - timedelta(seconds=30)
    later = NOW + timedelta(minutes=2)
    assert (
        cache.lookup("the_odds_api", endpoint, "bookmakers=pinnacle&markets=h2h", ttl, later)
        is None
    )
    assert cache.lookup("the_odds_api", endpoint, "otro", ttl, NOW) is None  # respuesta 500

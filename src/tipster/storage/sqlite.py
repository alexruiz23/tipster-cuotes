"""Implementación SQLite de los repositorios y de la caché de respuestas."""

import json
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta

from tipster.domain.models import Event, OddsQuote, Opportunity, Pick
from tipster.domain.sports import SportId
from tipster.pricing.classify import Label
from tipster.pricing.devig import DevigMethod
from tipster.providers.base import CachedResponse, RequestRecord
from tipster.storage.db import from_iso, iso
from tipster.storage.repositories import RunStatus

Clock = Callable[[], datetime]

# Las etiquetas se guardan con un código estable, independiente del texto que se muestra.
_LABEL_CODES: Mapping[Label, str] = {Label.VALUE: "VALUE", Label.POSIBLE_ERROR: "POSIBLE_ERROR"}
_LABELS_BY_CODE = {code: label for label, code in _LABEL_CODES.items()}


def _optional_iso(value: datetime | None) -> str | None:
    return None if value is None else iso(value)


def _optional_from_iso(value: str | None) -> datetime | None:
    return None if value is None else from_iso(value)


class SqliteRunRepository:
    def __init__(self, conn: sqlite3.Connection, clock: Clock) -> None:
        self._conn = conn
        self._clock = clock

    def start(self, command: str, settings_snapshot: Mapping[str, object]) -> int:
        cursor = self._conn.execute(
            "INSERT INTO runs (command, started_at, status, settings_json) VALUES (?, ?, ?, ?)",
            (command, iso(self._clock()), "en_curso", json.dumps(settings_snapshot, default=str)),
        )
        self._conn.commit()
        return _rowid(cursor)

    def record_request(self, run_id: int, record: RequestRecord) -> int:
        cursor = self._conn.execute(
            "INSERT INTO provider_requests (run_id, provider, endpoint, params_key, http_status,"
            " from_cache, cost, credits_used, credits_remaining, requested_at, duration_ms,"
            " raw_path, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                record.provider,
                record.endpoint,
                record.params_key,
                record.http_status,
                int(record.from_cache),
                record.cost,
                record.credits_used,
                record.credits_remaining,
                iso(record.requested_at),
                record.duration_ms,
                record.raw_path,
                record.error,
            ),
        )
        self._conn.commit()
        return _rowid(cursor)

    def finish(self, run_id: int, status: RunStatus) -> None:
        self._conn.execute(
            "UPDATE runs SET finished_at = ?, status = ? WHERE id = ?",
            (iso(self._clock()), status, run_id),
        )
        self._conn.commit()


class SqliteEventRepository:
    def __init__(self, conn: sqlite3.Connection, clock: Clock) -> None:
        self._conn = conn
        self._clock = clock

    def upsert(self, event: Event, provider: str, external_id: str) -> None:
        self._conn.execute(
            "INSERT INTO events (id, sport, competition_id, home_team, away_team, kickoff_utc,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET"
            " home_team = excluded.home_team, away_team = excluded.away_team,"
            " kickoff_utc = excluded.kickoff_utc",
            (
                event.id,
                event.sport.value,
                event.competition_id,
                event.home_team,
                event.away_team,
                iso(event.kickoff),
                iso(self._clock()),
            ),
        )
        self._conn.execute(
            "INSERT INTO event_external_ids (provider, external_id, event_id) VALUES (?, ?, ?)"
            " ON CONFLICT (provider, external_id) DO NOTHING",
            (provider, external_id, event.id),
        )
        self._conn.commit()

    def get(self, event_id: str) -> Event | None:
        row = self._conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return None if row is None else _event(row)


def _event(row: sqlite3.Row) -> Event:
    return Event(
        id=row["id"],
        sport=SportId(row["sport"]),
        competition_id=row["competition_id"],
        home_team=row["home_team"],
        away_team=row["away_team"],
        kickoff=from_iso(row["kickoff_utc"]),
    )


def _quote(row: sqlite3.Row) -> OddsQuote:
    return OddsQuote(
        event_id=row["event_id"],
        bookmaker_id=row["bookmaker_id"],
        market_id=row["market_id"],
        selection=row["selection"],
        price=row["price"],
        captured_at=from_iso(row["captured_at"]),
        provider_last_update=_optional_from_iso(row["provider_last_update"]),
        source=row["source"],
    )


class SqliteOddsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add_batch(self, request_id: int, quotes: Sequence[OddsQuote]) -> list[int]:
        ids = []
        for quote in quotes:
            cursor = self._conn.execute(
                "INSERT INTO odds_quotes (request_id, event_id, bookmaker_id, market_id,"
                " selection, price, captured_at, provider_last_update, source)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    request_id,
                    quote.event_id,
                    quote.bookmaker_id,
                    quote.market_id,
                    quote.selection,
                    quote.price,
                    iso(quote.captured_at),
                    _optional_iso(quote.provider_last_update),
                    quote.source,
                ),
            )
            ids.append(_rowid(cursor))
        self._conn.commit()
        return ids

    def latest(self, event_id: str, market_id: str) -> list[OddsQuote]:
        rows = self._conn.execute(
            "SELECT * FROM odds_quotes WHERE event_id = ? AND market_id = ?"
            " ORDER BY captured_at, id",
            (event_id, market_id),
        ).fetchall()
        latest: dict[tuple[str, str], OddsQuote] = {}
        for row in rows:  # orden ascendente: la última que se ve es la más reciente
            latest[(row["bookmaker_id"], row["selection"])] = _quote(row)
        return list(latest.values())


class SqlitePickRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, run_id: int, picks: Sequence[Pick]) -> None:
        for pick in picks:
            o = pick.opportunity
            self._conn.execute(
                "INSERT INTO picks (run_id, quote_id, label, feed_es, reference_bookmaker_id,"
                " reference_captured_at, reference_odds_json, devig_method, p_market, p_model,"
                " p_final, fair_odds, ev, stake, reasons_json, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    pick.quote_id,
                    _LABEL_CODES[o.label],
                    int(o.feed_es),
                    o.reference_bookmaker_id,
                    iso(o.reference_captured_at),
                    json.dumps([[s, price] for s, price in o.reference_odds]),
                    o.devig_method.value,
                    o.p_market,
                    o.p_model,
                    o.p_final,
                    o.fair_odds,
                    o.ev,
                    o.stake,
                    json.dumps(list(o.reasons), ensure_ascii=False),
                    iso(pick.created_at),
                ),
            )
        self._conn.commit()

    def for_run(self, run_id: int) -> list[Pick]:
        rows = self._conn.execute(
            "SELECT p.*, q.event_id, q.bookmaker_id, q.market_id, q.selection, q.price,"
            " q.captured_at, q.provider_last_update, q.source FROM picks p"
            " JOIN odds_quotes q ON q.id = p.quote_id WHERE p.run_id = ? ORDER BY p.id",
            (run_id,),
        ).fetchall()
        events = SqliteEventRepository(self._conn, lambda: datetime.min)
        picks = []
        for row in rows:
            event = events.get(row["event_id"])
            if event is None:  # imposible por la clave foránea
                raise LookupError(f"Evento {row['event_id']} no encontrado")
            opportunity = Opportunity(
                event=event,
                quote=_quote(row),
                feed_es=bool(row["feed_es"]),
                reference_bookmaker_id=row["reference_bookmaker_id"],
                reference_captured_at=from_iso(row["reference_captured_at"]),
                reference_odds=tuple(
                    (s, float(price)) for s, price in json.loads(row["reference_odds_json"])
                ),
                devig_method=DevigMethod(row["devig_method"]),
                p_market=row["p_market"],
                p_model=row["p_model"],
                p_final=row["p_final"],
                fair_odds=row["fair_odds"],
                ev=row["ev"],
                stake=row["stake"],
                label=_LABELS_BY_CODE[row["label"]],
                reasons=tuple(json.loads(row["reasons_json"])),
            )
            picks.append(
                Pick(
                    quote_id=row["quote_id"],
                    opportunity=opportunity,
                    created_at=from_iso(row["created_at"]),
                )
            )
        return picks


class SqliteResponseCache:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def lookup(
        self, provider: str, endpoint: str, params_key: str, max_age: timedelta, now: datetime
    ) -> CachedResponse | None:
        row = self._conn.execute(
            "SELECT id, requested_at, raw_path FROM provider_requests WHERE provider = ?"
            " AND endpoint = ? AND params_key = ? AND http_status = 200 AND from_cache = 0"
            " AND raw_path IS NOT NULL AND requested_at >= ? AND requested_at <= ?"
            " ORDER BY requested_at DESC LIMIT 1",
            (provider, endpoint, params_key, iso(now - max_age), iso(now)),
        ).fetchone()
        if row is None:
            return None
        return CachedResponse(
            request_id=row["id"],
            requested_at=from_iso(row["requested_at"]),
            raw_path=row["raw_path"],
        )


def _rowid(cursor: sqlite3.Cursor) -> int:
    if cursor.lastrowid is None:
        raise sqlite3.DatabaseError("La inserción no devolvió id")
    return cursor.lastrowid

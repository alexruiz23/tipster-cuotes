"""Servicio scan de principio a fin con fixtures sintéticas y SQLite en memoria."""

import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from tipster.config import Settings
from tipster.domain.markets import get_market
from tipster.errors import BudgetExceededError, ProviderAuthError
from tipster.pricing.devig import devig
from tipster.providers.base import CompetitionListing, OddsBatch, OddsRequest, ProviderCompetition
from tipster.providers.budget import CreditBudget
from tipster.providers.http import HttpClient, HttpPolicy
from tipster.providers.the_odds_api.client import TheOddsApiProvider
from tipster.providers.the_odds_api.offline import OfflineFetcher
from tipster.services.scan import ScanResult, ScanService
from tipster.storage.db import MEMORY, connect
from tipster.storage.sqlite import (
    SqliteEventRepository,
    SqliteOddsRepository,
    SqlitePickRepository,
    SqliteResponseCache,
    SqliteRunRepository,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "the_odds_api" / "sintetico"
CAPTURED = datetime(2026, 10, 21, 18, 0, tzinfo=UTC)
KEY = "clave-de-prueba-scan"


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    connection = connect(MEMORY)
    yield connection
    connection.close()


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "competitions": ("laliga", "premier", "segunda"),
        "ODDS_API_KEY": KEY,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def _service(
    conn: sqlite3.Connection,
    provider: object,
    settings: Settings,
    now: datetime = CAPTURED,
) -> ScanService:
    def clock() -> datetime:
        return now

    return ScanService(
        provider=provider,  # type: ignore[arg-type]
        events=SqliteEventRepository(conn, clock),
        odds=SqliteOddsRepository(conn),
        picks=SqlitePickRepository(conn),
        runs=SqliteRunRepository(conn, clock),
        settings=settings,
        clock=clock,
    )


def _offline_scan(conn: sqlite3.Connection) -> ScanResult:
    provider = TheOddsApiProvider(OfflineFetcher(FIXTURES))
    return _service(conn, provider, _settings()).run()


def _pick_summary(result: ScanResult) -> set[tuple[str, str, str, str, str]]:
    return {
        (
            p.opportunity.event.home_team,
            p.opportunity.quote.bookmaker_id,
            p.opportunity.quote.selection,
            p.opportunity.label.name,
            p.opportunity.reference_bookmaker_id,
        )
        for p in result.picks
    }


def test_scan_offline_produce_los_picks_calculados_a_mano(conn: sqlite3.Connection) -> None:
    result = _offline_scan(conn)
    assert _pick_summary(result) == {
        ("Local Prueba FC", "888sport_no_es", "local", "VALUE", "pinnacle"),
        ("Local Prueba FC", "williamhill_no_es", "local", "POSIBLE_ERROR", "pinnacle"),
        ("Local Prueba FC", "winamax_fr", "mas", "VALUE", "pinnacle"),
        ("Ciudad Ficticia CF", "888sport_no_es", "local", "VALUE", "betfair_ex_no_es"),
    }
    evs = {
        (p.opportunity.quote.bookmaker_id, p.opportunity.quote.selection): p for p in result.picks
    }
    assert evs[("888sport_no_es", "local")].opportunity.ev == pytest.approx(9 / 145, abs=1e-9)
    assert all(not p.opportunity.feed_es for p in result.picks)
    assert result.status == "ok"


def test_descartes_y_competiciones_saltadas(conn: sqlite3.Connection) -> None:
    result = _offline_scan(conn)
    assert result.discards["cuota antigua"] == 3  # Marathonbet: 3 selecciones de hace 15 min
    assert result.discards["sin referencia válida"] == 3  # Premier: Pinnacle y Betfair antiguas
    by_id = {c.competition_id: c for c in result.competitions}
    assert by_id["laliga"].status == "ok"
    assert by_id["segunda"].status == "saltada"
    assert "soccer_spain_segunda_division" in (by_id["segunda"].detail or "")
    assert any("casa_desconocida" in w for w in result.warnings)


def test_picks_guardados_con_cuotas_de_referencia_reproducibles(conn: sqlite3.Connection) -> None:
    result = _offline_scan(conn)
    rows = conn.execute("SELECT * FROM picks").fetchall()
    assert len(rows) == 4
    for row in rows:
        odds = json.loads(row["reference_odds_json"])
        quote = conn.execute(
            "SELECT * FROM odds_quotes WHERE id = ?", (row["quote_id"],)
        ).fetchone()
        market = get_market(quote["market_id"])
        assert [s for s, _ in odds] == list(market.selections)
        p = devig([price for _, price in odds], result.devig_method)
        assert p[market.selections.index(quote["selection"])] == pytest.approx(row["p_market"])


def test_cuotas_guardadas_con_hora_y_origen_y_sin_clave(conn: sqlite3.Connection) -> None:
    _offline_scan(conn)
    origins = conn.execute("SELECT DISTINCT source, captured_at FROM odds_quotes").fetchall()
    assert [tuple(r) for r in origins] == [("the_odds_api:offline", CAPTURED.isoformat())]
    settings_json = conn.execute("SELECT settings_json FROM runs").fetchone()[0]
    assert KEY not in settings_json
    assert conn.execute("SELECT status FROM runs").fetchone()[0] == "ok"


class _FailingProvider:
    name = "the_odds_api"

    def __init__(self, error: Exception, fail_on: str) -> None:
        self._error = error
        self._fail_on = fail_on
        self._inner = TheOddsApiProvider(OfflineFetcher(FIXTURES))

    def list_competitions(self) -> CompetitionListing:
        listing = self._inner.list_competitions()
        extra = ProviderCompetition(provider_key="soccer_italy_serie_a", title="x", active=True)
        return listing.model_copy(update={"competitions": [*listing.competitions, extra]})

    def fetch_odds(self, request: OddsRequest) -> OddsBatch:
        if request.competition_id == self._fail_on:
            raise self._error
        return self._inner.fetch_odds(request)


def test_presupuesto_agotado_para_y_conserva_lo_leido(conn: sqlite3.Connection) -> None:
    provider = _FailingProvider(BudgetExceededError("sin presupuesto"), fail_on="premier")
    result = _service(conn, provider, _settings(competitions=("laliga", "premier"))).run()
    assert result.status == "parcial"
    assert result.aborted is not None
    assert "presupuesto" in result.aborted
    assert len(result.picks) == 4  # los de LaLiga, leídos antes de cortar


def test_credenciales_rechazadas_abortan_con_error(conn: sqlite3.Connection) -> None:
    provider = _FailingProvider(ProviderAuthError("401"), fail_on="laliga")
    result = _service(conn, provider, _settings(competitions=("laliga", "premier"))).run()
    assert result.status == "error"
    assert result.picks == []
    assert conn.execute("SELECT status FROM runs").fetchone()[0] == "error"


def test_segundo_scan_dentro_del_ttl_no_gasta_creditos(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    calls: list[httpx.Request] = []
    files = {
        "/v4/sports": FIXTURES / "sports.json",
        "/v4/sports/soccer_spain_la_liga/odds": FIXTURES / "odds_soccer_spain_la_liga.json",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        cost = "0" if request.url.path == "/v4/sports" else "2"
        headers = {"x-requests-last": cost, "x-requests-remaining": "480", "x-requests-used": "20"}
        return httpx.Response(200, content=files[request.url.path].read_bytes(), headers=headers)

    def scan(now: datetime) -> ScanResult:
        http = HttpClient(
            provider="the_odds_api",
            base_url="https://api.the-odds-api.com",
            secret_params={"apiKey": KEY},
            policy=HttpPolicy(min_interval_s=0),
            budget=CreditBudget(30),
            cache=SqliteResponseCache(conn),
            cache_ttl=timedelta(seconds=60),
            raw_dir=tmp_path,
            clock=lambda: now,
            transport=httpx.MockTransport(handler),
        )
        return _service(
            conn, TheOddsApiProvider(http), _settings(competitions=("laliga",)), now
        ).run()

    first = scan(CAPTURED)
    second = scan(CAPTURED + timedelta(seconds=30))
    assert first.credits_spent == 2
    assert second.credits_spent == 0
    assert second.cache_hits == 2
    assert len(calls) == 2  # /sports y /odds solo en la primera ejecución
    assert _pick_summary(second) == _pick_summary(first)
    raw_files = list(tmp_path.rglob("*.json"))
    assert raw_files
    assert all(KEY not in f.read_text(encoding="utf-8") for f in raw_files)

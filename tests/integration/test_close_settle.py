"""`tipster close` y `tipster settle` con proveedores simulados. Nunca tocan la red.

La frescura real de Pinnacle en la última media hora es NO VERIFICADO: aquí solo se comprueba que
el sistema marca como no fiable un cierre antiguo y nunca inventa una cuota.
"""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.factories import make_quote
from tests.integration.test_tracking import _make_pick
from tipster.config import Settings
from tipster.domain.models import OddsQuote
from tipster.providers.base import MatchScore, OddsBatch, OddsRequest, RequestRecord, ScoreBatch
from tipster.services.close import CloseService
from tipster.services.settle import SettleService
from tipster.storage.db import connect
from tipster.storage.sqlite import SqliteRunRepository
from tipster.storage.tracking import SqliteBankrollRepository, SqliteTrackingRepository

NOW = datetime(2026, 11, 7, 14, 50, tzinfo=UTC)


def clock() -> datetime:
    return NOW


def _record(endpoint: str = "/v4/sports/soccer_spain_la_liga/odds") -> RequestRecord:
    return RequestRecord(
        provider="the_odds_api", endpoint=endpoint, params_key="", http_status=200,
        from_cache=False, cost=1, credits_used=1, credits_remaining=499, requested_at=NOW,
        duration_ms=10, raw_path=None,
    )  # fmt: skip


class FakeOdds:
    name = "the_odds_api"

    def __init__(self, quotes: list[OddsQuote]) -> None:
        self.quotes = quotes
        self.requests: list[OddsRequest] = []

    def fetch_odds(self, request: OddsRequest) -> OddsBatch:
        self.requests.append(request)
        return OddsBatch(
            competition_id=request.competition_id, events=[], external_ids={},
            quotes=self.quotes, request=_record(), warnings=[],
        )  # fmt: skip

    def list_competitions(self):  # type: ignore[no-untyped-def]
        raise AssertionError("no se usa")


def _pinnacle(
    event_id: str,
    odds: tuple[float, ...],
    *,
    captured: datetime = NOW,
    last_update: datetime | None = None,
    market: str = "1x2",
) -> list[OddsQuote]:
    selections = ("local", "empate", "visitante") if market == "1x2" else ("mas", "menos")
    updated = last_update or captured - timedelta(seconds=40)
    return [
        make_quote(
            event_id=event_id,
            bookmaker_id="pinnacle",
            market_id=market,
            selection=s,
            price=p,
            captured_at=captured,
            last_update=updated,
        )
        for s, p in zip(selections, odds, strict=False)
    ]


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(tmp_path / "tipster.sqlite")
    yield connection
    connection.close()


def _open(conn: sqlite3.Connection, event_id: str, *, minutes_to_kickoff: float,
          stake: float | None = 20.0, price: float = 2.20, selection: str = "local",
          market_id: str = "1x2") -> int:  # fmt: skip
    pick_id, quote_id, run_id = _make_pick(
        conn, event_id, selection=selection, price=price, market_id=market_id
    )
    kickoff = NOW + timedelta(minutes=minutes_to_kickoff)
    conn.execute("UPDATE events SET kickoff_utc = ? WHERE id = ?", (kickoff.isoformat(), event_id))
    if stake is not None:
        SqliteTrackingRepository(conn).set_stakes(run_id, {quote_id: stake})
    return pick_id


def _close(conn: sqlite3.Connection, provider: FakeOdds, **settings: object):  # type: ignore[no-untyped-def]
    service = CloseService(
        provider=provider,
        tracking=SqliteTrackingRepository(conn),
        runs=SqliteRunRepository(conn, clock),
        settings=Settings(_env_file=None, **settings),  # type: ignore[arg-type]
        clock=clock,
    )
    return service.run()


# -- close -------------------------------------------------------------------------------------


def test_close_captura_el_cierre_y_calcula_el_clv_con_la_cuota_justa(
    conn: sqlite3.Connection,
) -> None:
    pick_id = _open(conn, "e1", minutes_to_kickoff=10)
    provider = FakeOdds(_pinnacle("e1", (1.80, 3.60, 3.60)))
    result = _close(conn, provider)
    assert result.captured == [pick_id]
    row = conn.execute("SELECT * FROM picks WHERE id = ?", (pick_id,)).fetchone()
    assert row["closing_odds"] == 1.80
    assert row["closing_fair_odds"] == pytest.approx(2.0)
    assert (row["closing_reliable"], row["clv"]) == (1, pytest.approx(0.10))  # 2,20 / 2,00 − 1
    # una petición por competición: solo Pinnacle y solo el mercado necesario
    assert [(r.competition_id, r.market_ids, r.bookmaker_ids) for r in provider.requests] == [
        ("laliga", ("1x2",), ("pinnacle",))
    ]


def test_close_ignora_lo_que_no_esta_en_la_ventana_sin_gastar_creditos(
    conn: sqlite3.Connection,
) -> None:
    _open(conn, "lejos", minutes_to_kickoff=40)  # ventana de 15 min
    _open(conn, "empezado", minutes_to_kickoff=-1)
    provider = FakeOdds(_pinnacle("lejos", (1.80, 3.60, 3.60)))
    result = _close(conn, provider)
    assert result.captured == [] and provider.requests == []


def test_close_salta_picks_sin_stake_o_con_cierre_ya_capturado(conn: sqlite3.Connection) -> None:
    _open(conn, "sin-stake", minutes_to_kickoff=10, stake=None)
    done = _open(conn, "hecho", minutes_to_kickoff=10)
    provider = FakeOdds(_pinnacle("hecho", (1.80, 3.60, 3.60)))
    assert _close(conn, provider).captured == [done]
    again = FakeOdds(_pinnacle("hecho", (1.50, 4.00, 6.00)))
    assert _close(conn, again).captured == [] and again.requests == []  # idempotente
    assert (
        conn.execute("SELECT closing_odds FROM picks WHERE id = ?", (done,)).fetchone()[0] == 1.80
    )


def test_el_last_update_no_decide_la_fiabilidad_si_se_captura_en_la_ventana(
    conn: sqlite3.Connection,
) -> None:
    pick_id = _open(conn, "e1", minutes_to_kickoff=10)
    old = _pinnacle("e1", (1.80, 3.60, 3.60), last_update=NOW - timedelta(minutes=45))
    result = _close(conn, FakeOdds(old))
    assert result.captured == [pick_id] and not result.unreliable
    row = conn.execute(
        "SELECT closing_reliable, closing_odds, clv IS NOT NULL FROM picks"
    ).fetchone()
    assert tuple(row) == (1, 1.80, 1)  # se guarda el last_update, pero no cambia nada


def test_una_captura_fuera_de_la_ventana_previa_al_inicio_no_es_fiable(
    conn: sqlite3.Connection,
) -> None:
    pick_id = _open(conn, "e1", minutes_to_kickoff=10)
    early = _pinnacle("e1", (1.80, 3.60, 3.60), captured=NOW - timedelta(minutes=10))  # KO − 20
    result = _close(conn, FakeOdds(early))
    assert result.unreliable == [pick_id]
    row = conn.execute("SELECT closing_reliable, clv, closing_odds FROM picks").fetchone()
    assert tuple(row) == (0, None, 1.80)  # la cuota queda registrada, el CLV no se calcula
    assert SqliteTrackingRepository(conn).clv_values() == []


def test_una_captura_posterior_al_inicio_no_es_fiable(conn: sqlite3.Connection) -> None:
    pick_id = _open(conn, "e1", minutes_to_kickoff=10)
    late = _pinnacle("e1", (1.80, 3.60, 3.60), captured=NOW + timedelta(minutes=11))  # KO + 1
    result = _close(conn, FakeOdds(late))
    assert result.unreliable == [pick_id]


def test_sin_cuota_de_pinnacle_no_se_inventa_nada(conn: sqlite3.Connection) -> None:
    _open(conn, "e1", minutes_to_kickoff=10)
    result = _close(conn, FakeOdds([]))
    assert result.captured == [] and len(result.missing) == 1
    assert conn.execute("SELECT closing_odds, clv FROM picks").fetchone()[0] is None


def test_close_con_over_under(conn: sqlite3.Connection) -> None:
    pick_id = _open(
        conn, "e1", minutes_to_kickoff=5, selection="mas", price=2.05, market_id="ou_2.5"
    )
    provider = FakeOdds(_pinnacle("e1", (1.90, 2.00), market="ou_2.5"))
    assert _close(conn, provider).captured == [pick_id]
    assert provider.requests[0].market_ids == ("ou_2.5",)


# -- settle ------------------------------------------------------------------------------------


class FakeScores:
    name = "the_odds_api"

    def __init__(self, scores: list[MatchScore]) -> None:
        self.scores = scores
        self.calls: list[tuple[str, int]] = []

    def fetch_scores(self, competition_id: str, days_from: int) -> ScoreBatch:
        self.calls.append((competition_id, days_from))
        return ScoreBatch(self.scores, _record("/v4/sports/x/scores"))


def _settle(conn: sqlite3.Connection, scores: FakeScores | None, manual=None):  # type: ignore[no-untyped-def]
    bank = SqliteBankrollRepository(conn, clock)
    bank.ensure_initial(1000.0)
    service = SettleService(
        provider=scores, tracking=SqliteTrackingRepository(conn), bankroll=bank,
        runs=SqliteRunRepository(conn, clock), clock=clock,
    )  # fmt: skip
    return service.run(manual or {}), bank


def test_settle_liquida_con_los_resultados_del_proveedor_y_actualiza_el_bankroll(
    conn: sqlite3.Connection,
) -> None:
    won = _open(conn, "e1", minutes_to_kickoff=-180)
    lost = _open(conn, "e2", minutes_to_kickoff=-200)
    scores = FakeScores([MatchScore("xe1", True, 2, 1), MatchScore("xe2", True, 0, 0)])
    result, bank = _settle(conn, scores)
    assert sorted(s.pick_id for s in result.settled) == sorted([won, lost])
    rows = {r["id"]: r for r in conn.execute("SELECT * FROM picks")}
    assert (rows[won]["status"], rows[won]["profit"], rows[won]["result"]) == (
        "ganado",
        pytest.approx(24.0),
        "local",
    )
    assert (rows[lost]["status"], rows[lost]["profit"]) == ("perdido", -20.0)
    assert bank.balance() == 1004.0
    assert scores.calls == [("laliga", 1)]


def test_settle_no_toca_lo_que_no_ha_terminado_ni_lo_que_aun_no_ha_pasado(
    conn: sqlite3.Connection,
) -> None:
    _open(conn, "pendiente", minutes_to_kickoff=-180)
    _open(conn, "futuro", minutes_to_kickoff=600)
    scores = FakeScores([MatchScore("xpendiente", False, None, None)])
    result, bank = _settle(conn, scores)
    assert result.settled == [] and len(result.pending) == 1
    assert bank.balance() == 1000.0


def test_settle_es_idempotente(conn: sqlite3.Connection) -> None:
    _open(conn, "e1", minutes_to_kickoff=-180)
    scores = FakeScores([MatchScore("xe1", True, 2, 1)])
    _settle(conn, scores)
    result, bank = _settle(conn, scores)
    assert result.settled == []
    assert bank.balance() == 1024.0
    assert conn.execute("SELECT COUNT(*) FROM bankroll_entries").fetchone()[0] == 2


def test_settle_manual_funciona_sin_proveedor(conn: sqlite3.Connection) -> None:
    pick_id = _open(conn, "e1", minutes_to_kickoff=-30)  # aún dentro de las 2 h: solo manual
    result, bank = _settle(conn, None, manual={"e1": (1, 3)})
    assert [s.pick_id for s in result.settled] == [pick_id]
    assert conn.execute("SELECT status, result FROM picks").fetchone()[:] == (
        "perdido",
        "visitante",
    )
    assert bank.balance() == 980.0


def test_un_pick_sin_stake_se_liquida_sin_mover_el_bankroll(conn: sqlite3.Connection) -> None:
    _open(conn, "e1", minutes_to_kickoff=-180, stake=None)
    result, bank = _settle(conn, FakeScores([MatchScore("xe1", True, 2, 1)]))
    assert len(result.settled) == 1
    assert conn.execute("SELECT status, profit FROM picks").fetchone()[:] == ("ganado", None)
    assert (
        bank.balance() == 1000.0
        and conn.execute("SELECT COUNT(*) FROM bankroll_entries").fetchone()[0] == 1
    )

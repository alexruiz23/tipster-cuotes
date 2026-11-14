"""Reglas del ADR 014: devig Shin por defecto, nivel principal e improbable, y horizonte de días."""

import sqlite3
from collections.abc import Iterator
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.factories import NOW, make_opportunity, make_quote
from tests.integration.test_scan_service import FIXTURES, KEY, _service
from tests.integration.test_tracking import _make_pick
from tipster.config import Settings
from tipster.domain.models import Opportunity, Pick
from tipster.pricing.devig import DevigMethod, devig
from tipster.providers.the_odds_api.client import TheOddsApiProvider
from tipster.providers.the_odds_api.offline import OfflineFetcher
from tipster.services.scan import NO_LONGSHOT_ROOM, ONE_PER_EVENT, ScanService
from tipster.services.status import paper_status, status_lines
from tipster.storage.db import MEMORY, connect
from tipster.storage.tracking import SqliteTrackingRepository


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    connection = connect(MEMORY)
    yield connection
    connection.close()


def _svc(conn: sqlite3.Connection, **overrides: object) -> ScanService:
    settings = Settings(_env_file=None, ODDS_API_KEY=KEY, **overrides)  # type: ignore[arg-type]
    return _service(conn, TheOddsApiProvider(OfflineFetcher(FIXTURES)), settings, now=NOW)


def _opp(price: float, ev: float, event_id: str = "e1", days: float = 2) -> Opportunity:
    base = make_opportunity(quote=make_quote(event_id=event_id, price=price))
    event = base.event.model_copy(update={"kickoff": NOW + timedelta(days=days)})
    return base.model_copy(update={"ev": ev, "event": event})


def _why(service: ScanService, o: Opportunity) -> str | None:
    return service._blocked(o, loss_hit=False, open_events={}, now=NOW)


def test_el_devig_por_defecto_es_shin_y_da_menos_probabilidad_a_la_cuota_larga() -> None:
    assert Settings(_env_file=None).devig_method is DevigMethod.SHIN
    odds = (1.30, 5.60, 10.50)
    shin, mult = devig(odds, DevigMethod.SHIN), devig(odds, DevigMethod.MULTIPLICATIVE)
    assert sum(shin) == pytest.approx(1.0)
    assert shin[2] < mult[2] and shin[0] > mult[0]  # quita más margen a la improbable


def test_shin_tambien_vale_para_mercados_de_dos_resultados() -> None:
    p = devig((1.90, 2.00), DevigMethod.SHIN)
    assert sum(p) == pytest.approx(1.0) and all(0 < x < 1 for x in p)


def test_nivel_principal_basta_el_ev_minimo_general(conn: sqlite3.Connection) -> None:
    service = _svc(conn)
    assert _why(service, _opp(3.5, 0.031)) is None
    assert _why(service, _opp(4.0, 0.031)) is None  # 4,0 exacto sigue siendo principal


def test_nivel_improbable_exige_ev_del_6_por_ciento(conn: sqlite3.Connection) -> None:
    service = _svc(conn)
    reason = _why(service, _opp(5.0, 0.045))
    assert reason == "cuota 5 improbable (> 4): exige EV de 6% y tiene 4.5%"
    assert _why(service, _opp(5.0, 0.061)) is None
    assert "max_odds 8" in (_why(service, _opp(9.0, 0.20)) or "")  # el tope sigue mandando


def test_un_partido_a_mas_de_4_dias_no_lleva_stake(conn: sqlite3.Connection) -> None:
    service = _svc(conn)
    far = _why(service, _opp(2.2, 0.05, days=4.5))
    assert far is not None and "más de 4 días" in far
    assert _why(service, _opp(2.2, 0.05, days=3.9)) is None
    assert _why(_svc(conn, max_days_ahead=10), _opp(2.2, 0.05, days=4.5)) is None


def _select(service: ScanService, opps: list[Opportunity]):  # type: ignore[no-untyped-def]
    picks = [Pick(quote_id=i + 1, opportunity=o, created_at=NOW) for i, o in enumerate(opps)]
    return picks, service._select(picks, False, {}, NOW)


def test_solo_caben_dos_improbables_y_entran_los_de_mas_ev(conn: sqlite3.Connection) -> None:
    opps = [
        _opp(5.0, 0.07, "a"),
        _opp(6.0, 0.12, "b"),
        _opp(7.0, 0.09, "c"),
        _opp(2.5, 0.04, "d"),  # principal: no consume hueco
    ]
    picks, (blocked, best, no_slot) = _select(_svc(conn), opps)
    assert all(v is None for v in blocked.values()) and len(best) == 4
    assert no_slot == {picks[0].quote_id}  # el de menos EV de los tres improbables


def test_los_improbables_ya_abiertos_consumen_hueco(conn: sqlite3.Connection) -> None:
    track = SqliteTrackingRepository(conn)
    _, q1, r1 = _make_pick(conn, "x1", price=6.0)
    track.set_stakes(r1, {q1: 1.0})
    _, q2, r2 = _make_pick(conn, "x2", price=2.0)  # principal abierto: no cuenta
    track.set_stakes(r2, {q2: 1.0})
    _make_pick(conn, "x3", price=7.0)  # sin stake: no cuenta
    assert track.open_longshots(4.0) == 1
    picks, (_, _, no_slot) = _select(_svc(conn), [_opp(5.0, 0.07, "a"), _opp(6.0, 0.12, "b")])
    assert no_slot == {picks[0].quote_id}
    _, (_, _, none_left) = _select(_svc(conn, max_open_longshots=0), [_opp(5.0, 0.07, "a")])
    assert len(none_left) == 1


def test_un_pick_bloqueado_no_compite_con_otro_de_su_partido(conn: sqlite3.Connection) -> None:
    # mismo partido: improbable con más EV pero sin llegar al 6 % y principal válido
    opps = [_opp(5.0, 0.055, "a"), _opp(2.5, 0.035, "a")]
    picks, (blocked, best, _) = _select(_svc(conn), opps)
    assert blocked[picks[0].quote_id] is not None and best["a"] is picks[1]
    assert ONE_PER_EVENT and NO_LONGSHOT_ROOM  # motivos que se muestran al usuario


def test_status_desglosa_el_clv_por_nivel_y_por_casa(conn: sqlite3.Connection) -> None:
    track = SqliteTrackingRepository(conn)
    for event, price, clv in (("a", 2.0, 0.02), ("b", 3.0, 0.04), ("c", 6.0, -0.10)):
        pick_id, quote_id, run_id = _make_pick(conn, event, price=price)
        track.set_stakes(run_id, {quote_id: 1.0})
        conn.execute("UPDATE picks SET closing_reliable = 1, clv = ? WHERE id = ?", (clv, pick_id))
    groups = track.clv_breakdown(4.0)
    assert [(name, n) for name, n, _ in groups["nivel"]] == [("principal", 2), ("improbable", 1)]
    assert [mean for _, _, mean in groups["nivel"]] == pytest.approx([0.03, -0.10])
    assert sum(n for _, n, _ in groups["casa"]) == 3
    text = "\n".join(status_lines(paper_status(conn, NOW), ZoneInfo("Europe/Madrid")))
    assert "CLV por nivel: principal +3.0 % (2) · improbable -10.0 % (1)" in text
    assert "CLV por casa:" in text


def test_sin_cierres_status_no_muestra_desgloses(conn: sqlite3.Connection) -> None:
    text = "\n".join(status_lines(paper_status(conn, NOW), ZoneInfo("Europe/Madrid")))
    assert "CLV por nivel" not in text and "CLV por casa" not in text

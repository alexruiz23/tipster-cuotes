"""Proveedor The Odds API con fixtures sintéticas (estructura NO VERIFICADA hasta R3)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from tipster.errors import ConfigError, ProviderResponseError, ProviderUnavailableError
from tipster.providers.base import OddsRequest
from tipster.providers.budget import CreditBudget
from tipster.providers.http import HttpClient, HttpPolicy
from tipster.providers.the_odds_api.client import TheOddsApiProvider, estimate_odds_cost
from tipster.providers.the_odds_api.offline import OfflineFetcher

FIXTURES = Path(__file__).parent.parent / "fixtures" / "the_odds_api" / "sintetico"
CAPTURED = datetime(2026, 10, 21, 18, 0, tzinfo=UTC)
BOOKMAKERS = (
    "pinnacle",
    "betfair_ex_no_es",
    "888sport_no_es",
    "williamhill_no_es",
    "marathonbet_no_es",
    "winamax_fr",
)
REQUEST = OddsRequest("laliga", ("1x2", "ou_2.5"), BOOKMAKERS)


def _offline() -> TheOddsApiProvider:
    return TheOddsApiProvider(OfflineFetcher(FIXTURES))


def _by(quotes: list, **match: object) -> list:  # type: ignore[type-arg]
    return [q for q in quotes if all(getattr(q, k) == v for k, v in match.items())]


def test_mapea_1x2_por_nombre_de_equipo() -> None:
    batch = _offline().fetch_odds(REQUEST)
    assert [e.name for e in batch.events] == [
        "Local Prueba FC – Visitante Prueba CF",
        "Ciudad Ficticia CF – Atlético Inventado",
    ]
    event = batch.events[0]
    q888 = {
        q.selection: q.price
        for q in _by(batch.quotes, event_id=event.id, bookmaker_id="888sport_no_es")
    }
    assert q888 == {"local": 2.2, "empate": 3.4, "visitante": 3.9}
    assert event.kickoff == datetime(2026, 10, 25, 19, 0, tzinfo=UTC)


def test_totales_solo_con_linea_2_5() -> None:
    batch = _offline().fetch_odds(REQUEST)
    winamax = _by(batch.quotes, bookmaker_id="winamax_fr", market_id="ou_2.5")
    assert {q.selection: q.price for q in winamax} == {"mas": 2.05, "menos": 1.8}
    assert any("2.25" in w for w in batch.warnings)


def test_casa_desconocida_se_ignora_con_aviso() -> None:
    batch = _offline().fetch_odds(REQUEST)
    assert not _by(batch.quotes, bookmaker_id="casa_desconocida")
    assert any("casa_desconocida" in w for w in batch.warnings)


def test_origen_hora_de_captura_y_last_update() -> None:
    batch = _offline().fetch_odds(REQUEST)
    assert {q.source for q in batch.quotes} == {"the_odds_api:offline"}
    assert {q.captured_at for q in batch.quotes} == {CAPTURED}
    # El mercado de totales de Winamax no trae last_update: se usa el de la casa.
    winamax = _by(batch.quotes, bookmaker_id="winamax_fr")[0]
    assert winamax.provider_last_update == datetime(2026, 10, 21, 17, 58, 30, tzinfo=UTC)
    assert batch.request.from_cache is False
    assert batch.request.cost == 0


def test_ids_de_evento_estables() -> None:
    first = _offline().fetch_odds(REQUEST).events
    second = _offline().fetch_odds(REQUEST).events
    assert [e.id for e in first] == [e.id for e in second]
    assert len({e.id for e in first}) == 2


def test_competiciones_listadas() -> None:
    listing = _offline().list_competitions()
    assert {c.provider_key for c in listing.competitions} == {"soccer_spain_la_liga", "soccer_epl"}
    assert all(c.active for c in listing.competitions)


def test_offline_sin_respuesta_grabada() -> None:
    with pytest.raises(ProviderUnavailableError):
        _offline().fetch_odds(OddsRequest("segunda", ("1x2",), BOOKMAKERS))


def test_offline_exige_manifiesto(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        OfflineFetcher(tmp_path)


@pytest.mark.parametrize(
    ("markets", "bookmakers", "cost"), [(2, 8, 2), (2, 10, 2), (2, 11, 4), (1, 21, 3)]
)
def test_estimacion_de_coste(markets: int, bookmakers: int, cost: int) -> None:
    # Coste = mercados × grupos de 10 casas (nivel B).
    assert estimate_odds_cost(markets, bookmakers) == cost


def _live(tmp_path: Path, body: bytes, seen: list[httpx.Request]) -> TheOddsApiProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        headers = {"x-requests-last": "2", "x-requests-remaining": "498", "x-requests-used": "2"}
        return httpx.Response(200, content=body, headers=headers)

    http = HttpClient(
        provider="the_odds_api",
        base_url="https://api.the-odds-api.com",
        secret_params={"apiKey": "k"},
        policy=HttpPolicy(min_interval_s=0),
        budget=CreditBudget(30),
        cache=None,
        cache_ttl=timedelta(0),
        raw_dir=tmp_path,
        clock=lambda: CAPTURED,
        transport=httpx.MockTransport(handler),
    )
    return TheOddsApiProvider(http)


def test_peticion_en_vivo_parametros_y_coste(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    body = (FIXTURES / "odds_soccer_spain_la_liga.json").read_bytes()
    batch = _live(tmp_path, body, seen).fetch_odds(REQUEST)
    url = seen[0].url
    assert url.path == "/v4/sports/soccer_spain_la_liga/odds"
    assert url.params["markets"] == "h2h,totals"
    assert url.params["bookmakers"] == (
        "betfair_ex_eu,marathonbet,pinnacle,sport888,williamhill,winamax_fr"
    )
    assert (url.params["oddsFormat"], url.params["dateFormat"]) == ("decimal", "iso")
    assert batch.request.cost == 2
    assert {q.source for q in batch.quotes} == {"the_odds_api"}


def test_esquema_invalido_lanza_error(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    with pytest.raises(ProviderResponseError) as excinfo:
        _live(tmp_path, json.dumps([{"id": 1}]).encode(), seen).fetch_odds(REQUEST)
    assert excinfo.value.record is not None

"""Formato de la respuesta de The Odds API y su parseo (criterio R3).

Corre siempre con la fixture sintética. Con la fixture REAL grabada en R1 (`real/`, solo en local
y fuera de git por los términos del proveedor) corre además, y se omite si la carpeta no existe.
Comprueban la estructura y que el proveedor la parsea, no las cuotas concretas.
"""

import json
from pathlib import Path

import pytest

from tipster.domain.bookmakers import BOOKMAKERS
from tipster.providers.base import OddsRequest
from tipster.providers.the_odds_api.client import TheOddsApiProvider
from tipster.providers.the_odds_api.offline import OfflineFetcher

BASE = Path(__file__).parent.parent / "fixtures" / "the_odds_api"
DIRECTORIOS = [
    "sintetico",
    pytest.param(
        "real",
        marks=pytest.mark.skipif(
            not (BASE / "real").is_dir(), reason="fixture real solo en local (fuera de git)"
        ),
    ),
]
COMPETICIONES = {"laliga": "soccer_spain_la_liga", "premier": "soccer_epl"}


@pytest.mark.parametrize("directorio", DIRECTORIOS)
@pytest.mark.parametrize("sport_key", COMPETICIONES.values())
def test_estructura_de_la_respuesta(directorio: str, sport_key: str) -> None:
    events = json.loads((BASE / directorio / f"odds_{sport_key}.json").read_text(encoding="utf-8"))
    assert isinstance(events, list) and events
    for event in events:
        assert {"id", "sport_key", "commence_time", "home_team", "away_team", "bookmakers"} <= set(
            event
        )
        assert event["sport_key"] == sport_key
        for bookmaker in event["bookmakers"]:
            assert {"key", "title", "last_update", "markets"} <= set(bookmaker)
            for market in bookmaker["markets"]:
                assert {"key", "outcomes"} <= set(market)
                if directorio == "real":  # la sintética omite last_update a propósito
                    assert "last_update" in market
                assert market["key"] in {"h2h", "h2h_lay", "totals"}
                for outcome in market["outcomes"]:
                    assert {"name", "price"} <= set(outcome)
                    assert ("point" in outcome) == (market["key"] == "totals")


@pytest.mark.parametrize("directorio", DIRECTORIOS)
@pytest.mark.parametrize("competition", COMPETICIONES)
def test_el_proveedor_parsea_la_fixture(directorio: str, competition: str) -> None:
    fetcher = OfflineFetcher(BASE / directorio)
    batch = TheOddsApiProvider(fetcher).fetch_odds(
        OddsRequest(competition, ("1x2", "ou_2.5"), tuple(BOOKMAKERS))
    )
    assert batch.events
    assert batch.quotes
    assert {q.market_id for q in batch.quotes} <= {"1x2", "ou_2.5"}
    assert {q.bookmaker_id for q in batch.quotes} <= set(BOOKMAKERS)
    assert all(q.price > 1 for q in batch.quotes)
    assert all(q.captured_at == fetcher.captured_at for q in batch.quotes)
    # h2h_lay (precios de lay del exchange) no se confunde con h2h
    assert not any("h2h_lay" in w for w in batch.warnings)

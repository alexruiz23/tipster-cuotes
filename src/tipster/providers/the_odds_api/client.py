"""Proveedor The Odds API v4 detrás del protocolo OddsProvider (ADR 001)."""

import math

from pydantic import ValidationError

from tipster.domain.bookmakers import get_bookmaker
from tipster.domain.competitions import THE_ODDS_API, get_competition
from tipster.errors import ProviderResponseError
from tipster.providers.base import (
    CompetitionListing,
    OddsBatch,
    OddsRequest,
    ProviderCompetition,
)
from tipster.providers.http import JsonFetcher
from tipster.providers.the_odds_api.mapping import MARKETS, MappedBatch, map_events
from tipster.providers.the_odds_api.schemas import EVENTS, SPORTS

BASE_URL = "https://api.the-odds-api.com"  # documentación v4 [B]
SPORTS_ENDPOINT = "/v4/sports"  # gratis, no gasta créditos [B]


def estimate_odds_cost(markets: int, bookmakers: int) -> int:
    """Coste de /odds: mercados × grupos de 10 casas (documentación, nivel B)."""
    return markets * math.ceil(bookmakers / 10)


class TheOddsApiProvider:
    name = THE_ODDS_API

    def __init__(self, fetcher: JsonFetcher) -> None:
        self._fetcher = fetcher

    def list_competitions(self) -> CompetitionListing:
        result = self._fetcher.get_json(SPORTS_ENDPOINT, {}, estimated_cost=0)
        try:
            sports = SPORTS.validate_python(result.data)
        except ValidationError as exc:
            raise ProviderResponseError(
                f"{self.name}: respuesta de /v4/sports con formato inesperado", result.record
            ) from exc
        return CompetitionListing(
            competitions=[
                ProviderCompetition(provider_key=s.key, title=s.title, active=s.active)
                for s in sports
            ],
            request=result.record,
        )

    def fetch_odds(self, request: OddsRequest) -> OddsBatch:
        sport_key = get_competition(request.competition_id).provider_keys[self.name]
        bookmaker_keys = sorted(
            get_bookmaker(b).provider_keys[self.name] for b in request.bookmaker_ids
        )
        market_keys = [MARKETS[m].provider_key for m in request.market_ids]
        params = {
            "bookmakers": ",".join(bookmaker_keys),  # tiene prioridad sobre regions [B]
            "markets": ",".join(dict.fromkeys(market_keys)),
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }
        result = self._fetcher.get_json(
            f"/v4/sports/{sport_key}/odds",
            params,
            estimated_cost=estimate_odds_cost(len(set(market_keys)), len(bookmaker_keys)),
        )
        try:
            events = EVENTS.validate_python(result.data)
        except ValidationError as exc:
            raise ProviderResponseError(
                f"{self.name}: respuesta de cuotas con formato inesperado", result.record
            ) from exc
        mapped: MappedBatch = map_events(
            events,
            competition_id=request.competition_id,
            market_ids=request.market_ids,
            captured_at=result.captured_at,
            source=self._fetcher.source,
        )
        return OddsBatch(
            competition_id=request.competition_id,
            events=mapped.events,
            external_ids=mapped.external_ids,
            quotes=mapped.quotes,
            request=result.record,
            warnings=mapped.warnings,
        )

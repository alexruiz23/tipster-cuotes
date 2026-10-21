"""Traducción del JSON de The Odds API a modelos canónicos.

Cada mercado canónico se describe con su clave en el proveedor, su línea y una función que
resuelve la selección; el flujo no tiene `if/else` por mercado (ADR 005).
"""

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from tipster.domain.bookmakers import find_by_provider_key
from tipster.domain.competitions import THE_ODDS_API
from tipster.domain.models import Event, OddsQuote
from tipster.domain.sports import SportId
from tipster.providers.the_odds_api.schemas import TOAEvent, TOAOutcome

LINE_TOL = 1e-9
_EVENT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/alexruiz23/tipster-cuotes")


@dataclass(frozen=True)
class MarketMapping:
    provider_key: str
    line: float | None
    resolve: Callable[[TOAOutcome, TOAEvent], str | None]  # selección canónica o None


def _h2h(outcome: TOAOutcome, event: TOAEvent) -> str | None:
    names = {event.home_team: "local", event.away_team: "visitante", "Draw": "empate"}
    return names.get(outcome.name)


def _totals(outcome: TOAOutcome, event: TOAEvent) -> str | None:
    return {"Over": "mas", "Under": "menos"}.get(outcome.name)


MARKETS: Mapping[str, MarketMapping] = MappingProxyType(
    {
        "1x2": MarketMapping("h2h", None, _h2h),
        "ou_2.5": MarketMapping("totals", 2.5, _totals),
    }
)


def event_id(external_id: str) -> str:
    """Id canónico estable a partir del id del proveedor."""
    return str(uuid.uuid5(_EVENT_NAMESPACE, f"{THE_ODDS_API}:{external_id}"))


@dataclass(frozen=True)
class MappedBatch:
    events: list[Event]
    external_ids: dict[str, str]  # id canónico → id del proveedor
    quotes: list[OddsQuote]
    warnings: list[str]


def map_events(
    events: Sequence[TOAEvent],
    *,
    competition_id: str,
    market_ids: Sequence[str],
    captured_at: datetime,
    source: str,
) -> MappedBatch:
    wanted = [(market_id, MARKETS[market_id]) for market_id in market_ids]
    warnings: dict[str, None] = {}  # ordenado y sin duplicados
    mapped_events: list[Event] = []
    external_ids: dict[str, str] = {}
    quotes: list[OddsQuote] = []

    for raw in events:
        event = Event(
            id=event_id(raw.id),
            sport=SportId.FOOTBALL,
            competition_id=competition_id,
            home_team=raw.home_team,
            away_team=raw.away_team,
            kickoff=raw.commence_time,
        )
        mapped_events.append(event)
        external_ids[event.id] = raw.id

        for bookmaker in raw.bookmakers:
            spec = find_by_provider_key(THE_ODDS_API, bookmaker.key)
            if spec is None:
                warnings[f"casa desconocida ignorada: {bookmaker.key}"] = None
                continue
            for market in bookmaker.markets:
                for market_id, mapping in wanted:
                    if market.key != mapping.provider_key:
                        continue
                    last_update = market.last_update or bookmaker.last_update
                    if last_update is None:
                        warnings[f"{bookmaker.key} {market.key}: sin last_update"] = None
                    seen: set[str] = set()
                    for outcome in market.outcomes:
                        if mapping.line is not None and (
                            outcome.point is None or abs(outcome.point - mapping.line) > LINE_TOL
                        ):
                            warnings[
                                f"{bookmaker.key} {market.key}: línea {outcome.point} ignorada "
                                f"(solo {mapping.line})"
                            ] = None
                            continue
                        selection = mapping.resolve(outcome, raw)
                        if selection is None or selection in seen:
                            warnings[
                                f"{bookmaker.key} {market.key}: selección no reconocida o "
                                f"repetida: {outcome.name}"
                            ] = None
                            continue
                        seen.add(selection)
                        quotes.append(
                            OddsQuote(
                                event_id=event.id,
                                bookmaker_id=spec.id,
                                market_id=market_id,
                                selection=selection,
                                price=outcome.price,
                                captured_at=captured_at,
                                provider_last_update=last_update,
                                source=source,
                            )
                        )
    return MappedBatch(mapped_events, external_ids, quotes, list(warnings))

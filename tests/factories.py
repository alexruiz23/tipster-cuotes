"""Objetos de prueba. Cuotas y equipos inventados para tests: no son datos reales."""

from datetime import UTC, datetime, timedelta

from tipster.domain.models import Event, OddsQuote, Opportunity
from tipster.domain.sports import SportId
from tipster.pricing.classify import Label
from tipster.pricing.devig import DevigMethod

NOW = datetime(2026, 10, 21, 18, 0, tzinfo=UTC)


def make_event(event_id: str = "e1", competition_id: str = "laliga") -> Event:
    return Event(
        id=event_id,
        sport=SportId.FOOTBALL,
        competition_id=competition_id,
        home_team="Local Prueba FC",
        away_team="Visitante Prueba CF",
        kickoff=NOW + timedelta(days=2),
    )


def make_quote(
    *,
    event_id: str = "e1",
    bookmaker_id: str = "888sport_no_es",
    market_id: str = "1x2",
    selection: str = "local",
    price: float = 2.20,
    captured_at: datetime = NOW,
    last_update: datetime | None = NOW - timedelta(minutes=2),
) -> OddsQuote:
    return OddsQuote(
        event_id=event_id,
        bookmaker_id=bookmaker_id,
        market_id=market_id,
        selection=selection,
        price=price,
        captured_at=captured_at,
        provider_last_update=last_update,
        source="the_odds_api",
    )


def make_opportunity(label: Label = Label.VALUE, quote: OddsQuote | None = None) -> Opportunity:
    quote = quote or make_quote()
    p = 14 / 29
    return Opportunity(
        event=make_event(quote.event_id),
        quote=quote,
        feed_es=False,
        reference_bookmaker_id="pinnacle",
        reference_captured_at=NOW,
        reference_odds=(("local", 2.00), ("empate", 3.50), ("visitante", 4.00)),
        devig_method=DevigMethod.MULTIPLICATIVE,
        p_market=p,
        p_final=p,
        fair_odds=1 / p,
        ev=p * quote.price - 1,
        label=label,
        reasons=("EV +6.21 %",),
    )

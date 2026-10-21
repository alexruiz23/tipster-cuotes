"""Elección de la referencia sharp y su probabilidad justa (D2, ADR 002).

Se recorren las casas de referencia en el orden configurado (por defecto Pinnacle y después
Betfair Exchange) y se usa la primera que tenga todas las selecciones del mercado, cuotas no
más antiguas que el máximo y un devig válido.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType

from tipster.domain.markets import MarketSpec
from tipster.domain.models import OddsQuote
from tipster.errors import DevigError
from tipster.pricing.classify import format_age
from tipster.pricing.devig import DevigMethod, devig


@dataclass(frozen=True)
class Reference:
    bookmaker_id: str
    captured_at: datetime  # la captura más reciente de las cuotas usadas
    odds: tuple[tuple[str, float], ...]  # (selección, cuota) en el orden del mercado
    probabilities: Mapping[str, float]  # en el orden del mercado
    method: DevigMethod


@dataclass(frozen=True)
class ReferenceResult:
    reference: Reference | None
    rejections: tuple[str, ...]  # por qué se descartó cada candidata anterior


def latest_by_selection(quotes: Sequence[OddsQuote]) -> dict[str, OddsQuote]:
    """Última captura de cada selección."""
    latest: dict[str, OddsQuote] = {}
    for quote in quotes:
        current = latest.get(quote.selection)
        if current is None or quote.captured_at > current.captured_at:
            latest[quote.selection] = quote
    return latest


def _try_bookmaker(
    bookmaker_id: str,
    *,
    quotes: Sequence[OddsQuote],
    market: MarketSpec,
    method: DevigMethod,
    max_age: timedelta,
    now: datetime,
) -> Reference | str:
    latest = latest_by_selection([q for q in quotes if q.bookmaker_id == bookmaker_id])
    if not latest:
        return f"{bookmaker_id}: sin cuotas"
    missing = [s for s in market.selections if s not in latest]
    if missing:
        return f"{bookmaker_id}: falta la selección {', '.join(missing)}"
    chosen = [latest[s] for s in market.selections]
    oldest = max(q.age(now) for q in chosen)
    if oldest > max_age:
        return f"{bookmaker_id}: referencia con {format_age(oldest)} de antigüedad"
    odds = tuple((q.selection, q.price) for q in chosen)
    try:
        probabilities = devig([price for _, price in odds], method)
    except DevigError as exc:
        return f"{bookmaker_id}: {exc}"
    return Reference(
        bookmaker_id=bookmaker_id,
        captured_at=max(q.captured_at for q in chosen),
        odds=odds,
        probabilities=MappingProxyType(dict(zip(market.selections, probabilities, strict=True))),
        method=method,
    )


def select_reference(
    quotes: Sequence[OddsQuote],
    *,
    market: MarketSpec,
    order: Sequence[str],
    method: DevigMethod,
    max_age: timedelta,
    now: datetime,
) -> ReferenceResult:
    """`quotes`: cuotas de un evento y mercado, de cualquier casa."""
    rejections: list[str] = []
    for bookmaker_id in order:
        outcome = _try_bookmaker(
            bookmaker_id, quotes=quotes, market=market, method=method, max_age=max_age, now=now
        )
        if isinstance(outcome, Reference):
            return ReferenceResult(outcome, tuple(rejections))
        rejections.append(outcome)
    return ReferenceResult(None, tuple(rejections))

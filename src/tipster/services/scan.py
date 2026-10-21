"""Orquestación de `tipster scan`: leer, guardar, elegir referencia, evaluar y emitir picks."""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from tipster.config import Settings
from tipster.domain.bookmakers import get_bookmaker
from tipster.domain.competitions import get_competition
from tipster.domain.markets import get_market
from tipster.domain.models import PICK_LABELS, Event, OddsQuote, Opportunity, Pick
from tipster.errors import (
    BudgetExceededError,
    ProviderAuthError,
    ProviderError,
    QuotaExhaustedError,
)
from tipster.pricing.classify import Label, classify
from tipster.pricing.devig import DevigMethod
from tipster.providers.base import OddsBatch, OddsProvider, OddsRequest, RequestRecord
from tipster.services.reference import Reference, select_reference
from tipster.storage.repositories import (
    EventRepository,
    OddsRepository,
    PickRepository,
    RunRepository,
    RunStatus,
)

STALE_QUOTE = "cuota antigua"
NO_REFERENCE = "sin referencia válida"
UNKNOWN_LIQUIDITY = "liquidez desconocida"  # The Odds API no da liquidez ni límites (ADR 001)
_FATAL = (ProviderAuthError, QuotaExhaustedError)

QuoteKey = tuple[str, str, str, str]  # evento, casa, mercado, selección


@dataclass(frozen=True)
class CompetitionReport:
    competition_id: str
    status: Literal["ok", "saltada", "error"]
    detail: str | None = None
    events: int = 0
    quotes: int = 0


@dataclass
class ScanResult:
    run_id: int
    evaluated_at: datetime
    devig_method: DevigMethod
    status: RunStatus = "ok"
    opportunities: list[Opportunity] = field(default_factory=list)
    picks: list[Pick] = field(default_factory=list)
    discards: Counter[str] = field(default_factory=Counter)
    competitions: list[CompetitionReport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    records: list[RequestRecord] = field(default_factory=list)
    aborted: str | None = None

    @property
    def requests(self) -> int:
        return len(self.records)

    @property
    def cache_hits(self) -> int:
        return sum(r.from_cache for r in self.records)

    @property
    def credits_spent(self) -> int:
        return sum(r.cost or 0 for r in self.records if not r.from_cache)

    @property
    def credits_remaining(self) -> int | None:
        remaining = [r.credits_remaining for r in self.records if r.credits_remaining is not None]
        return remaining[-1] if remaining else None


class ScanService:
    def __init__(
        self,
        *,
        provider: OddsProvider,
        events: EventRepository,
        odds: OddsRepository,
        picks: PickRepository,
        runs: RunRepository,
        settings: Settings,
        clock: Callable[[], datetime],
    ) -> None:
        self._provider = provider
        self._events = events
        self._odds = odds
        self._picks = picks
        self._runs = runs
        self._settings = settings
        self._clock = clock

    def run(self) -> ScanResult:
        now = self._clock()
        settings = self._settings
        result = ScanResult(
            run_id=self._runs.start("scan", settings.snapshot()),
            evaluated_at=now,
            devig_method=settings.devig_method,
        )
        fatal = False
        try:
            active = self._active_keys(result)
            for competition_id in settings.competitions:
                if not self._scan_competition(competition_id, active, result, now):
                    break
        except _FATAL as exc:
            fatal = True
            self._record_failure(exc, result)
            result.aborted = str(exc)

        result.status = _status(result, fatal)
        self._runs.finish(result.run_id, result.status)
        return result

    # -- pasos ------------------------------------------------------------------------------

    def _active_keys(self, result: ScanResult) -> set[str] | None:
        """Claves que el proveedor lista como activas; None si no se pudo comprobar."""
        try:
            listing = self._provider.list_competitions()
        except _FATAL:
            raise
        except ProviderError as exc:
            self._record_failure(exc, result)
            result.warnings.append(f"no se pudieron validar las competiciones: {exc}")
            return None
        self._record(listing.request, result)
        return {c.provider_key for c in listing.competitions if c.active}

    def _scan_competition(
        self, competition_id: str, active: set[str] | None, result: ScanResult, now: datetime
    ) -> bool:
        """Procesa una competición. Devuelve False si hay que dejar de escanear."""
        key = get_competition(competition_id).provider_keys[self._provider.name]
        if active is not None and key not in active:
            result.competitions.append(
                CompetitionReport(
                    competition_id,
                    "saltada",
                    f"la clave {key} no aparece en /v4/sports "
                    "(clave NO VERIFICADA o competición fuera de temporada)",
                )
            )
            return True
        request = OddsRequest(competition_id, self._settings.markets, self._settings.bookmakers)
        try:
            batch = self._provider.fetch_odds(request)
        except BudgetExceededError as exc:
            result.competitions.append(CompetitionReport(competition_id, "error", str(exc)))
            result.aborted = f"presupuesto de créditos agotado: {exc}"
            return False
        except _FATAL:
            result.competitions.append(CompetitionReport(competition_id, "error", "abortado"))
            raise
        except ProviderError as exc:
            self._record_failure(exc, result)
            result.competitions.append(CompetitionReport(competition_id, "error", str(exc)))
            return True

        quote_ids = self._store(batch, result)
        opportunities, picks = self._evaluate(batch, quote_ids, result, now)
        self._picks.add(result.run_id, picks)
        result.opportunities.extend(opportunities)
        result.picks.extend(picks)
        result.warnings.extend(f"{competition_id}: {w}" for w in batch.warnings)
        result.competitions.append(
            CompetitionReport(
                competition_id, "ok", events=len(batch.events), quotes=len(batch.quotes)
            )
        )
        return True

    def _store(self, batch: OddsBatch, result: ScanResult) -> dict[QuoteKey, int]:
        request_id = self._record(batch.request, result)
        for event in batch.events:
            self._events.upsert(event, self._provider.name, batch.external_ids[event.id])
        ids = self._odds.add_batch(request_id, batch.quotes)
        return {_key(q): quote_id for q, quote_id in zip(batch.quotes, ids, strict=True)}

    def _evaluate(
        self,
        batch: OddsBatch,
        quote_ids: dict[QuoteKey, int],
        result: ScanResult,
        now: datetime,
    ) -> tuple[list[Opportunity], list[Pick]]:
        settings = self._settings
        opportunities: list[Opportunity] = []
        picks: list[Pick] = []
        for event in batch.events:
            for market_id in settings.markets:
                market = get_market(market_id)
                quotes = [
                    q for q in batch.quotes if q.event_id == event.id and q.market_id == market_id
                ]
                retail = [q for q in quotes if not get_bookmaker(q.bookmaker_id).is_reference]
                if not retail:
                    continue
                chosen = select_reference(
                    quotes,
                    market=market,
                    order=settings.reference_order,
                    method=settings.devig_method,
                    max_age=timedelta(minutes=settings.max_reference_age_minutes),
                    now=now,
                )
                if chosen.reference is None:
                    result.discards[NO_REFERENCE] += len(retail)
                    result.warnings.append(
                        f"{event.name} · {market.name}: {NO_REFERENCE} "
                        f"({'; '.join(chosen.rejections)})"
                    )
                    continue
                for quote in retail:
                    opportunity = self._opportunity(
                        event, quote, chosen.reference, chosen.rejections, now
                    )
                    if opportunity.label is Label.DESCARTADA:
                        result.discards[STALE_QUOTE] += 1
                    opportunities.append(opportunity)
                    if opportunity.label in PICK_LABELS:
                        picks.append(
                            Pick(
                                quote_id=quote_ids[_key(quote)],
                                opportunity=opportunity,
                                created_at=now,
                            )
                        )
        return opportunities, picks

    def _opportunity(
        self,
        event: Event,
        quote: OddsQuote,
        reference: Reference,
        rejections: tuple[str, ...],
        now: datetime,
    ) -> Opportunity:
        p_market = reference.probabilities[quote.selection]
        outcome = classify(
            price=quote.price,
            p_market=p_market,
            p_final=p_market,  # F1: sin modelo, p_final = p_mercado
            quote_age=quote.age(now),
            thresholds=self._settings.thresholds(),
        )
        reasons = list(outcome.reasons)
        reasons.extend(f"referencia descartada: {r}" for r in rejections)
        if quote.provider_last_update is None:
            reasons.append("sin last_update: antigüedad según la hora de captura")
        reasons.append(UNKNOWN_LIQUIDITY)
        return Opportunity(
            event=event,
            quote=quote,
            feed_es=get_bookmaker(quote.bookmaker_id).es_site,
            reference_bookmaker_id=reference.bookmaker_id,
            reference_captured_at=reference.captured_at,
            reference_odds=reference.odds,
            devig_method=reference.method,
            p_market=p_market,
            p_final=p_market,
            fair_odds=1 / p_market,
            ev=p_market * quote.price - 1,
            label=outcome.label,
            reasons=tuple(reasons),
        )

    # -- registro ---------------------------------------------------------------------------

    def _record(self, record: RequestRecord, result: ScanResult) -> int:
        result.records.append(record)
        return self._runs.record_request(result.run_id, record)

    def _record_failure(self, exc: ProviderError, result: ScanResult) -> None:
        if exc.record is not None:
            self._record(exc.record, result)


def _key(quote: OddsQuote) -> QuoteKey:
    return (quote.event_id, quote.bookmaker_id, quote.market_id, quote.selection)


def _status(result: ScanResult, fatal: bool) -> RunStatus:
    ok = any(c.status == "ok" for c in result.competitions)
    failed = result.aborted is not None or any(c.status == "error" for c in result.competitions)
    if fatal or (failed and not ok):
        return "error"
    return "parcial" if failed else "ok"

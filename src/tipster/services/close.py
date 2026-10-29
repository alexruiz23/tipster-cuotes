"""Captura del cierre de Pinnacle de los picks abiertos y cálculo del CLV (ADR 012).

Nunca se inventa una cuota: sin cuota de Pinnacle no hay cierre, y un cierre dudoso se guarda como
no fiable y no entra en el CLV. Que Pinnacle actualice su cuota en la última media hora es NO
VERIFICADO; el `last_update` de cada captura queda registrado para comprobarlo con datos reales.
"""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from tipster.config import Settings
from tipster.domain.markets import get_market
from tipster.errors import (
    BudgetExceededError,
    ProviderAuthError,
    ProviderError,
    QuotaExhaustedError,
)
from tipster.providers.base import OddsProvider, OddsRequest, RequestRecord
from tipster.storage.repositories import RunRepository
from tipster.storage.tracking import OpenPick, SqliteTrackingRepository
from tipster.tracking.clv import closing_fair_odds, clv

PINNACLE = "pinnacle"
_FATAL = (ProviderAuthError, QuotaExhaustedError)


@dataclass
class CloseResult:
    run_id: int
    captured: list[int] = field(default_factory=list)  # picks con cierre fiable y CLV
    unreliable: list[int] = field(default_factory=list)  # cierre guardado sin CLV
    missing: list[str] = field(default_factory=list)  # picks sin cuota de cierre de Pinnacle
    warnings: list[str] = field(default_factory=list)
    records: list[RequestRecord] = field(default_factory=list)
    aborted: str | None = None


class CloseService:
    def __init__(
        self,
        *,
        provider: OddsProvider,
        tracking: SqliteTrackingRepository,
        runs: RunRepository,
        settings: Settings,
        clock: Callable[[], datetime],
    ) -> None:
        self._provider = provider
        self._tracking = tracking
        self._runs = runs
        self._settings = settings
        self._clock = clock

    def run(self) -> CloseResult:
        now = self._clock()
        s = self._settings
        result = CloseResult(run_id=self._runs.start("close", s.snapshot()))
        window = timedelta(minutes=s.closing_window_minutes)
        due = [
            p
            for p in self._tracking.open_picks()
            if p.stake and not p.has_closing and timedelta(0) <= p.kickoff - now <= window
        ]
        by_competition: dict[str, list[OpenPick]] = defaultdict(list)
        for pick in due:
            by_competition[pick.competition_id].append(pick)
        for competition_id, picks in by_competition.items():
            markets = tuple(sorted({p.market_id for p in picks}))
            try:
                batch = self._provider.fetch_odds(OddsRequest(competition_id, markets, (PINNACLE,)))
            except BudgetExceededError as exc:
                result.aborted = f"presupuesto de créditos agotado: {exc}"
                break
            except _FATAL as exc:
                result.aborted = str(exc)
                break
            except ProviderError as exc:
                result.warnings.append(f"{competition_id}: {exc}")
                continue
            result.records.append(batch.request)
            self._runs.record_request(result.run_id, batch.request)
            for pick in picks:
                self._close_pick(pick, batch.quotes, result)
        self._runs.finish(result.run_id, "error" if result.aborted else "ok")
        return result

    def _close_pick(self, pick: OpenPick, quotes: list, result: CloseResult) -> None:  # type: ignore[type-arg]
        s = self._settings
        selections = get_market(pick.market_id).selections
        prices = {
            q.selection: q
            for q in quotes
            if q.event_id == pick.event_id
            and q.market_id == pick.market_id
            and q.bookmaker_id == PINNACLE
        }
        if set(prices) != set(selections):
            result.missing.append(
                f"{pick.home_team} – {pick.away_team} ({pick.market_id}): sin cuota de Pinnacle"
            )
            return
        raw = tuple(prices[name].price for name in selections)
        index = selections.index(pick.selection)
        quote = prices[pick.selection]
        fair = closing_fair_odds(raw, index, s.devig_method)
        max_age = timedelta(minutes=s.closing_max_age_minutes)
        before_kickoff = pick.kickoff - quote.captured_at
        fresh = (
            quote.provider_last_update is not None
            and quote.captured_at - quote.provider_last_update <= max_age
        )
        reliable = timedelta(0) <= before_kickoff <= max_age and fresh
        self._tracking.set_closing(
            pick.id,
            closing_odds=raw[index],
            closing_fair_odds=fair,
            captured_at=quote.captured_at,
            last_update=quote.provider_last_update,
            reliable=reliable,
            clv=clv(pick.price, fair) if reliable else None,
        )
        (result.captured if reliable else result.unreliable).append(pick.id)

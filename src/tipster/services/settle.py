"""Liquidación de los picks abiertos con los resultados del proveedor o a mano (ADR 012)."""

import math
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from tipster.errors import ProviderError
from tipster.providers.base import ScoreProvider
from tipster.storage.repositories import RunRepository
from tipster.storage.tracking import OpenPick, SqliteBankrollRepository, SqliteTrackingRepository
from tipster.tracking.settlement import settle_pick

FINISHED_AFTER = timedelta(hours=2)  # un partido se consulta tras este tiempo desde su inicio
MAX_DAYS_FROM = 3  # tope de `daysFrom` de The Odds API según su documentación (nivel C)


@dataclass(frozen=True)
class Settled:
    pick_id: int
    status: str
    profit: float | None


@dataclass
class SettleResult:
    run_id: int
    settled: list[Settled] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SettleService:
    def __init__(
        self,
        *,
        provider: ScoreProvider | None,
        tracking: SqliteTrackingRepository,
        bankroll: SqliteBankrollRepository,
        runs: RunRepository,
        clock: Callable[[], datetime],
    ) -> None:
        self._provider = provider
        self._tracking = tracking
        self._bankroll = bankroll
        self._runs = runs
        self._clock = clock

    def run(self, manual: Mapping[str, tuple[int, int]]) -> SettleResult:
        now = self._clock()
        result = SettleResult(run_id=self._runs.start("settle", {}))
        picks = self._tracking.open_picks()
        scores = dict(manual)  # id canónico del evento → (goles local, goles visitante)
        if self._provider is not None:
            scores.update(self._fetch(picks, set(manual), now, result))
        for pick in picks:
            if pick.event_id not in scores:
                if now - pick.kickoff >= FINISHED_AFTER:
                    result.pending.append(
                        f"{pick.home_team} – {pick.away_team} ({pick.market_id} {pick.selection}): "
                        "sin resultado (usa --result)"
                    )
                continue
            home, away = scores[pick.event_id]
            s = settle_pick(
                pick.market_id, pick.selection, pick.price, pick.stake,
                home_goals=home, away_goals=away,
            )  # fmt: skip
            self._tracking.settle(
                pick.id, result=s.result, status=s.status, profit=s.profit, settled_at=now
            )
            if s.profit is not None:
                self._bankroll.settle(pick.id, s.profit)
            result.settled.append(Settled(pick.id, s.status, s.profit))
        self._runs.finish(result.run_id, "ok")
        return result

    def _fetch(
        self, picks: list[OpenPick], manual: set[str], now: datetime, result: SettleResult
    ) -> dict[str, tuple[int, int]]:
        assert self._provider is not None
        due: dict[str, list[OpenPick]] = defaultdict(list)
        for pick in picks:
            if pick.event_id not in manual and now - pick.kickoff >= FINISHED_AFTER:
                due[pick.competition_id].append(pick)
        external = self._tracking.events_by_external(self._provider.name)
        found: dict[str, tuple[int, int]] = {}
        for competition_id, group in due.items():
            oldest = min(p.kickoff for p in group)
            days = min(max(math.ceil((now - oldest).total_seconds() / 86400), 1), MAX_DAYS_FROM)
            try:
                batch = self._provider.fetch_scores(competition_id, days)
            except ProviderError as exc:
                result.warnings.append(f"{competition_id}: {exc}")
                continue
            self._runs.record_request(result.run_id, batch.request)
            for score in batch.scores:
                event_id = external.get(score.external_id)
                if (
                    event_id is not None
                    and score.completed
                    and score.home_goals is not None
                    and score.away_goals is not None
                ):
                    found[event_id] = (score.home_goals, score.away_goals)
        return found

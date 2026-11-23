"""Simulación de la estrategia sobre partidos históricos (BACKLOG 53).

Sin datos del futuro: p justa = Shin sobre el Pinnacle PREVIO; el cierre solo mide el CLV.
Aproximaciones declaradas: el tope de improbables abiertos se aplica por semana ISO; no existen
casas .es; el horizonte de 4 días no se puede probar (una sola foto de cuotas por partido).
"""

import math
import random
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache

from tipster.backtest.football_data import Match
from tipster.pricing.devig import devig_shin


@cache
def _shin(odds: tuple[float, float, float]) -> tuple[float, ...]:
    """El barrido repite miles de veces el mismo partido: el devig se calcula una sola vez."""
    return devig_shin(odds)


@dataclass(frozen=True)
class Strategy:
    book: str = "b365"  # b365 | avg | max
    longshot_odds: float = 4.0
    ev_min: float = 0.03
    longshot_ev_min: float = 0.06
    max_odds: float = 8.0
    min_odds: float = 1.5
    max_open_longshots: int = 2


@dataclass(frozen=True)
class Bet:
    season: str
    week: tuple[int, int]
    odds: float
    ev: float
    won: bool
    clv: float
    longshot: bool

    @property
    def profit(self) -> float:
        return self.odds - 1 if self.won else -1.0


@dataclass(frozen=True)
class Summary:
    n: int
    roi: float | None
    clv: float | None
    clv_se: float | None
    hit: float | None


def _candidate(m: Match, s: Strategy) -> Bet | None:
    prices = m.taken.get(s.book)
    if prices is None:
        return None
    fair = _shin(m.ps_open)
    fair_close = _shin(m.ps_close)
    best: Bet | None = None
    for i, price in enumerate(prices):
        if not s.min_odds <= price <= s.max_odds:
            continue
        ev = fair[i] * price - 1
        longshot = price > s.longshot_odds
        if ev < (s.longshot_ev_min if longshot else s.ev_min):
            continue
        if best is None or ev > best.ev:
            iso = m.day.isocalendar()
            best = Bet(
                m.season, (iso.year, iso.week), price, ev, m.result == i,
                price * fair_close[i] - 1, longshot,
            )  # fmt: skip
    return best


def run(matches: Sequence[Match], s: Strategy) -> list[Bet]:
    """Un pick por partido; tope de improbables por semana ISO (los de mayor EV primero)."""
    candidates = [b for m in sorted(matches, key=lambda x: x.day) if (b := _candidate(m, s))]
    longshots: dict[tuple[int, int], int] = defaultdict(int)
    bets: list[Bet] = []
    for bet in sorted(candidates, key=lambda b: -b.ev):
        if bet.longshot:
            if longshots[bet.week] >= s.max_open_longshots:
                continue
            longshots[bet.week] += 1
        bets.append(bet)
    return bets


def summarize(bets: Sequence[Bet]) -> Summary:
    n = len(bets)
    if n == 0:
        return Summary(0, None, None, None, None)
    clv = [b.clv for b in bets]
    mean = sum(clv) / n
    se = math.sqrt(sum((x - mean) ** 2 for x in clv) / (n - 1) / n) if n > 1 else None
    return Summary(n, sum(b.profit for b in bets) / n, mean, se, sum(b.won for b in bets) / n)


def block_bootstrap(
    bets: Sequence[Bet], *, n_boot: int = 2000, seed: int = 1
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Intervalos del 95 % para el CLV medio y el ROI, remuestreando SEMANAS enteras.

    Los picks de una misma semana comparten mercado y noticias: tratarlos como independientes
    (el error típico de `summarize`) estrecha demasiado el intervalo. Devuelve None con menos de
    dos semanas."""
    weeks: dict[tuple[str, tuple[int, int]], list[Bet]] = defaultdict(list)
    for bet in bets:
        weeks[(bet.season, bet.week)].append(bet)
    blocks = list(weeks.values())
    if len(blocks) < 2:
        return None
    rng = random.Random(seed)
    clvs: list[float] = []
    rois: list[float] = []
    for _ in range(n_boot):
        sample = [b for block in rng.choices(blocks, k=len(blocks)) for b in block]
        clvs.append(sum(b.clv for b in sample) / len(sample))
        rois.append(sum(b.profit for b in sample) / len(sample))
    clvs.sort()
    rois.sort()
    lo, hi = int(0.025 * n_boot), int(0.975 * n_boot) - 1
    return (clvs[lo], clvs[hi]), (rois[lo], rois[hi])

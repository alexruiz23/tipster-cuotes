"""CLV: cuota tomada frente a la cuota justa (sin margen) de cierre de Pinnacle (ADR 002, 012)."""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from tipster.pricing.devig import DevigMethod, devig


def closing_fair_odds(raw_odds: Sequence[float], index: int, method: DevigMethod) -> float:
    """Cuota justa de la selección `index` a partir de la cuota cruda de cierre."""
    return 1.0 / devig(raw_odds, method)[index]


def clv(price: float, fair_close_odds: float) -> float:
    """CLV = cuota_tomada / cuota_justa_de_cierre − 1 (= cuota · p_cierre_justa − 1)."""
    return price / fair_close_odds - 1.0


@dataclass(frozen=True)
class ClvSummary:
    n: int
    mean: float | None
    weighted_mean: float | None  # ponderada por stake
    median: float | None
    share_positive: float | None
    stderr: float | None  # sd/√n; None con n < 2


def summarize_clv(values: Sequence[tuple[float, float]]) -> ClvSummary:
    """Resumen de `(clv, stake)` de una muestra de picks."""
    n = len(values)
    if n == 0:
        return ClvSummary(0, None, None, None, None, None)
    clvs = [v for v, _ in values]
    total_stake = sum(s for _, s in values)
    return ClvSummary(
        n=n,
        mean=statistics.fmean(clvs),
        weighted_mean=sum(v * s for v, s in values) / total_stake if total_stake else None,
        median=statistics.median(clvs),
        share_positive=sum(v > 0 for v in clvs) / n,
        stderr=statistics.stdev(clvs) / n**0.5 if n > 1 else None,
    )

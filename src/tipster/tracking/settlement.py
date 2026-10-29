"""Liquidación de un pick con el resultado final (ADR 012)."""

from dataclasses import dataclass

from tipster.models.evaluation import outcome_index

OU_LINE_GOALS = 3  # O/U 2.5: «más» con 3 goles o más


@dataclass(frozen=True)
class Settlement:
    result: str  # local/empate/visitante o mas/menos
    status: str  # ganado/perdido
    profit: float | None  # None si el pick no tenía stake


def outcome_of(market_id: str, home_goals: int, away_goals: int) -> str:
    if market_id == "ou_2.5":
        return "mas" if home_goals + away_goals >= OU_LINE_GOALS else "menos"
    return ("local", "empate", "visitante")[outcome_index(home_goals, away_goals)]


def settle_pick(
    market_id: str,
    selection: str,
    price: float,
    stake: float | None,
    *,
    home_goals: int,
    away_goals: int,
) -> Settlement:
    result = outcome_of(market_id, home_goals, away_goals)
    won = selection == result
    profit = None if not stake else (stake * (price - 1.0) if won else -stake)
    return Settlement(result, "ganado" if won else "perdido", profit)

"""Stake flat como porcentaje del bankroll con límites absolutos (ADR 012)."""


def flat_stake(bankroll: float, *, pct: float, min_abs: float, max_abs: float) -> float:
    """`max(min_abs, min(max_abs, bankroll · pct))`, redondeado a céntimos."""
    return round(max(min_abs, min(max_abs, bankroll * pct)), 2)

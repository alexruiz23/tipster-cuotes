"""Kelly fraccionado (ADR 012): f* = (p·o − 1)/(o − 1), con una fracción y un tope por apuesta."""


def kelly_fraction(p: float, odds: float) -> float:
    """Fracción de Kelly completa; negativa si no hay ventaja."""
    return (p * odds - 1.0) / (odds - 1.0)


def kelly_stake(
    bankroll: float,
    p: float,
    odds: float,
    *,
    fraction: float = 0.25,
    cap: float | None = 0.02,
) -> float:
    """Stake en unidades de bankroll, redondeado a céntimos; 0 si no hay ventaja."""
    share = max(kelly_fraction(p, odds), 0.0) * fraction
    if cap is not None:
        share = min(share, cap)
    return round(bankroll * share, 2)

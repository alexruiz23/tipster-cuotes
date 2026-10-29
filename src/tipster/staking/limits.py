"""Límites de exposición diaria y de pérdida (ADR 012)."""

from collections.abc import Sequence

LIMIT_TOL = 1e-9


def allocate_daily(
    picks: Sequence[tuple[str, float, float]],
    *,
    bankroll: float,
    daily_cap: float = 0.10,
    min_stake: float = 0.0025,
) -> dict[str, float]:
    """Reparte el tope diario entre `(clave, stake bruto, EV)` por EV decreciente.

    El que no cabe se recorta al hueco que queda; un stake por debajo del mínimo se descarta (0).
    """
    remaining = daily_cap * bankroll
    floor = min_stake * bankroll
    stakes: dict[str, float] = {}
    for key, raw, _ in sorted(picks, key=lambda p: (-p[2], p[0])):
        stake = min(raw, remaining)
        if stake < floor - LIMIT_TOL:
            stakes[key] = 0.0
            continue
        stakes[key] = round(stake, 2)
        remaining -= stakes[key]
    return stakes


def loss_limit_reached(pnl_today: float, *, bankroll: float, limit: float = 0.05) -> bool:
    """True si las pérdidas liquidadas del día alcanzan `limit` del bankroll."""
    return pnl_today <= -limit * bankroll + LIMIT_TOL

"""Cuota justa y valor esperado (EV) de una apuesta a una unidad."""

import math

from tipster.errors import DevigError


def _check_probability(p: float) -> None:
    if not math.isfinite(p) or not 0 < p <= 1:
        raise DevigError(f"Probabilidad fuera de (0, 1]: {p!r}")


def fair_odds(p: float) -> float:
    """Cuota sin margen: 1 / p."""
    _check_probability(p)
    return 1 / p


def expected_value(p: float, odds: float) -> float:
    """EV por unidad apostada: p × cuota − 1."""
    _check_probability(p)
    return p * odds - 1

"""Mezcla de probabilidades y calibración multinomial (ADR 012).

Convención del PLAN: `w` es el peso del mercado. Orden de los resultados: local, empate, visitante.
"""

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize, minimize_scalar

from tipster.models.dixon_coles import Floats, Ints

Probs = tuple[float, float, float]
SNAP_ONE = 0.95  # un peso de mercado por encima de esto se fija en 1 (ADR 012)
SNAP_LOW = 1e-3


def blend_probs(
    p_market: Probs, p_model: Probs, w_market: float, *, logarithmic: bool = False
) -> Probs:
    """Lineal `w·p_mercado + (1 − w)·p_modelo` o logarítmica `p_mercado^w · p_modelo^(1 − w)`."""
    if logarithmic:
        raw = [m**w_market * q ** (1 - w_market) for m, q in zip(p_market, p_model, strict=True)]
        total = sum(raw)
        return (raw[0] / total, raw[1] / total, raw[2] / total)
    mixed = [w_market * m + (1 - w_market) * q for m, q in zip(p_market, p_model, strict=True)]
    return (mixed[0], mixed[1], mixed[2])


@dataclass(frozen=True)
class Calibrator:
    """p'_k ∝ exp(β·ln p_k + b_k), con b_local = 0."""

    beta: float
    b_draw: float
    b_away: float

    def apply(self, probs: Probs) -> Probs:
        z = [
            self.beta * math.log(p) + b
            for p, b in zip(probs, (0.0, self.b_draw, self.b_away), strict=True)
        ]
        top = max(z)
        exp = [math.exp(v - top) for v in z]
        total = sum(exp)
        return (exp[0] / total, exp[1] / total, exp[2] / total)


IDENTITY = Calibrator(1.0, 0.0, 0.0)


def _log_loss_of(probs: Floats, outcomes: Ints) -> float:
    return float(-np.log(probs[np.arange(len(outcomes)), outcomes]).mean())


def _calibrated(probs: Floats, theta: Floats) -> Floats:
    z = theta[0] * np.log(probs) + np.array([0.0, theta[1], theta[2]])
    z = z - z.max(axis=1, keepdims=True)
    exp = np.exp(z)
    result: Floats = exp / exp.sum(axis=1, keepdims=True)
    return result


def fit_calibrator(probs: Floats, outcomes: Ints) -> Calibrator:
    """Ajusta (β, b_empate, b_visitante) minimizando el log-loss; parte de la identidad."""
    result = minimize(
        lambda theta: _log_loss_of(_calibrated(probs, theta), outcomes),
        np.array([1.0, 0.0, 0.0]),
        method="BFGS",
    )
    return Calibrator(float(result.x[0]), float(result.x[1]), float(result.x[2]))


def fit_market_weight(
    p_model: Floats,
    p_market: Floats,
    outcomes: Ints,
    *,
    logarithmic: bool = False,
    minimum: float = 0.5,
) -> float:
    """Peso del mercado en [minimum, 1] que minimiza el log-loss de la mezcla.

    Por encima de 0,95 se fija en 1 (el modelo no aporta) y a 1e-3 del mínimo, en el mínimo.
    """

    def loss(w: float) -> float:
        if logarithmic:
            raw = p_market**w * p_model ** (1 - w)
            mixed = raw / raw.sum(axis=1, keepdims=True)
        else:
            mixed = w * p_market + (1 - w) * p_model
        return _log_loss_of(mixed, outcomes)

    w = float(minimize_scalar(loss, bounds=(minimum, 1.0), method="bounded").x)
    if w > SNAP_ONE:
        return 1.0
    return minimum if w < minimum + SNAP_LOW else w

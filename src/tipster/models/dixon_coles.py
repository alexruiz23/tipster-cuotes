"""Núcleo de Dixon-Coles (ADR 008): verosimilitud, matriz de marcadores y, más adelante, el ajuste.

    λ = exp(a_local + d_visitante + γ)        μ = exp(a_visitante + d_local)
    P(x, y) = τ(x, y; λ, μ, ρ) · Poisson(x; λ) · Poisson(y; μ)

`d` es la debilidad defensiva: más alto = peor defensa.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.special import gammaln

Floats = NDArray[np.float64]
Ints = NDArray[np.int64]

TAU_FLOOR = 1e-12  # solo para que el optimizador pueda retroceder; el ajuste comprueba τ > 0
MAX_GOALS = 20


@dataclass(frozen=True)
class Match:
    home_id: int
    away_id: int
    home_goals: int
    away_goals: int


@dataclass(frozen=True, eq=False)
class MatchData:
    """Partidos como arrays; los equipos se numeran 0…n−1 en el orden de sus ids."""

    team_ids: tuple[int, ...]
    home: Ints
    away: Ints
    x: Ints
    y: Ints


def prepare(matches: Sequence[Match]) -> MatchData:
    team_ids = tuple(sorted({t for m in matches for t in (m.home_id, m.away_id)}))
    index = {team: i for i, team in enumerate(team_ids)}
    return MatchData(
        team_ids=team_ids,
        home=np.array([index[m.home_id] for m in matches], dtype=np.int64),
        away=np.array([index[m.away_id] for m in matches], dtype=np.int64),
        x=np.array([m.home_goals for m in matches], dtype=np.int64),
        y=np.array([m.away_goals for m in matches], dtype=np.int64),
    )


def tau(x: Ints, y: Ints, lam: Floats | float, mu: Floats | float, rho: float) -> Floats:
    """Corrección de Dixon-Coles de los marcadores bajos; vale 1 en cualquier otro."""
    lam_, mu_ = np.broadcast_arrays(np.asarray(lam, dtype=np.float64), np.asarray(mu, np.float64))
    out = np.ones(np.broadcast(x, y, lam_).shape, dtype=np.float64)
    out = np.where((x == 0) & (y == 0), 1.0 - lam_ * mu_ * rho, out)
    out = np.where((x == 0) & (y == 1), 1.0 + lam_ * rho, out)
    out = np.where((x == 1) & (y == 0), 1.0 + mu_ * rho, out)
    return np.where((x == 1) & (y == 1), 1.0 - rho, out)


def log_likelihood(data: MatchData, a: Floats, d: Floats, gamma: float, rho: float) -> float:
    """ℓ completa (con los `log x!`); `a` y `d` llevan un valor por equipo de `data.team_ids`."""
    eta_h = a[data.home] + d[data.away] + gamma
    eta_v = a[data.away] + d[data.home]
    lam, mu = np.exp(eta_h), np.exp(eta_v)
    log_tau = np.log(np.maximum(tau(data.x, data.y, lam, mu, rho), TAU_FLOOR))
    terms = (
        log_tau
        + data.x * eta_h
        - lam
        - gammaln(data.x + 1)
        + data.y * eta_v
        - mu
        - gammaln(data.y + 1)
    )
    return float(terms.sum())


def score_matrix(
    lam: float, mu: float, rho: float, max_goals: int = MAX_GOALS, *, normalize: bool = True
) -> Floats:
    """P(x, y) para x, y = 0…max_goals; filas = goles del local, columnas = del visitante."""
    goals = np.arange(max_goals + 1)
    pmf_h = np.exp(goals * np.log(lam) - lam - gammaln(goals + 1))
    pmf_v = np.exp(goals * np.log(mu) - mu - gammaln(goals + 1))
    x, y = np.meshgrid(goals, goals, indexing="ij")
    matrix = tau(x, y, lam, mu, rho) * np.outer(pmf_h, pmf_v)
    return matrix / matrix.sum() if normalize else matrix

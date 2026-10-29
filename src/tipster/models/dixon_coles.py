"""Núcleo de Dixon-Coles (ADR 008): verosimilitud, matriz de marcadores y ajuste por MLE.

    λ = exp(a_local + d_visitante + γ)        μ = exp(a_visitante + d_local)
    P(x, y) = τ(x, y; λ, μ, ρ) · Poisson(x; λ) · Poisson(y; μ)

`d` es la debilidad defensiva: más alto = peor defensa.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize
from scipy.special import gammaln

from tipster.errors import FitError

Floats = NDArray[np.float64]
Ints = NDArray[np.int64]

TAU_FLOOR = 1e-12  # solo para que el optimizador pueda retroceder; el ajuste comprueba τ > 0
MAX_GOALS = 20
RHO_BOUND = 0.5
MAX_ABS_PARAM = 6.0  # |a| o |d| mayor: λ fuera de [0,0025; 400], señal de divergencia
GRADIENT_TOL = 1e-4  # provisional (ADR 008)


@dataclass(frozen=True)
class Match:
    home_id: int
    away_id: int
    home_goals: int
    away_goals: int
    day: date | None = None


@dataclass(frozen=True, eq=False)
class MatchData:
    """Partidos como arrays; los equipos se numeran 0…n−1 en el orden de sus ids."""

    team_ids: tuple[int, ...]
    home: Ints
    away: Ints
    x: Ints
    y: Ints
    w: Floats  # peso de cada partido (1 sin decaimiento)


def decay_weights(days_ago: Floats | Ints, half_life_days: float) -> Floats:
    """w = exp(−ξ·Δt) = 0,5^(Δt / vida media), con ξ = ln 2 / vida media (ADR 009)."""
    return np.asarray(0.5 ** (np.asarray(days_ago, dtype=np.float64) / half_life_days))


def prepare(matches: Sequence[Match], half_life_days: float | None = None) -> MatchData:
    """Con `half_life_days`, cada partido pesa según su distancia al último partido de la lista."""
    team_ids = tuple(sorted({t for m in matches for t in (m.home_id, m.away_id)}))
    index = {team: i for i, team in enumerate(team_ids)}
    if half_life_days is None:
        weights = np.ones(len(matches))
    else:
        days = [m.day for m in matches]
        if any(d is None for d in days):
            raise FitError("El decaimiento temporal necesita la fecha de cada partido")
        last = max(d for d in days if d is not None)
        weights = decay_weights(
            np.array([(last - d).days for d in days if d is not None]), half_life_days
        )
    return MatchData(
        team_ids=team_ids,
        home=np.array([index[m.home_id] for m in matches], dtype=np.int64),
        away=np.array([index[m.away_id] for m in matches], dtype=np.int64),
        x=np.array([m.home_goals for m in matches], dtype=np.int64),
        y=np.array([m.away_goals for m in matches], dtype=np.int64),
        w=weights,
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
    return float((data.w * terms).sum())


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


def _split(theta: Floats, n: int) -> tuple[Floats, Floats, float, float]:
    """θ = [a_1…a_{n−1}, d_1…d_n, γ, ρ]; el último ataque cierra `mean(a) = 0`."""
    free = theta[: n - 1]
    return (
        np.append(free, -free.sum()),
        theta[n - 1 : 2 * n - 1],
        float(theta[-2]),
        float(theta[-1]),
    )


def _objective(theta: Floats, data: MatchData, l2: float = 0.0) -> tuple[float, Floats]:
    """−ℓ + λ₂·(Σ a² + Σ (d − media d)²) y su gradiente analítico respecto a θ (ADR 009)."""
    n = len(data.team_ids)
    a, d, gamma, rho = _split(theta, n)
    lam = np.exp(a[data.home] + d[data.away] + gamma)
    mu = np.exp(a[data.away] + d[data.home])
    x, y = data.x, data.y
    t = tau(x, y, lam, mu, rho)
    ok = t > TAU_FLOOR
    t = np.where(ok, t, 1.0)  # donde se recorta, log τ es constante: sin derivada
    m00, m01, m10, m11 = (
        ok & (x == 0) & (y == 0),
        ok & (x == 0) & (y == 1),
        ok & (x == 1) & (y == 0),
        ok & (x == 1) & (y == 1),
    )
    w = data.w
    g_h = w * (
        x - lam + np.where(m00, -lam * mu * rho / t, 0.0) + np.where(m01, lam * rho / t, 0.0)
    )
    g_v = w * (y - mu + np.where(m00, -lam * mu * rho / t, 0.0) + np.where(m10, mu * rho / t, 0.0))
    g_rho = float(
        (
            w
            * (
                np.where(m00, -lam * mu / t, 0.0)
                + np.where(m01, lam / t, 0.0)
                + np.where(m10, mu / t, 0.0)
                + np.where(m11, -1.0 / t, 0.0)
            )
        ).sum()
    )
    g_a = np.bincount(data.home, g_h, n) + np.bincount(data.away, g_v, n)
    g_d = np.bincount(data.away, g_h, n) + np.bincount(data.home, g_v, n)
    grad = -np.concatenate([g_a[:-1] - g_a[-1], g_d, [g_h.sum(), g_rho]])
    value = -log_likelihood(data, a, d, gamma, rho)
    if l2:
        d_centered = d - d.mean()
        pen_a = 2.0 * l2 * a
        value += l2 * float(a @ a + d_centered @ d_centered)
        grad += np.concatenate([pen_a[:-1] - pen_a[-1], 2.0 * l2 * d_centered, [0.0, 0.0]])
    return value, grad


@dataclass(frozen=True, eq=False)
class DixonColesFit:
    team_ids: tuple[int, ...]
    a: Floats
    d: Floats
    gamma: float
    rho: float
    log_likelihood: float
    n_matches: int
    iterations: int
    max_gradient: float
    half_life_days: float | None = None
    l2: float = 0.0

    def knows(self, team_id: int) -> bool:
        return team_id in self.team_ids

    def _strengths(self, team_id: int) -> tuple[float, float]:
        """(ataque, debilidad defensiva); un equipo sin historial es el equipo medio (ADR 008)."""
        if team_id not in self.team_ids:
            return 0.0, float(self.d.mean())
        i = self.team_ids.index(team_id)
        return float(self.a[i]), float(self.d[i])

    def predict_proba(self, home_id: int, away_id: int) -> dict[str, float]:
        a_h, d_h = self._strengths(home_id)
        a_v, d_v = self._strengths(away_id)
        matrix = score_matrix(
            float(np.exp(a_h + d_v + self.gamma)), float(np.exp(a_v + d_h)), self.rho
        )
        return {
            "local": float(np.tril(matrix, -1).sum()),
            "empate": float(np.trace(matrix)),
            "visitante": float(np.triu(matrix, 1).sum()),
        }


def fit(
    matches: Sequence[Match], *, half_life_days: float | None = None, l2: float = 0.0
) -> DixonColesFit:
    """MLE de una liga con L-BFGS-B. Lanza `FitError` si no converge o diverge (ADR 008)."""
    if not matches:
        raise FitError("No hay partidos con los que ajustar")
    if l2 < 0:
        raise FitError(f"l2 debe ser >= 0 (recibido {l2})")
    data = prepare(matches, half_life_days)
    n = len(data.team_ids)
    mean_home, mean_away = float(data.x.mean()), float(data.y.mean())
    if n < 2 or mean_home == 0 or mean_away == 0:
        raise FitError("Hacen falta al menos dos equipos y goles de local y de visitante")
    theta0 = np.concatenate(
        [np.zeros(n - 1), np.full(n, np.log(mean_away)), [np.log(mean_home / mean_away), 0.0]]
    )
    bounds = [(None, None)] * (2 * n) + [(-RHO_BOUND, RHO_BOUND)]
    result = minimize(
        _objective,
        theta0,
        args=(data, l2),
        jac=True,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 5000, "maxfun": 20000, "ftol": 0.0, "gtol": 1e-9},
    )
    a, d, gamma, rho = _split(result.x, n)
    max_gradient = float(np.abs(result.jac).max())
    low = (data.x <= 1) & (data.y <= 1)
    lam, mu = np.exp(a[data.home] + d[data.away] + gamma), np.exp(a[data.away] + d[data.home])
    min_tau = float(tau(data.x, data.y, lam, mu, rho)[low].min(initial=1.0))
    problems = []
    # El criterio es la optimalidad de primer orden: L-BFGS-B puede parar con «ABNORMAL» en el
    # límite de precisión con el gradiente ya en ~1e-6, así que su mensaje solo se informa.
    if max_gradient > GRADIENT_TOL:
        problems.append(
            f"el gradiente final es {max_gradient:.2e} (máximo {GRADIENT_TOL:.0e}); "
            f"scipy: {result.message}"
        )
    if abs(abs(rho) - RHO_BOUND) < 1e-6:
        problems.append(f"ρ = {rho:.4f} está en una cota")
    if min_tau <= 0:
        problems.append(f"τ no es positivo en algún marcador bajo (mínimo {min_tau:.3g})")
    if max(np.abs(a).max(), np.abs(d).max()) > MAX_ABS_PARAM:
        problems.append("algún ataque o defensa diverge (|valor| > 6)")
    if problems:
        raise FitError("; ".join(problems))
    return DixonColesFit(
        team_ids=data.team_ids,
        a=a,
        d=d,
        gamma=gamma,
        rho=rho,
        log_likelihood=log_likelihood(data, a, d, gamma, rho),
        n_matches=len(matches),
        iterations=int(result.nit),
        max_gradient=max_gradient,
        half_life_days=half_life_days,
        l2=l2,
    )

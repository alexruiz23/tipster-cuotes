"""Elo con empate (Elo-Davidson, ADR 010).

    d = R_local + H − R_visitante          γ_h/γ_a = 10^(d/400)
    P(local) = γ_h/Z   P(empate) = ν·√(γ_h·γ_a)/Z   P(visitante) = γ_a/Z   (Z = suma de los tres)
    R_local += K·(S − E)   con   E = P(local) + ½·P(empate)

La actualización es un paso de gradiente de la log-verosimilitud del propio modelo.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from itertools import groupby

import numpy as np
from scipy.optimize import minimize

from tipster.errors import FitError
from tipster.models.dixon_coles import Match
from tipster.models.evaluation import outcome_index

START_RATING = 1500.0
Probs = tuple[float, float, float]


@dataclass(frozen=True)
class EloParams:
    k: float
    home_advantage: float
    nu: float
    carry: float  # fracción de la distancia a la media que se conserva al cambiar de temporada
    newcomer_offset: float  # δ: los equipos nuevos entran con la media + δ


def season_of(day: date) -> int:
    """Año de inicio de la temporada, con corte el 1 de agosto."""
    return day.year if day.month >= 8 else day.year - 1


def davidson_probs(d: float, nu: float) -> Probs:
    """(local, empate, visitante) para una diferencia de rating `d` (en puntos, con la ventaja)."""
    g = 10.0 ** (d / 400.0)
    root = math.sqrt(g)
    z = g + 1.0 + nu * root
    return g / z, nu * root / z, 1.0 / z


def _regress(
    ratings: dict[int, float], last: dict[int, int], ended: int, carry: float
) -> dict[int, float]:
    """Regresión a la media de todos los equipos al acabar la temporada `ended`."""
    played = [r for t, r in ratings.items() if last[t] == ended]
    mean = float(np.mean(played if played else list(ratings.values()))) if ratings else 0.0
    return {t: mean + carry * (r - mean) for t, r in ratings.items()}


def _newcomer(ratings: dict[int, float], last: dict[int, int], season: int, offset: float) -> float:
    recent = [r for t, r in ratings.items() if last[t] >= season - 1]
    return float(np.mean(recent)) + offset if recent else START_RATING


@dataclass(frozen=True)
class EloFit:
    params: EloParams
    ratings: dict[int, float]
    last_season: dict[int, int]  # última temporada en que jugó cada equipo
    season: int | None

    def knows(self, team_id: int) -> bool:
        return team_id in self.ratings

    def rating(self, team_id: int) -> float:
        """Rating actual; un equipo sin historial vale la media reciente + δ."""
        if team_id in self.ratings:
            return self.ratings[team_id]
        if self.season is None:
            return START_RATING
        return _newcomer(self.ratings, self.last_season, self.season, self.params.newcomer_offset)

    def regressed_to(self, season: int) -> "EloFit":
        """El mismo estado al empezar `season`: aplica la regresión de cada cambio de temporada."""
        if self.season is None or season <= self.season:
            return self
        ratings = dict(self.ratings)
        for ended in range(self.season, season):
            ratings = _regress(ratings, self.last_season, ended, self.params.carry)
        return replace(self, ratings=ratings, season=season)

    def predict_proba(self, home_id: int, away_id: int) -> dict[str, float]:
        d = self.rating(home_id) + self.params.home_advantage - self.rating(away_id)
        local, draw, away = davidson_probs(d, self.params.nu)
        return {"local": local, "empate": draw, "visitante": away}


@dataclass(frozen=True)
class EloRun:
    fit: EloFit
    probs: list[Probs]  # en el orden de entrada, cada una hecha solo con lo anterior a su día


def run(matches: Sequence[Match], params: EloParams, state: EloFit | None = None) -> EloRun:
    """Recorre los partidos por fecha, prediciendo cada día antes de actualizar con él."""
    if any(m.day is None for m in matches):
        raise FitError("Elo necesita la fecha de cada partido")
    ratings = dict(state.ratings) if state else {}
    last = dict(state.last_season) if state else {}
    season = state.season if state else None
    probs: list[Probs] = [(0.0, 0.0, 0.0)] * len(matches)
    order = sorted(range(len(matches)), key=lambda i: matches[i].day)  # type: ignore[arg-type, return-value]
    for day, group in groupby(order, key=lambda i: matches[i].day):
        indices = list(group)
        current = season_of(day)
        if season is None:
            season = current
        elif current > season:
            for ended in range(season, current):
                ratings = _regress(ratings, last, ended, params.carry)
            season = current
        entry = _newcomer(ratings, last, season, params.newcomer_offset)
        for i in indices:
            for team in (matches[i].home_id, matches[i].away_id):
                if team not in ratings:
                    ratings[team] = entry
                    last[team] = season
        for i in indices:
            m = matches[i]
            d = ratings[m.home_id] + params.home_advantage - ratings[m.away_id]
            probs[i] = davidson_probs(d, params.nu)
        for i in indices:
            m = matches[i]
            d = ratings[m.home_id] + params.home_advantage - ratings[m.away_id]
            local, draw, _ = davidson_probs(d, params.nu)
            outcome = outcome_index(m.home_goals, m.away_goals)
            delta = params.k * ((1.0, 0.5, 0.0)[outcome] - (local + 0.5 * draw))
            ratings[m.home_id] += delta
            ratings[m.away_id] -= delta
            last[m.home_id] = last[m.away_id] = season
    return EloRun(EloFit(params, ratings, last, season), probs)


def prequential_nll(matches: Sequence[Match], params: EloParams, scored_after: date) -> float:
    """Σ −log P(resultado real) de los partidos posteriores a `scored_after`, cada uno predicho
    solo con lo anterior (los anteriores sirven de calentamiento)."""
    result = run(matches, params)
    total = 0.0
    for m, p in zip(matches, result.probs, strict=True):
        if m.day is not None and m.day > scored_after:
            total -= math.log(p[outcome_index(m.home_goals, m.away_goals)])
    return total


def _to_params(x: Sequence[float]) -> EloParams:
    return EloParams(
        k=math.exp(x[0]),
        home_advantage=x[1],
        nu=math.exp(x[2]),
        carry=1.0 / (1.0 + math.exp(-x[3])),
        newcomer_offset=x[4],
    )


def _to_vector(p: EloParams) -> list[float]:
    return [
        math.log(p.k),
        p.home_advantage,
        math.log(p.nu),
        math.log(p.carry / (1.0 - p.carry)),
        p.newcomer_offset,
    ]


STARTS = (
    EloParams(20.0, 60.0, 0.7, 0.75, 0.0),
    EloParams(10.0, 100.0, 0.5, 0.5, -50.0),
    EloParams(30.0, 80.0, 0.9, 0.85, -25.0),
)


def fit_params_starts(
    train: Sequence[Match], scored_after: date, starts: Sequence[EloParams] = STARTS
) -> list[tuple[float, EloParams]]:
    """Nelder-Mead desde cada punto de partida: (−logL prequential, parámetros), ordenado."""
    found = []
    for start in starts:
        result = minimize(
            lambda x: prequential_nll(train, _to_params(x), scored_after),
            _to_vector(start),
            method="Nelder-Mead",
            options={"maxiter": 800, "xatol": 1e-3, "fatol": 1e-6},
        )
        found.append((float(result.fun), _to_params(result.x)))
    return sorted(found, key=lambda pair: pair[0])


def fit_params(
    train: Sequence[Match], scored_after: date, starts: Sequence[EloParams] = STARTS
) -> EloParams:
    """Hiperparámetros por máxima verosimilitud prequential sobre los partidos posteriores a
    `scored_after` (ADR 010). Solo ve `train`."""
    return fit_params_starts(train, scored_after, starts)[0][1]

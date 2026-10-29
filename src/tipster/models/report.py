"""Informe del walk-forward estricto de una liga: Dixon-Coles, Elo y Pinnacle (ADR 011)."""

import sqlite3
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
from numpy.typing import NDArray

from tipster.errors import FitError
from tipster.history.matches import load_market_odds, load_market_probs, load_matches
from tipster.models.dixon_coles import Floats, Ints, fit
from tipster.models.elo import EloParams, fit_params_starts, season_of
from tipster.models.evaluation import outcome_index
from tipster.models.tuning import predict_matches
from tipster.models.walk_forward import walk_forward_dixon_coles, walk_forward_elo


@dataclass(frozen=True, eq=False)
class LeagueReport:
    competition: str
    n_train: int
    n_test: int
    outcomes: Ints
    dc: Floats  # Dixon-Coles reajustado por bloques
    dc_frozen: Floats  # Dixon-Coles ajustado una vez (referencia sin reajuste)
    elo: Floats  # Elo partido a partido
    market: Floats | None  # Pinnacle sin margen, solo de los partidos con cuota
    has_market: NDArray[np.bool_]
    elo_params: EloParams
    elo_dispersion: float  # −logL del peor menos el del mejor de los inicios
    dc_fits: int
    dc_seconds: float
    elo_fit_seconds: float
    unseen: int


def evaluate_league(
    conn: sqlite3.Connection,
    competition: str,
    *,
    train_from: date,
    test_from: date,
    test_to: date,
    scored_after: date,
    half_life_days: float,
    block_days: int,
    l2: float,
) -> LeagueReport:
    history = load_matches(conn, competition, train_from, test_from - timedelta(days=1))
    test = load_matches(conn, competition, test_from, test_to)
    outcomes = np.array([outcome_index(m.home_goals, m.away_goals) for m in test])
    market = load_market_probs(conn, competition, test_from, test_to)
    has_market = np.array([p is not None for p in market])
    started = time.perf_counter()
    starts = fit_params_starts(history, scored_after)  # solo ve el historial
    elo_fit_seconds = time.perf_counter() - started
    best_nll, params = starts[0]
    wf = walk_forward_dixon_coles(
        history, test, half_life_days=half_life_days, block_days=block_days, l2=l2
    )
    return LeagueReport(
        competition=competition,
        n_train=len(history),
        n_test=len(test),
        outcomes=outcomes,
        dc=wf.probs,
        dc_frozen=predict_matches(fit(history, half_life_days=half_life_days, l2=l2), test)[0],
        elo=walk_forward_elo(history, test, params),
        market=np.array([p for p in market if p is not None]) if has_market.any() else None,
        has_market=has_market,
        elo_params=params,
        elo_dispersion=starts[-1][0] - best_nll,
        dc_fits=wf.fits,
        dc_seconds=wf.seconds,
        elo_fit_seconds=elo_fit_seconds,
        unseen=wf.unseen,
    )


BLIND_FROM = date(2024, 8, 1)  # 2024/25 es el test ciego (ADR 007, 012): no se usa para elegir nada


@dataclass(frozen=True, eq=False)
class ValidationData:
    raw_odds: Floats  # cierre crudo de Pinnacle 1X2, solo de los partidos con cuota
    p_model: Floats  # Dixon-Coles reajustado diariamente (walk-forward), mismos partidos
    outcomes: Ints
    folds: Ints  # año de inicio de la temporada de cada partido
    competitions: tuple[str, ...]
    without_odds: int
    seconds: float


def build_validation(
    conn: sqlite3.Connection,
    competitions: Sequence[str],
    *,
    train_from: date,
    val_from: date,
    val_to: date,
    half_life_days: float,
    l2: float,
    block_days: int,
) -> ValidationData:
    """Predicciones walk-forward de Dixon-Coles y cuotas de cierre para el tramo de validación."""
    if val_to >= BLIND_FROM:
        raise FitError(f"La validación no puede llegar a {BLIND_FROM}: 2024/25 es el test ciego")
    started = time.perf_counter()
    odds, probs, outcomes, folds, names = [], [], [], [], []
    without = 0
    for competition in competitions:
        history = load_matches(conn, competition, train_from, val_from - timedelta(days=1))
        matches = load_matches(conn, competition, val_from, val_to)
        market = load_market_odds(conn, competition, val_from, val_to)
        wf = walk_forward_dixon_coles(
            history, matches, half_life_days=half_life_days, block_days=block_days, l2=l2
        )
        for match, row, p in zip(matches, market, wf.probs, strict=True):
            if row is None or match.day is None:
                without += 1
                continue
            odds.append(row)
            probs.append(p)
            outcomes.append(outcome_index(match.home_goals, match.away_goals))
            folds.append(season_of(match.day))
            names.append(competition)
    return ValidationData(
        raw_odds=np.array(odds),
        p_model=np.array(probs),
        outcomes=np.array(outcomes),
        folds=np.array(folds),
        competitions=tuple(names),
        without_odds=without,
        seconds=time.perf_counter() - started,
    )

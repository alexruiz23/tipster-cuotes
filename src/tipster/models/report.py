"""Informe del walk-forward estricto de una liga: Dixon-Coles, Elo y Pinnacle (ADR 011)."""

import sqlite3
import time
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
from numpy.typing import NDArray

from tipster.history.matches import load_market_probs, load_matches
from tipster.models.dixon_coles import Floats, Ints, fit
from tipster.models.elo import EloParams, fit_params_starts
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

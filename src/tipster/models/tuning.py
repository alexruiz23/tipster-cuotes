"""Malla de hiperparámetros de Dixon-Coles con validación walk-forward simple (ADR 009)."""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from tipster.errors import FitError
from tipster.models.dixon_coles import DixonColesFit, Floats, Match, fit
from tipster.models.evaluation import brier, log_loss, outcome_index


@dataclass(frozen=True)
class GridResult:
    half_life_days: float | None
    l2: float
    log_loss: float
    brier: float
    unseen: int  # partidos de prueba con algún equipo sin historial (equipo medio)
    error: str | None = None


def predict_matches(model: DixonColesFit, matches: Sequence[Match]) -> tuple[Floats, int]:
    """Probabilidades 1X2 de cada partido y cuántos incluyen un equipo desconocido."""
    probs = np.array(
        [
            [p["local"], p["empate"], p["visitante"]]
            for p in (model.predict_proba(m.home_id, m.away_id) for m in matches)
        ]
    )
    unseen = sum(not (model.knows(m.home_id) and model.knows(m.away_id)) for m in matches)
    return probs, unseen


def grid_search(
    train: Sequence[Match],
    test: Sequence[Match],
    *,
    half_lives: Sequence[float | None],
    l2s: Sequence[float],
) -> list[GridResult]:
    """Ajusta con `train` (nunca ve `test`) cada combinación y la puntúa en `test`.

    Devuelve las filas por log-loss creciente; las celdas que no convergen van al final.
    """
    outcomes = np.array([outcome_index(m.home_goals, m.away_goals) for m in test])
    results = []
    for half_life in half_lives:
        for l2 in l2s:
            try:
                model = fit(train, half_life_days=half_life, l2=l2)
            except FitError as exc:
                results.append(GridResult(half_life, l2, np.nan, np.nan, 0, str(exc)))
                continue
            probs, unseen = predict_matches(model, test)
            results.append(
                GridResult(half_life, l2, log_loss(probs, outcomes), brier(probs, outcomes), unseen)
            )
    return sorted(results, key=lambda r: (r.error is not None, r.log_loss))

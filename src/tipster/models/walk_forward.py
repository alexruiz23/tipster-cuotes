"""Walk-forward estricto (ADR 011): cada bloque se predice solo con datos anteriores a su fecha."""

import time
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np

from tipster.errors import FitError
from tipster.models.dixon_coles import Floats, Match, fit
from tipster.models.elo import EloParams, run


@dataclass(frozen=True, eq=False)
class WalkForwardResult:
    probs: Floats  # (n, 3): local, empate, visitante, en el orden de la prueba
    fits: int  # ajustes hechos
    seconds: float  # tiempo de cómputo
    unseen: int  # partidos con algún equipo sin historial (equipo medio)


def _day(match: Match) -> date:
    if match.day is None:
        raise FitError("El walk-forward necesita la fecha de cada partido")
    return match.day


def _check(history: Sequence[Match], test: Sequence[Match]) -> None:
    if history and test and max(_day(m) for m in history) >= min(_day(m) for m in test):
        raise FitError("La prueba debe ser posterior a todo el historial")


def day_blocks(test: Sequence[Match], block_days: int) -> list[list[int]]:
    """Índices de `test` por bloque cronológico: bloque = (día − primer día) // `block_days`."""
    days = [_day(m) for m in test]
    first = min(days)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in sorted(range(len(test)), key=lambda i: (days[i], i)):
        groups[(days[i] - first).days // block_days].append(i)
    return [groups[key] for key in sorted(groups)]


def walk_forward_dixon_coles(
    history: Sequence[Match],
    test: Sequence[Match],
    *,
    half_life_days: float,
    block_days: int = 1,
) -> WalkForwardResult:
    """Reajusta Dixon-Coles antes de cada bloque con el historial y todo lo de la prueba anterior
    a la primera fecha del bloque (estrictamente anterior), y predice el bloque."""
    _check(history, test)
    probs = np.zeros((len(test), 3))
    unseen = fits = 0
    started = time.perf_counter()
    for block in day_blocks(test, block_days):
        first = min(_day(test[i]) for i in block)
        training = [*history, *(m for m in test if _day(m) < first)]
        model = fit(training, half_life_days=half_life_days)
        fits += 1
        for i in block:
            p = model.predict_proba(test[i].home_id, test[i].away_id)
            probs[i] = (p["local"], p["empate"], p["visitante"])
            unseen += not (model.knows(test[i].home_id) and model.knows(test[i].away_id))
    return WalkForwardResult(probs, fits, time.perf_counter() - started, unseen)


def walk_forward_elo(history: Sequence[Match], test: Sequence[Match], params: EloParams) -> Floats:
    """Elo partido a partido: pasada prequential por todo el historial y la prueba (cada día se
    predice antes de actualizar con él); devuelve las probabilidades de la prueba."""
    _check(history, test)
    return np.array(run([*history, *test], params).probs[len(history) :])

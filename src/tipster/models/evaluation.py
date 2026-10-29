"""Métricas del 1X2 (ADR 009). Columnas de las probabilidades: local, empate, visitante."""

import numpy as np

from tipster.models.dixon_coles import Floats, Ints


def outcome_index(home_goals: int, away_goals: int) -> int:
    """0 = local, 1 = empate, 2 = visitante."""
    return 0 if home_goals > away_goals else 1 if home_goals == away_goals else 2


def log_loss(probs: Floats, outcomes: Ints) -> float:
    """Media de −ln p(resultado real)."""
    return float(-np.log(probs[np.arange(len(outcomes)), outcomes]).mean())


def brier(probs: Floats, outcomes: Ints) -> float:
    """Media de Σ_k (p_k − o_k)² (suma de los tres términos, sin dividir entre 3)."""
    observed = np.eye(3)[outcomes]
    return float(((probs - observed) ** 2).sum(axis=1).mean())

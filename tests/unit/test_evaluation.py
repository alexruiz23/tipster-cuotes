"""Métricas 1X2 (ADR 009) con casos calculados a mano."""

import math

import numpy as np
import pytest

from tipster.models.evaluation import brier, log_loss, outcome_index, paired_difference


def test_indice_del_resultado() -> None:
    assert [outcome_index(2, 1), outcome_index(1, 1), outcome_index(0, 3)] == [0, 1, 2]


def test_log_loss_y_brier_a_mano_para_un_partido() -> None:
    probs = np.array([[0.5, 0.3, 0.2]])
    # resultado local: −ln 0,5 = 0,693147 · Brier = (0,5−1)² + 0,3² + 0,2² = 0,38
    assert log_loss(probs, np.array([0])) == pytest.approx(0.6931472, abs=1e-7)
    assert brier(probs, np.array([0])) == pytest.approx(0.38, abs=1e-12)


def test_log_loss_y_brier_a_mano_para_dos_partidos() -> None:
    probs = np.array([[0.5, 0.3, 0.2], [0.2, 0.2, 0.6]])
    outcomes = np.array([0, 2])  # local y visitante
    assert log_loss(probs, outcomes) == pytest.approx(
        (-math.log(0.5) - math.log(0.6)) / 2, abs=1e-12
    )
    # segundo partido: 0,2² + 0,2² + (0,6−1)² = 0,24 → media (0,38 + 0,24) / 2
    assert brier(probs, outcomes) == pytest.approx(0.31, abs=1e-12)


def test_una_prediccion_perfecta_y_una_uniforme() -> None:
    assert brier(np.array([[1.0, 0.0, 0.0]]), np.array([0])) == 0.0
    uniform = np.full((1, 3), 1 / 3)
    assert log_loss(uniform, np.array([1])) == pytest.approx(math.log(3), abs=1e-12)
    assert brier(uniform, np.array([1])) == pytest.approx(2 / 3, abs=1e-12)


def test_diferencia_pareada_de_log_loss_a_mano() -> None:
    a = np.array([[0.5, 0.3, 0.2], [0.4, 0.4, 0.2]])
    b = np.array([[0.25, 0.5, 0.25], [0.4, 0.4, 0.2]])
    outcomes = np.array([0, 1])
    # por partido (a − b): −ln 0,5 + ln 0,25 = −0,693147 y −ln 0,4 + ln 0,4 = 0
    # media −0,346574; desviación (n−1) = 0,693147/√2 = 0,490129; error típico = 0,490129/√2
    mean, se = paired_difference(a, b, outcomes)
    assert mean == pytest.approx(-0.3465736, abs=1e-7)
    assert se == pytest.approx(0.3465736, abs=1e-7)
    assert paired_difference(a, a, outcomes) == (0.0, 0.0)

"""Núcleo de Dixon-Coles (ADR 008) con casos calculados a mano."""

import math

import numpy as np
import pytest

from tipster.models.dixon_coles import Match, log_likelihood, prepare, score_matrix, tau

LAM = math.exp(0.2)  # λ = exp(a + d + γ) con a = d = 0 y γ = 0,2
MU = 1.0
RHO = -0.1

# 4 equipos, todos contra todos (una vuelta). Valores de log P calculados aparte con `math`:
# A-B 1-0 → -2,1267633 · A-C 0-0 → -2,1061649 · A-D 2-1 → -2,5145499
# B-C 1-1 → -1,9260926 · B-D 0-1 → -2,3516712 · C-D 3-2 → -4,1063094
TOY = [
    Match(1, 2, 1, 0),
    Match(1, 3, 0, 0),
    Match(1, 4, 2, 1),
    Match(2, 3, 1, 1),
    Match(2, 4, 0, 1),
    Match(3, 4, 3, 2),
]
TOY_LOGL = -15.1315514


@pytest.mark.parametrize(
    ("x", "y", "expected"),
    [
        (0, 0, 1 - LAM * MU * RHO),  # 1,1221403
        (0, 1, 1 + LAM * RHO),  # 0,8778597
        (1, 0, 1 + MU * RHO),  # 0,9
        (1, 1, 1 - RHO),  # 1,1
        (2, 1, 1.0),
        (0, 2, 1.0),
        (3, 3, 1.0),
    ],
)
def test_tau_casos_a_mano(x: int, y: int, expected: float) -> None:
    assert float(tau(np.array(x), np.array(y), LAM, MU, RHO)) == pytest.approx(expected, abs=1e-12)


def test_tau_valores_numericos_a_mano() -> None:
    values = [
        float(tau(np.array(x), np.array(y), LAM, MU, RHO))
        for x, y in [(0, 0), (0, 1), (1, 0), (1, 1)]
    ]
    assert values == pytest.approx([1.1221403, 0.8778597, 0.9, 1.1], abs=1e-7)


def test_tau_con_rho_cero_no_corrige_nada() -> None:
    for x, y in [(0, 0), (0, 1), (1, 0), (1, 1)]:
        assert float(tau(np.array(x), np.array(y), 1.7, 0.9, 0.0)) == 1.0


def test_log_verosimilitud_a_mano() -> None:
    data = prepare(TOY)
    value = log_likelihood(data, np.zeros(4), np.zeros(4), 0.2, RHO)
    assert value == pytest.approx(TOY_LOGL, abs=1e-6)


def test_prepare_ordena_los_ids_de_equipo() -> None:
    data = prepare([Match(30, 10, 1, 0), Match(10, 20, 2, 2)])
    assert data.team_ids == (10, 20, 30)
    assert data.home.tolist() == [2, 0]
    assert data.away.tolist() == [0, 1]


def test_la_verosimilitud_no_cambia_al_sumar_c_a_los_ataques_y_restarla_a_las_defensas() -> None:
    data = prepare(TOY)
    a = np.array([0.3, -0.1, 0.2, -0.4])
    d = np.array([0.1, 0.0, -0.2, 0.1])
    base = log_likelihood(data, a, d, 0.25, -0.05)
    shifted = log_likelihood(data, a + 0.7, d - 0.7, 0.25, -0.05)
    assert shifted == pytest.approx(base, abs=1e-12)


def test_matriz_de_marcadores_sin_correccion_es_poisson_independiente() -> None:
    m = score_matrix(LAM, MU, 0.0)
    assert m[0, 0] == pytest.approx(math.exp(-(LAM + MU)), abs=1e-12)
    assert m[2, 1] == pytest.approx(math.exp(-LAM) * LAM**2 / 2 * math.exp(-MU) * MU, abs=1e-12)


def test_matriz_de_marcadores_aplica_tau_en_los_cuatro_marcadores_bajos() -> None:
    plain = score_matrix(LAM, MU, 0.0)
    corrected = score_matrix(LAM, MU, RHO)
    for (x, y), expected in {
        (0, 0): 1.1221403,
        (0, 1): 0.8778597,
        (1, 0): 0.9,
        (1, 1): 1.1,
        (2, 2): 1.0,
    }.items():
        assert corrected[x, y] / plain[x, y] == pytest.approx(expected, abs=1e-7)


def test_matriz_de_marcadores_suma_1_y_casi_no_pierde_masa() -> None:
    for lam, mu in [(1.2, 0.9), (3.0, 1.0), (5.0, 5.0)]:
        raw = score_matrix(lam, mu, -0.1, normalize=False)
        assert raw.sum() == pytest.approx(1.0, abs=1e-6)  # la corrección τ conserva la masa
        assert score_matrix(lam, mu, -0.1).sum() == pytest.approx(1.0, abs=1e-12)

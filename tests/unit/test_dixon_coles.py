"""Núcleo de Dixon-Coles (ADR 008) con casos calculados a mano."""

import math

import numpy as np
import pytest
from scipy.optimize import check_grad

from tipster.errors import FitError
from tipster.models.dixon_coles import (
    DixonColesFit,
    Match,
    _objective,
    fit,
    log_likelihood,
    prepare,
    score_matrix,
    tau,
)

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


# -- Gradiente ---------------------------------------------------------------------------------


def test_el_gradiente_analitico_coincide_con_las_diferencias_finitas() -> None:
    data = prepare(TOY)
    # [a_1..a_3, d_1..d_4, γ, ρ] con valores que no anulan ningún término
    theta = np.array([0.2, -0.1, 0.15, 0.1, -0.05, 0.2, 0.0, 0.22, -0.08])
    error = check_grad(lambda t: _objective(t, data)[0], lambda t: _objective(t, data)[1], theta)
    assert error < 1e-5


def test_el_objetivo_es_menos_la_log_verosimilitud_con_el_ultimo_ataque_que_cierra_la_suma() -> (
    None
):
    data = prepare(TOY)
    theta = np.array([0.2, -0.1, 0.15, 0.1, -0.05, 0.2, 0.0, 0.22, -0.08])
    a = np.array([0.2, -0.1, 0.15, -0.25])  # a_4 = −(a_1 + a_2 + a_3)
    d = np.array([0.1, -0.05, 0.2, 0.0])
    value, _ = _objective(theta, data)
    assert value == pytest.approx(-log_likelihood(data, a, d, 0.22, -0.08), abs=1e-12)


# -- Ajuste ------------------------------------------------------------------------------------

TRUE_A = np.array([0.30, 0.10, -0.10, -0.30])  # suma 0
TRUE_D = np.array([0.05, -0.05, 0.10, -0.10])
TRUE_GAMMA = 0.25
TRUE_RHO = -0.10
# Tolerancias = 3 desviaciones típicas medidas en 200 simulaciones (semillas 0–199, 0 fallos):
# a 0,051 · d 0,067 · γ 0,049 · ρ 0,052. El sesgo medido es < 0,005 en γ y ρ.
TOL_A, TOL_D, TOL_GAMMA, TOL_RHO = 0.16, 0.21, 0.15, 0.16


def simulate(seed: int, repeats: int = 50) -> list[Match]:
    """Cada par ordenado de 4 equipos `repeats` veces (600 partidos con 50), con la ley de DC."""
    rng = np.random.default_rng(seed)
    matches = []
    for h in range(4):
        for v in range(4):
            if h == v:
                continue
            lam = math.exp(TRUE_A[h] + TRUE_D[v] + TRUE_GAMMA)
            mu = math.exp(TRUE_A[v] + TRUE_D[h])
            probs = score_matrix(lam, mu, TRUE_RHO).ravel()
            cells = rng.choice(probs.size, size=repeats, p=probs)
            side = int(math.sqrt(probs.size))
            matches += [Match(h + 1, v + 1, int(c) // side, int(c) % side) for c in cells]
    return matches


def test_con_6_partidos_el_maximo_no_existe_y_el_ajuste_falla_de_forma_controlada() -> None:
    # 9 parámetros libres para 12 goles: el MLE diverge y `fit` lo dice en vez de devolver nada
    with pytest.raises(FitError):
        fit(TOY)


def test_un_equipo_que_nunca_marca_hace_fallar_el_ajuste() -> None:
    matches = simulate(seed=1, repeats=10)
    matches = [
        Match(
            m.home_id,
            m.away_id,
            0 if m.home_id == 4 else m.home_goals,
            0 if m.away_id == 4 else m.away_goals,
        )
        for m in matches
    ]
    with pytest.raises(FitError):
        fit(matches)


def test_recupera_los_parametros_de_600_partidos_simulados() -> None:
    result = fit(simulate(seed=2024))
    assert result.team_ids == (1, 2, 3, 4)
    assert float(result.a.mean()) == pytest.approx(0.0, abs=1e-9)  # la restricción
    np.testing.assert_allclose(result.a, TRUE_A, atol=TOL_A)
    np.testing.assert_allclose(result.d, TRUE_D, atol=TOL_D)
    assert result.gamma == pytest.approx(TRUE_GAMMA, abs=TOL_GAMMA)
    assert result.rho == pytest.approx(TRUE_RHO, abs=TOL_RHO)
    # el óptimo no puede ser peor que los parámetros verdaderos
    truth = log_likelihood(prepare(simulate(seed=2024)), TRUE_A, TRUE_D, TRUE_GAMMA, TRUE_RHO)
    assert result.log_likelihood >= truth - 1e-6
    assert result.max_gradient <= 1e-4


# -- Predicción --------------------------------------------------------------------------------


def _fit(
    team_ids: tuple[int, ...], a: list[float], d: list[float], gamma: float, rho: float
) -> DixonColesFit:
    return DixonColesFit(
        team_ids=team_ids,
        a=np.array(a),
        d=np.array(d),
        gamma=gamma,
        rho=rho,
        log_likelihood=0.0,
        n_matches=0,
        iterations=0,
        max_gradient=0.0,
    )


def test_predict_proba_con_dos_equipos_iguales_y_sin_ventaja_a_mano() -> None:
    # λ = μ = 1, ρ = 0: P(empate) = Σ_k Poisson(k; 1)² = e⁻² · I₀(2) = 0,3085083
    probs = _fit((1, 2), [0.0, 0.0], [0.0, 0.0], 0.0, 0.0).predict_proba(1, 2)
    assert probs["empate"] == pytest.approx(0.3085083, abs=1e-6)
    assert probs["local"] == pytest.approx((1 - 0.3085083) / 2, abs=1e-6)
    assert probs["local"] == pytest.approx(probs["visitante"], abs=1e-12)
    assert sum(probs.values()) == pytest.approx(1.0, abs=1e-12)


def test_predict_proba_el_local_con_ventaja_gana_mas_que_el_visitante() -> None:
    probs = _fit((1, 2), [0.0, 0.0], [0.0, 0.0], 0.3, -0.1).predict_proba(1, 2)
    assert probs["local"] > probs["visitante"]
    assert sum(probs.values()) == pytest.approx(1.0, abs=1e-12)


def test_un_equipo_sin_historial_se_trata_como_el_equipo_medio() -> None:
    known = _fit((1, 2, 3), [0.2, -0.2, 0.0], [0.1, 0.3, 0.2], 0.25, -0.1)  # d_3 = media(d_1, d_2)
    base = _fit((1, 2), [0.2, -0.2], [0.1, 0.3], 0.25, -0.1)
    assert not base.knows(99)
    assert base.knows(1)
    assert base.predict_proba(1, 99) == pytest.approx(known.predict_proba(1, 3))
    assert base.predict_proba(99, 2) == pytest.approx(known.predict_proba(3, 2))

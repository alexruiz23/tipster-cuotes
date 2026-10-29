"""Mezcla de probabilidades y calibración multinomial (ADR 012)."""

import numpy as np
import pytest

from tipster.models.dixon_coles import Floats, Ints
from tipster.pricing.blend import (
    IDENTITY,
    Calibrator,
    blend_probs,
    fit_calibrator,
    fit_market_weight,
)

MARKET = (0.5, 0.25, 0.25)
MODEL = (0.6, 0.2, 0.2)


def test_mezcla_lineal_a_mano() -> None:
    assert blend_probs(MARKET, MODEL, 0.7) == pytest.approx((0.53, 0.235, 0.235), abs=1e-12)


def test_mezcla_logaritmica_a_mano() -> None:
    probs = blend_probs(MARKET, MODEL, 0.7, logarithmic=True)
    assert probs == pytest.approx((0.530372, 0.234814, 0.234814), abs=1e-6)
    assert sum(probs) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("logarithmic", [False, True])
def test_con_peso_1_devuelve_el_mercado_y_con_0_el_modelo(logarithmic: bool) -> None:
    assert blend_probs(MARKET, MODEL, 1.0, logarithmic=logarithmic) == pytest.approx(MARKET)
    assert blend_probs(MARKET, MODEL, 0.0, logarithmic=logarithmic) == pytest.approx(MODEL)


def test_calibrador_a_mano_y_identidad() -> None:
    probs = (0.5, 0.3, 0.2)
    c = Calibrator(beta=1.0, b_draw=float(np.log(2.0)), b_away=0.0)
    assert c.apply(probs) == pytest.approx((0.384615, 0.461538, 0.153846), abs=1e-6)
    assert IDENTITY.apply(probs) == pytest.approx(probs, abs=1e-12)


def test_beta_menor_que_1_acerca_las_probabilidades_al_reparto_uniforme() -> None:
    sharp = (0.8, 0.15, 0.05)
    softer = Calibrator(beta=0.5, b_draw=0.0, b_away=0.0).apply(sharp)
    assert softer[0] < sharp[0]
    assert softer[2] > sharp[2]
    assert sum(softer) == pytest.approx(1.0, abs=1e-12)


def _simulate(true: Calibrator, n: int = 6000, seed: int = 0) -> tuple[Floats, Ints]:
    rng = np.random.default_rng(seed)
    probs = rng.dirichlet([4.0, 2.5, 3.0], size=n)
    calibrated = np.array([true.apply(tuple(p)) for p in probs])
    outcomes = np.array([rng.choice(3, p=p) for p in calibrated])
    return probs, outcomes


def test_fit_calibrator_recupera_los_parametros_de_datos_simulados() -> None:
    true = Calibrator(beta=0.8, b_draw=0.3, b_away=-0.1)
    probs, outcomes = _simulate(true)
    fitted = fit_calibrator(probs, outcomes)
    # tolerancias = 3 desviaciones típicas medidas en 30 simulaciones: β 0,028 · b_empate 0,034 ·
    # b_visitante 0,028 (sesgo < 0,011)
    assert fitted.beta == pytest.approx(true.beta, abs=0.09)
    assert fitted.b_draw == pytest.approx(true.b_draw, abs=0.11)
    assert fitted.b_away == pytest.approx(true.b_away, abs=0.09)


def test_fit_calibrator_con_datos_ya_calibrados_se_queda_cerca_de_la_identidad() -> None:
    probs, outcomes = _simulate(IDENTITY, seed=1)
    fitted = fit_calibrator(probs, outcomes)
    assert fitted.beta == pytest.approx(1.0, abs=0.1)
    assert abs(fitted.b_draw) < 0.1 and abs(fitted.b_away) < 0.1


def test_fit_market_weight_recupera_el_peso_verdadero() -> None:
    rng = np.random.default_rng(3)
    market = rng.dirichlet([4.0, 2.5, 3.0], size=8000)
    model = rng.dirichlet([4.0, 2.5, 3.0], size=8000)
    truth = np.array(
        [blend_probs(tuple(a), tuple(b), 0.7) for a, b in zip(market, model, strict=True)]
    )
    outcomes = np.array([rng.choice(3, p=p) for p in truth])
    # tolerancia = 3 desviaciones típicas medidas en 30 simulaciones (0,016; sesgo 0,001)
    assert fit_market_weight(model, market, outcomes) == pytest.approx(0.7, abs=0.05)


def test_si_el_modelo_no_aporta_nada_el_peso_del_mercado_es_1() -> None:
    rng = np.random.default_rng(4)
    market = rng.dirichlet([4.0, 2.5, 3.0], size=8000)
    model = rng.dirichlet([4.0, 2.5, 3.0], size=8000)  # ruido independiente del resultado
    outcomes = np.array([rng.choice(3, p=p) for p in market])
    assert fit_market_weight(model, market, outcomes) == 1.0


def test_el_peso_nunca_baja_del_minimo() -> None:
    rng = np.random.default_rng(5)
    market = rng.dirichlet([4.0, 2.5, 3.0], size=4000)
    model = rng.dirichlet([4.0, 2.5, 3.0], size=4000)
    outcomes = np.array([rng.choice(3, p=p) for p in model])  # solo el modelo acierta
    assert fit_market_weight(model, market, outcomes) == 0.5

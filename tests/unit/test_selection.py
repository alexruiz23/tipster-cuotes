"""Selección de devig, calibrador y mezcla con datos de validación (ADR 012)."""

import numpy as np
import pytest

from tipster.models.dixon_coles import Floats, Ints
from tipster.models.selection import select_blend
from tipster.pricing.blend import Calibrator
from tipster.pricing.devig import DevigMethod

N = 6000


def _world(
    seed: int,
    *,
    market_noise: float,
    model_noise: float,
    model_calibrator: Calibrator | None = None,
) -> tuple[Floats, Floats, Ints, Ints]:
    """Verdad q por partido; mercado y modelo la ven con ruido; cuota cruda = 1/(p·1,03)."""
    rng = np.random.default_rng(seed)
    q = rng.dirichlet([4.0, 2.5, 3.0], size=N)

    def noisy(sd: float) -> Floats:
        raw = q * np.exp(rng.normal(0, sd, size=q.shape))
        result: Floats = raw / raw.sum(axis=1, keepdims=True)
        return result

    p_market = noisy(market_noise)
    p_model = noisy(model_noise)
    if model_calibrator is not None:
        p_model = np.array([model_calibrator.apply(tuple(p)) for p in p_model])
    outcomes = np.array([rng.choice(3, p=p) for p in q])
    raw_odds = 1.0 / (p_market * 1.03)
    folds = np.where(np.arange(N) < N // 2, 2021, 2022)
    return raw_odds, p_model, outcomes, folds


def test_si_el_modelo_solo_aporta_ruido_el_peso_del_mercado_es_1() -> None:
    odds, model, outcomes, folds = _world(0, market_noise=0.1, model_noise=0.6)
    d = select_blend(odds, model, outcomes, folds)
    assert d.w_market == 1.0
    assert d.devig is DevigMethod.MULTIPLICATIVE
    # un modelo ruidoso está sobreconfiado: el calibrador sí lo suaviza, pero no le da peso
    assert d.calibrator_active and d.losses["modelo_calibrado"] < d.losses["modelo_bruto"]
    assert d.losses["mezcla"] == pytest.approx(d.losses["mercado"], abs=1e-9)


def test_si_el_mercado_es_peor_que_el_modelo_el_modelo_pesa() -> None:
    odds, model, outcomes, folds = _world(1, market_noise=0.5, model_noise=0.1)
    d = select_blend(odds, model, outcomes, folds)
    assert d.w_market < 0.95
    assert d.losses["mezcla"] < d.losses["mercado"]
    assert d.gain_vs_market[0] < -d.gain_vs_market[1]  # mejora de más de un error típico


def test_un_modelo_mal_calibrado_activa_el_calibrador() -> None:
    bad = Calibrator(beta=1.8, b_draw=-0.4, b_away=0.2)  # demasiado seguro y sin empates
    odds, model, outcomes, folds = _world(
        2, market_noise=0.5, model_noise=0.1, model_calibrator=bad
    )
    d = select_blend(odds, model, outcomes, folds)
    assert d.calibrator_active
    assert d.calibrator.beta < 1.0  # lo suaviza
    assert d.losses["modelo_calibrado"] < d.losses["modelo_bruto"]


def test_un_modelo_ya_calibrado_no_activa_el_calibrador() -> None:
    odds, model, outcomes, folds = _world(3, market_noise=0.5, model_noise=0.1)
    assert not select_blend(odds, model, outcomes, folds).calibrator_active


def test_el_umbral_de_revision_manual_es_el_percentil_98_de_la_diferencia() -> None:
    odds, model, outcomes, folds = _world(3, market_noise=0.5, model_noise=0.1)
    d = select_blend(odds, model, outcomes, folds)
    assert not d.calibrator_active  # así el modelo usado es el bruto
    p_market = (1 / odds) / (1 / odds).sum(axis=1, keepdims=True)  # multiplicativo
    gaps = np.abs(p_market - model).ravel()
    assert d.max_model_gap == pytest.approx(np.percentile(gaps, 98), rel=0.02)


def test_el_resultado_se_serializa_con_todo_lo_necesario() -> None:
    odds, model, outcomes, folds = _world(5, market_noise=0.1, model_noise=0.6)
    data = select_blend(odds, model, outcomes, folds).to_json()
    assert {"devig", "logarithmic", "w_market", "calibrator", "calibrator_active", "max_model_gap",
            "n_matches", "losses"} <= set(data)  # fmt: skip

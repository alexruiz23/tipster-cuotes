"""Elección de devig, calibrador y mezcla con los datos de validación (ADR 012).

Solo ve lo que se le pasa (cuotas de cierre, probabilidades del modelo y resultados de la
validación): no hay forma de que lea la temporada de prueba.
"""

from dataclasses import dataclass

import numpy as np

from tipster.errors import DevigError
from tipster.models.dixon_coles import Floats, Ints
from tipster.models.evaluation import log_loss, paired_difference
from tipster.pricing.blend import (
    IDENTITY,
    Calibrator,
    blend_array,
    fit_calibrator,
    fit_market_weight,
)
from tipster.pricing.devig import DevigMethod, devig

GAP_PERCENTILE = 98  # REVISIÓN MANUAL: percentil de |p_mercado − p_modelo| en la validación


@dataclass(frozen=True, eq=False)
class BlendDecision:
    devig: DevigMethod
    devig_losses: dict[str, float | None]  # None: el método falló en alguna cuota
    logarithmic: bool
    w_market: float
    calibrator: Calibrator
    calibrator_active: bool
    max_model_gap: float
    losses: dict[str, float]
    gain_vs_market: tuple[float, float]  # diferencia pareada de log-loss mezcla − mercado
    calibrator_gain: tuple[float, float] | None  # validación cruzada: calibrado − bruto
    n_matches: int

    def to_json(self) -> dict[str, object]:
        return {
            "devig": self.devig.value,
            "devig_losses": self.devig_losses,
            "logarithmic": self.logarithmic,
            "w_market": self.w_market,
            "calibrator": {
                "beta": self.calibrator.beta,
                "b_draw": self.calibrator.b_draw,
                "b_away": self.calibrator.b_away,
            },
            "calibrator_active": self.calibrator_active,
            "max_model_gap": self.max_model_gap,
            "losses": self.losses,
            "gain_vs_market": list(self.gain_vs_market),
            "calibrator_gain": None if self.calibrator_gain is None else list(self.calibrator_gain),
            "n_matches": self.n_matches,
        }


def _devig_all(raw_odds: Floats, method: DevigMethod) -> Floats | None:
    try:
        return np.array([devig(row, method) for row in raw_odds])
    except DevigError:
        return None


def _better(candidate: Floats, reference: Floats, outcomes: Ints) -> bool:
    """¿Mejora el log-loss en más de un error típico (diferencia pareada)?"""
    mean, se = paired_difference(candidate, reference, outcomes)
    return mean < -se


def select_blend(raw_odds: Floats, p_model: Floats, outcomes: Ints, folds: Ints) -> BlendDecision:
    """Elige, en este orden y solo con estos datos:

    1. devig de `p_mercado` (menor log-loss; si no mejora al multiplicativo en más de un error
       típico, el multiplicativo);
    2. calibrador del modelo (validación cruzada por `folds`; activo solo si mejora en más de un
       error típico);
    3. forma de la mezcla (lineal salvo que la logarítmica mejore en más de un error típico) y el
       peso del mercado (mínimo 0,5; por encima de 0,95, 1).
    """
    candidates = {m: _devig_all(raw_odds, m) for m in DevigMethod}
    devig_losses = {
        m.value: None if p is None else log_loss(p, outcomes) for m, p in candidates.items()
    }
    base = candidates[DevigMethod.MULTIPLICATIVE]
    assert base is not None
    chosen, p_market = DevigMethod.MULTIPLICATIVE, base
    valid = {m: p for m, p in candidates.items() if p is not None}
    best = min(valid, key=lambda m: log_loss(valid[m], outcomes))
    if best is not DevigMethod.MULTIPLICATIVE and _better(valid[best], base, outcomes):
        chosen, p_market = best, valid[best]

    cross = np.zeros_like(p_model)
    for fold in np.unique(folds):
        train, test = folds != fold, folds == fold
        if train.any():
            calibrator = fit_calibrator(p_model[train], outcomes[train])
            cross[test] = [calibrator.apply((a, b, c)) for a, b, c in p_model[test]]
        else:
            cross[test] = p_model[test]
    cross_fitted = len(np.unique(folds)) > 1
    active = cross_fitted and _better(cross, p_model, outcomes)
    calibrator = fit_calibrator(p_model, outcomes) if active else IDENTITY
    used = np.array([calibrator.apply((a, b, c)) for a, b, c in p_model]) if active else p_model

    fits = {
        log: fit_market_weight(used, p_market, outcomes, logarithmic=log) for log in (False, True)
    }
    mixes = {log: blend_array(p_market, used, fits[log], logarithmic=log) for log in (False, True)}
    logarithmic = _better(mixes[True], mixes[False], outcomes)
    w_market = fits[logarithmic]
    final = mixes[logarithmic]
    return BlendDecision(
        devig=chosen,
        devig_losses=devig_losses,
        logarithmic=logarithmic and w_market < 1.0,
        w_market=w_market,
        calibrator=calibrator,
        calibrator_active=bool(active),
        max_model_gap=float(np.percentile(np.abs(p_market - used), GAP_PERCENTILE)),
        losses={
            "mercado": log_loss(p_market, outcomes),
            "modelo_bruto": log_loss(p_model, outcomes),
            "modelo_calibrado": log_loss(used, outcomes),
            "mezcla_lineal": log_loss(mixes[False], outcomes),
            "mezcla_logaritmica": log_loss(mixes[True], outcomes),
            "mezcla": log_loss(final, outcomes),
        },
        gain_vs_market=paired_difference(final, p_market, outcomes),
        calibrator_gain=paired_difference(cross, p_model, outcomes) if cross_fitted else None,
        n_matches=len(outcomes),
    )

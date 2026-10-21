"""Cuota justa y EV con casos calculados a mano (docs/fase-1/plan.md §6)."""

from fractions import Fraction

import pytest

from tipster.errors import DevigError
from tipster.pricing.value import expected_value, fair_odds

P_LOCAL = 14 / 29  # p del local tras devig multiplicativo del caso base 2.00 / 3.50 / 4.00


def test_cuota_justa_es_la_inversa_de_la_probabilidad() -> None:
    assert fair_odds(P_LOCAL) == pytest.approx(float(Fraction(29, 14)), abs=1e-12)  # ≈ 2.0714286
    assert fair_odds(0.5) == 2.0


def test_ev_caso_a_mano() -> None:
    # 2.2 × 14/29 − 1 = 30.8/29 − 1 = 1.8/29 = 9/145
    assert expected_value(P_LOCAL, 2.20) == pytest.approx(float(Fraction(9, 145)), abs=1e-12)


def test_ev_es_cero_a_la_cuota_justa_y_negativo_por_debajo() -> None:
    assert expected_value(P_LOCAL, fair_odds(P_LOCAL)) == pytest.approx(0.0, abs=1e-12)
    assert expected_value(0.5, 1.90) == pytest.approx(-0.05, abs=1e-12)


@pytest.mark.parametrize("p", [0.0, -0.1, 1.1, float("nan")])
def test_probabilidad_fuera_de_rango_lanza_error(p: float) -> None:
    with pytest.raises(DevigError):
        fair_odds(p)
    with pytest.raises(DevigError):
        expected_value(p, 2.0)

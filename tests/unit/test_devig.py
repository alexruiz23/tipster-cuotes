"""Devig con casos calculados a mano (docs/fase-1/plan.md §6).

Caso base: referencia 1X2 2.00 / 3.50 / 4.00 → q = 1/2, 2/7, 1/4 → Q = Σq = 29/28.
"""

from collections.abc import Callable, Sequence
from fractions import Fraction
from itertools import pairwise

import pytest

from tipster.errors import DevigError
from tipster.pricing.devig import DevigMethod, devig, devig_additive, devig_multiplicative

Devig = Callable[[Sequence[float]], tuple[float, ...]]

BASE = (2.00, 3.50, 4.00)
METHODS: dict[str, Devig] = {
    "multiplicativo": devig_multiplicative,
    "aditivo": devig_additive,
}


def _close(actual: Sequence[float], expected: Sequence[float | Fraction], tol: float) -> None:
    assert len(actual) == len(expected)
    for a, e in zip(actual, expected, strict=True):
        assert a == pytest.approx(float(e), abs=tol)


def test_multiplicativo_caso_base() -> None:
    # p_i = q_i / Q = (1/2, 2/7, 1/4) · 28/29
    _close(devig_multiplicative(BASE), [Fraction(14, 29), Fraction(8, 29), Fraction(7, 29)], 1e-12)


def test_aditivo_caso_base() -> None:
    # (Q − 1)/n = (1/28)/3 = 1/84 → p = 42/84 − 1/84, 24/84 − 1/84, 21/84 − 1/84
    _close(devig_additive(BASE), [Fraction(41, 84), Fraction(23, 84), Fraction(20, 84)], 1e-12)


def test_aditivo_con_probabilidad_negativa_lanza_error() -> None:
    # q = 0.714286, 0.344828, 0.01 → (Q − 1)/3 = 0.023038 → p₃ = 0.01 − 0.023038 < 0
    with pytest.raises(DevigError):
        devig_additive((1.40, 2.90, 100.0))


INVARIANT_CASES = [BASE, (1.80, 2.10), (1.90, 1.90), (1.25, 4.50), (1.50, 4.20, 6.50)]


@pytest.mark.parametrize("name", list(METHODS))
@pytest.mark.parametrize("odds", INVARIANT_CASES)
def test_invariantes(name: str, odds: tuple[float, ...]) -> None:
    p = METHODS[name](odds)
    assert sum(p) == pytest.approx(1.0, abs=1e-12)
    assert all(0 < x < 1 for x in p)
    # A menor cuota, mayor probabilidad (se conserva el orden).
    by_odds = [x for _, x in sorted(zip(odds, p, strict=True))]
    assert all(a >= b for a, b in pairwise(by_odds))


@pytest.mark.parametrize("name", list(METHODS))
def test_cuotas_iguales_dan_probabilidades_iguales(name: str) -> None:
    _close(METHODS[name]((1.90, 1.90)), [0.5, 0.5], 1e-12)


@pytest.mark.parametrize("name", list(METHODS))
@pytest.mark.parametrize(
    ("odds", "expected"), [((2.0, 2.0), (0.5, 0.5)), ((2.0, 4.0, 4.0), (0.5, 0.25, 0.25))]
)
def test_libro_sin_margen_devuelve_q(
    name: str, odds: tuple[float, ...], expected: tuple[float, ...]
) -> None:
    _close(METHODS[name](odds), expected, 1e-12)


@pytest.mark.parametrize("name", list(METHODS))
@pytest.mark.parametrize(
    "odds",
    [
        (2.0,),  # menos de 2 cuotas
        (1.0, 3.0),  # cuota ≤ 1
        (2.0, float("nan")),  # no finita
        (2.0, float("inf")),
        (2.2, 2.2),  # Q = 0.909 < 1: margen negativo, anomalía de datos
    ],
)
def test_entradas_invalidas_lanzan_error(name: str, odds: tuple[float, ...]) -> None:
    with pytest.raises(DevigError):
        METHODS[name](odds)


@pytest.mark.parametrize("method", [m for m in DevigMethod if m.value in METHODS])
def test_devig_despacha_al_metodo_pedido(method: DevigMethod) -> None:
    assert devig(BASE, method) == METHODS[method.value](BASE)

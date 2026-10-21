"""Devig con casos calculados a mano (docs/fase-1/plan.md §6).

Caso base: referencia 1X2 2.00 / 3.50 / 4.00 → q = 1/2, 2/7, 1/4 → Q = Σq = 29/28.

Las constantes de power y Shin se calcularon fuera del código del proyecto, por bisección con
aritmética decimal de 50 dígitos sobre las ecuaciones Σ q_i^k = 1 (power) y Σ p_i(z) = 1 (Shin).
El test las fija: no compara la implementación consigo misma.
"""

from collections.abc import Callable, Sequence
from fractions import Fraction
from itertools import pairwise

import pytest

from tipster.errors import DevigError
from tipster.pricing.devig import (
    DevigMethod,
    devig,
    devig_additive,
    devig_multiplicative,
    devig_power,
    devig_shin,
    power_exponent,
    shin_z,
)

Devig = Callable[[Sequence[float]], tuple[float, ...]]

BASE = (2.00, 3.50, 4.00)
METHODS: dict[str, Devig] = {
    "multiplicativo": devig_multiplicative,
    "aditivo": devig_additive,
    "power": devig_power,
    "shin": devig_shin,
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


def test_power_caso_base() -> None:
    assert power_exponent(BASE) == pytest.approx(1.034636783579165, abs=1e-9)
    _close(devig_power(BASE), [0.488138759923535, 0.273581791136778, 0.238279448939687], 1e-9)


def test_power_dos_resultados() -> None:
    odds = (1.80, 2.10)
    assert power_exponent(odds) == pytest.approx(1.047439088610018, abs=1e-9)
    _close(devig_power(odds), [0.540278393591849, 0.459721606408151], 1e-9)


def test_shin_caso_base_distinto_del_aditivo() -> None:
    """Con 3 resultados Shin no coincide con el aditivo: detecta un Shin hecho como aditivo."""
    assert shin_z(BASE) == pytest.approx(0.017891311770305, abs=1e-9)
    shin = devig_shin(BASE)
    _close(shin, [0.486733634762945, 0.274328396122804, 0.238937969114251], 1e-9)
    additive = devig_additive(BASE)  # 0.488095 / 0.273810 / 0.238095
    assert max(abs(a - b) for a, b in zip(shin, additive, strict=True)) > 1e-3


@pytest.mark.parametrize(
    ("odds", "z", "expected"),
    [
        ((1.80, 2.10), Fraction(407, 12818), (Fraction(34, 63), Fraction(29, 63))),
        ((1.50, 2.50), Fraction(14, 209), (Fraction(19, 30), Fraction(11, 30))),
    ],
)
def test_shin_dos_resultados_con_z_exacto(
    odds: tuple[float, float], z: Fraction, expected: tuple[Fraction, Fraction]
) -> None:
    """Valores de Shin calculados con la ecuación de Shin y su z exacto.

    La ecuación p = (√(z² + 4(1−z)·q²/Q) − z) / (2(1−z)) equivale a (1−z)·p² + z·p = q²/Q, es decir,
    z = (q²/Q − p²) / (p(1−p)). Ejemplo 1.80/2.10: q = 5/9, 10/21; Q = 65/63; con p₁ = 34/63,
    z = ((25/81)(63/65) − (34/63)²) / ((34/63)(29/63)) = 407/12818, y el residuo de la ecuación
    es exactamente 0 en las dos selecciones.
    """
    assert shin_z(odds) == pytest.approx(float(z), abs=1e-12)
    _close(devig_shin(odds), expected, 1e-12)


@pytest.mark.parametrize("odds", [(1.80, 2.10), (1.50, 2.50), (1.25, 4.50)])
def test_shin_y_aditivo_coinciden_exactamente_con_dos_resultados(odds: tuple[float, float]) -> None:
    """Equivalencia exacta para n = 2.

    Prueba: con p_i = q_i − (Q − 1)/2 (aditivo), z = (q_i²/Q − p_i²) / (p_i(1 − p_i)) es el mismo
    para las dos selecciones. El denominador coincide porque p₂ = 1 − p₁. Los numeradores también:
    (q₁² − q₂²)/Q = (q₁ − q₂)(q₁ + q₂)/Q = q₁ − q₂, y p₁² − p₂² = (p₁ − p₂)(p₁ + p₂) = q₁ − q₂.
    Luego el resultado aditivo cumple la ecuación de Shin con un único z. (1.25/4.50: p = 71/90,
    19/90; z = 697/31027.)
    """
    _close(devig_shin(odds), devig_additive(odds), 1e-12)


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

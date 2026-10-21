"""Devig: de cuotas decimales a probabilidades sin margen.

Notación: q_i = 1 / cuota_i (probabilidad implícita) y Q = Σ q_i (1 + margen).
Todos los métodos devuelven las probabilidades en el mismo orden que las cuotas de entrada.
"""

import math
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from types import MappingProxyType

from scipy.optimize import brentq

from tipster.errors import DevigError

# Tolerancia para considerar que un libro no tiene margen (Q = 1).
FAIR_BOOK_TOL = 1e-12


class DevigMethod(StrEnum):
    MULTIPLICATIVE = "multiplicativo"
    ADDITIVE = "aditivo"
    POWER = "power"
    SHIN = "shin"


def _implied(odds: Sequence[float]) -> tuple[list[float], float]:
    """Valida las cuotas y devuelve (q, Q)."""
    if len(odds) < 2:
        raise DevigError(f"Hacen falta al menos 2 cuotas; hay {len(odds)}")
    for price in odds:
        if not math.isfinite(price) or price <= 1:
            raise DevigError(f"Cuota inválida: {price!r} (debe ser finita y mayor que 1)")
    q = [1 / price for price in odds]
    total = math.fsum(q)
    if total < 1 - FAIR_BOOK_TOL:
        # Un libro de referencia con margen negativo indica datos incoherentes (cuotas de
        # momentos distintos, suspensión…): no se intenta corregirlo.
        raise DevigError(f"Margen negativo: Σ 1/cuota = {total:.6f} < 1")
    return q, total


def _is_fair(total: float) -> bool:
    return abs(total - 1) <= FAIR_BOOK_TOL


def devig_multiplicative(odds: Sequence[float]) -> tuple[float, ...]:
    """p_i = q_i / Q."""
    q, total = _implied(odds)
    return tuple(x / total for x in q)


def devig_additive(odds: Sequence[float]) -> tuple[float, ...]:
    """p_i = q_i − (Q − 1)/n. Lanza DevigError si algún p_i ≤ 0."""
    q, total = _implied(odds)
    if _is_fair(total):
        return tuple(q)
    share = (total - 1) / len(q)
    probabilities = tuple(x - share for x in q)
    if any(p <= 0 for p in probabilities):
        raise DevigError(
            f"El método aditivo da una probabilidad ≤ 0 (margen por selección {share:.6f})"
        )
    return probabilities


def _solve(
    func: Callable[[float], float], low: float, high: float, tol: float, max_iter: int
) -> float:
    try:
        root = brentq(func, low, high, xtol=tol, maxiter=max_iter)
    except (ValueError, RuntimeError) as exc:  # sin cambio de signo o sin convergencia
        raise DevigError(f"No converge: {exc}") from exc
    return float(root)


def power_exponent(odds: Sequence[float], *, tol: float = 1e-12, max_iter: int = 200) -> float:
    """k tal que Σ q_i^k = 1. Con margen positivo, k > 1."""
    q, total = _implied(odds)
    if _is_fair(total):
        return 1.0

    def excess(k: float) -> float:
        return math.fsum(x**k for x in q) - 1

    # excess(1) = Q − 1 > 0 y decrece con k (q_i < 1): se busca un extremo con excess < 0.
    high = 2.0
    while excess(high) > 0:
        high *= 2
        if high > 1e6:
            raise DevigError("No se encuentra el exponente del método power")
    return _solve(excess, 1.0, high, tol, max_iter)


def devig_power(
    odds: Sequence[float], *, tol: float = 1e-12, max_iter: int = 200
) -> tuple[float, ...]:
    """p_i = q_i^k, con k tal que Σ q_i^k = 1."""
    q, _ = _implied(odds)
    k = power_exponent(odds, tol=tol, max_iter=max_iter)
    powered = [x**k for x in q]
    total = math.fsum(powered)
    return tuple(x / total for x in powered)


def _shin_probabilities(q: Sequence[float], total: float, z: float) -> list[float]:
    return [(math.sqrt(z * z + 4 * (1 - z) * x * x / total) - z) / (2 * (1 - z)) for x in q]


def shin_z(odds: Sequence[float], *, tol: float = 1e-12, max_iter: int = 200) -> float:
    """Proporción z de apostadores informados del modelo de Shin, tal que Σ p_i(z) = 1."""
    q, total = _implied(odds)
    if _is_fair(total):
        return 0.0

    def excess(z: float) -> float:
        return math.fsum(_shin_probabilities(q, total, z)) - 1

    # excess(0) = √Q − 1 > 0; cuando z → 1, Σ p_i → Σ q_i²/Q < 1: la raíz está en (0, 1).
    return _solve(excess, 0.0, 1 - 1e-9, tol, max_iter)


def devig_shin(
    odds: Sequence[float], *, tol: float = 1e-12, max_iter: int = 200
) -> tuple[float, ...]:
    """p_i = (√(z² + 4(1−z)·q_i²/Q) − z) / (2(1−z)), con z ∈ [0, 1) tal que Σp = 1."""
    q, total = _implied(odds)
    z = shin_z(odds, tol=tol, max_iter=max_iter)
    probabilities = _shin_probabilities(q, total, z)
    norm = math.fsum(probabilities)
    return tuple(x / norm for x in probabilities)


_METHODS: Mapping[DevigMethod, Callable[[Sequence[float]], tuple[float, ...]]] = MappingProxyType(
    {
        DevigMethod.MULTIPLICATIVE: devig_multiplicative,
        DevigMethod.ADDITIVE: devig_additive,
        DevigMethod.POWER: devig_power,
        DevigMethod.SHIN: devig_shin,
    }
)


def devig(odds: Sequence[float], method: DevigMethod) -> tuple[float, ...]:
    """Aplica el método pedido (despacho por diccionario, sin if/else)."""
    return _METHODS[method](odds)

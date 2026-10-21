"""Devig: de cuotas decimales a probabilidades sin margen.

Notación: q_i = 1 / cuota_i (probabilidad implícita) y Q = Σ q_i (1 + margen).
Todos los métodos devuelven las probabilidades en el mismo orden que las cuotas de entrada.
"""

import math
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from types import MappingProxyType

from tipster.errors import DevigError

# Tolerancia para considerar que un libro no tiene margen (Q = 1).
FAIR_BOOK_TOL = 1e-12


class DevigMethod(StrEnum):
    MULTIPLICATIVE = "multiplicativo"
    ADDITIVE = "aditivo"


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


_METHODS: Mapping[DevigMethod, Callable[[Sequence[float]], tuple[float, ...]]] = MappingProxyType(
    {
        DevigMethod.MULTIPLICATIVE: devig_multiplicative,
        DevigMethod.ADDITIVE: devig_additive,
    }
)


def devig(odds: Sequence[float], method: DevigMethod) -> tuple[float, ...]:
    """Aplica el método pedido (despacho por diccionario, sin if/else)."""
    return _METHODS[method](odds)

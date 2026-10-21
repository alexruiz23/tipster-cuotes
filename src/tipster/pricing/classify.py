"""Clasificación de una cuota frente a la probabilidad justa.

Orden fijo: DESCARTADA → REVISIÓN MANUAL → POSIBLE ERROR → VALUE → SIN VALOR.
Las comparaciones con los umbrales usan una tolerancia explícita para que los casos frontera no
dependan del redondeo en coma flotante.
"""

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

THRESHOLD_TOL = 1e-9


class Label(StrEnum):
    VALUE = "VALUE"
    POSIBLE_ERROR = "POSIBLE ERROR · RIESGO DE ANULACIÓN"
    REVISION_MANUAL = "REVISIÓN MANUAL"
    DESCARTADA = "DESCARTADA"
    SIN_VALOR = "SIN VALOR"


@dataclass(frozen=True)
class Thresholds:
    ev_min: float
    error_margin: float
    max_quote_age: timedelta
    max_model_gap: float | None = None  # se usa cuando exista p_modelo (F3)

    def __post_init__(self) -> None:
        if not 0 <= self.ev_min < self.error_margin:
            raise ValueError("Se necesita 0 ≤ ev_min < error_margin")
        if self.max_quote_age <= timedelta(0):
            raise ValueError("max_quote_age debe ser positiva")


@dataclass(frozen=True)
class Classification:
    label: Label
    reasons: tuple[str, ...]


def format_age(age: timedelta) -> str:
    seconds = int(age.total_seconds())
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min {seconds % 60} s"
    return f"{seconds // 3600} h {seconds % 3600 // 60} min"


def classify(
    *,
    price: float,
    p_market: float,
    p_final: float,
    quote_age: timedelta,
    thresholds: Thresholds,
    p_model: float | None = None,
) -> Classification:
    if quote_age > thresholds.max_quote_age:
        return Classification(
            Label.DESCARTADA, (f"cuota con {format_age(quote_age)} de antigüedad",)
        )

    gap = thresholds.max_model_gap
    if p_model is not None and gap is not None and abs(p_market - p_model) > gap + THRESHOLD_TOL:
        return Classification(
            Label.REVISION_MANUAL,
            (f"p_mercado y p_modelo difieren {abs(p_market - p_model) * 100:.1f} puntos",),
        )

    fair = 1 / p_market
    edge = price / fair - 1
    if edge > thresholds.error_margin + THRESHOLD_TOL:
        return Classification(
            Label.POSIBLE_ERROR,
            (f"cuota {edge * 100:.2f} % por encima de la justa ({fair:.3f})",),
        )

    ev = p_final * price - 1
    if ev >= thresholds.ev_min - THRESHOLD_TOL:
        return Classification(Label.VALUE, (f"EV {ev * 100:+.2f} %",))
    return Classification(Label.SIN_VALOR, (f"EV {ev * 100:+.2f} %",))

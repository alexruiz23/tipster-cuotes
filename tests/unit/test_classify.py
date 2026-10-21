"""Clasificación value / posible error / descarte con casos a mano (docs/fase-1/plan.md §6).

p_mercado = 14/29 (local del caso base); cuota justa = 29/14 ≈ 2.0714286. En la Fase 1,
p_final = p_mercado, así que el EV coincide con el exceso sobre la cuota justa.
"""

from datetime import timedelta

import pytest

from tipster.pricing.classify import Label, Thresholds, classify, format_age

P = 14 / 29
FAIR = 29 / 14
THRESHOLDS = Thresholds(ev_min=0.03, error_margin=0.15, max_quote_age=timedelta(minutes=10))
FRESH = timedelta(minutes=2)


def _label(price: float, age: timedelta = FRESH, p_model: float | None = None) -> Label:
    return classify(
        price=price, p_market=P, p_final=P, quote_age=age, thresholds=THRESHOLDS, p_model=p_model
    ).label


@pytest.mark.parametrize(
    ("price", "label"),
    [
        (2.10, Label.SIN_VALOR),  # 2.1 × 14/29 − 1 = 0.4/29 ≈ +1.38 %
        (2.20, Label.VALUE),  # 1.8/29 ≈ +6.21 %
        (2.40, Label.POSIBLE_ERROR),  # 4.6/29 ≈ +15.86 % > 15 %
    ],
)
def test_casos_a_mano(price: float, label: Label) -> None:
    assert _label(price) is label


def test_frontera_de_value_incluida() -> None:
    at_threshold = 1.03 * FAIR  # ≈ 2.1335714: EV = 3 % exacto
    assert _label(at_threshold) is Label.VALUE
    assert _label(at_threshold * (1 - 1e-6)) is Label.SIN_VALOR


def test_frontera_de_error_excluida() -> None:
    at_margin = 1.15 * FAIR  # ≈ 2.3821429: 15 % exacto no es «más de» 15 %
    assert _label(at_margin) is Label.VALUE
    assert _label(at_margin * (1 + 1e-6)) is Label.POSIBLE_ERROR


def test_descarte_por_antiguedad() -> None:
    assert _label(2.20, age=timedelta(minutes=10)) is Label.VALUE  # máximo exacto: válida
    result = classify(
        price=2.20,
        p_market=P,
        p_final=P,
        quote_age=timedelta(minutes=10, seconds=1),
        thresholds=THRESHOLDS,
    )
    assert result.label is Label.DESCARTADA
    assert result.reasons == ("cuota con 10 min 1 s de antigüedad",)


def test_el_descarte_tiene_prioridad_sobre_el_posible_error() -> None:
    assert _label(2.40, age=timedelta(minutes=30)) is Label.DESCARTADA


def test_revision_manual_solo_con_modelo_y_umbral() -> None:
    con_umbral = Thresholds(
        ev_min=0.03,
        error_margin=0.15,
        max_quote_age=timedelta(minutes=10),
        max_model_gap=0.05,
    )
    result = classify(
        price=2.20,
        p_market=P,
        p_final=P,
        quote_age=FRESH,
        thresholds=con_umbral,
        p_model=P + 0.06,
    )
    assert result.label is Label.REVISION_MANUAL
    # Sin p_modelo (Fase 1) la regla no se aplica.
    assert _label(2.20) is Label.VALUE


def test_los_motivos_explican_la_etiqueta() -> None:
    result = classify(price=2.40, p_market=P, p_final=P, quote_age=FRESH, thresholds=THRESHOLDS)
    assert result.reasons == ("cuota 15.86 % por encima de la justa (2.071)",)
    value = classify(price=2.20, p_market=P, p_final=P, quote_age=FRESH, thresholds=THRESHOLDS)
    assert value.reasons == ("EV +6.21 %",)


@pytest.mark.parametrize(
    ("age", "text"),
    [
        (timedelta(seconds=45), "45 s"),
        (timedelta(minutes=10), "10 min 0 s"),
        (timedelta(minutes=10, seconds=1), "10 min 1 s"),
        (timedelta(hours=1, minutes=2, seconds=3), "1 h 2 min"),
    ],
)
def test_formato_de_antiguedad(age: timedelta, text: str) -> None:
    assert format_age(age) == text


def test_umbrales_incoherentes_se_rechazan() -> None:
    with pytest.raises(ValueError):
        Thresholds(ev_min=0.2, error_margin=0.15, max_quote_age=timedelta(minutes=10))

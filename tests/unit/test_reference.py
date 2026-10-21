"""Elección de la referencia (D2): Pinnacle si está fresca y completa; si no, Betfair Exchange."""

from datetime import UTC, datetime, timedelta

import pytest

from tipster.domain.markets import get_market
from tipster.domain.models import OddsQuote
from tipster.pricing.devig import DevigMethod, devig
from tipster.services.reference import ReferenceResult, select_reference

NOW = datetime(2026, 10, 21, 18, 0, tzinfo=UTC)
MAX_AGE = timedelta(minutes=10)
ORDER = ("pinnacle", "betfair_ex_no_es")
MARKET = get_market("1x2")


def _quotes(
    bookmaker: str,
    prices: dict[str, float],
    age: timedelta = timedelta(minutes=2),
    captured_offset: timedelta = timedelta(0),
) -> list[OddsQuote]:
    return [
        OddsQuote(
            event_id="e1",
            bookmaker_id=bookmaker,
            market_id="1x2",
            selection=selection,
            price=price,
            captured_at=NOW - captured_offset,
            provider_last_update=NOW - age,
            source="the_odds_api",
        )
        for selection, price in prices.items()
    ]


PINNACLE = {"local": 2.00, "empate": 3.50, "visitante": 4.00}
BETFAIR = {"local": 2.04, "empate": 3.55, "visitante": 4.10}


def _select(
    quotes: list[OddsQuote], method: DevigMethod = DevigMethod.MULTIPLICATIVE
) -> ReferenceResult:
    return select_reference(
        quotes, market=MARKET, order=ORDER, method=method, max_age=MAX_AGE, now=NOW
    )


def test_pinnacle_fresca_es_la_referencia() -> None:
    result = _select(_quotes("pinnacle", PINNACLE) + _quotes("betfair_ex_no_es", BETFAIR))
    assert result.reference is not None
    assert result.reference.bookmaker_id == "pinnacle"
    assert result.reference.odds == (("local", 2.00), ("empate", 3.50), ("visitante", 4.00))
    assert result.reference.probabilities["local"] == pytest.approx(14 / 29, abs=1e-12)
    assert result.rejections == ()


def test_pinnacle_antigua_pasa_a_betfair() -> None:
    quotes = _quotes("pinnacle", PINNACLE, age=timedelta(minutes=12)) + _quotes(
        "betfair_ex_no_es", BETFAIR
    )
    result = _select(quotes)
    assert result.reference is not None
    assert result.reference.bookmaker_id == "betfair_ex_no_es"
    assert result.rejections == ("pinnacle: referencia con 12 min 0 s de antigüedad",)


def test_pinnacle_sin_empate_pasa_a_betfair() -> None:
    incompleta = {"local": 2.00, "visitante": 4.00}
    result = _select(_quotes("pinnacle", incompleta) + _quotes("betfair_ex_no_es", BETFAIR))
    assert result.reference is not None
    assert result.reference.bookmaker_id == "betfair_ex_no_es"
    assert result.rejections == ("pinnacle: falta la selección empate",)


def test_sin_referencia_valida_no_hay_referencia() -> None:
    stale = timedelta(minutes=11)
    quotes = _quotes("pinnacle", PINNACLE, age=stale) + _quotes(
        "betfair_ex_no_es", BETFAIR, age=stale
    )
    result = _select(quotes)
    assert result.reference is None
    assert len(result.rejections) == 2


def test_referencia_con_margen_negativo_se_rechaza() -> None:
    anomala = {"local": 2.60, "empate": 3.80, "visitante": 4.50}  # Σq ≈ 0.869 < 1
    result = _select(_quotes("pinnacle", anomala) + _quotes("betfair_ex_no_es", BETFAIR))
    assert result.reference is not None
    assert result.reference.bookmaker_id == "betfair_ex_no_es"
    assert result.rejections[0].startswith("pinnacle: Margen negativo")


def test_se_usa_la_ultima_captura_de_cada_seleccion() -> None:
    vieja = _quotes("pinnacle", {"local": 1.90}, captured_offset=timedelta(minutes=1))
    result = _select(vieja + _quotes("pinnacle", PINNACLE))
    assert result.reference is not None
    assert dict(result.reference.odds)["local"] == 2.00


@pytest.mark.parametrize("method", list(DevigMethod))
def test_las_probabilidades_se_reproducen_desde_las_cuotas_guardadas(method: DevigMethod) -> None:
    # El orden de entrada de las cuotas no importa: se ordenan por las selecciones del mercado.
    quotes = list(reversed(_quotes("pinnacle", PINNACLE)))
    result = _select(quotes, method)
    assert result.reference is not None
    expected = devig([price for _, price in result.reference.odds], method)
    assert tuple(result.reference.probabilities.values()) == expected
    assert tuple(result.reference.probabilities) == MARKET.selections

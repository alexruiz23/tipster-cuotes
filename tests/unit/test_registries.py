from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from tipster.domain.bookmakers import BOOKMAKERS, Role, find_by_provider_key, get_bookmaker
from tipster.domain.competitions import COMPETITIONS, THE_ODDS_API, get_competition
from tipster.domain.markets import MARKETS, SELECTION_LABELS, get_market
from tipster.domain.models import Event, OddsQuote
from tipster.domain.sports import SPORTS, SportId
from tipster.errors import RegistryError


def test_las_siete_competiciones_son_de_futbol_y_tienen_clave_de_the_odds_api() -> None:
    assert set(COMPETITIONS) == {
        "laliga",
        "segunda",
        "premier",
        "serie_a",
        "bundesliga",
        "ligue_1",
        "champions",
    }
    for spec in COMPETITIONS.values():
        assert spec.sport in SPORTS
        assert spec.provider_keys[THE_ODDS_API]


@pytest.mark.parametrize("market_id", list(MARKETS))
def test_todo_mercado_tiene_selecciones_unicas_y_etiquetadas(market_id: str) -> None:
    spec = MARKETS[market_id]
    assert len(spec.selections) >= 2
    assert len(set(spec.selections)) == len(spec.selections)
    assert all(s in SELECTION_LABELS for s in spec.selections)
    assert spec.enabled or spec.disabled_reason


def test_ou_tiene_linea_2_5_y_btts_esta_desactivado_por_d5() -> None:
    assert get_market("ou_2.5").line == 2.5
    btts = get_market("btts")
    assert not btts.enabled
    assert btts.disabled_reason is not None
    assert "D5" in btts.disabled_reason


def test_ninguna_casa_se_marca_como_web_es_en_la_fase_1() -> None:
    # The Odds API no tiene feeds .es (Fase 0, nivel B): marcar uno así lo haría pasar por .es.
    assert not any(spec.es_site for spec in BOOKMAKERS.values())


def test_roles_de_referencia() -> None:
    assert get_bookmaker("pinnacle").role is Role.SHARP
    assert get_bookmaker("betfair_ex_no_es").role is Role.EXCHANGE
    assert get_bookmaker("pinnacle").is_reference
    assert not get_bookmaker("888sport_no_es").is_reference


def test_las_claves_de_proveedor_son_unicas_y_reversibles() -> None:
    for spec in BOOKMAKERS.values():
        for provider, key in spec.provider_keys.items():
            assert find_by_provider_key(provider, key) is spec
    assert find_by_provider_key(THE_ODDS_API, "casa_inexistente") is None


@pytest.mark.parametrize(
    ("getter", "key"),
    [(get_competition, "liga_x"), (get_market, "mercado_x"), (get_bookmaker, "casa_x")],
)
def test_id_desconocido_lanza_registry_error(getter: object, key: str) -> None:
    with pytest.raises(RegistryError):
        getter(key)  # type: ignore[operator]


def _quote(**overrides: object) -> OddsQuote:
    data: dict[str, object] = {
        "event_id": "e1",
        "bookmaker_id": "pinnacle",
        "market_id": "1x2",
        "selection": "local",
        "price": 2.0,
        "captured_at": datetime(2026, 10, 21, 10, 0, tzinfo=UTC),
        "provider_last_update": None,
        "source": "the_odds_api",
    }
    data.update(overrides)
    return OddsQuote.model_validate(data)


@pytest.mark.parametrize("price", [1.0, 0.5, float("inf"), float("nan")])
def test_cuota_invalida_se_rechaza(price: float) -> None:
    with pytest.raises(ValidationError):
        _quote(price=price)


def test_fecha_sin_zona_se_rechaza_y_las_aware_pasan_a_utc() -> None:
    with pytest.raises(ValidationError):
        _quote(captured_at=datetime(2026, 10, 21, 10, 0))
    madrid = timezone(timedelta(hours=2))
    quote = _quote(captured_at=datetime(2026, 10, 21, 12, 0, tzinfo=madrid))
    assert quote.captured_at == datetime(2026, 10, 21, 10, 0, tzinfo=UTC)
    assert quote.captured_at.tzinfo is UTC


def test_antiguedad_usa_last_update_y_si_falta_la_captura() -> None:
    now = datetime(2026, 10, 21, 10, 10, tzinfo=UTC)
    sin_proveedor = _quote()
    assert sin_proveedor.age(now) == timedelta(minutes=10)
    con_proveedor = _quote(provider_last_update=datetime(2026, 10, 21, 9, 58, tzinfo=UTC))
    assert con_proveedor.age(now) == timedelta(minutes=12)


def test_evento_normaliza_inicio_a_utc() -> None:
    event = Event(
        id="e1",
        sport=SportId.FOOTBALL,
        competition_id="laliga",
        home_team="Local",
        away_team="Visitante",
        kickoff=datetime(2026, 10, 25, 21, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    assert event.kickoff == datetime(2026, 10, 25, 19, 0, tzinfo=UTC)
    assert event.name == "Local – Visitante"

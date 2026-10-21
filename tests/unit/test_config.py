"""Configuración (pydantic-settings) leída de variables de entorno; sin .env en los tests."""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from tipster.config import Settings
from tipster.pricing.devig import DevigMethod

KEY = "clave-de-prueba-config"  # gitleaks:allow (clave falsa de test)


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ODDS_API_KEY", "TIPSTER_COMPETITIONS", "TIPSTER_MARKETS", "TIPSTER_EV_MIN"):
        monkeypatch.delenv(name, raising=False)


def test_valores_por_defecto(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch)
    assert s.odds_api_key is None
    assert len(s.competitions) == 7
    assert s.markets == ("1x2", "ou_2.5")
    assert s.reference_order == ("pinnacle", "betfair_ex_no_es")
    assert s.devig_method is DevigMethod.MULTIPLICATIVE
    t = s.thresholds()
    assert (t.ev_min, t.error_margin, t.max_quote_age) == (0.03, 0.15, timedelta(minutes=10))


def test_listas_separadas_por_comas(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, TIPSTER_COMPETITIONS="laliga, premier", TIPSTER_DEVIG_METHOD="shin")
    assert s.competitions == ("laliga", "premier")
    assert s.devig_method is DevigMethod.SHIN


def test_btts_se_rechaza_citando_d5(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="D5"):
        _settings(monkeypatch, TIPSTER_MARKETS="1x2,btts")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("TIPSTER_COMPETITIONS", "liga_inventada"),
        ("TIPSTER_BOOKMAKERS", "pinnacle,casa_inventada"),
        ("TIPSTER_REFERENCE_ORDER", "888sport_no_es"),  # no es sharp ni exchange
        ("TIPSTER_EV_MIN", "0.2"),  # mayor que el margen de error
        ("TIPSTER_TIMEZONE", "Europe/Inventada"),
    ],
)
def test_configuracion_invalida(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    with pytest.raises(ValidationError):
        _settings(monkeypatch, **{name: value})


def test_la_referencia_debe_estar_entre_las_casas_pedidas(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        _settings(monkeypatch, TIPSTER_BOOKMAKERS="pinnacle,888sport_no_es")


def test_la_clave_se_lee_pero_nunca_se_muestra(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, ODDS_API_KEY=KEY)
    assert s.odds_api_key is not None
    assert s.odds_api_key.get_secret_value() == KEY
    assert KEY not in repr(s)
    assert KEY not in str(s.snapshot())
    assert "odds_api_key" not in s.snapshot()

"""Configuración leída de `.env` y de variables de entorno (ver `.env.example`).

Logs y métricas en la Fase 1: solo se escribe a stdout (tabla y resumen de cada ejecución). El
consumo de créditos queda en las tablas `provider_requests` y `runs` de la base de datos.
Backup de la base de datos: no se hace en la Fase 1; se decide en la Fase 3.
"""

from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from tipster.domain.bookmakers import BOOKMAKERS
from tipster.domain.competitions import COMPETITIONS
from tipster.domain.markets import MARKETS
from tipster.pricing.classify import Thresholds
from tipster.pricing.devig import DevigMethod

LOG_DESTINATION = "stdout"

CommaList = Annotated[tuple[str, ...], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TIPSTER_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    odds_api_key: SecretStr | None = Field(default=None, validation_alias="ODDS_API_KEY")
    db_path: Path = Path("data/tipster.sqlite")
    raw_dir: Path = Path("data/raw")
    cache_ttl_seconds: NonNegativeInt = 60
    max_credits_per_run: NonNegativeInt = 30
    min_request_interval_s: NonNegativeFloat = 1.0
    competitions: CommaList = tuple(COMPETITIONS)
    markets: CommaList = ("1x2", "ou_2.5")
    bookmakers: CommaList = (
        "pinnacle",
        "betfair_ex_no_es",
        "888sport_no_es",
        "williamhill_no_es",
        "marathonbet_no_es",
        "winamax_fr",
        "winamax_de",
        "betfair_sb_uk",
    )
    reference_order: CommaList = ("pinnacle", "betfair_ex_no_es")
    devig_method: DevigMethod = DevigMethod.MULTIPLICATIVE  # provisional (F2 lo decidirá)
    ev_min: float = 0.03
    error_margin: float = 0.15
    max_quote_age_minutes: PositiveInt = 10
    max_reference_age_minutes: PositiveInt = 10
    timezone: str = "Europe/Madrid"
    # Fase 3 (ADR 012): bankroll de papel, Kelly y límites
    bankroll_initial: PositiveFloat = 1000.0
    kelly_fraction: float = Field(default=0.25, gt=0, le=1)
    max_stake: float = Field(default=0.02, gt=0, le=1)  # por apuesta, fracción del bankroll
    daily_exposure: float = Field(default=0.10, gt=0, le=1)
    daily_loss_limit: float = Field(default=0.05, gt=0, le=1)  # provisional
    min_stake: float = Field(default=0.0025, ge=0, lt=1)
    closing_window_minutes: PositiveInt = 15  # `tipster close` captura a ≤ N min del inicio
    closing_max_age_minutes: PositiveInt = 30  # una captura más lejana del inicio no es fiable

    @field_validator("competitions", "markets", "bookmakers", "reference_order", mode="before")
    @classmethod
    def _split(cls, value: Any) -> Any:
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

    @field_validator("competitions")
    @classmethod
    def _known_competitions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        unknown = [c for c in value if c not in COMPETITIONS]
        if unknown:
            raise ValueError(f"competiciones desconocidas: {unknown}")
        return value

    @field_validator("markets")
    @classmethod
    def _known_markets(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for market_id in value:
            spec = MARKETS.get(market_id)
            if spec is None:
                raise ValueError(f"mercado desconocido: {market_id}")
            if not spec.enabled:
                raise ValueError(f"mercado {market_id} desactivado: {spec.disabled_reason}")
        return value

    @field_validator("bookmakers")
    @classmethod
    def _known_bookmakers(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        unknown = [b for b in value if b not in BOOKMAKERS]
        if unknown:
            raise ValueError(f"casas desconocidas: {unknown}")
        return value

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"zona horaria desconocida: {value}") from exc
        return value

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        for bookmaker_id in self.reference_order:
            spec = BOOKMAKERS.get(bookmaker_id)
            if spec is None or not spec.is_reference:
                raise ValueError(f"{bookmaker_id} no es una referencia (sharp o exchange)")
            if bookmaker_id not in self.bookmakers:
                raise ValueError(f"la referencia {bookmaker_id} debe estar en TIPSTER_BOOKMAKERS")
        if not 0 <= self.ev_min < self.error_margin:
            raise ValueError("se necesita 0 ≤ TIPSTER_EV_MIN < TIPSTER_ERROR_MARGIN")
        return self

    def thresholds(self) -> Thresholds:
        return Thresholds(
            ev_min=self.ev_min,
            error_margin=self.error_margin,
            max_quote_age=timedelta(minutes=self.max_quote_age_minutes),
        )

    def snapshot(self) -> dict[str, object]:
        """Configuración usada en una ejecución, para guardarla en `runs`. Nunca lleva la clave."""
        return self.model_dump(mode="json", exclude={"odds_api_key"})

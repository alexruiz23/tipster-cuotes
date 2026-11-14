"""Configuración leída de `.env` y de variables de entorno (ver `.env.example`).

Logs y métricas en la Fase 1: solo se escribe a stdout (tabla y resumen de cada ejecución). El
consumo de créditos queda en las tablas `provider_requests` y `runs` de la base de datos.
Backup de la base de datos: no se hace en la Fase 1; se decide en la Fase 3.
"""

from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any, Literal, Self
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
    telegram_bot_token: SecretStr | None = Field(
        default=None, validation_alias="TELEGRAM_BOT_TOKEN"
    )
    telegram_chat_id: str | None = Field(default=None, validation_alias="TELEGRAM_CHAT_ID")
    db_path: Path = Path("data/tipster.sqlite")
    raw_dir: Path = Path("data/raw")
    cache_ttl_seconds: NonNegativeInt = 60
    max_credits_per_run: NonNegativeInt = 30
    min_request_interval_s: NonNegativeFloat = 1.0
    # segunda excluida del paper trading (ADR 012, BACKLOG 37): sin cierre fiable de Pinnacle
    competitions: CommaList = tuple(c for c in COMPETITIONS if c != "segunda")
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
    # Shin desde el 2026-11-14 (antes multiplicativo): corrige el sesgo favorito-longshot que infla
    # el EV de las cuotas largas; en validación empató en log-loss con los demás (ADR 014)
    devig_method: DevigMethod = DevigMethod.SHIN
    ev_min: float = 0.03
    error_margin: float = 0.15
    max_quote_age_minutes: PositiveInt = 10
    max_reference_age_minutes: PositiveInt = 10
    timezone: str = "Europe/Madrid"
    # Fase 3 (ADR 012): bankroll de papel, sizing y límites
    sizing_strategy: Literal["flat", "kelly"] = "flat"
    stake_pct: float = Field(default=0.01, gt=0, le=1)  # sizing flat: fracción del bankroll actual
    min_stake_abs: PositiveFloat = 0.50  # € mínimo por apuesta con sizing flat
    max_stake_abs: PositiveFloat = 5.0  # € máximo por apuesta con sizing flat
    # solo flat, fracción del bankroll actual en el momento del scan (kelly usa los dos de abajo)
    max_daily_exposure_pct: float = Field(default=0.05, gt=0, le=1)
    max_daily_loss_pct: float = Field(default=0.10, gt=0, le=1)
    bankroll_initial: PositiveFloat = 100.0
    kelly_fraction: float = Field(default=0.25, gt=0, le=1)
    max_stake: float = Field(default=0.02, gt=0, le=1)  # por apuesta, fracción del bankroll
    daily_exposure: float = Field(default=0.10, gt=0, le=1)
    daily_loss_limit: float = Field(default=0.05, gt=0, le=1)  # provisional
    # Sesgo favorito-longshot (ADR 012): el EV de una cuota larga está sobrestimado. 8,0 desde el
    # 2026-11-14 (antes 15,0): ver «Cambio del 2026-11-14» en el ADR 012
    max_odds: float = Field(default=8.0, gt=1)
    # Dos niveles (ADR 014). Principal: cuota ≤ longshot_odds con EV ≥ ev_min. Improbable: cuota
    # mayor, hasta max_odds, que exige EV ≥ longshot_ev_min y con un tope de picks abiertos a la vez
    longshot_odds: float = Field(default=4.0, gt=1)
    longshot_ev_min: float = Field(default=0.06, ge=0)
    max_open_longshots: NonNegativeInt = 2
    # Solo llevan stake los partidos que empiezan en los próximos N días: a más distancia las
    # líneas son menos firmes y la cuota de la casa puede estar sin actualizar (ADR 014)
    max_days_ahead: PositiveInt = 4
    min_odds: float = Field(default=1.5, gt=1)
    min_stake: float = Field(default=0.005, ge=0, lt=1)  # fracción del bankroll: 0,50 € con 100 €
    closing_window_minutes: PositiveInt = 15  # `tipster close` captura a ≤ N min del inicio
    # `close` repite la captura mientras la última esté a más de N min del inicio, para que el
    # cierre guardado sea el más cercano posible. N ≥ closing_window_minutes la desactiva.
    closing_refresh_minutes: PositiveInt = 5
    # Copias de la base de datos (`tipster backup`) y avisos (`tipster notify --alerts`)
    backup_dir: Path = Path("data/backups")
    backup_keep: PositiveInt = 14  # copias diarias que se conservan
    low_credits_alert: NonNegativeInt = 60  # avisa si los créditos restantes bajan de este valor

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
        return self.model_dump(
            mode="json", exclude={"odds_api_key", "telegram_bot_token", "telegram_chat_id"}
        )

"""Modelos canónicos (pydantic, inmutables). Todas las fechas se normalizan a UTC."""

from datetime import UTC, datetime, timedelta

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from tipster.domain.sports import SportId


def to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    sport: SportId
    competition_id: str
    home_team: str
    away_team: str
    kickoff: AwareDatetime

    @field_validator("kickoff")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return to_utc(value)

    @property
    def name(self) -> str:
        return f"{self.home_team} – {self.away_team}"


class OddsQuote(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    bookmaker_id: str
    market_id: str
    selection: str
    price: float = Field(gt=1, allow_inf_nan=False)
    captured_at: AwareDatetime  # cuándo la recibimos
    provider_last_update: AwareDatetime | None  # cuándo la vio el proveedor en la casa
    source: str

    @field_validator("captured_at", "provider_last_update")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else to_utc(value)

    def age(self, now: datetime) -> timedelta:
        """Antigüedad según `provider_last_update`; si falta, según `captured_at`."""
        return now - (self.provider_last_update or self.captured_at)

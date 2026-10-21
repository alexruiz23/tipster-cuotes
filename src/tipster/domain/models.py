"""Modelos canónicos (pydantic, inmutables). Todas las fechas se normalizan a UTC."""

from datetime import UTC, datetime, timedelta

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from tipster.domain.sports import SportId
from tipster.pricing.classify import Label
from tipster.pricing.devig import DevigMethod


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
    captured_at: AwareDatetime  # momento de la petición HTTP que trajo la cuota (o la cacheada)
    provider_last_update: AwareDatetime | None  # cuándo la vio el proveedor en la casa
    source: str

    @field_validator("captured_at", "provider_last_update")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else to_utc(value)

    def age(self, now: datetime) -> timedelta:
        """Antigüedad según `provider_last_update`; si falta, según `captured_at`."""
        return now - (self.provider_last_update or self.captured_at)


class Opportunity(BaseModel):
    """Una cuota de una casa evaluada contra la referencia."""

    model_config = ConfigDict(frozen=True)

    event: Event
    quote: OddsQuote
    feed_es: bool  # D1: False → «FEED NO-ES · VERIFICA LA CUOTA EN LA WEB .ES»
    reference_bookmaker_id: str  # D2
    reference_captured_at: AwareDatetime
    reference_odds: tuple[tuple[str, float], ...]  # cuotas exactas del devig, en orden de selección
    devig_method: DevigMethod
    p_market: float
    p_model: float | None = None  # F2–F3
    p_final: float
    fair_odds: float
    ev: float
    stake: float | None = None  # F3
    label: Label
    reasons: tuple[str, ...]


PICK_LABELS = frozenset({Label.VALUE, Label.POSIBLE_ERROR})


class Pick(BaseModel):
    """Oportunidad emitida como recomendación (VALUE o POSIBLE ERROR), enlazada a su cuota."""

    model_config = ConfigDict(frozen=True)

    quote_id: int
    opportunity: Opportunity
    created_at: AwareDatetime

    @field_validator("opportunity")
    @classmethod
    def _is_pick(cls, value: Opportunity) -> Opportunity:
        if value.label not in PICK_LABELS:
            raise ValueError(f"Solo VALUE o POSIBLE ERROR son picks, no {value.label}")
        return value

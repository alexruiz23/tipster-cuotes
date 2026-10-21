"""Contrato de los proveedores de cuotas. El resto del sistema solo conoce estos tipos."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict

from tipster.domain.models import Event, OddsQuote


class RequestRecord(BaseModel):
    """Registro de una petición (o de su reutilización desde la caché). Nunca contiene la clave."""

    model_config = ConfigDict(frozen=True)

    provider: str
    endpoint: str
    params_key: str  # parámetros ordenados, sin apiKey
    http_status: int | None
    from_cache: bool
    cost: int | None
    credits_used: int | None
    credits_remaining: int | None
    requested_at: AwareDatetime
    duration_ms: int | None
    raw_path: str | None
    error: str | None = None


@dataclass(frozen=True)
class CachedResponse:
    request_id: int
    requested_at: datetime
    raw_path: str


class ResponseCache(Protocol):
    def lookup(
        self, provider: str, endpoint: str, params_key: str, max_age: timedelta, now: datetime
    ) -> CachedResponse | None: ...


@dataclass(frozen=True)
class OddsRequest:
    competition_id: str  # canónico, p. ej. "laliga"
    market_ids: tuple[str, ...]  # ("1x2", "ou_2.5")
    bookmaker_ids: tuple[str, ...]  # canónicos; el proveedor los traduce


class ProviderCompetition(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_key: str
    title: str
    active: bool


class CompetitionListing(BaseModel):
    model_config = ConfigDict(frozen=True)

    competitions: list[ProviderCompetition]
    request: RequestRecord


class OddsBatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    competition_id: str
    events: list[Event]
    external_ids: dict[str, str]  # id canónico del evento → id en el proveedor
    quotes: list[OddsQuote]
    request: RequestRecord
    warnings: list[str]


class OddsProvider(Protocol):
    name: str

    def list_competitions(self) -> CompetitionListing: ...

    def fetch_odds(self, request: OddsRequest) -> OddsBatch: ...

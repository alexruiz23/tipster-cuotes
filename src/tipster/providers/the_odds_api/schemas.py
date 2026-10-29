"""Esquemas del JSON de The Odds API v4.

Estructura tomada de la documentación del proveedor y NO VERIFICADA con una respuesta real
(criterio R3 de la Fase 1). Los campos que no se usan se ignoran.
"""

from pydantic import AwareDatetime, BaseModel, ConfigDict, TypeAdapter


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class TOAOutcome(_Model):
    name: str
    price: float
    point: float | None = None


class TOAMarket(_Model):
    key: str
    last_update: AwareDatetime | None = None
    outcomes: list[TOAOutcome]


class TOABookmaker(_Model):
    key: str
    title: str
    last_update: AwareDatetime | None = None
    markets: list[TOAMarket]


class TOAEvent(_Model):
    id: str
    sport_key: str
    commence_time: AwareDatetime
    home_team: str
    away_team: str
    bookmakers: list[TOABookmaker] = []


class TOASport(_Model):
    key: str
    title: str
    active: bool


class TOAScore(_Model):
    name: str
    score: str | None = None


class TOAScoreEvent(_Model):
    id: str
    completed: bool
    home_team: str
    away_team: str
    scores: list[TOAScore] | None = None


EVENTS = TypeAdapter(list[TOAEvent])
SCORES = TypeAdapter(list[TOAScoreEvent])
SPORTS = TypeAdapter(list[TOASport])

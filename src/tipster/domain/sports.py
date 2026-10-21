"""Deportes soportados. Añadir un deporte es añadir su especificación aquí (ADR 005)."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class SportId(StrEnum):
    FOOTBALL = "futbol"


@dataclass(frozen=True)
class SportSpec:
    id: SportId
    name: str


SPORTS: Mapping[SportId, SportSpec] = MappingProxyType(
    {SportId.FOOTBALL: SportSpec(SportId.FOOTBALL, "Fútbol")}
)

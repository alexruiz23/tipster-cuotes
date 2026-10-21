"""Registro de mercados: el flujo lo consulta y no conoce mercados concretos (ADR 005)."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from tipster.domain.sports import SportId
from tipster.errors import RegistryError


@dataclass(frozen=True)
class MarketSpec:
    id: str
    sport: SportId
    name: str
    selections: tuple[str, ...]
    line: float | None
    enabled: bool = True
    disabled_reason: str | None = None


MARKETS: Mapping[str, MarketSpec] = MappingProxyType(
    {
        spec.id: spec
        for spec in (
            MarketSpec(
                id="1x2",
                sport=SportId.FOOTBALL,
                name="1X2",
                selections=("local", "empate", "visitante"),
                line=None,
            ),
            MarketSpec(
                id="ou_2.5",
                sport=SportId.FOOTBALL,
                name="Más/Menos 2.5 goles",
                selections=("mas", "menos"),
                line=2.5,
            ),
            MarketSpec(
                id="btts",
                sport=SportId.FOOTBALL,
                name="Ambos marcan",
                selections=("si", "no"),
                line=None,
                enabled=False,
                disabled_reason=(
                    "D5: Ambos Marcan solo como salida del modelo hasta tener una fuente de "
                    "cuotas verificada"
                ),
            ),
        )
    }
)

SELECTION_LABELS: Mapping[str, str] = MappingProxyType(
    {
        "local": "Local",
        "empate": "Empate",
        "visitante": "Visitante",
        "mas": "Más de 2.5",
        "menos": "Menos de 2.5",
        "si": "Sí",
        "no": "No",
    }
)


def get_market(market_id: str) -> MarketSpec:
    try:
        return MARKETS[market_id]
    except KeyError:
        raise RegistryError(f"Mercado desconocido: {market_id!r}") from None

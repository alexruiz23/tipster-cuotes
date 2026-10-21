"""Registro de competiciones y su clave en cada proveedor.

Claves de The Odds API: solo `soccer_epl` está confirmada (nivel B, verificación de la Fase 0).
El resto son NO VERIFICADAS. `scan` las contrasta con `/v4/sports` y salta, con aviso, la
competición cuya clave no aparezca. La verificación de nivel A es el criterio R4 de la Fase 1.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from tipster.domain.sports import SportId
from tipster.errors import RegistryError

THE_ODDS_API = "the_odds_api"


@dataclass(frozen=True)
class CompetitionSpec:
    id: str
    sport: SportId
    name: str
    provider_keys: Mapping[str, str]


def _football(id_: str, name: str, the_odds_api_key: str) -> CompetitionSpec:
    return CompetitionSpec(
        id=id_,
        sport=SportId.FOOTBALL,
        name=name,
        provider_keys=MappingProxyType({THE_ODDS_API: the_odds_api_key}),
    )


COMPETITIONS: Mapping[str, CompetitionSpec] = MappingProxyType(
    {
        spec.id: spec
        for spec in (
            _football("laliga", "LaLiga", "soccer_spain_la_liga"),
            _football("segunda", "Segunda División", "soccer_spain_segunda_division"),
            _football("premier", "Premier League", "soccer_epl"),
            _football("serie_a", "Serie A", "soccer_italy_serie_a"),
            _football("bundesliga", "Bundesliga", "soccer_germany_bundesliga"),
            _football("ligue_1", "Ligue 1", "soccer_france_ligue_one"),
            _football("champions", "Champions League", "soccer_uefa_champs_league"),
        )
    }
)


def get_competition(competition_id: str) -> CompetitionSpec:
    try:
        return COMPETITIONS[competition_id]
    except KeyError:
        raise RegistryError(f"Competición desconocida: {competition_id!r}") from None

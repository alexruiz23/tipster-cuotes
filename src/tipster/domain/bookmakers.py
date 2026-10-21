"""Registro canónico de casas, con la jurisdicción de cada feed (ADR 003).

`es_site` es verdadero solo si el feed corresponde a la web .es con licencia DGOJ. En la Fase 1
ninguna lo es: The Odds API no tiene feeds .es (verificación de la Fase 0, nivel B).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from tipster.domain.competitions import THE_ODDS_API
from tipster.errors import RegistryError


class Role(StrEnum):
    SHARP = "sharp"
    EXCHANGE = "exchange"
    RETAIL = "casa"


@dataclass(frozen=True)
class BookmakerSpec:
    id: str
    brand: str
    jurisdiction: str
    role: Role
    es_site: bool
    provider_keys: Mapping[str, str]

    @property
    def is_reference(self) -> bool:
        return self.role in (Role.SHARP, Role.EXCHANGE)


def _no_es(id_: str, brand: str, jurisdiction: str, role: Role, key: str) -> BookmakerSpec:
    return BookmakerSpec(
        id=id_,
        brand=brand,
        jurisdiction=jurisdiction,
        role=role,
        es_site=False,
        provider_keys=MappingProxyType({THE_ODDS_API: key}),
    )


BOOKMAKERS: Mapping[str, BookmakerSpec] = MappingProxyType(
    {
        spec.id: spec
        for spec in (
            _no_es("pinnacle", "Pinnacle", "NO-ES", Role.SHARP, "pinnacle"),
            _no_es("betfair_ex_no_es", "Betfair Exchange", "NO-ES", Role.EXCHANGE, "betfair_ex_eu"),
            _no_es("888sport_no_es", "888sport", "NO-ES", Role.RETAIL, "sport888"),
            _no_es("williamhill_no_es", "William Hill", "NO-ES", Role.RETAIL, "williamhill"),
            _no_es("marathonbet_no_es", "Marathonbet", "NO-ES", Role.RETAIL, "marathonbet"),
            _no_es("winamax_fr", "Winamax", "FR", Role.RETAIL, "winamax_fr"),
            _no_es("winamax_de", "Winamax", "DE", Role.RETAIL, "winamax_de"),
            _no_es("betfair_sb_uk", "Betfair Sportsbook", "UK", Role.RETAIL, "betfair_sb_uk"),
        )
    }
)

_BY_PROVIDER_KEY: Mapping[tuple[str, str], BookmakerSpec] = MappingProxyType(
    {
        (provider, key): spec
        for spec in BOOKMAKERS.values()
        for provider, key in spec.provider_keys.items()
    }
)


def get_bookmaker(bookmaker_id: str) -> BookmakerSpec:
    try:
        return BOOKMAKERS[bookmaker_id]
    except KeyError:
        raise RegistryError(f"Casa desconocida: {bookmaker_id!r}") from None


def find_by_provider_key(provider: str, key: str) -> BookmakerSpec | None:
    """Casa canónica que corresponde a la clave de un proveedor, o None si no está registrada."""
    return _BY_PROVIDER_KEY.get((provider, key))

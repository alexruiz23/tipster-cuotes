"""Contraste de nuestro Shin con el paquete `shin` (mberk), solo como dependencia de desarrollo."""

import pytest
import shin

from tipster.pricing.devig import devig_additive, devig_shin

TOL = 1e-6

CASOS = {
    "1x2 típico": [2.00, 3.50, 4.00],
    "1x2 margen alto (~12 %)": [1.80, 3.10, 3.60],
    "1x2 margen casi nulo": [2.001, 3.50, 3.995],
    "1x2 favorito claro": [1.20, 6.50, 15.0],
    "1x2 con cuota muy grande": [1.05, 12.0, 101.0],
    "over/under 2.5": [1.90, 1.95],
    "over/under margen alto": [1.75, 1.95],
    "over/under cuota larga": [1.15, 5.50],
}


@pytest.mark.parametrize("odds", CASOS.values(), ids=CASOS.keys())
def test_nuestro_shin_coincide_con_el_paquete(odds: list[float]) -> None:
    ours = devig_shin(odds)
    ref = shin.calculate_implied_probabilities(odds, force_python_optimiser=True)
    assert sum(ours) == pytest.approx(1.0, abs=1e-9)
    assert list(ours) == pytest.approx(ref, abs=TOL)


@pytest.mark.parametrize(
    "odds",
    [o for o in CASOS.values() if len(o) == 2],
    ids=[k for k, o in CASOS.items() if len(o) == 2],
)
def test_con_dos_resultados_shin_es_igual_al_aditivo(odds: list[float]) -> None:
    """Comprobación extra pedida: con 2 resultados Shin coincide con el aditivo."""
    assert list(devig_shin(odds)) == pytest.approx(list(devig_additive(odds)), abs=1e-9)

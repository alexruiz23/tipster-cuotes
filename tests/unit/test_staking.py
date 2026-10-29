"""Kelly fraccionado y límites de exposición (ADR 012) con casos calculados a mano."""

import numpy as np
import pytest

from tipster.staking.kelly import kelly_fraction, kelly_stake
from tipster.staking.limits import allocate_daily, loss_limit_reached


def test_fraccion_de_kelly_a_mano() -> None:
    assert kelly_fraction(0.5, 2.2) == pytest.approx(1 / 12, abs=1e-12)  # caso del PLAN
    assert kelly_fraction(0.55, 2.0) == pytest.approx(0.10, abs=1e-12)
    assert kelly_fraction(0.52, 2.0) == pytest.approx(0.04, abs=1e-12)
    assert kelly_fraction(0.4, 2.0) == pytest.approx(-0.2, abs=1e-12)  # sin ventaja: negativa


@pytest.mark.parametrize(
    ("p", "odds", "uncapped", "capped"),
    [
        (0.50, 2.20, 20.83, 20.00),  # 1/4 · 1/12 = 2,083 %: manda el tope del 2 %
        (0.55, 2.00, 25.00, 20.00),  # 1/4 · 0,10 = 2,5 %: manda el tope
        (0.52, 2.00, 10.00, 10.00),  # 1/4 · 0,04 = 1 %: sin tope
    ],
)
def test_stake_de_un_cuarto_de_kelly_con_y_sin_tope(
    p: float, odds: float, uncapped: float, capped: float
) -> None:
    assert kelly_stake(1000.0, p, odds, cap=None) == pytest.approx(uncapped, abs=0.005)
    assert kelly_stake(1000.0, p, odds) == pytest.approx(capped, abs=0.005)


def test_sin_ventaja_no_se_apuesta() -> None:
    assert kelly_stake(1000.0, 0.4, 2.0) == 0.0
    assert kelly_stake(1000.0, 0.5, 2.0) == 0.0  # EV exactamente 0


def test_el_stake_nunca_supera_el_tope_por_apuesta() -> None:
    rng = np.random.default_rng(0)
    for _ in range(2000):
        p, odds, bankroll = rng.uniform(0.01, 0.99), rng.uniform(1.01, 60.0), rng.uniform(10, 5000)
        assert 0.0 <= kelly_stake(bankroll, p, odds) <= 0.02 * bankroll + 0.005


def test_el_stake_escala_con_el_bankroll() -> None:
    assert kelly_stake(2000.0, 0.52, 2.0, cap=None) == pytest.approx(20.0, abs=0.005)


def test_seis_picks_con_tope_diario_del_10_por_ciento() -> None:
    # stakes brutos del 2, 2, 2, 2, 1,5 y 1 % (de 1 000) por EV decreciente
    picks = [("a", 20.0, 0.09), ("b", 20.0, 0.08), ("c", 20.0, 0.07), ("d", 20.0, 0.06),
             ("e", 15.0, 0.05), ("f", 10.0, 0.04)]  # fmt: skip
    stakes = allocate_daily(picks, bankroll=1000.0)
    assert [stakes[k] for k in "abcde"] == [20.0, 20.0, 20.0, 20.0, 15.0]  # suman 95
    assert stakes["f"] == pytest.approx(5.0)  # recortado al 0,5 % que queda
    assert sum(stakes.values()) == pytest.approx(100.0)


def test_el_reparto_va_por_ev_decreciente_aunque_lleguen_desordenados() -> None:
    picks = [("bajo", 60.0, 0.04), ("alto", 60.0, 0.09)]
    stakes = allocate_daily(picks, bankroll=1000.0)
    assert stakes == {"alto": 60.0, "bajo": 40.0}


def test_un_stake_recortado_por_debajo_del_minimo_se_descarta() -> None:
    picks = [("a", 98.0, 0.09), ("b", 20.0, 0.05)]  # quedan 2,00 < 2,50 (0,25 %)
    stakes = allocate_daily(picks, bankroll=1000.0)
    assert stakes == {"a": 98.0, "b": 0.0}


def test_un_stake_bruto_por_debajo_del_minimo_se_descarta() -> None:
    assert allocate_daily([("a", 2.0, 0.05)], bankroll=1000.0) == {"a": 0.0}


@pytest.mark.parametrize(
    ("pnl", "reached"),
    [(-50.0, True), (-49.99, False), (-80.0, True), (0.0, False), (120.0, False)],
)
def test_limite_de_perdida_diaria_del_5_por_ciento(pnl: float, reached: bool) -> None:
    assert loss_limit_reached(pnl, bankroll=1000.0) is reached


def test_la_exposicion_ya_abierta_reduce_el_hueco_del_dia() -> None:
    # 60 ya abiertos de un tope de 100: caben 40
    stakes = allocate_daily([("a", 30.0, 0.09), ("b", 30.0, 0.05)], bankroll=1000.0, already=60.0)
    assert stakes == {"a": 30.0, "b": 10.0}


def test_con_el_dia_ya_completo_no_cabe_nada() -> None:
    assert allocate_daily([("a", 30.0, 0.09)], bankroll=1000.0, already=100.0) == {"a": 0.0}

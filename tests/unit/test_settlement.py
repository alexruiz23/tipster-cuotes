"""Liquidación de picks (ADR 012) con casos calculados a mano."""

import pytest

from tipster.tracking.settlement import outcome_of, settle_pick


@pytest.mark.parametrize(
    ("market", "hg", "ag", "expected"),
    [
        ("1x2", 2, 1, "local"),
        ("1x2", 1, 1, "empate"),
        ("1x2", 0, 3, "visitante"),
        ("ou_2.5", 2, 1, "mas"),  # 3 goles
        ("ou_2.5", 1, 1, "menos"),  # 2 goles
        ("ou_2.5", 0, 0, "menos"),
        ("ou_2.5", 3, 2, "mas"),
    ],
)
def test_resultado_segun_el_mercado(market: str, hg: int, ag: int, expected: str) -> None:
    assert outcome_of(market, hg, ag) == expected


def test_pick_ganado_con_stake_a_mano() -> None:
    s = settle_pick("1x2", "local", price=2.20, stake=20.0, home_goals=2, away_goals=1)
    assert (s.result, s.status) == ("local", "ganado")
    assert s.profit == pytest.approx(24.0, abs=1e-9)  # 20 · (2,20 − 1)


def test_pick_perdido_con_stake_a_mano() -> None:
    s = settle_pick("1x2", "local", price=2.20, stake=20.0, home_goals=0, away_goals=0)
    assert (s.result, s.status, s.profit) == ("empate", "perdido", -20.0)


def test_over_under_a_mano() -> None:
    assert settle_pick(
        "ou_2.5", "mas", 2.05, 10.0, home_goals=2, away_goals=1
    ).profit == pytest.approx(10.5)
    lost = settle_pick("ou_2.5", "mas", 2.05, 10.0, home_goals=1, away_goals=1)
    assert (lost.result, lost.status, lost.profit) == ("menos", "perdido", -10.0)


@pytest.mark.parametrize("stake", [None, 0.0])
def test_sin_stake_se_registra_el_resultado_pero_no_hay_beneficio(stake: float | None) -> None:
    s = settle_pick("1x2", "visitante", price=3.0, stake=stake, home_goals=0, away_goals=1)
    assert (s.status, s.profit) == ("ganado", None)

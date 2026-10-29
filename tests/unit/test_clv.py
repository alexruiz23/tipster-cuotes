"""CLV con la cuota justa de cierre (ADR 012, ADR 002) con casos calculados a mano."""

import pytest

from tipster.pricing.devig import DevigMethod
from tipster.tracking.clv import closing_fair_odds, clv, summarize_clv


def test_clv_a_mano() -> None:
    assert clv(2.20, 2.00) == pytest.approx(0.10, abs=1e-12)  # caso del PLAN
    assert clv(1.90, 2.00) == pytest.approx(-0.05, abs=1e-12)
    assert clv(2.00, 2.00) == 0.0


def test_la_cuota_justa_de_cierre_sale_del_cierre_crudo_sin_margen() -> None:
    raw = (1.80, 3.60, 3.60)  # Σ 1/cuota = 10/9
    assert closing_fair_odds(raw, 0, DevigMethod.MULTIPLICATIVE) == pytest.approx(2.0, abs=1e-12)
    assert closing_fair_odds(raw, 1, DevigMethod.MULTIPLICATIVE) == pytest.approx(4.0, abs=1e-12)
    # con la cuota cruda el CLV de 2,20 saldría 22 % - 10 % = menos: 2,20/1,80 − 1 = +22,2 %
    assert clv(2.20, closing_fair_odds(raw, 0, DevigMethod.MULTIPLICATIVE)) == pytest.approx(0.10)


def test_resumen_del_clv_a_mano() -> None:
    summary = summarize_clv([(0.10, 10.0), (-0.05, 10.0), (0.02, 20.0)])
    assert summary.n == 3
    assert summary.mean == pytest.approx(0.023333, abs=1e-6)
    assert summary.weighted_mean == pytest.approx(0.0225, abs=1e-12)  # (1,0 − 0,5 + 0,4) / 40
    assert summary.median == pytest.approx(0.02, abs=1e-12)
    assert summary.share_positive == pytest.approx(2 / 3, abs=1e-12)
    assert summary.stderr == pytest.approx(0.043333, abs=1e-6)  # sd 0,075056 / √3


def test_resumen_sin_picks_o_con_uno() -> None:
    empty = summarize_clv([])
    assert empty.n == 0 and empty.stderr is None
    one = summarize_clv([(0.04, 5.0)])
    assert one.mean == pytest.approx(0.04) and one.stderr is None  # sin desviación con n = 1

import pytest

from tipster.tracking.bootstrap import block_bootstrap_ci


def test_con_pocas_semanas_no_da_intervalo() -> None:
    assert block_bootstrap_ci([[0.1], [0.2], [0.3]]) is None
    assert block_bootstrap_ci([[0.1], [], [], [0.2]]) is None  # las vacías no cuentan


def test_contiene_la_media_y_es_reproducible() -> None:
    blocks = [[0.05, -0.02], [0.01], [-0.03, 0.04, 0.0], [0.02], [0.06, -0.01]]
    ci = block_bootstrap_ci(blocks)
    assert ci is not None
    mean = sum(x for b in blocks for x in b) / sum(len(b) for b in blocks)
    assert ci[0] <= mean <= ci[1]
    assert block_bootstrap_ci(blocks) == ci


def test_semanas_correlacionadas_dan_un_intervalo_ancho() -> None:
    blocks = [[0.05] * 10 if i % 2 else [-0.05] * 10 for i in range(8)]
    lo, hi = block_bootstrap_ci(blocks) or (0.0, 0.0)
    assert hi - lo > 0.04  # ± 5 % por semana: el intervalo no colapsa

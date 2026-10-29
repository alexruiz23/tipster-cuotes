"""Walk-forward estricto (ADR 011): ningún bloque ve datos de su fecha ni posteriores."""

import math
from datetime import date, timedelta

import numpy as np
import pytest

from tipster.errors import FitError
from tipster.models import walk_forward
from tipster.models.dixon_coles import Match, fit
from tipster.models.elo import STARTS, run
from tipster.models.walk_forward import day_blocks, walk_forward_dixon_coles, walk_forward_elo

A = np.array([0.4, 0.1, -0.1, -0.4])
D = np.array([0.05, -0.05, 0.10, -0.10])
START = date(2023, 1, 1)


def _league(seed: int, weeks: int = 40) -> list[Match]:
    """4 equipos, un partido por par ordenado cada semana, en el orden cronológico."""
    rng = np.random.default_rng(seed)
    matches = []
    for week in range(weeks):
        day = START + timedelta(days=7 * week)
        for h in range(4):
            for v in range(4):
                if h != v:
                    goals = (
                        int(rng.poisson(math.exp(A[h] + D[v] + 0.25))),
                        int(rng.poisson(math.exp(A[v] + D[h]))),
                    )
                    matches.append(Match(h + 1, v + 1, *goals, day))
    return matches


@pytest.fixture
def split() -> tuple[list[Match], list[Match]]:
    matches = _league(5)
    return matches[: 12 * 24], matches[12 * 24 :]  # 24 semanas de historia y 16 de prueba


def test_day_blocks_a_mano() -> None:
    days = [date(2024, 1, 1), date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 8)]
    matches = [Match(1, 2, 0, 0, d) for d in days]
    assert day_blocks(matches, 1) == [[0, 1], [2], [3]]
    assert day_blocks(matches, 7) == [[0, 1, 2], [3]]  # desfases 0, 0, 1 y 7 días
    assert day_blocks(matches[::-1], 1) == [[2, 3], [1], [0]]  # por fecha; índices de entrada


def test_el_primer_bloque_es_el_ajuste_directo_con_el_historial(
    split: tuple[list[Match], list[Match]],
) -> None:
    history, test = split
    result = walk_forward_dixon_coles(history, test, half_life_days=730, block_days=7)
    direct = fit(history, half_life_days=730)
    first = [i for i, m in enumerate(test) if m.day == test[0].day]
    for i in first:
        expected = direct.predict_proba(test[i].home_id, test[i].away_id)
        assert tuple(result.probs[i]) == pytest.approx(
            (expected["local"], expected["empate"], expected["visitante"]), abs=1e-12
        )


def test_cada_ajuste_solo_ve_datos_anteriores_al_bloque(
    split: tuple[list[Match], list[Match]], monkeypatch: pytest.MonkeyPatch
) -> None:
    history, test = split
    seen = []

    def spy(matches: list[Match], **kwargs: float | None) -> object:
        seen.append(list(matches))
        return fit(matches, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(walk_forward, "fit", spy)
    result = walk_forward_dixon_coles(history, test, half_life_days=730, block_days=7)
    blocks = day_blocks(test, 7)
    assert len(seen) == len(blocks) == result.fits
    for indices, training in zip(blocks, seen, strict=True):
        first_day = min(test[i].day for i in indices)  # type: ignore[type-var]
        assert all(m.day < first_day for m in training)  # type: ignore[operator]
        before = [m for m in test if m.day < first_day]  # type: ignore[operator]
        assert len(training) == len(history) + len(before)  # y no se deja fuera nada anterior
        assert not any(test[i] in training for i in indices)


def test_las_predicciones_no_dependen_de_los_resultados_posteriores(
    split: tuple[list[Match], list[Match]],
) -> None:
    history, test = split
    cut = 12 * 8  # a partir de la 9.ª semana de prueba se cambian los resultados
    altered = [
        *test[:cut],
        *(
            Match(m.home_id, m.away_id, m.away_goals + 2, m.home_goals + 1, m.day)
            for m in test[cut:]
        ),
    ]
    a = walk_forward_dixon_coles(history, test, half_life_days=730, block_days=7)
    b = walk_forward_dixon_coles(history, altered, half_life_days=730, block_days=7)
    assert np.array_equal(a.probs[:cut], b.probs[:cut])
    assert not np.array_equal(a.probs[cut:], b.probs[cut:])
    ea, eb = (
        walk_forward_elo(history, test, STARTS[0]),
        walk_forward_elo(history, altered, STARTS[0]),
    )
    assert np.array_equal(ea[:cut], eb[:cut])
    assert not np.array_equal(ea[cut:], eb[cut:])


def test_el_orden_de_salida_es_el_de_la_prueba(split: tuple[list[Match], list[Match]]) -> None:
    history, test = split
    ordered = walk_forward_dixon_coles(history, test, half_life_days=730, block_days=7).probs
    reversed_ = walk_forward_dixon_coles(
        history, test[::-1], half_life_days=730, block_days=7
    ).probs
    assert np.allclose(ordered, reversed_[::-1], atol=1e-12)


def test_walk_forward_elo_es_la_parte_final_de_la_pasada_prequential(
    split: tuple[list[Match], list[Match]],
) -> None:
    history, test = split
    probs = walk_forward_elo(history, test, STARTS[0])
    expected = run([*history, *test], STARTS[0]).probs[len(history) :]
    assert np.allclose(probs, np.array(expected), atol=1e-15)
    assert probs.shape == (len(test), 3)


def test_la_prueba_no_puede_solaparse_con_el_historial(
    split: tuple[list[Match], list[Match]],
) -> None:
    history, test = split
    with pytest.raises(FitError, match="historial"):
        walk_forward_dixon_coles(test, history, half_life_days=730)  # al revés: se solapan
    with pytest.raises(FitError, match="historial"):
        walk_forward_elo(test, history, STARTS[0])


def _with_newcomer(split: tuple[list[Match], list[Match]]) -> tuple[list[Match], list[Match]]:
    """Un ascendido (equipo 5) juega un único partido el primer día de la prueba."""
    history, test = split
    day = test[0].day
    assert day is not None
    return history, [Match(5, 1, 3, 0, day), *test]


def test_un_equipo_con_un_solo_partido_diverge_sin_l2_y_converge_con_ella(
    split: tuple[list[Match], list[Match]],
) -> None:
    history, test = _with_newcomer(split)
    with pytest.raises(FitError, match="diverge"):
        walk_forward_dixon_coles(history, test, half_life_days=730, block_days=7)
    result = walk_forward_dixon_coles(history, test, half_life_days=730, block_days=7, l2=0.01)
    assert result.probs.shape == (len(test), 3)
    assert np.allclose(result.probs.sum(axis=1), 1.0)


def test_l2_se_pasa_a_cada_ajuste(
    split: tuple[list[Match], list[Match]], monkeypatch: pytest.MonkeyPatch
) -> None:
    history, test = split
    seen = []

    def spy(matches: list[Match], **kwargs: float | None) -> object:
        seen.append(kwargs["l2"])
        return fit(matches, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(walk_forward, "fit", spy)
    walk_forward_dixon_coles(history, test, half_life_days=730, block_days=28, l2=0.01)
    assert seen and set(seen) == {0.01}

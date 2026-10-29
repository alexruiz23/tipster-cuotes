"""Malla de hiperparámetros de Dixon-Coles con validación walk-forward simple (ADR 009)."""

import math
from datetime import date, timedelta

import numpy as np
import pytest

from tipster.models import tuning
from tipster.models.dixon_coles import Match, fit
from tipster.models.tuning import GridResult, grid_search, predict_matches

A_EARLY = np.array([0.5, 0.1, -0.1, -0.5])
A_LATE = np.array([-0.5, 0.1, -0.1, 0.5])  # el equipo 1 se hunde y el 4 sube
D = np.array([0.05, -0.05, 0.10, -0.10])


def _period(rng: np.random.Generator, a: np.ndarray, start: date, repeats: int) -> list[Match]:
    matches = []
    for rep in range(repeats):
        day = start + timedelta(days=7 * rep)
        for h in range(4):
            for v in range(4):
                if h != v:
                    lam = math.exp(a[h] + D[v] + 0.25)
                    mu = math.exp(a[v] + D[h])
                    matches.append(
                        Match(h + 1, v + 1, int(rng.poisson(lam)), int(rng.poisson(mu)), day)
                    )
    return matches


@pytest.fixture
def drift() -> tuple[list[Match], list[Match]]:
    rng = np.random.default_rng(11)
    train = _period(rng, A_EARLY, date(2022, 1, 1), 30) + _period(rng, A_LATE, date(2022, 8, 1), 30)
    test = _period(rng, A_LATE, date(2023, 3, 1), 15)
    return train, test


def test_la_malla_devuelve_una_fila_por_combinacion_ordenada_por_log_loss(
    drift: tuple[list[Match], list[Match]],
) -> None:
    train, test = drift
    results = grid_search(train, test, half_lives=[30, 90, None], l2s=[0.0, 5.0])
    assert {(r.half_life_days, r.l2) for r in results} == {
        (hl, l2) for hl in (30, 90, None) for l2 in (0.0, 5.0)
    }
    losses = [r.log_loss for r in results]
    assert losses == sorted(losses)
    assert all(isinstance(r, GridResult) and r.error is None for r in results)


def test_con_deriva_de_nivel_gana_una_vida_media_corta_al_no_decaer(
    drift: tuple[list[Match], list[Match]],
) -> None:
    train, test = drift
    results = grid_search(train, test, half_lives=[30, None], l2s=[0.0])
    by_hl = {r.half_life_days: r for r in results}
    assert by_hl[30].log_loss < by_hl[None].log_loss
    assert results[0].half_life_days == 30


def test_predict_matches_devuelve_probabilidades_que_suman_uno_y_cuenta_los_desconocidos(
    drift: tuple[list[Match], list[Match]],
) -> None:
    train, test = drift
    model = fit(train)
    probs, unseen = predict_matches(model, [*test[:3], Match(9, 1, 1, 0, date(2023, 3, 1))])
    assert probs.shape == (4, 3)
    assert probs.sum(axis=1) == pytest.approx(np.ones(4), abs=1e-12)
    assert unseen == 1  # el equipo 9 no estaba en el entrenamiento


def test_una_celda_que_no_converge_se_registra_sin_romper_la_malla() -> None:
    # 6 partidos: el MLE sin penalización no existe (ADR 008) pero con L2 sí
    toy = [
        Match(1, 2, 1, 0, date(2023, 1, 1)),
        Match(1, 3, 0, 0, date(2023, 1, 2)),
        Match(1, 4, 2, 1, date(2023, 1, 3)),
        Match(2, 3, 1, 1, date(2023, 1, 4)),
        Match(2, 4, 0, 1, date(2023, 1, 5)),
        Match(3, 4, 3, 2, date(2023, 1, 6)),
    ]
    results = grid_search(toy, toy[:2], half_lives=[None], l2s=[0.0, 5.0])
    by_l2 = {r.l2: r for r in results}
    assert by_l2[0.0].error is not None
    assert by_l2[5.0].error is None
    assert results[0].l2 == 5.0  # las celdas con error van al final


def test_el_ajuste_de_la_malla_solo_ve_el_entrenamiento(
    drift: tuple[list[Match], list[Match]], monkeypatch: pytest.MonkeyPatch
) -> None:
    train, test = drift
    seen: list[list[Match]] = []

    def spy(matches: list[Match], **kwargs: float | None) -> object:
        seen.append(list(matches))
        return fit(matches, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(tuning, "fit", spy)
    grid_search(train, test, half_lives=[None, 90], l2s=[0.0, 1.0])
    assert len(seen) == 4
    assert all(matches == train for matches in seen)
    assert not any(m in train for m in test)  # los dos periodos no comparten partidos

"""Elo-Davidson (ADR 010) con casos calculados a mano."""

import math
from datetime import date, timedelta

import numpy as np
import pytest

from tipster.errors import FitError
from tipster.models.dixon_coles import Match
from tipster.models.elo import (
    STARTS,
    EloParams,
    davidson_probs,
    fit_params,
    prequential_nll,
    run,
    season_of,
)

K20 = EloParams(k=20.0, home_advantage=100.0, nu=0.7, carry=1.0, newcomer_offset=0.0)
D1 = date(2020, 9, 1)  # temporada 2020
D2 = date(2021, 9, 1)  # temporada 2021


def _m(h: int, a: int, hg: int, ag: int, day: date) -> Match:
    return Match(h, a, hg, ag, day)


# -- Davidson ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("d", "nu", "expected", "expected_e"),
    [
        (0.0, 0.5, (0.4, 0.2, 0.4), 0.5),
        (100.0, 0.7, (0.479095, 0.251490, 0.269415), 0.604840),
        (-100.0, 0.7, (0.269415, 0.251490, 0.479095), 0.395160),
        (200.0, 0.7, (0.584841, 0.230216, 0.184943), 0.699949),
    ],
)
def test_davidson_a_mano(
    d: float, nu: float, expected: tuple[float, float, float], expected_e: float
) -> None:
    probs = davidson_probs(d, nu)
    assert probs == pytest.approx(expected, abs=1e-6)
    assert sum(probs) == pytest.approx(1.0, abs=1e-12)
    assert probs[0] + 0.5 * probs[1] == pytest.approx(expected_e, abs=1e-6)


def test_la_probabilidad_de_empate_es_maxima_con_equipos_iguales() -> None:
    draws = [davidson_probs(d, 0.7)[1] for d in (0, 50, 100, 200, 400)]
    assert draws == sorted(draws, reverse=True)
    assert davidson_probs(0.0, 0.7)[1] == pytest.approx(0.7 / 2.7, abs=1e-12)


def test_el_score_de_la_log_verosimilitud_es_s_menos_e() -> None:
    # d log P(resultado) / d ln γ_h = S − E; ln γ_h = d·ln10/400 → d/dd = (ln10/400)(S − E)
    d, nu, eps = 73.0, 0.8, 1e-5
    local, draw, _ = davidson_probs(d, nu)
    e = local + 0.5 * draw
    for index, s in enumerate((1.0, 0.5, 0.0)):
        hi = math.log(davidson_probs(d + eps, nu)[index])
        lo = math.log(davidson_probs(d - eps, nu)[index])
        slope = (hi - lo) / (2 * eps) * 400 / math.log(10)
        assert slope == pytest.approx(s - e, abs=1e-7)


# -- Actualización -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("hg", "ag", "delta_home"),
    [(2, 1, 7.9032), (1, 1, -2.0968), (0, 1, -12.0968)],
)
def test_actualizacion_a_mano_con_d_100(hg: int, ag: int, delta_home: float) -> None:
    result = run([_m(1, 2, hg, ag, D1)], K20)
    assert result.probs[0] == pytest.approx(davidson_probs(100.0, 0.7), abs=1e-12)
    assert result.fit.rating(1) == pytest.approx(1500 + delta_home, abs=1e-4)
    assert result.fit.rating(2) == pytest.approx(1500 - delta_home, abs=1e-4)  # suma cero


def test_con_d_cero_el_local_que_gana_sube_k_por_un_medio() -> None:
    params = EloParams(k=20.0, home_advantage=0.0, nu=0.5, carry=1.0, newcomer_offset=0.0)
    result = run([_m(1, 2, 3, 0, D1)], params)
    assert result.fit.rating(1) == pytest.approx(1510.0, abs=1e-9)
    assert result.fit.rating(2) == pytest.approx(1490.0, abs=1e-9)


def test_la_suma_de_ratings_se_conserva_dentro_de_una_temporada() -> None:
    days = [D1 + timedelta(days=7 * i) for i in range(6)]
    matches = [
        _m(1, 2, 2, 0, days[0]), _m(3, 4, 1, 1, days[0]),
        _m(1, 3, 0, 1, days[1]), _m(2, 4, 3, 2, days[1]),
        _m(1, 4, 1, 0, days[2]), _m(2, 3, 0, 0, days[2]),
        _m(4, 1, 2, 2, days[3]), _m(3, 2, 1, 0, days[3]),
    ]  # fmt: skip
    fit = run(matches, K20).fit
    assert sum(fit.rating(t) for t in (1, 2, 3, 4)) == pytest.approx(6000.0, abs=1e-9)


def test_season_of_corta_el_1_de_agosto() -> None:
    assert season_of(date(2021, 7, 31)) == 2020
    assert season_of(date(2021, 8, 1)) == 2021


# -- Regresión entre temporadas y equipos nuevos -----------------------------------------------


def test_regresion_entre_temporadas_a_mano() -> None:
    params = EloParams(k=20.0, home_advantage=100.0, nu=0.7, carry=0.5, newcomer_offset=0.0)
    fit = run([_m(1, 2, 2, 1, D1)], params).fit  # 1507.9032 y 1492.0968
    one = fit.regressed_to(2021)
    assert one.rating(1) == pytest.approx(1500 + 0.5 * 7.9032, abs=1e-4)
    two = fit.regressed_to(2022)  # c² = 0,25 tras una temporada sin jugar
    assert two.rating(1) == pytest.approx(1500 + 0.25 * 7.9032, abs=1e-4)
    assert fit.rating(1) == pytest.approx(1507.9032, abs=1e-4)  # no muta el original


def test_run_aplica_la_regresion_antes_de_predecir_la_nueva_temporada() -> None:
    params = EloParams(k=20.0, home_advantage=100.0, nu=0.7, carry=0.5, newcomer_offset=0.0)
    result = run([_m(1, 2, 2, 1, D1), _m(1, 2, 0, 0, D2)], params)
    d = (1500 + 0.5 * 7.9032) + 100 - (1500 - 0.5 * 7.9032)
    assert result.probs[1] == pytest.approx(davidson_probs(d, 0.7), abs=1e-6)


def test_un_equipo_nuevo_entra_con_la_media_mas_delta_y_los_del_primer_dia_con_1500() -> None:
    params = EloParams(k=20.0, home_advantage=100.0, nu=0.7, carry=1.0, newcomer_offset=-50.0)
    result = run([_m(1, 2, 2, 1, D1), _m(3, 1, 0, 0, D2)], params)
    assert result.fit.knows(2)
    # primer día: ambos a 1 500 (sin δ); segunda temporada: el 3 entra con 1 500 − 50 = 1 450
    assert result.probs[0] == pytest.approx(davidson_probs(100.0, 0.7), abs=1e-12)
    d = 1450 + 100 - (1500 + 7.9032)
    assert result.probs[1] == pytest.approx(davidson_probs(d, 0.7), abs=1e-6)
    assert not result.fit.knows(99)
    assert result.fit.rating(99) == pytest.approx(
        np.mean([result.fit.rating(t) for t in (1, 2, 3)]) - 50, abs=1.0
    )


# -- Sin fuga ----------------------------------------------------------------------------------


def _season(seed: int, n: int = 30) -> list[Match]:
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        h, a = rng.choice(6, size=2, replace=False) + 1
        out.append(
            _m(
                int(h),
                int(a),
                int(rng.poisson(1.4)),
                int(rng.poisson(1.1)),
                D1 + timedelta(days=3 * i),
            )
        )
    return out


def test_las_predicciones_no_dependen_de_los_resultados_posteriores() -> None:
    base = _season(1)
    altered = [
        *base[:20],
        *(Match(m.home_id, m.away_id, m.away_goals + 3, m.home_goals, m.day) for m in base[20:]),
    ]
    p1, p2 = run(base, K20).probs, run(altered, K20).probs
    assert p1[:20] == p2[:20]
    assert p1[20:] != p2[20:]


def test_las_predicciones_de_un_dia_se_hacen_antes_de_actualizar_ese_dia() -> None:
    day0, day1 = D1, D1 + timedelta(days=7)
    matches = [
        _m(1, 2, 3, 0, day0),
        _m(1, 3, 1, 0, day1),  # el equipo 1 juega dos veces el mismo día
        _m(1, 4, 0, 2, day1),
    ]
    probs = run(matches, K20).probs
    # 3 y 4 entran igual (misma media y δ): si la segunda predicción viera la actualización del
    # primer partido de ese día, el rating del 1 sería otro y las probabilidades diferirían
    assert probs[1] == pytest.approx(probs[2], abs=1e-12)


def test_los_partidos_se_procesan_por_fecha_aunque_lleguen_desordenados() -> None:
    ordered = _season(2)
    shuffled = ordered[::-1]
    a, b = run(ordered, K20), run(shuffled, K20)
    assert a.fit.rating(1) == pytest.approx(b.fit.rating(1), abs=1e-9)
    assert a.probs == b.probs[::-1]  # las probabilidades salen en el orden de entrada


def test_sin_fechas_es_un_error() -> None:
    with pytest.raises(FitError, match="fecha"):
        run([Match(1, 2, 1, 0)], K20)


# -- Estimación de hiperparámetros -------------------------------------------------------------

TRUE = EloParams(k=24.0, home_advantage=70.0, nu=0.65, carry=0.7, newcomer_offset=-40.0)
# Tolerancias = 3 desviaciones típicas medidas en 12 simulaciones (semillas 0–11): H 6,8 · ν 0,049 ·
# K 4,7 · carry 0,14. δ casi no se identifica (desviación 40: entra un solo equipo nuevo por
# temporada), así que no se comprueba. Sesgo medido: H −0,2 · ν +0,005 · K −1,1 · carry −0,03.
TOL_H, TOL_NU, TOL_K, TOL_CARRY = 21.0, 0.15, 15.0, 0.45


def simulate(seed: int, seasons: int = 14, n_teams: int = 10) -> list[Match]:
    """Resultados 1X2 generados por el propio modelo: cada partido (uno por día) se sortea con las
    probabilidades de Davidson de los ratings vigentes, que luego se actualizan."""
    rng = np.random.default_rng(seed)
    results: list[Match] = []
    state = None
    team_ids = list(range(1, n_teams + 1))
    for s in range(seasons):
        if s:  # sale un equipo y entra uno nuevo cada temporada (id nuevo)
            team_ids = [*team_ids[1:], n_teams + s]
        day = date(2010 + s, 8, 20)
        for rnd in range(2):
            for i in team_ids:
                for j in team_ids:
                    if i >= j:
                        continue
                    h, a = (i, j) if rnd == 0 else (j, i)
                    probs = run([_m(h, a, 0, 0, day)], TRUE, state).probs[0]  # solo para predecir
                    hg, ag = ((1, 0), (0, 0), (0, 1))[int(rng.choice(3, p=probs))]
                    match = _m(h, a, hg, ag, day)
                    state = run([match], TRUE, state).fit
                    results.append(match)
                    day += timedelta(days=1)
    return results


def test_fit_params_recupera_h_y_nu_y_no_es_peor_que_los_parametros_verdaderos() -> None:
    matches = simulate(seed=1)
    scored_after = date(2012, 7, 31)  # calentamiento de dos temporadas
    fitted = fit_params(matches, scored_after, starts=(STARTS[0],))
    assert prequential_nll(matches, fitted, scored_after) <= (
        prequential_nll(matches, TRUE, scored_after) + 1e-6
    )
    assert fitted.home_advantage == pytest.approx(TRUE.home_advantage, abs=TOL_H)
    assert fitted.nu == pytest.approx(TRUE.nu, abs=TOL_NU)
    assert fitted.k == pytest.approx(TRUE.k, abs=TOL_K)
    assert fitted.carry == pytest.approx(TRUE.carry, abs=TOL_CARRY)

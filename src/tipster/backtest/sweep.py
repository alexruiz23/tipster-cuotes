"""Barrido de umbrales con validación fuera de muestra y el informe de texto (BACKLOG 53).

Se elige con las temporadas antiguas y se valida con las dos últimas sin tocarlas; el informe
dice cuántas combinaciones se probaron, porque con muchas alguna sale bien por pura suerte.
"""

from collections.abc import Sequence
from dataclasses import replace
from itertools import product
from typing import Any

from tipster.backtest.football_data import LoadReport, Match
from tipster.backtest.simulate import Bet, Strategy, Summary, block_bootstrap, run, summarize

GRID = {
    "longshot_odds": (3.0, 4.0, 5.0),
    "ev_min": (0.02, 0.03, 0.05),
    "longshot_ev_min": (0.04, 0.06, 0.08, 0.10),
    "max_odds": (6.0, 8.0, 10.0, 15.0),
    "max_open_longshots": (1, 2, 3, 99),
}
VALIDATION_SEASONS = 2
MIN_TRAIN_BETS = 300  # por debajo, el CLV medio es demasiado ruidoso para elegir


def split_seasons(matches: Sequence[Match]) -> tuple[list[str], list[str]]:
    seasons = sorted({m.season for m in matches})
    return seasons[:-VALIDATION_SEASONS], seasons[-VALIDATION_SEASONS:]


def _fmt(s: Summary) -> str:
    if s.n == 0:
        return "0 picks"
    se = "" if s.clv_se is None else f" ± {s.clv_se * 100:.1f}"
    return (
        f"{s.n:5d} picks · CLV {s.clv * 100:+.2f} %{se} · ROI {s.roi * 100:+.1f} % · "  # type: ignore[operator]
        f"acierto {s.hit * 100:.0f} %"  # type: ignore[operator]
    )


def _ci(bets: Sequence[Bet]) -> str:
    ci = block_bootstrap(bets)
    if ci is None:
        return "IC 95 %: muestra insuficiente"
    (c0, c1), (r0, r1) = ci
    return (
        f"IC 95 % (bootstrap por semanas): CLV [{c0 * 100:+.2f}, {c1 * 100:+.2f}] % · "
        f"ROI [{r0 * 100:+.1f}, {r1 * 100:+.1f}] %"
    )


def _by(bets: Sequence[Bet], seasons: Sequence[str]) -> list[Bet]:
    wanted = set(seasons)
    return [b for b in bets if b.season in wanted]


def sweep(
    matches: Sequence[Match], base: Strategy, train: Sequence[str], valid: Sequence[str]
) -> list[tuple[Strategy, Summary, Summary]]:
    names = list(GRID)
    rows = []
    for values in product(*GRID.values()):
        overrides: dict[str, Any] = dict(zip(names, values, strict=True))
        s = replace(base, **overrides)
        bets = run(matches, s)
        rows.append((s, summarize(_by(bets, train)), summarize(_by(bets, valid))))
    return rows


def report(matches: Sequence[Match], loaded: LoadReport, current: Strategy) -> str:
    train, valid = split_seasons(matches)
    out = [
        "BACKTEST con football-data.co.uk (5 ligas, sin Champions)",
        f"Partidos: {loaded.kept} usados de {loaded.rows}; descartados: "
        + (", ".join(f"{k} {v}" for k, v in loaded.dropped.items()) or "ninguno"),
        f"Entrenamiento: {train[0]}–{train[-1]} · validación (sin tocar): {', '.join(valid)}",
        "p justa = Shin sobre el Pinnacle PREVIO; CLV frente al Pinnacle de CIERRE (Shin).",
        "No probado: max_days_ahead (una sola foto de cuotas por partido) ni casas .es. "
        "Tope de improbables abiertos aplicado por semana ISO (aproximación).",
        "",
        f"## Configuración actual (longshot {current.longshot_odds}, EV {current.ev_min:.0%}/"
        f"{current.longshot_ev_min:.0%}, max {current.max_odds}, "
        f"tope {current.max_open_longshots})",
    ]
    for book, note in (("b365", "casa realista"), ("avg", "media del mercado"),
                       ("max", "techo optimista")):  # fmt: skip
        bets = run(matches, replace(current, book=book))
        out.append(f"  {book:5s} ({note})")
        out.append(f"    entrenamiento: {_fmt(summarize(_by(bets, train)))}")
        out.append(f"    validación:    {_fmt(summarize(_by(bets, valid)))}")
    bets = run(matches, current)
    for label, tier in (
        ("total", bets),
        ("principal", [b for b in bets if not b.longshot]),
        ("improbable", [b for b in bets if b.longshot]),
    ):
        out.append(f"  nivel {label}: {_fmt(summarize(tier))}")
        out.append(f"    {_ci(tier)}")
    out += ["", "## CLV por temporada (configuración actual, b365)"]
    for season in train + valid:
        out.append(f"  {season}: {_fmt(summarize(_by(bets, [season])))}")

    rows = sweep(matches, current, train, valid)
    ranked = sorted(
        (r for r in rows if r[1].n >= MIN_TRAIN_BETS and r[1].clv is not None),
        key=lambda r: -(r[1].clv or 0),
    )
    out += [
        "",
        f"## Barrido: {len(rows)} combinaciones probadas "
        f"(elegidas por CLV en entrenamiento, mín. {MIN_TRAIN_BETS} picks)",
    ]
    for s, tr, va in ranked[:5]:
        out.append(
            f"  longshot {s.longshot_odds} · EV {s.ev_min:.0%}/{s.longshot_ev_min:.0%} · "
            f"max {s.max_odds} · tope {s.max_open_longshots}"
        )
        out.append(f"    entrenamiento: {_fmt(tr)}")
        out.append(f"    validación:    {_fmt(va)}")
    out += [
        "",
        "Lectura: si la validación de la combinación elegida no supera a la de la configuración "
        "actual, el barrido solo ha encontrado ruido y no hay motivo para cambiar umbrales.",
    ]
    return "\n".join(out)

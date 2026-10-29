"""Calibración del cierre de Pinnacle (devig multiplicativo) en 2024/25 y 2025/26 (ADR 012).

Solo mide: no elige ningún hiperparámetro.
Uso: PYTHONPATH=src python scripts/calibracion_pinnacle.py
"""

import sqlite3
from datetime import date

import numpy as np

from tipster.history.matches import load_market_probs, load_matches
from tipster.models.dixon_coles import Floats, Ints
from tipster.models.evaluation import brier, outcome_index, reliability_table

LEAGUES = ["premier", "laliga", "serie_a", "bundesliga", "ligue_1", "segunda"]
CUTOFF = date(2025, 7, 23)  # cierre de la API pública de Pinnacle (ADR 002)
EDGES = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0]
NAMES = ("local", "empate", "visitante")


def load(conn: sqlite3.Connection, start: date, end: date) -> tuple[Floats, Ints, list[date], int]:
    probs, outcomes, days, total = [], [], [], 0
    for league in LEAGUES:
        matches = load_matches(conn, league, start, end)
        for match, p in zip(matches, load_market_probs(conn, league, start, end), strict=True):
            total += 1
            if p is not None and match.day is not None:
                probs.append(p)
                outcomes.append(outcome_index(match.home_goals, match.away_goals))
                days.append(match.day)
    return np.array(probs), np.array(outcomes), days, total


def summary(label: str, probs: Floats, outcomes: Ints, total: int, base: Floats) -> None:
    rows = np.arange(len(outcomes))
    loss = -np.log(probs[rows, outcomes])
    uninformed = -np.log(base[outcomes])
    print(
        f"{label:<34} n={len(outcomes):>5}/{total:<5} log-loss {loss.mean():.4f} ± "
        f"{loss.std(ddof=1) / np.sqrt(len(loss)):.4f}  Brier {brier(probs, outcomes):.4f}  "
        f"sin información {uninformed.mean():.4f}  "
        f"(mercado − nada {loss.mean() - uninformed.mean():+.4f})"
    )


def reliability(probs: Floats, outcomes: Ints) -> None:
    for k, name in enumerate(NAMES):
        cells = [
            f"{b.low:.1f}-{b.high:.1f}: n={b.n} prev {b.mean_predicted:.3f} real {b.observed:.3f}"
            for b in reliability_table(probs, outcomes, k, EDGES)
            if b.n
        ]
        print(f"  {name}: " + " | ".join(cells))


def main() -> None:
    conn = sqlite3.connect("file:data/tipster.sqlite?mode=ro", uri=True)
    before = load(conn, date(2016, 8, 1), date(2024, 7, 31))
    freq = np.bincount(before[1], minlength=3) / len(before[1])
    print(f"Frecuencias 1X2 hasta 2023/24 (referencia «sin información»): {np.round(freq, 4)}")
    segments = {
        "2021/22–2022/23 (validación)": (date(2021, 8, 1), date(2023, 7, 31)),
        "2024/25 (ciego)": (date(2024, 8, 1), date(2025, 7, 22)),
        "2024/25 después del 23/07/2025": (CUTOFF, date(2025, 7, 31)),
        "2025/26 ago–dic 2025": (date(2025, 8, 1), date(2025, 12, 31)),
        "2025/26 ene–mar 2026": (date(2026, 1, 1), date(2026, 3, 31)),
        "2025/26 abr–jun 2026": (date(2026, 4, 1), date(2026, 6, 30)),
    }
    for label, (start, end) in segments.items():
        probs, outcomes, _, total = load(conn, start, end)
        if len(outcomes) < 2:
            print(f"{label:<34} n={len(outcomes)}/{total}: sin partidos")
            continue
        summary(label, probs, outcomes, total, freq)
    print("\n2024/25 por liga")
    for league in LEAGUES:
        s, e = date(2024, 8, 1), date(2025, 7, 22)
        matches = load_matches(conn, league, s, e)
        market = load_market_probs(conn, league, s, e)
        rows = [
            (p, outcome_index(m.home_goals, m.away_goals))
            for m, p in zip(matches, market, strict=True)
            if p
        ]
        summary(
            league,
            np.array([r[0] for r in rows]),
            np.array([r[1] for r in rows]),
            len(matches),
            freq,
        )
    probs, outcomes, _, _ = load(conn, date(2024, 8, 1), date(2025, 7, 22))
    print("\nFiabilidad 2024/25 (prevista media → real)")
    reliability(probs, outcomes)
    for k, name in enumerate(NAMES):
        hit = (outcomes == k).astype(float)
        diff = hit - probs[:, k]
        print(
            f"Sesgo medio 2024/25 {name}: prevista {probs[:, k].mean():.3f}, "
            f"real {hit.mean():.3f}, "
            f"real − prevista {diff.mean():+.3f} ± {diff.std(ddof=1) / np.sqrt(len(diff)):.3f}"
        )


if __name__ == "__main__":
    main()

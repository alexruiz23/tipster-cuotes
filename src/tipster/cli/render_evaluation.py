"""Salida de `tipster evaluate`: tablas del walk-forward estricto. Solo escribe a stdout."""

from collections.abc import Sequence

import numpy as np
from rich.console import Console
from rich.table import Table

from tipster.models.dixon_coles import Floats
from tipster.models.evaluation import brier, log_loss, paired_difference
from tipster.models.report import LeagueReport


def _subset(r: LeagueReport, key: str) -> Floats:
    probs: Floats = getattr(r, key)
    return probs[r.has_market]


def _fmt(value: tuple[float, float]) -> str:
    return f"{value[0]:+.4f} ± {value[1]:.4f}"


def _pair(reports: Sequence[LeagueReport], a: str, b: str) -> list[str]:
    """Diferencia pareada de log-loss a − b por liga y en conjunto; contra `market`, solo en los
    partidos con cuota de Pinnacle."""
    cells, all_a, all_b, all_o = [], [], [], []
    for r in reports:
        use_market = b == "market"
        pa = _subset(r, a) if use_market else getattr(r, a)
        pb = r.market if use_market else getattr(r, b)
        out = r.outcomes[r.has_market] if use_market else r.outcomes
        assert pb is not None
        cells.append(_fmt(paired_difference(pa, pb, out)))
        all_a.append(pa)
        all_b.append(pb)
        all_o.append(out)
    cells.append(_fmt(paired_difference(np.vstack(all_a), np.vstack(all_b), np.concatenate(all_o))))
    return cells


def render_evaluation(
    console: Console, reports: Sequence[LeagueReport], block_days: int, l2: float
) -> None:
    names = [r.competition for r in reports]
    console.print(
        f"Walk-forward estricto, bloques de {block_days} día(s): Dixon-Coles se reajusta antes de "
        f"cada bloque con todo lo anterior (λ₂ = {l2:g}); el Elo se actualiza partido a partido.",
        markup=False,
    )

    hyper = Table("liga", "K", "H", "ν", "carry", "δ", "dispersión entre inicios", "equipos nuevos")
    for r in reports:
        p = r.elo_params
        hyper.add_row(
            r.competition,
            f"{p.k:.1f}",
            f"{p.home_advantage:.1f}",
            f"{p.nu:.3f}",
            f"{p.carry:.2f}",
            f"{p.newcomer_offset:.1f}",
            f"{r.elo_dispersion:.2f}",
            str(r.unseen),
        )
    console.print("Hiperparámetros del Elo (solo con el historial anterior a la prueba):")
    console.print(hyper)

    table = Table(
        "liga",
        "partidos",
        "DC sin reajuste",
        "Dixon-Coles",
        "Elo",
        "Pinnacle",
        title="log-loss (Brier)",
    )
    totals = {k: [0.0, 0.0, 0] for k in ("dc_frozen", "dc", "elo", "market")}
    for r in reports:
        cells = []
        for key in ("dc_frozen", "dc", "elo"):
            ll, br = log_loss(getattr(r, key), r.outcomes), brier(getattr(r, key), r.outcomes)
            cells.append(f"{ll:.4f} ({br:.4f})")
            totals[key][0] += ll * r.n_test
            totals[key][1] += br * r.n_test
            totals[key][2] += r.n_test
        if r.market is not None:
            out = r.outcomes[r.has_market]
            ll, br = log_loss(r.market, out), brier(r.market, out)
            cells.append(f"{ll:.4f} ({br:.4f})")
            totals["market"][0] += ll * len(out)
            totals["market"][1] += br * len(out)
            totals["market"][2] += len(out)
        table.add_row(r.competition, str(r.n_test), *cells)
    table.add_row(
        "TODAS",
        str(sum(r.n_test for r in reports)),
        *(
            f"{totals[k][0] / totals[k][2]:.4f} ({totals[k][1] / totals[k][2]:.4f})"
            if totals[k][2]
            else "-"
            for k in ("dc_frozen", "dc", "elo", "market")
        ),
    )
    console.print(table)

    diffs = Table(
        "comparación (a − b)",
        *names,
        "CONJUNTO",
        title="diferencia pareada de log-loss ± error típico",
    )
    for a, b, label in (
        ("elo", "dc", "Elo − Dixon-Coles"),
        ("dc", "dc_frozen", "Dixon-Coles reajustado − sin reajuste"),
        ("dc", "market", "Dixon-Coles − Pinnacle"),
        ("elo", "market", "Elo − Pinnacle"),
    ):
        if b == "market" and any(r.market is None for r in reports):
            diffs.add_row(label, *(["-"] * (len(reports) + 1)))  # sin cuotas de Pinnacle
        else:
            diffs.add_row(label, *_pair(reports, a, b))
    console.print(diffs)

    draws = Table("liga", "observada", "Dixon-Coles", "Elo", "Pinnacle", title="tasa de empates")
    for r in reports:
        draws.add_row(
            r.competition,
            f"{(r.outcomes == 1).mean():.3f}",
            f"{r.dc[:, 1].mean():.3f}",
            f"{r.elo[:, 1].mean():.3f}",
            f"{r.market[:, 1].mean():.3f}" if r.market is not None else "-",
        )
    observed = np.concatenate([r.outcomes for r in reports])
    draws.add_row(
        "TODAS",
        f"{(observed == 1).mean():.3f}",
        f"{np.vstack([r.dc for r in reports])[:, 1].mean():.3f}",
        f"{np.vstack([r.elo for r in reports])[:, 1].mean():.3f}",
        "",
    )
    console.print(draws)

    times = Table(
        "liga",
        "ajustes de Dixon-Coles",
        "segundos",
        "s por ajuste",
        "estimación del Elo (s)",
        title="cómputo",
    )
    for r in reports:
        times.add_row(
            r.competition,
            str(r.dc_fits),
            f"{r.dc_seconds:.1f}",
            f"{r.dc_seconds / max(r.dc_fits, 1):.2f}",
            f"{r.elo_fit_seconds:.1f}",
        )
    times.add_row(
        "TOTAL",
        str(sum(r.dc_fits for r in reports)),
        f"{sum(r.dc_seconds for r in reports):.1f}",
        "",
        f"{sum(r.elo_fit_seconds for r in reports):.1f}",
    )
    console.print(times)

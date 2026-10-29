"""Lectura de `historical_matches` para los modelos."""

import sqlite3
from datetime import date

from tipster.models.dixon_coles import Match
from tipster.pricing.devig import devig_multiplicative


def load_matches(
    conn: sqlite3.Connection, competition_id: str, start: date, end: date
) -> list[Match]:
    """Partidos de una competición entre `start` y `end` (ambos incluidos), por fecha.

    Las dos fechas van en el `WHERE`: un ajuste no puede ver partidos posteriores a `end`.
    """
    rows = conn.execute(
        "SELECT home_team_id, away_team_id, home_goals, away_goals, match_date"
        " FROM historical_matches"
        " WHERE competition_id = ? AND match_date >= ? AND match_date <= ?"
        " ORDER BY match_date, id",
        (competition_id, start.isoformat(), end.isoformat()),
    ).fetchall()
    return [Match(r[0], r[1], r[2], r[3], date.fromisoformat(r[4])) for r in rows]


def load_market_probs(
    conn: sqlite3.Connection, competition_id: str, start: date, end: date
) -> list[tuple[float, float, float] | None]:
    """Cierre de Pinnacle sin margen (multiplicativo) por partido, en el orden de `load_matches`."""
    rows = conn.execute(
        "SELECT pinnacle_home, pinnacle_draw, pinnacle_away FROM historical_matches"
        " WHERE competition_id = ? AND match_date >= ? AND match_date <= ?"
        " ORDER BY match_date, id",
        (competition_id, start.isoformat(), end.isoformat()),
    ).fetchall()
    probs: list[tuple[float, float, float] | None] = []
    for home, draw, away in rows:
        if home is None:
            probs.append(None)
        else:
            p_home, p_draw, p_away = devig_multiplicative((home, draw, away))
            probs.append((p_home, p_draw, p_away))
    return probs

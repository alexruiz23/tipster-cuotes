"""Lectura de `historical_matches` para los modelos."""

import sqlite3
from datetime import date

from tipster.models.dixon_coles import Match


def load_matches(
    conn: sqlite3.Connection, competition_id: str, start: date, end: date
) -> list[Match]:
    """Partidos de una competición entre `start` y `end` (ambos incluidos), por fecha.

    Las dos fechas van en el `WHERE`: un ajuste no puede ver partidos posteriores a `end`.
    """
    rows = conn.execute(
        "SELECT home_team_id, away_team_id, home_goals, away_goals FROM historical_matches"
        " WHERE competition_id = ? AND match_date >= ? AND match_date <= ?"
        " ORDER BY match_date, id",
        (competition_id, start.isoformat(), end.isoformat()),
    ).fetchall()
    return [Match(r[0], r[1], r[2], r[3]) for r in rows]

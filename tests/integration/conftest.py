"""Fixtures compartidas de los tests de integración."""

import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from tipster.storage.db import connect

A = np.array([0.4, 0.1, -0.1, -0.4])
D = np.array([0.05, -0.05, 0.10, -0.10])


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "tipster.sqlite"
    conn = connect(path)
    conn.execute(
        "INSERT INTO runs (command, started_at, status, settings_json)"
        " VALUES ('ingest', '2026-10-29T00:00:00+00:00', 'ok', '{}')"
    )
    conn.executemany(
        "INSERT INTO teams (id, name) VALUES (?, ?)", [(i, f"Equipo {i}") for i in range(1, 5)]
    )
    rng = np.random.default_rng(3)
    for week in range(60):
        day = (date(2022, 1, 1) + timedelta(days=7 * week)).isoformat()
        for h in range(4):
            for v in range(4):
                if h == v:
                    continue
                goals = (
                    int(rng.poisson(math.exp(A[h] + D[v] + 0.25))),
                    int(rng.poisson(math.exp(A[v] + D[h]))),
                )
                conn.execute(
                    "INSERT INTO historical_matches (competition_id, match_date, home_team_id,"
                    " away_team_id, home_goals, away_goals, source_fixture_id, run_id)"
                    " VALUES ('premier', ?, ?, ?, ?, ?, ?, 1)",
                    (day, h + 1, v + 1, *goals, week * 100 + h * 4 + v),
                )
    conn.commit()
    conn.close()
    return path

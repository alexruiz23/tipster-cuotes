"""`load_matches` lee `historical_matches` sin salirse del rango pedido (cero fuga de datos)."""

import sqlite3
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

from tipster.history.matches import load_matches
from tipster.models.dixon_coles import Match
from tipster.storage.db import connect


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(tmp_path / "tipster.sqlite")
    connection.execute(
        "INSERT INTO runs (command, started_at, status, settings_json)"
        " VALUES ('ingest', '2026-10-29T00:00:00+00:00', 'ok', '{}')"
    )
    connection.executemany("INSERT INTO teams (id, name) VALUES (?, ?)", [(1, "A"), (2, "B")])
    connection.executemany(
        "INSERT INTO historical_matches (competition_id, match_date, home_team_id, away_team_id,"
        " home_goals, away_goals, source_fixture_id, run_id) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
        [
            ("premier", "2016-08-13", 1, 2, 2, 1, 1),
            ("premier", "2024-07-31", 2, 1, 0, 0, 2),  # último día incluido
            ("premier", "2024-08-01", 1, 2, 3, 3, 3),  # fuera: ya es 2024/25
            ("premier", "2016-07-31", 1, 2, 9, 9, 4),  # fuera: anterior al inicio
            ("laliga", "2020-01-01", 1, 2, 1, 1, 5),  # fuera: otra liga
        ],
    )
    connection.commit()
    yield connection
    connection.close()


def test_load_matches_respeta_las_fechas_y_la_competicion(conn: sqlite3.Connection) -> None:
    matches = load_matches(conn, "premier", date(2016, 8, 1), date(2024, 7, 31))
    assert matches == [Match(1, 2, 2, 1), Match(2, 1, 0, 0)]


def test_load_matches_no_ve_nada_posterior_al_fin(conn: sqlite3.Connection) -> None:
    assert load_matches(conn, "premier", date(2016, 8, 1), date(2024, 7, 30)) == [Match(1, 2, 2, 1)]

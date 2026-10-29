"""Ingesta del histórico en SQLite (ADR 007): alias de equipo, duplicados y carga idempotente."""

import csv
import sqlite3
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path

from tipster.errors import IngestError
from tipster.history.hf_dataset import (
    DATASET,
    DATASET_REVISION,
    TABLES,
    PinnacleOdds,
    RawMatch,
    file_sha256,
    read_competitions,
    read_matches,
    read_pinnacle,
    read_team_names,
)
from tipster.storage.sqlite import SqliteRunRepository

DEFAULT_ALIASES = Path(__file__).parent / "team_aliases.csv"
MAX_GAP_DAYS = 1  # el CSV de origen a veces fecha un día antes que API-Football


@dataclass(frozen=True)
class Alias:
    alias_id: int
    alias_name: str
    canonical_id: int
    canonical_name: str


@dataclass(frozen=True)
class IngestResult:
    run_id: int
    matches_read: int
    duplicates_removed: int
    matches_loaded: int
    with_pinnacle: int
    first_date: date | None
    last_date: date | None
    per_competition: Mapping[str, int]


def load_aliases(path: Path) -> dict[int, Alias]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    aliases = {
        int(r["alias_id"]): Alias(
            int(r["alias_id"]), r["alias_name"], int(r["canonical_id"]), r["canonical_name"]
        )
        for r in rows
    }
    if len(aliases) != len(rows):
        raise IngestError(f"{path}: hay un alias_id repetido")
    for alias in aliases.values():
        if alias.canonical_id == alias.alias_id or alias.canonical_id in aliases:
            raise IngestError(f"{path}: el alias {alias.alias_id} apunta a sí mismo o a una cadena")
    return aliases


def _check_aliases(aliases: Mapping[int, Alias], names: Mapping[int, str]) -> None:
    """Un id del fichero con otro nombre en el dataset significa que los ids cambiaron."""
    for alias in aliases.values():
        for team_id, expected in (
            (alias.alias_id, alias.alias_name),
            (alias.canonical_id, alias.canonical_name),
        ):
            if team_id in names and names[team_id] != expected:
                raise IngestError(
                    f"El equipo {team_id} se llama {names[team_id]!r} en el dataset y "
                    f"{expected!r} en el fichero de alias"
                )


def collapse(matches: list[RawMatch], aliases: Mapping[int, Alias]) -> list[list[RawMatch]]:
    """Agrupa las copias de un mismo partido tras unificar los equipos.

    Dos filas son el mismo partido si coinciden competición, local y visitante (ya canónicos) y
    sus fechas distan como mucho `MAX_GAP_DAYS`. Si discrepan en el marcador, falla.
    """

    def canonical(team_id: int) -> int:
        return aliases[team_id].canonical_id if team_id in aliases else team_id

    unified = sorted(
        (replace(m, home_id=canonical(m.home_id), away_id=canonical(m.away_id)) for m in matches),
        key=lambda m: (m.competition_id, m.home_id, m.away_id, m.day, m.fixture_id),
    )
    groups: list[list[RawMatch]] = []
    for match in unified:
        last = groups[-1][-1] if groups else None
        if (
            last is not None
            and (last.competition_id, last.home_id, last.away_id)
            == (match.competition_id, match.home_id, match.away_id)
            and (match.day - last.day).days <= MAX_GAP_DAYS
        ):
            if (last.home_goals, last.away_goals) != (match.home_goals, match.away_goals):
                raise IngestError(
                    f"Los partidos {last.fixture_id} y {match.fixture_id} son el mismo "
                    f"({match.competition_id}, {match.day}) pero con distinto marcador"
                )
            groups[-1].append(match)
        else:
            groups.append([match])
    return groups


def _representative(group: list[RawMatch]) -> RawMatch:
    """La copia de fecha más tardía: nunca da un resultado por conocido antes de tiempo."""
    return max(group, key=lambda m: (m.day, -m.fixture_id))


def ingest(
    conn: sqlite3.Connection,
    folder: Path,
    start: date,
    end: date,
    *,
    aliases: Mapping[int, Alias],
    clock: Callable[[], datetime],
) -> IngestResult:
    paths = {name: folder / f"{name}.parquet" for name in TABLES}
    missing = [p.name for p in paths.values() if not p.exists()]
    if missing:
        raise IngestError(f"Faltan en {folder}: {', '.join(missing)}")
    competitions = read_competitions(paths["leagues"])
    raw = read_matches(paths["fixtures"], competitions, start, end)
    names = read_team_names(paths["teams"])
    _check_aliases(aliases, names)
    groups = collapse(raw, aliases)
    odds = read_pinnacle(paths["odds"], {m.fixture_id for m in raw})

    rows = []
    for group in groups:
        match = _representative(group)
        group_odds: PinnacleOdds | None = next(
            (odds[m.fixture_id] for m in group if m.fixture_id in odds), None
        )
        rows.append((match, group_odds))
    for match, _ in rows:
        for team_id in (match.home_id, match.away_id):
            if team_id not in names:
                raise IngestError(f"El equipo {team_id} no está en teams.parquet")

    snapshot = {
        "dataset": DATASET,
        "revision": DATASET_REVISION,
        "sha256": {name: file_sha256(path) for name, path in paths.items()},
        "from": start.isoformat(),
        "to": end.isoformat(),
    }
    runs = SqliteRunRepository(conn, clock)
    run_id = runs.start("ingest", snapshot)
    try:
        with conn:
            conn.executemany(
                "INSERT INTO teams (id, name) VALUES (?, ?)"
                " ON CONFLICT (id) DO UPDATE SET name = excluded.name",
                sorted({(t, names[t]) for m, _ in rows for t in (m.home_id, m.away_id)}),
            )
            conn.executemany(
                "INSERT INTO historical_matches (competition_id, match_date, home_team_id,"
                " away_team_id, home_goals, away_goals, pinnacle_home, pinnacle_draw,"
                " pinnacle_away, odds_source, source_fixture_id, run_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (competition_id, match_date, home_team_id, away_team_id)"
                " DO UPDATE SET home_goals = excluded.home_goals, away_goals = excluded.away_goals,"
                " pinnacle_home = excluded.pinnacle_home, pinnacle_draw = excluded.pinnacle_draw,"
                " pinnacle_away = excluded.pinnacle_away, odds_source = excluded.odds_source,"
                " source_fixture_id = excluded.source_fixture_id, run_id = excluded.run_id",
                [
                    (
                        m.competition_id,
                        m.day.isoformat(),
                        m.home_id,
                        m.away_id,
                        m.home_goals,
                        m.away_goals,
                        o.home if o else None,
                        o.draw if o else None,
                        o.away if o else None,
                        o.source if o else None,
                        m.fixture_id,
                        run_id,
                    )
                    for m, o in rows
                ],
            )
    except sqlite3.Error:
        runs.finish(run_id, "error")
        raise
    runs.finish(run_id, "ok")
    days = [m.day for m, _ in rows]
    return IngestResult(
        run_id=run_id,
        matches_read=len(raw),
        duplicates_removed=len(raw) - len(rows),
        matches_loaded=len(rows),
        with_pinnacle=sum(1 for _, o in rows if o is not None),
        first_date=min(days, default=None),
        last_date=max(days, default=None),
        per_competition=dict(sorted(Counter(m.competition_id for m, _ in rows).items())),
    )

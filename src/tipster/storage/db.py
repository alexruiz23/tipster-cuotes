"""Conexión SQLite y aplicación ordenada de migraciones (ADR 004)."""

import sqlite3
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

MEMORY = ":memory:"


def iso(value: datetime) -> str:
    """Fecha aware en texto ISO-8601 UTC; así ordenan bien como texto."""
    return value.astimezone(UTC).isoformat()


def from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def _migrations() -> list[tuple[int, str]]:
    folder = resources.files("tipster.storage.migrations")
    scripts = [
        (int(entry.name.split("_", 1)[0]), entry.read_text(encoding="utf-8"))
        for entry in folder.iterdir()
        if entry.name.endswith(".sql")
    ]
    return sorted(scripts)


def schema_versions(conn: sqlite3.Connection) -> list[int]:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
    ).fetchone()
    if not exists:
        return []
    return [row[0] for row in conn.execute("SELECT version FROM schema_version ORDER BY version")]


def apply_migrations(conn: sqlite3.Connection) -> None:
    applied = set(schema_versions(conn))
    for version, script in _migrations():
        if version in applied:
            continue
        conn.executescript(f"BEGIN;\n{script}\nCOMMIT;")
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (version, iso(datetime.now(UTC))),
        )
        conn.commit()


def connect(path: Path | str) -> sqlite3.Connection:
    if str(path) != MEMORY:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    apply_migrations(conn)
    return conn

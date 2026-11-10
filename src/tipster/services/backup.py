"""Copia de seguridad de la base de datos (BACKLOG 40).

La base `data/tipster.sqlite` es la única copia de los picks, los cierres y el bankroll: sin ella
no hay paper trading que medir. Se copia con la API de copia de SQLite (consistente aunque otro
proceso escriba), se comprueba la copia y se conservan solo las últimas `keep` copias diarias.
"""

import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tipster.errors import TipsterError

_NAME = re.compile(r"^tipster-(\d{4}-\d{2}-\d{2})\.sqlite$")


class BackupError(TipsterError):
    """La copia no se pudo hacer o no pasó la comprobación."""


def backup_database(
    source: Path, dest_dir: Path, *, now: datetime, tz: ZoneInfo, keep: int
) -> Path:
    """Copia `source` en `dest_dir/tipster-AAAA-MM-DD.sqlite` (una por día local) y rota."""
    if not source.is_file():
        raise BackupError(f"no existe la base de datos {source}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / f"tipster-{now.astimezone(tz).date().isoformat()}.sqlite"
    partial = final.with_suffix(".sqlite.part")
    partial.unlink(missing_ok=True)
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(partial)
        try:
            src.backup(dst)
            check = dst.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            dst.close()
    except sqlite3.Error as exc:
        partial.unlink(missing_ok=True)
        raise BackupError(f"fallo al copiar la base de datos: {exc}") from exc
    finally:
        src.close()
    if check != "ok":
        partial.unlink(missing_ok=True)
        raise BackupError(f"la copia no pasa integrity_check: {check}")
    os.replace(partial, final)  # atómico: nunca queda una copia a medias con el nombre final
    _rotate(dest_dir, keep)
    return final


def _rotate(dest_dir: Path, keep: int) -> None:
    copies = sorted(p for p in dest_dir.iterdir() if _NAME.match(p.name))
    for old in copies[: max(len(copies) - keep, 0)]:
        old.unlink()

"""`scripts/due.sh`: ¿toca ejecutar este trabajo ahora? (ADR 013).

Se ejecuta de verdad con un `date` simulado y, si el CLI `sqlite3` no está instalado, con un
`sqlite3` mínimo hecho con el módulo de Python."""

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from tipster.storage.db import connect

DUE = Path(__file__).resolve().parents[2] / "scripts" / "due.sh"

DATE_SHIM = """#!/bin/bash
# date simulado: solo las formas que usa due.sh
if [ "$1" = "-u" ]; then echo "$FAKE_TODAY"; exit 0; fi
case "$1" in
  +%u) echo "$FAKE_DOW" ;;
  +%H) echo "$FAKE_HOUR" ;;
  *) exec /bin/date "$@" ;;
esac
"""

SQLITE_SHIM = f"""#!{sys.executable}
import sqlite3, sys
args = sys.argv[1:]
sep = " "
if args[0] == "-separator":
    sep, args = args[1], args[2:]
conn = sqlite3.connect(args[0])
for row in conn.execute(args[1]):
    print(sep.join(str(v) for v in row))
"""


def _write_exe(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exe(bin_dir / "date", DATE_SHIM)
    if shutil.which("sqlite3") is None:
        _write_exe(bin_dir / "sqlite3", SQLITE_SHIM)
    db = tmp_path / "t.sqlite"
    connect(db).close()
    return {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "TIPSTER_DB_PATH": str(db),
        "FAKE_TODAY": "2026-11-10",
        "FAKE_DOW": "2",  # martes
        "FAKE_HOUR": "12",
    }


def _run(env: dict[str, str], job: str, **extra: str) -> bool:
    result = subprocess.run(
        ["bash", str(DUE), job], env={**env, **extra}, capture_output=True, text=True, check=False
    )
    assert result.returncode in (0, 1), result.stderr
    return result.returncode == 0


def _add_run(env: dict[str, str], command: str, status: str, day: str = "2026-11-10") -> None:
    conn = connect(env["TIPSTER_DB_PATH"])
    conn.execute(
        "INSERT INTO runs (command, started_at, status, settings_json) VALUES (?, ?, ?, '{}')",
        (command, f"{day}T11:05:00+00:00", status),
    )
    conn.commit()
    conn.close()


def test_el_scan_toca_el_martes_a_mediodia_si_no_ha_corrido(env: dict[str, str]) -> None:
    assert _run(env, "scan")


@pytest.mark.parametrize(
    ("dow", "hour"), [("3", "12"), ("1", "12"), ("2", "11"), ("2", "15")]
)  # miércoles, lunes, antes de las 12, a partir de las 15
def test_el_scan_solo_toca_martes_y_viernes_entre_las_12_y_las_15(
    env: dict[str, str], dow: str, hour: str
) -> None:
    assert not _run(env, "scan", FAKE_DOW=dow, FAKE_HOUR=hour)


def test_el_viernes_tambien_toca(env: dict[str, str]) -> None:
    assert _run(env, "scan", FAKE_DOW="5")


@pytest.mark.parametrize("status", ["ok", "parcial"])
def test_un_scan_terminado_bien_hoy_no_se_repite(env: dict[str, str], status: str) -> None:
    _add_run(env, "scan", status)
    assert not _run(env, "scan")


@pytest.mark.parametrize("status", ["error", "en_curso"])
def test_un_scan_en_error_o_caido_a_mitad_se_reintenta(env: dict[str, str], status: str) -> None:
    _add_run(env, "scan", status)
    assert _run(env, "scan")


def test_un_scan_de_otro_dia_no_cuenta(env: dict[str, str]) -> None:
    _add_run(env, "scan", "ok", day="2026-11-07")
    assert _run(env, "scan")


def test_un_scan_ok_no_oculta_el_settle_de_hoy_ni_al_reves(env: dict[str, str]) -> None:
    _add_run(env, "settle", "ok")  # otro comando: el scan sigue tocando
    assert _run(env, "scan")


def test_force_siempre_toca(env: dict[str, str]) -> None:
    _add_run(env, "scan", "ok")
    assert _run(env, "scan", FORCE="scan")
    assert not _run(env, "scan", FORCE="settle")

"""`scripts/r2.sh`: la subida a R2 nunca encoge la base ni añade claves foráneas rotas (ADR 013).

Se ejecuta de verdad con un `aws` simulado (un directorio hace de bucket) y, si falta el CLI
`sqlite3`, con el mismo `sqlite3` mínimo de los tests de `due.sh`."""

import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tests.integration.test_due_sh import SQLITE_SHIM, _write_exe
from tipster.storage.db import connect

R2 = Path(__file__).resolve().parents[2] / "scripts" / "r2.sh"

AWS_SHIM = f"""#!{sys.executable}
import hashlib, os, shutil, sys
from pathlib import Path
store = Path(os.environ["FAKE_R2"])
args = sys.argv[2:]  # sys.argv[1] == "s3api"
sub, opts, pos = args[0], {{}}, []
i = 1
while i < len(args):
    if args[i].startswith("--"):
        opts[args[i]] = args[i + 1]
        i += 2
    else:
        pos.append(args[i])
        i += 1
obj = store / opts.get("--key", "")
def etag(p):
    return hashlib.md5(p.read_bytes()).hexdigest()
if sub == "get-object":
    if not obj.exists():
        sys.exit("NoSuchKey")
    shutil.copy(obj, pos[0])
    print(etag(obj))
elif sub == "head-object":
    sys.exit(0 if obj.exists() else 1)
elif sub == "copy-object":
    obj.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(store / opts["--copy-source"].split("/", 1)[1], obj)
elif sub == "put-object":
    if "--if-match" in opts and (not obj.exists() or etag(obj) != opts["--if-match"]):
        sys.exit("PreconditionFailed")
    obj.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(opts["--body"], obj)
"""


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exe(bin_dir / "aws", AWS_SHIM)
    if shutil.which("sqlite3") is None:
        _write_exe(bin_dir / "sqlite3", SQLITE_SHIM)
    bucket = tmp_path / "bucket"
    bucket.mkdir()
    seed = tmp_path / "seed.sqlite"
    conn = connect(seed)
    conn.execute(
        "INSERT INTO runs (command, started_at, status, settings_json) "
        "VALUES ('scan', '2026-11-20T11:00:00Z', 'ok', '{}')"
    )
    conn.commit()
    conn.close()
    shutil.copy(seed, bucket / "tipster.sqlite")
    return {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "R2_BUCKET": "b",
        "FAKE_R2": str(bucket),
        "TIPSTER_DB_PATH": str(tmp_path / "work" / "tipster.sqlite"),
    }


def _r2(env: dict[str, str], action: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(R2), action], env=env, capture_output=True, text=True, check=False
    )


def _sql(env: dict[str, str], *statements: str) -> None:
    conn = sqlite3.connect(env["TIPSTER_DB_PATH"])
    for statement in statements:
        conn.execute(statement)
    conn.commit()
    conn.close()


def _remote(env: dict[str, str]) -> str:
    return hashlib.md5((Path(env["FAKE_R2"]) / "tipster.sqlite").read_bytes()).hexdigest()


def test_sin_cambios_no_sube(env: dict[str, str]) -> None:
    assert _r2(env, "pull").returncode == 0
    result = _r2(env, "push")
    assert result.returncode == 0
    assert "sin cambios" in result.stdout


def test_sube_si_la_base_crece(env: dict[str, str]) -> None:
    _r2(env, "pull")
    before = _remote(env)
    _sql(
        env,
        "INSERT INTO runs (command, started_at, status, settings_json) "
        "VALUES ('close', '2026-11-20T12:00:00Z', 'ok', '{}')",
    )
    assert _r2(env, "push").returncode == 0
    assert _remote(env) != before


def test_no_sube_si_desaparecen_ejecuciones(env: dict[str, str]) -> None:
    _r2(env, "pull")
    before = _remote(env)
    _sql(env, "DELETE FROM runs")
    result = _r2(env, "push")
    assert result.returncode == 1
    assert "menos filas" in result.stdout
    assert _remote(env) == before


def test_no_sube_si_la_ejecucion_rompe_claves_foraneas(env: dict[str, str]) -> None:
    _r2(env, "pull")
    before = _remote(env)
    _sql(
        env,
        "PRAGMA foreign_keys = OFF",
        "INSERT INTO provider_requests (run_id, provider, endpoint, params_key, from_cache, "
        "requested_at) VALUES (999, 'x', '/e', '', 0, '2026-11-20T12:00:00Z')",
    )
    result = _r2(env, "push")
    assert result.returncode == 1
    assert "claves foráneas rotas" in result.stdout
    assert _remote(env) == before


def test_conflicto_de_etag_guarda_copia_aparte(env: dict[str, str]) -> None:
    _r2(env, "pull")
    other = Path(env["FAKE_R2"]) / "tipster.sqlite"
    conn = sqlite3.connect(other)
    conn.execute(
        "INSERT INTO runs (command, started_at, status, settings_json) "
        "VALUES ('otro', '2026-11-20T12:00:00Z', 'ok', '{}')"
    )
    conn.commit()
    conn.close()
    _sql(
        env,
        "INSERT INTO runs (command, started_at, status, settings_json) "
        "VALUES ('close', '2026-11-20T12:00:00Z', 'ok', '{}')",
    )
    result = _r2(env, "push")
    assert result.returncode == 1
    assert list((Path(env["FAKE_R2"]) / "conflictos").iterdir())

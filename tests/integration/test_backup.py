"""`tipster backup`: copia consistente, comprobada y con rotación."""

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

from tipster.cli.app import app
from tipster.services.backup import BackupError, backup_database
from tipster.storage.db import connect

TZ = ZoneInfo("Europe/Madrid")
NOW = datetime(2026, 11, 10, 3, 0, tzinfo=UTC)


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "t.sqlite"
    conn = connect(path)
    conn.execute("INSERT INTO alerts_sent (key, sent_at) VALUES ('x', 'y')")
    conn.commit()
    conn.close()
    return path


def test_la_copia_contiene_los_datos_y_se_nombra_por_dia_local(tmp_path: Path) -> None:
    out = backup_database(_db(tmp_path), tmp_path / "b", now=NOW, tz=TZ, keep=3)
    assert out.name == "tipster-2026-11-10.sqlite"
    copy = sqlite3.connect(out)
    assert copy.execute("SELECT key FROM alerts_sent").fetchone()[0] == "x"
    copy.close()
    assert not list((tmp_path / "b").glob("*.part"))


def test_repetir_el_mismo_dia_sobrescribe_y_no_acumula(tmp_path: Path) -> None:
    src = _db(tmp_path)
    backup_database(src, tmp_path / "b", now=NOW, tz=TZ, keep=3)
    backup_database(src, tmp_path / "b", now=NOW + timedelta(hours=2), tz=TZ, keep=3)
    assert len(list((tmp_path / "b").iterdir())) == 1


def test_rota_y_conserva_solo_las_ultimas(tmp_path: Path) -> None:
    src = _db(tmp_path)
    for day in range(5):
        backup_database(src, tmp_path / "b", now=NOW + timedelta(days=day), tz=TZ, keep=2)
    names = sorted(p.name for p in (tmp_path / "b").iterdir())
    assert names == ["tipster-2026-11-13.sqlite", "tipster-2026-11-14.sqlite"]


def test_rotar_no_toca_ficheros_ajenos(tmp_path: Path) -> None:
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "notas.txt").write_text("hola")
    backup_database(_db(tmp_path), tmp_path / "b", now=NOW, tz=TZ, keep=1)
    assert (tmp_path / "b" / "notas.txt").exists()


def test_sin_base_de_datos_falla_con_error_claro(tmp_path: Path) -> None:
    with pytest.raises(BackupError, match="no existe"):
        backup_database(tmp_path / "nada.sqlite", tmp_path / "b", now=NOW, tz=TZ, keep=1)
    assert not (tmp_path / "b").exists() or not list((tmp_path / "b").iterdir())


def test_comando_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    src = _db(tmp_path)
    result = CliRunner().invoke(app, ["backup", "--db", str(src), "--dest", str(tmp_path / "b")])
    assert result.exit_code == 0, result.output
    assert "tipster-" in result.output
    assert len(list((tmp_path / "b").glob("tipster-*.sqlite"))) == 1


def test_comando_backup_sin_base_sale_con_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        app, ["backup", "--db", str(tmp_path / "no.sqlite"), "--dest", str(tmp_path / "b")]
    )
    assert result.exit_code == 1

"""CLI `tipster scan` (Typer) con fixtures sintéticas; nunca toca la red."""

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tipster.cli.app import app
from tipster.storage.db import connect

FIXTURES = Path(__file__).parent.parent / "fixtures" / "the_odds_api" / "sintetico"
WIDE = {"COLUMNS": "260"}


@pytest.fixture(autouse=True)
def _aislado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)  # sin .env del repositorio
    for name in ("ODDS_API_KEY", "TIPSTER_MARKETS", "TIPSTER_COMPETITIONS"):
        monkeypatch.delenv(name, raising=False)


def _scan(*args: str, env: dict[str, str] | None = None) -> tuple[int, str]:
    result = CliRunner().invoke(app, ["scan", *args], env={**WIDE, **(env or {})})
    return result.exit_code, result.output


def test_ayuda_muestra_el_aviso_de_juego_responsable() -> None:
    result = CliRunner().invoke(app, ["--help"], env=WIDE)
    assert result.exit_code == 0
    assert "18" in result.output
    assert "jugarbien.es" in result.output


def test_scan_offline_muestra_la_tabla_y_el_aviso() -> None:
    code, out = _scan("--offline", str(FIXTURES))
    assert code == 0
    assert "DATOS GRABADOS, NO EN VIVO" in out
    assert "sintetico" in out
    assert "jugarbien.es" in out
    for column in ("Partido", "Mercado", "Selección", "Casa", "Cuota", "Cuota justa"):
        assert column in out
    for column in ("p_modelo", "p_mercado", "EV", "Stake", "Etiqueta", "Ref.", "Captura"):
        assert column in out
    assert "Local Prueba FC" in out
    assert "POSIBLE ERROR · RIESGO DE ANULACIÓN" in out
    assert "FEED NO-ES · VERIFICA LA CUOTA EN LA WEB .ES" in out
    assert "betfair_ex_no_es" in out  # referencia de respaldo (D2)
    assert "Picks: 4" in out
    assert "Créditos gastados: 0" in out
    assert "liquidez desconocida" in out


def test_scan_offline_guarda_los_picks_si_se_pide_bd(tmp_path: Path) -> None:
    db = tmp_path / "offline.sqlite"
    code, _ = _scan("--offline", str(FIXTURES), "--db", str(db))
    assert code == 0
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM picks").fetchone()[0] == 4


def test_scan_en_vivo_sin_clave_no_llama_y_termina_con_error_de_configuracion() -> None:
    code, out = _scan()
    assert code == 2
    assert "ODDS_API_KEY" in out


def test_configuracion_invalida_termina_con_codigo_2() -> None:
    code, out = _scan("--offline", str(FIXTURES), env={"TIPSTER_MARKETS": "1x2,btts"})
    assert code == 2
    assert "D5" in out


def test_competicion_concreta() -> None:
    code, out = _scan("--offline", str(FIXTURES), "--competicion", "premier")
    assert code == 0
    assert "Local Prueba FC" not in out
    assert "Picks: 0" in out


def test_scan_se_niega_si_la_mezcla_pide_un_modelo_que_no_existe(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(db)
    connect(db).close()
    conn.execute(
        "INSERT INTO blend_configs (created_at, settings_json) VALUES ('2026-10-29T00:00:00+00:00',"
        " '{\"w_market\": 0.8}')"
    )
    conn.commit()
    conn.close()
    code, out = _scan("--offline", str(FIXTURES), "--db", str(db))
    assert code == 2
    assert "proveedor del modelo" in out

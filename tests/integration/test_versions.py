"""Versiones de la estrategia en el `status` (auditoría del 23/11/2026)."""

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.integration.test_tracking import _make_pick
from tipster.config import STRATEGY_LOGIC_VERSION, Settings
from tipster.services.versions import shadow_lines, strategy_hash, version_lines, version_stats
from tipster.storage.db import connect

OLD = {"devig_method": "multiplicativo", "max_odds": 15.0, "db_path": "a.sqlite"}
NEW = {"devig_method": "shin", "max_odds": 8.0, "db_path": "a.sqlite"}


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(tmp_path / "t.sqlite")
    yield connection
    connection.close()


def _pick(
    conn: sqlite3.Connection,
    event: str,
    config: dict[str, object],
    started: str,
    *,
    stake: float | None = 1.0,
    clv: float | None = None,
    status: str = "abierto",
    profit: float | None = None,
    kickoff: str = "2026-11-21T15:00:00+00:00",
) -> None:
    pick_id, _, run_id = _make_pick(conn, event)
    conn.execute("UPDATE events SET kickoff_utc = ? WHERE id = ?", (kickoff, event))
    conn.execute(
        "UPDATE runs SET settings_json = ?, started_at = ? WHERE id = ?",
        (json.dumps(config), started, run_id),
    )
    conn.execute(
        "UPDATE picks SET stake = ?, clv = ?, closing_reliable = ?, status = ?, profit = ?"
        " WHERE id = ?",
        (stake, clv, None if clv is None else 1, status, profit, pick_id),
    )


def test_la_version_de_la_logica_forma_parte_de_la_estrategia() -> None:
    snapshot = Settings(_env_file=None).snapshot()
    assert snapshot["strategy_logic_version"] == STRATEGY_LOGIC_VERSION
    # los scans de antes de existir la clave cuentan como lógica 1, no como versión nueva
    legacy = {k: v for k, v in snapshot.items() if k != "strategy_logic_version"}
    assert strategy_hash(legacy) == strategy_hash({**legacy, "strategy_logic_version": 1})
    assert strategy_hash(legacy) != strategy_hash({**legacy, "strategy_logic_version": 2})


def test_bankroll_initial_no_cambia_la_version() -> None:
    """Solo siembra una base vacía; el stake sale del saldo real (ensure_initial)."""
    assert strategy_hash({**OLD, "bankroll_initial": 100.0}) == strategy_hash(
        {**OLD, "bankroll_initial": 500.0}
    )


def test_el_hash_ignora_las_claves_operativas() -> None:
    assert strategy_hash(OLD) == strategy_hash({**OLD, "db_path": "otra.sqlite"})
    assert strategy_hash(OLD) != strategy_hash(NEW)
    assert strategy_hash(Settings(_env_file=None).snapshot()) == strategy_hash(
        {**Settings(_env_file=None).snapshot(), "timezone": "UTC", "backup_keep": 3}
    )


def test_separa_versiones_y_marca_la_vigente(conn: sqlite3.Connection) -> None:
    _pick(conn, "a", OLD, "2026-11-06T11:00:00+00:00", clv=-0.20, status="perdido", profit=-1.0)
    _pick(conn, "b", OLD, "2026-11-06T11:00:00+00:00", clv=-0.10, status="perdido", profit=-1.0)
    _pick(conn, "c", NEW, "2026-11-20T11:00:00+00:00", clv=0.05)  # abierto pero con cierre
    _pick(conn, "d", NEW, "2026-11-20T11:00:00+00:00", stake=None)
    old, new = version_stats(conn, NEW)
    assert (old.label, old.current, old.detected, old.staked, old.roi) == ("v1", False, 2, 2, -1.0)
    assert old.clv == pytest.approx([-0.20, -0.10])
    assert (new.label, new.current, new.detected, new.staked) == ("v2", True, 2, 1)
    assert new.clv == pytest.approx([0.05])  # un pick abierto con cierre capturado sí cuenta
    assert new.changes == ["devig_method multiplicativo→shin", "max_odds 15.0→8.0"]


def test_las_lineas_dicen_la_vigente_y_su_intervalo(conn: sqlite3.Connection) -> None:
    for i, value in enumerate((0.02, 0.04, -0.01)):
        _pick(conn, f"n{i}", NEW, "2026-11-20T11:00:00+00:00", clv=value)
    text = "\n".join(version_lines(conn, NEW))
    assert "v1 (vigente) desde 2026-11-20" in text
    assert "Estrategia vigente (v1): 3 detectados · 3 con stake · 3 con cierre fiable" in text
    assert "(2 > 0, 1 ≤ 0)" in text
    assert "muestra insuficiente (1 < 4 semanas)" in text  # 3 picks de una sola semana


def test_con_cuatro_semanas_o_mas_da_el_intervalo_por_semanas(conn: sqlite3.Connection) -> None:
    for week in range(5):
        for j, value in enumerate((0.03, -0.01)):
            _pick(conn, f"w{week}{j}", NEW, "2026-11-20T11:00:00+00:00", clv=value,
                  kickoff=f"2026-11-{2 + 7 * week:02d}T15:00:00+00:00")  # fmt: skip
    text = "\n".join(version_lines(conn, NEW))
    assert "IC 95 % por semanas [" in text
    assert "muestra insuficiente" not in text


def test_sin_picks_de_la_configuracion_vigente_lo_dice(conn: sqlite3.Connection) -> None:
    _pick(conn, "a", OLD, "2026-11-06T11:00:00+00:00")
    text = "\n".join(version_lines(conn, NEW))
    assert "Estrategia vigente: aún no ha generado ningún pick." in text


def _shadow(conn: sqlite3.Connection, event: str, reason: str, clv: float, config=NEW) -> None:  # type: ignore[no-untyped-def]
    _pick(conn, event, config, "2026-11-24T11:00:00+00:00", stake=None, clv=clv)
    conn.execute(
        "UPDATE picks SET reasons_json = ? WHERE quote_id IN"
        " (SELECT id FROM odds_quotes WHERE event_id = ?)",
        (json.dumps(["VALUE", reason]), event),
    )


def test_la_sombra_agrupa_el_clv_de_los_descartes_por_motivo(conn: sqlite3.Connection) -> None:
    _shadow(conn, "a", "partido a más de 4 días: fuera del horizonte", 0.04)
    _shadow(conn, "b", "partido a más de 4 días: fuera del horizonte", -0.02)
    _shadow(conn, "c", "cuota 9.5 por encima de max_odds 8.0", -0.10)
    _shadow(conn, "d", "cuota 9.5 por encima de max_odds 8.0", 0.5, config=OLD)  # otra versión
    _pick(conn, "e", NEW, "2026-11-24T11:00:00+00:00", clv=0.3)  # con stake: no es sombra
    text = "\n".join(shadow_lines(conn, NEW))
    assert "3 con cierre" in text
    assert "a más de 4 días: CLV +1.0 % en 2 (1 > 0)" in text
    assert "cuota demasiado alta: CLV -10.0 % en 1 (0 > 0)" in text


def test_shadow_closing_no_crea_una_version_nueva() -> None:
    snapshot = Settings(_env_file=None).snapshot()
    assert strategy_hash(snapshot) == strategy_hash({**snapshot, "shadow_closing": False})

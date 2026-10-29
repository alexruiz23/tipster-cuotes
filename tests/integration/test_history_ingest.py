"""Ingesta del histórico (ADR 007) con Parquet sintéticos en miniatura; nunca toca la red."""

import hashlib
import sqlite3
from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from tipster.cli.app import app
from tipster.errors import IngestError
from tipster.history.hf_dataset import DATASET_REVISION, fetch_tables
from tipster.history.ingest import DEFAULT_ALIASES, IngestResult, ingest, load_aliases
from tipster.storage.db import connect, schema_versions

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
START, END = date(2016, 8, 1), date(2026, 7, 31)
API = "API-Football-closing"

Columns = dict[str, Any]
Fixture = tuple[int, str, int, int, int, int | None, int | None, bool]
OddsRow = tuple[int, float, float, float, str, str]


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text)


def _write(folder: Path, name: str, columns: Columns) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(columns), folder / f"{name}.parquet")


def _fixtures(rows: Sequence[Fixture]) -> Columns:
    """(id, fecha, liga, local, visitante, goles_local, goles_visitante, jugado)."""
    cols = list(zip(*rows, strict=True))
    return {
        "id": pa.array(cols[0], pa.int64()),
        "date_utc": pa.array([_dt(d) for d in cols[1]], pa.timestamp("us")),
        "league_id": pa.array(cols[2], pa.int64()),
        "home_team_id": pa.array(cols[3], pa.int64()),
        "away_team_id": pa.array(cols[4], pa.int64()),
        "goals_home": pa.array(cols[5], pa.int32()),
        "goals_away": pa.array(cols[6], pa.int32()),
        "is_played": pa.array(cols[7], pa.bool_()),
    }


def _odds(rows: Sequence[OddsRow]) -> Columns:
    """(partido, local, empate, visitante, casa, fuente)."""
    cols = list(zip(*rows, strict=True))
    return {
        "fixture_id": pa.array(cols[0], pa.int64()),
        "home_win": pa.array(cols[1], pa.float64()),
        "draw": pa.array(cols[2], pa.float64()),
        "away_win": pa.array(cols[3], pa.float64()),
        "bookmaker": pa.array(cols[4], pa.string()),
        "source": pa.array(cols[5], pa.string()),
    }


def _write_dataset(
    folder: Path, *, extra_fixtures: Sequence[Fixture] = (), extra_odds: Sequence[OddsRow] = ()
) -> None:
    _write(
        folder,
        "fixtures",
        _fixtures(
            [
                (
                    10,
                    "2024-08-17 17:00:00",
                    1,
                    1,
                    2,
                    2,
                    1,
                    True,
                ),  # normal, con dos cuotas de Pinnacle
                (20, "2024-08-24 18:00:00", 5, 3, 2, 1, 1, True),  # «Gamma Club» (3)
                (
                    21,
                    "2024-08-25 00:00:00",
                    5,
                    4,
                    2,
                    1,
                    1,
                    True,
                ),  # mismo partido: «Gamma» (4), un día después
                (30, "2024-09-01 20:00:00", 1, 2, 1, 0, 3, True),  # sin cuota de Pinnacle
                (31, "2024-09-08 20:00:00", 1, 1, 2, None, None, False),  # no jugado
                (32, "2024-09-08 20:00:00", 99, 1, 2, 1, 0, True),  # liga que no es de las 6
                (33, "2015-05-01 20:00:00", 1, 1, 2, 1, 0, True),  # anterior a --from
                (34, "2024-09-15 20:00:00", 1, 1, 2, 2, 2, True),  # cuota inválida (<= 1)
                *extra_fixtures,
            ]
        ),
    )
    _write(
        folder,
        "odds",
        _odds(
            [
                (10, 2.0, 3.5, 4.0, "Pinnacle", "The-Odds-API"),
                (10, 1.9, 3.4, 4.2, "Pinnacle", API),  # la de API-Football gana
                (10, 1.8, 3.3, 4.5, "Bet365", "CSV"),
                (20, 2.5, 3.1, 2.9, "Pinnacle", API),  # solo en la copia que se conserva
                (30, 1.5, 4.0, 6.0, "Bet365", "CSV"),  # solo otra casa
                (34, 1.0, 3.0, 3.0, "Pinnacle", API),
                *extra_odds,
            ]
        ),
    )
    _write(
        folder,
        "teams",
        {
            "id": pa.array([1, 2, 3, 4], pa.int64()),
            "name": pa.array(["Alfa", "Beta", "Gamma Club", "Gamma"], pa.string()),
        },
    )
    _write(
        folder,
        "leagues",
        {
            "id": pa.array([1, 5, 99], pa.int64()),
            "fd_code": pa.array(["E0", "SP1", "XX"], pa.string()),
        },
    )


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    folder = tmp_path / "huggingface"
    _write_dataset(folder)
    return folder


@pytest.fixture
def aliases(tmp_path: Path) -> Path:
    path = tmp_path / "aliases.csv"
    path.write_text(
        "alias_id,alias_name,canonical_id,canonical_name\n4,Gamma,3,Gamma Club\n", encoding="utf-8"
    )
    return path


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(tmp_path / "tipster.sqlite")
    yield connection
    connection.close()


def _run(conn: sqlite3.Connection, folder: Path, alias_file: Path) -> IngestResult:
    return ingest(conn, folder, START, END, aliases=load_aliases(alias_file), clock=lambda: NOW)


def _rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT m.match_date, m.competition_id, h.name AS home, a.name AS away, m.home_goals,"
        " m.away_goals, m.pinnacle_home, m.pinnacle_draw, m.pinnacle_away, m.odds_source,"
        " m.source_fixture_id FROM historical_matches m"
        " JOIN teams h ON h.id = m.home_team_id JOIN teams a ON a.id = m.away_team_id"
        " ORDER BY m.match_date, m.source_fixture_id"
    ).fetchall()


def test_la_migracion_crea_el_historico(conn: sqlite3.Connection) -> None:
    assert schema_versions(conn) == [1, 2]
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(historical_matches)")}
    assert {"competition_id", "match_date", "home_team_id", "away_team_id", "home_goals"} <= columns
    assert {"pinnacle_home", "pinnacle_draw", "pinnacle_away", "odds_source"} <= columns
    assert "known_at" not in columns  # no es una hora de captura fiable (ADR 007)


def test_carga_los_partidos_jugados_de_las_seis_ligas(
    conn: sqlite3.Connection, dataset: Path, aliases: Path
) -> None:
    result = _run(conn, dataset, aliases)
    rows = _rows(conn)
    assert [(r["match_date"], r["competition_id"], r["home"], r["away"]) for r in rows] == [
        ("2024-08-17", "premier", "Alfa", "Beta"),
        ("2024-08-25", "laliga", "Gamma Club", "Beta"),
        ("2024-09-01", "premier", "Beta", "Alfa"),
        ("2024-09-15", "premier", "Alfa", "Beta"),
    ]
    assert [(r["home_goals"], r["away_goals"]) for r in rows] == [(2, 1), (1, 1), (0, 3), (2, 2)]
    assert (result.matches_read, result.duplicates_removed, len(rows)) == (5, 1, 4)


def test_la_fecha_es_solo_el_dia(conn: sqlite3.Connection, dataset: Path, aliases: Path) -> None:
    _run(conn, dataset, aliases)
    assert all(len(r["match_date"]) == 10 for r in _rows(conn))  # AAAA-MM-DD, sin hora


def test_las_cuotas_de_pinnacle_priorizan_api_football_y_las_ausentes_son_nulas(
    conn: sqlite3.Connection, dataset: Path, aliases: Path
) -> None:
    result = _run(conn, dataset, aliases)
    by_date = {r["match_date"]: r for r in _rows(conn)}
    first = by_date["2024-08-17"]
    assert (first["pinnacle_home"], first["pinnacle_draw"], first["pinnacle_away"]) == (
        1.9,
        3.4,
        4.2,
    )
    assert first["odds_source"] == API
    # solo tenía otra casa: el partido se guarda igual, con la cuota nula
    nulls = by_date["2024-09-01"]
    assert (nulls["pinnacle_home"], nulls["odds_source"]) == (None, None)
    # una cuota <= 1 se trata como ausente
    assert by_date["2024-09-15"]["pinnacle_home"] is None
    assert result.with_pinnacle == 2


def test_colapsa_el_equipo_duplicado_y_conserva_la_cuota_de_la_copia_que_la_tiene(
    conn: sqlite3.Connection, dataset: Path, aliases: Path
) -> None:
    _run(conn, dataset, aliases)
    gamma = [r for r in _rows(conn) if r["competition_id"] == "laliga"]
    assert len(gamma) == 1
    assert (gamma[0]["home"], gamma[0]["pinnacle_home"], gamma[0]["source_fixture_id"]) == (
        "Gamma Club",
        2.5,
        21,
    )
    assert not conn.execute("SELECT 1 FROM teams WHERE name = 'Gamma'").fetchone()


def test_sin_alias_el_duplicado_sigue_ahi(conn: sqlite3.Connection, dataset: Path) -> None:
    sin_alias = dataset.parent / "vacio.csv"
    sin_alias.write_text("alias_id,alias_name,canonical_id,canonical_name\n", encoding="utf-8")
    result = _run(conn, dataset, sin_alias)
    assert result.duplicates_removed == 0
    assert len([r for r in _rows(conn) if r["competition_id"] == "laliga"]) == 2


def test_la_carga_es_idempotente(conn: sqlite3.Connection, dataset: Path, aliases: Path) -> None:
    _run(conn, dataset, aliases)
    before = [tuple(r) for r in _rows(conn)]
    teams = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
    again = _run(conn, dataset, aliases)
    assert conn.execute("SELECT COUNT(*) FROM historical_matches").fetchone()[0] == len(before)
    assert conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0] == teams
    assert again.matches_read == 5
    assert conn.execute("SELECT COUNT(*) FROM runs WHERE command = 'ingest'").fetchone()[0] == 2
    assert [tuple(r) for r in _rows(conn)] == before


def test_la_ejecucion_guarda_la_revision_y_los_sha256(
    conn: sqlite3.Connection, dataset: Path, aliases: Path
) -> None:
    _run(conn, dataset, aliases)
    snapshot = conn.execute("SELECT settings_json FROM runs WHERE command = 'ingest'").fetchone()[0]
    expected = hashlib.sha256((dataset / "fixtures.parquet").read_bytes()).hexdigest()
    assert expected in snapshot
    assert DATASET_REVISION in snapshot


def test_duplicados_con_distinto_resultado_hacen_fallar_la_carga(
    conn: sqlite3.Connection, tmp_path: Path, aliases: Path
) -> None:
    folder = tmp_path / "conflicto"
    _write_dataset(
        folder, extra_fixtures=[(22, "2024-08-24 18:00:00", 5, 4, 2, 3, 0, True)]
    )  # otra copia de Gamma-Beta con otro marcador
    with pytest.raises(IngestError, match=r"20.*22|22.*20"):
        _run(conn, folder, aliases)
    assert conn.execute("SELECT COUNT(*) FROM historical_matches").fetchone()[0] == 0


def test_un_alias_cuyo_nombre_no_coincide_con_el_dataset_falla(
    conn: sqlite3.Connection, dataset: Path, tmp_path: Path
) -> None:
    deriva = tmp_path / "deriva.csv"
    deriva.write_text(
        "alias_id,alias_name,canonical_id,canonical_name\n4,Otro nombre,3,Gamma Club\n",
        encoding="utf-8",
    )
    with pytest.raises(IngestError, match="Otro nombre"):
        _run(conn, dataset, deriva)


def test_el_fichero_de_alias_del_repositorio_es_coherente() -> None:
    aliases = load_aliases(DEFAULT_ALIASES)
    assert aliases
    assert all(a.alias_id != a.canonical_id for a in aliases.values())
    assert not {a.canonical_id for a in aliases.values()} & set(aliases)  # sin cadenas
    assert {a.canonical_name for a in aliases.values()} >= {"Athletic Club", "Inter Milan"}
    assert aliases[107].canonical_id == 4643  # Ath Bilbao → Athletic Club


# -- Descarga y trazabilidad ------------------------------------------------------------------


def _client(calls: list[httpx.Request], payloads: dict[str, bytes]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        name = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, content=payloads[name])

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_descarga_guarda_el_parquet_con_su_sha256_y_no_repite(tmp_path: Path) -> None:
    payloads = {
        f"{n}.parquet": f"contenido de {n}".encode()
        for n in ("fixtures", "odds", "teams", "leagues")
    }
    calls: list[httpx.Request] = []
    first = fetch_tables(tmp_path, _client(calls, payloads))
    assert len(calls) == 4
    assert all(DATASET_REVISION in str(c.url) for c in calls)  # revisión fijada
    path = first["odds"].path
    assert path.parent == tmp_path / DATASET_REVISION[:12]
    digest = hashlib.sha256(payloads["odds.parquet"]).hexdigest()
    assert first["odds"].sha256 == digest
    assert (path.parent / "odds.parquet.sha256").read_text(encoding="utf-8").split()[0] == digest
    second = fetch_tables(tmp_path, _client(calls, payloads))
    assert len(calls) == 4  # caché: no vuelve a descargar
    assert second["odds"].sha256 == digest


def test_un_parquet_alterado_en_disco_falla(tmp_path: Path) -> None:
    payloads = {f"{n}.parquet": b"x" for n in ("fixtures", "odds", "teams", "leagues")}
    calls: list[httpx.Request] = []
    fetch_tables(tmp_path, _client(calls, payloads))
    (tmp_path / DATASET_REVISION[:12] / "odds.parquet").write_bytes(b"alterado")
    with pytest.raises(IngestError, match="sha256"):
        fetch_tables(tmp_path, _client(calls, payloads))


# -- CLI ---------------------------------------------------------------------------------------


def test_cli_ingest_sobre_la_carpeta_ya_descargada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # sin .env del repositorio
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    _write_dataset(tmp_path / "data" / "raw" / "huggingface" / DATASET_REVISION[:12])
    result = CliRunner().invoke(
        app, ["ingest", "--from", "2016", "--to", "2025"], env={"COLUMNS": "200"}
    )
    assert result.exit_code == 0, result.output
    assert "Partidos cargados" in result.output
    assert "Duplicados eliminados" in result.output
    assert "con cuota de Pinnacle completa" in result.output
    assert "eatpizzanot/soccer-dataset" in result.output  # atribución (CC-BY-4.0)
    db = sqlite3.connect(tmp_path / "data" / "tipster.sqlite")
    assert db.execute("SELECT COUNT(*) FROM historical_matches").fetchone()[0] > 0

"""Dataset `eatpizzanot/soccer-dataset` de Hugging Face (CC-BY-4.0, ADR 007).

Descarga los Parquet de una revisión fija, con su sha256, y los lee. Solo se leen las columnas y
filas que usa la ingesta; `known_at` no se lee: no es una hora de captura fiable.
"""

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import pyarrow.parquet as pq

from tipster.errors import IngestError

DATASET = "eatpizzanot/soccer-dataset"
DATASET_REVISION = "f0cbe86bee3f28cc4b803f735a5287968741c471"  # 2026-07-05
TABLES = ("fixtures", "odds", "teams", "leagues")
ATTRIBUTION = (
    "Datos: eatpizzanot/soccer-dataset (CC-BY-4.0), compilado a partir de API-Football y "
    "football-data.co.uk."
)
_URL = f"https://huggingface.co/datasets/{DATASET}/resolve/{DATASET_REVISION}/" + "{name}.parquet"
FD_CODES = {
    "E0": "premier",
    "SP1": "laliga",
    "SP2": "segunda",
    "I1": "serie_a",
    "D1": "bundesliga",
    "F1": "ligue_1",
}
PINNACLE = "Pinnacle"
PREFERRED_SOURCE = "API-Football-closing"


@dataclass(frozen=True)
class FetchedFile:
    path: Path
    sha256: str
    downloaded: bool


@dataclass(frozen=True)
class RawMatch:
    fixture_id: int
    competition_id: str
    day: date
    home_id: int
    away_id: int
    home_goals: int
    away_goals: int


@dataclass(frozen=True)
class PinnacleOdds:
    home: float
    draw: float
    away: float
    source: str


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fetch_one(folder: Path, name: str, client: httpx.Client) -> FetchedFile:
    path = folder / f"{name}.parquet"
    sidecar = folder / f"{name}.parquet.sha256"
    downloaded = not path.exists()
    if downloaded:
        try:
            response = client.get(_URL.format(name=name))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise IngestError(f"No se pudo descargar {name}.parquet: {exc}") from exc
        path.write_bytes(response.content)
    digest = file_sha256(path)
    if sidecar.exists() and sidecar.read_text(encoding="utf-8").split()[0] != digest:
        raise IngestError(f"{path}: el sha256 no coincide con el registrado; el fichero cambió")
    sidecar.write_text(f"{digest}  {name}.parquet\n", encoding="utf-8")
    return FetchedFile(path=path, sha256=digest, downloaded=downloaded)


def fetch_tables(base: Path, client: httpx.Client | None = None) -> dict[str, FetchedFile]:
    """Deja los Parquet en `base/<revisión>/`; la revisión fijada no cambia, no se repite."""
    folder = base / DATASET_REVISION[:12]
    folder.mkdir(parents=True, exist_ok=True)
    owned = client is None
    http = client or httpx.Client(follow_redirects=True, timeout=120)
    try:
        return {name: _fetch_one(folder, name, http) for name in TABLES}
    finally:
        if owned:
            http.close()


def read_competitions(path: Path) -> dict[int, str]:
    """`leagues.id` → id de competición del proyecto, solo para las 6 ligas."""
    rows = pq.read_table(path, columns=["id", "fd_code"]).to_pylist()
    return {r["id"]: FD_CODES[r["fd_code"]] for r in rows if r["fd_code"] in FD_CODES}


def read_team_names(path: Path) -> dict[int, str]:
    return {r["id"]: r["name"] for r in pq.read_table(path, columns=["id", "name"]).to_pylist()}


def read_matches(
    path: Path, competitions: Mapping[int, str], start: date, end: date
) -> list[RawMatch]:
    """Partidos jugados de las competiciones entre `start` y `end` (ambos incluidos)."""
    table = pq.read_table(
        path,
        columns=[
            "id",
            "date_utc",
            "league_id",
            "home_team_id",
            "away_team_id",
            "goals_home",
            "goals_away",
        ],
        filters=[
            ("league_id", "in", list(competitions)),
            ("is_played", "==", True),
            ("date_utc", ">=", datetime.combine(start, datetime.min.time())),
            ("date_utc", "<", datetime.combine(end + timedelta(days=1), datetime.min.time())),
        ],
    )
    matches = []
    for r in table.to_pylist():
        if r["goals_home"] is None or r["goals_away"] is None:
            raise IngestError(f"El partido {r['id']} figura como jugado pero no tiene goles")
        matches.append(
            RawMatch(
                fixture_id=r["id"],
                competition_id=competitions[r["league_id"]],
                day=r["date_utc"].date(),
                home_id=r["home_team_id"],
                away_id=r["away_team_id"],
                home_goals=r["goals_home"],
                away_goals=r["goals_away"],
            )
        )
    return matches


def read_pinnacle(path: Path, fixture_ids: set[int]) -> dict[int, PinnacleOdds]:
    """Cierre de Pinnacle 1X2 por partido. Una cuota <= 1 cuenta como ausente; si hay varias
    filas de Pinnacle se prefiere la de API-Football y, a igualdad, la de `source` menor."""
    table = pq.read_table(
        path,
        columns=["fixture_id", "home_win", "draw", "away_win", "source"],
        filters=[("bookmaker", "==", PINNACLE)],
    )
    best: dict[int, PinnacleOdds] = {}
    for r in table.to_pylist():
        fixture_id = r["fixture_id"]
        prices = (r["home_win"], r["draw"], r["away_win"])
        if fixture_id not in fixture_ids or any(p is None or p <= 1 for p in prices):
            continue
        odds = PinnacleOdds(*prices, source=r["source"])
        current = best.get(fixture_id)
        if current is None or _rank(odds) < _rank(current):
            best[fixture_id] = odds
    return best


def _rank(odds: PinnacleOdds) -> tuple[bool, str]:
    return (odds.source != PREFERRED_SOURCE, odds.source)

"""Lectura de los CSV de football-data.co.uk para el backtest (BACKLOG 53).

Cada partido trae dos fotos: cuotas previas (viernes/martes por la tarde) y de cierre. La
probabilidad justa sale SIEMPRE de la cuota previa de Pinnacle; el cierre solo mide el CLV. Los
nombres de columna cambian según la temporada, así que cada cuota admite varios alias.
"""

import csv
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

BASE_URL = "https://www.football-data.co.uk/mmz4281"
LEAGUES: Mapping[str, str] = {
    "premier": "E0",
    "laliga": "SP1",
    "serie_a": "I1",
    "bundesliga": "D1",
    "ligue_1": "F1",
}
Triple = tuple[float, float, float]

# (local, empate, visitante) con los alias que ha tenido cada cuota
_COLUMNS: Mapping[str, Sequence[tuple[str, str, str]]] = {
    "ps_open": (("PSH", "PSD", "PSA"), ("PH", "PD", "PA")),
    "ps_close": (("PSCH", "PSCD", "PSCA"), ("PCH", "PCD", "PCA")),
    "b365": (("B365H", "B365D", "B365A"),),
    "avg": (("AvgH", "AvgD", "AvgA"), ("BbAvH", "BbAvD", "BbAvA")),
    "max": (("MaxH", "MaxD", "MaxA"), ("BbMxH", "BbMxD", "BbMxA")),
}


@dataclass(frozen=True)
class Match:
    league: str
    season: str  # «1920» = 2019/20
    day: date
    home: str
    away: str
    result: int  # 0 local, 1 empate, 2 visitante
    ps_open: Triple
    ps_close: Triple
    taken: Mapping[str, Triple]  # b365, avg, max: lo que se podría tomar


@dataclass
class LoadReport:
    rows: int = 0
    kept: int = 0
    dropped: dict[str, int] = field(default_factory=dict)

    def drop(self, why: str) -> None:
        self.dropped[why] = self.dropped.get(why, 0) + 1


def season_code(start_year: int) -> str:
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def season_url(season: str, league_code: str) -> str:
    return f"{BASE_URL}/{season}/{league_code}.csv"


def _triple(row: Mapping[str, str], aliases: Iterable[tuple[str, str, str]]) -> Triple | None:
    for names in aliases:
        try:
            values = tuple(float(row[n]) for n in names)
        except (KeyError, ValueError):
            continue
        if all(v > 1.0 for v in values):
            return values  # type: ignore[return-value]
    return None


def _parse_date(text: str) -> date | None:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def read_csv(path: Path, league: str, season: str, report: LoadReport) -> list[Match]:
    matches: list[Match] = []
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            if not row.get("HomeTeam"):
                continue  # filas vacías al final del CSV
            report.rows += 1
            day = _parse_date(row.get("Date", ""))
            result = {"H": 0, "D": 1, "A": 2}.get(row.get("FTR", ""))
            if day is None or result is None:
                report.drop("sin fecha o resultado")
                continue
            ps_open = _triple(row, _COLUMNS["ps_open"])
            if ps_open is None:
                report.drop("sin Pinnacle previo")
                continue
            ps_close = _triple(row, _COLUMNS["ps_close"])
            if ps_close is None:
                report.drop("sin Pinnacle de cierre")
                continue
            taken = {
                k: t for k in ("b365", "avg", "max") if (t := _triple(row, _COLUMNS[k])) is not None
            }
            if not taken:
                report.drop("sin cuota de casa")
                continue
            report.kept += 1
            matches.append(
                Match(
                    league, season, day, row["HomeTeam"], row["AwayTeam"], result,
                    ps_open, ps_close, taken,
                )
            )  # fmt: skip
    return matches


def load_dir(data_dir: Path) -> tuple[list[Match], LoadReport]:
    """Carga `data_dir/<temporada>/<código>.csv` de las ligas del registro."""
    report = LoadReport()
    matches: list[Match] = []
    for season_dir in sorted(p for p in data_dir.iterdir() if p.is_dir()):
        for league, code in LEAGUES.items():
            path = season_dir / f"{code}.csv"
            if path.exists():
                matches.extend(read_csv(path, league, season_dir.name, report))
    return matches, report


def download(
    data_dir: Path,
    first_year: int,
    last_year: int,
    fetch: Callable[[str], bytes | None],
) -> tuple[int, int]:
    """Baja `<temporada>/<código>.csv`. Las temporadas cerradas no se vuelven a pedir; la última
    (en curso) sí. Devuelve (descargados, ya en caché)."""
    got = cached = 0
    for year in range(first_year, last_year + 1):
        season = season_code(year)
        for code in LEAGUES.values():
            path = data_dir / season / f"{code}.csv"
            if path.exists() and year < last_year:
                cached += 1
                continue
            body = fetch(season_url(season, code))
            if body is None:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            got += 1
    return got, cached

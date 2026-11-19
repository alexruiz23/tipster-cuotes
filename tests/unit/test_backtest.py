from datetime import date
from pathlib import Path

import pytest

from tipster.backtest.football_data import (
    LoadReport,
    Match,
    download,
    load_dir,
    read_csv,
    season_code,
)
from tipster.backtest.simulate import Strategy, run, summarize

HEADER = "Div,Date,HomeTeam,AwayTeam,FTR,{cols}\n"


def _csv(tmp_path: Path, season: str, cols: str, rows: list[str]) -> Path:
    path = tmp_path / season / "E0.csv"
    path.parent.mkdir(parents=True)
    path.write_text(HEADER.format(cols=cols) + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_lee_columnas_con_alias_y_descarta_sin_cierre(tmp_path: Path) -> None:
    cols = "PH,PD,PA,PCH,PCD,PCA,B365H,B365D,B365A"
    path = _csv(
        tmp_path,
        "2526",
        cols,
        [
            "E0,16/08/2025,A,B,H,2.0,3.5,4.0,1.9,3.6,4.4,2.1,3.4,4.0",
            "E0,17/08/2025,C,D,A,2.0,3.5,4.0,,,,2.1,3.4,4.0",  # sin cierre
            "E0,18/08/2025,E,F,D,,,,,,,2.1,3.4,4.0",  # sin Pinnacle previo
        ],
    )
    report = LoadReport()
    matches = read_csv(path, "premier", "2526", report)
    assert [m.home for m in matches] == ["A"]
    assert report.rows == 3
    assert report.dropped == {"sin Pinnacle de cierre": 1, "sin Pinnacle previo": 1}
    assert matches[0].ps_open == (2.0, 3.5, 4.0)
    assert matches[0].taken["b365"] == (2.1, 3.4, 4.0)


def test_descarta_pinnacle_con_margen_negativo(tmp_path: Path) -> None:
    cols = "PSH,PSD,PSA,PSCH,PSCD,PSCA,B365H,B365D,B365A"
    path = _csv(tmp_path, "2526", cols, ["E0,16/08/2025,A,B,H,3,4,4,2,3.5,4,2,3.5,4"])
    report = LoadReport()
    assert read_csv(path, "premier", "2526", report) == []
    assert report.dropped == {"Pinnacle con margen negativo": 1}


def test_fecha_con_anio_de_dos_cifras(tmp_path: Path) -> None:
    cols = "PSH,PSD,PSA,PSCH,PSCD,PSCA,B365H,B365D,B365A"
    path = _csv(tmp_path, "1213", cols, ["E0,16/08/13,A,B,H,2,3.5,4,2,3.5,4,2,3.5,4"])
    assert read_csv(path, "premier", "1213", LoadReport())[0].day == date(2013, 8, 16)


def _match(
    result: int,
    open_: tuple[float, float, float],
    taken: tuple[float, float, float],
    close: tuple[float, float, float] | None = None,
    day: date = date(2025, 8, 16),
) -> Match:
    return Match("premier", "2526", day, "A", "B", result, open_, close or open_, {"b365": taken})


def test_la_probabilidad_justa_sale_del_previo_y_el_clv_del_cierre() -> None:
    # previo justo 2.0/2.0 sobre dos resultados no aplica en 1X2; usamos un 1X2 casi sin margen
    open_ = (2.0, 4.0, 4.0)  # q = .5/.25/.25, sin margen: p = q
    taken = (2.2, 3.0, 3.0)  # EV local = .5*2.2-1 = +10 %
    close = (1.8, 4.5, 4.5)  # el mercado se mueve hacia nuestro pick
    bets = run([_match(0, open_, taken, close)], Strategy(book="b365"))
    assert len(bets) == 1
    assert bets[0].ev == pytest.approx(0.10, abs=1e-6)
    fair_close = (1 / 1.8) / (1 / 1.8 + 2 / 4.5)
    assert bets[0].clv == pytest.approx(2.2 * fair_close - 1, abs=1e-6)
    assert bets[0].profit == pytest.approx(1.2)


def test_un_pick_por_partido_y_tope_de_improbables_por_semana() -> None:
    open_ = (6.0, 6.0, 1.5)
    taken = (7.0, 7.0, 1.5)  # dos improbables con EV +17 %
    same_week = [_match(0, open_, taken, day=date(2025, 8, 11 + i)) for i in range(3)]
    assert len(run(same_week, Strategy(max_open_longshots=2))) == 2
    assert len(run(same_week, Strategy(max_open_longshots=99))) == 3
    assert len(run(same_week[:1], Strategy())) == 1  # un pick por partido, no dos


def test_resumen_vacio_y_con_picks() -> None:
    assert summarize([]).n == 0
    bets = run([_match(0, (2.0, 4.0, 4.0), (2.2, 3.0, 3.0))], Strategy())
    s = summarize(bets)
    assert s.n == 1
    assert s.roi == pytest.approx(1.2)
    assert s.hit == 1.0


def test_descarga_no_repite_temporadas_cerradas(tmp_path: Path) -> None:
    calls: list[str] = []

    def fetch(url: str) -> bytes | None:
        calls.append(url)
        return b"x"

    first = download(tmp_path, 2024, 2025, fetch)
    calls.clear()
    second = download(tmp_path, 2024, 2025, fetch)
    assert first == (10, 0)
    assert second == (5, 5)  # la temporada en curso (2025) se pide de nuevo
    assert all("/2526/" in c for c in calls)
    assert season_code(2025) == "2526"


def test_load_dir_recorre_temporadas(tmp_path: Path) -> None:
    cols = "PSH,PSD,PSA,PSCH,PSCD,PSCA,B365H,B365D,B365A"
    _csv(tmp_path, "2526", cols, ["E0,16/08/2025,A,B,H,2,3.5,4,2,3.5,4,2,3.5,4"])
    matches, report = load_dir(tmp_path)
    assert len(matches) == 1 and report.kept == 1

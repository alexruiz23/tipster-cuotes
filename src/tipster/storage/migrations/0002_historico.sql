-- 0002: histórico de partidos de la Fase 2 (ADR 007). Fechas AAAA-MM-DD: el dataset no da una
-- hora fiable, así que no se guarda ninguna.

CREATE TABLE teams (
    id INTEGER PRIMARY KEY, -- id canónico del dataset de Hugging Face (tras aplicar los alias)
    name TEXT NOT NULL
);

CREATE TABLE historical_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competition_id TEXT NOT NULL,
    match_date TEXT NOT NULL,
    home_team_id INTEGER NOT NULL REFERENCES teams (id),
    away_team_id INTEGER NOT NULL REFERENCES teams (id),
    home_goals INTEGER NOT NULL CHECK (home_goals >= 0),
    away_goals INTEGER NOT NULL CHECK (away_goals >= 0),
    -- cierre de Pinnacle 1X2; NULL si el partido no tiene (el partido se guarda igual)
    pinnacle_home REAL CHECK (pinnacle_home > 1),
    pinnacle_draw REAL CHECK (pinnacle_draw > 1),
    pinnacle_away REAL CHECK (pinnacle_away > 1),
    odds_source TEXT, -- columna `source` del dataset (API-Football-closing, CSV, …)
    source_fixture_id INTEGER NOT NULL, -- fixtures.id del dataset de la copia conservada
    run_id INTEGER NOT NULL REFERENCES runs (id), -- última ejecución de `ingest` que la escribió
    CHECK (home_team_id <> away_team_id),
    CHECK ((pinnacle_home IS NULL) = (pinnacle_draw IS NULL)),
    CHECK ((pinnacle_home IS NULL) = (pinnacle_away IS NULL)),
    CHECK ((pinnacle_home IS NULL) = (odds_source IS NULL)),
    UNIQUE (competition_id, match_date, home_team_id, away_team_id)
);
CREATE INDEX ix_hist_comp_date ON historical_matches (competition_id, match_date);

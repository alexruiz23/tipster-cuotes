-- 0001: esquema inicial de la Fase 1. SQL portable; fechas en texto ISO-8601 UTC.

CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('en_curso', 'ok', 'parcial', 'error')),
    settings_json TEXT NOT NULL -- umbrales usados; nunca la clave
);

CREATE TABLE provider_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs (id),
    provider TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    params_key TEXT NOT NULL, -- parámetros ordenados, sin apiKey
    http_status INTEGER,
    from_cache INTEGER NOT NULL CHECK (from_cache IN (0, 1)),
    cost INTEGER,
    credits_used INTEGER,
    credits_remaining INTEGER,
    requested_at TEXT NOT NULL,
    duration_ms INTEGER,
    raw_path TEXT,
    error TEXT
);
CREATE INDEX ix_req_cache ON provider_requests (provider, endpoint, params_key, requested_at);
CREATE INDEX ix_req_run ON provider_requests (run_id);

CREATE TABLE events (
    id TEXT PRIMARY KEY,
    sport TEXT NOT NULL,
    competition_id TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    kickoff_utc TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX ix_events_comp ON events (competition_id, kickoff_utc);

CREATE TABLE event_external_ids (
    provider TEXT NOT NULL,
    external_id TEXT NOT NULL,
    event_id TEXT NOT NULL REFERENCES events (id),
    PRIMARY KEY (provider, external_id)
);
CREATE INDEX ix_ext_event ON event_external_ids (event_id);

CREATE TABLE odds_quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL REFERENCES provider_requests (id),
    event_id TEXT NOT NULL REFERENCES events (id),
    bookmaker_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    selection TEXT NOT NULL,
    price REAL NOT NULL CHECK (price > 1),
    captured_at TEXT NOT NULL, -- momento de la petición que trajo la cuota (UTC)
    provider_last_update TEXT, -- cuándo la vio el proveedor en la casa (UTC)
    source TEXT NOT NULL,
    UNIQUE (request_id, event_id, bookmaker_id, market_id, selection)
);
CREATE INDEX ix_quotes_lookup ON odds_quotes (event_id, market_id, bookmaker_id, captured_at);

CREATE TABLE picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs (id),
    quote_id INTEGER NOT NULL REFERENCES odds_quotes (id),
    label TEXT NOT NULL CHECK (label IN ('VALUE', 'POSIBLE_ERROR')),
    feed_es INTEGER NOT NULL CHECK (feed_es IN (0, 1)),
    reference_bookmaker_id TEXT NOT NULL,
    reference_captured_at TEXT NOT NULL,
    reference_odds_json TEXT NOT NULL, -- [[selección, cuota], ...] en orden de selección
    devig_method TEXT NOT NULL,
    p_market REAL NOT NULL,
    p_model REAL,
    p_final REAL NOT NULL,
    fair_odds REAL NOT NULL,
    ev REAL NOT NULL,
    stake REAL, -- NULL hasta la Fase 3
    reasons_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (run_id, quote_id)
);
CREATE INDEX ix_picks_run ON picks (run_id);

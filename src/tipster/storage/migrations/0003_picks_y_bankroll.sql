-- 0003: seguimiento de picks y bankroll de papel (Fase 3, ADR 012). Fechas en texto ISO-8601 UTC.

ALTER TABLE picks ADD COLUMN p_model_raw REAL; -- Dixon-Coles sin calibrar
ALTER TABLE picks ADD COLUMN w_market REAL; -- peso del mercado en la mezcla
ALTER TABLE picks ADD COLUMN model_name TEXT; -- NULL si el pick no usó modelo
ALTER TABLE picks ADD COLUMN model_version TEXT; -- id de la configuración de mezcla usada
ALTER TABLE picks ADD COLUMN status TEXT NOT NULL DEFAULT 'abierto'
    CHECK (status IN ('abierto', 'ganado', 'perdido', 'nulo'));
ALTER TABLE picks ADD COLUMN result TEXT
    CHECK (result IN ('local', 'empate', 'visitante', 'mas', 'menos'));
ALTER TABLE picks ADD COLUMN settled_at TEXT;
ALTER TABLE picks ADD COLUMN profit REAL; -- NULL si el pick no tenía stake
ALTER TABLE picks ADD COLUMN closing_odds REAL CHECK (closing_odds > 1); -- cuota cruda de Pinnacle
ALTER TABLE picks ADD COLUMN closing_fair_odds REAL CHECK (closing_fair_odds > 1); -- sin margen
ALTER TABLE picks ADD COLUMN closing_captured_at TEXT;
ALTER TABLE picks ADD COLUMN closing_last_update TEXT; -- last_update de Pinnacle en esa captura
ALTER TABLE picks ADD COLUMN closing_reliable INTEGER CHECK (closing_reliable IN (0, 1));
ALTER TABLE picks ADD COLUMN clv REAL; -- NULL sin cierre fiable: nunca se imputa
CREATE INDEX ix_picks_status ON picks (status);

CREATE TABLE bankroll_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('deposito', 'liquidacion')),
    amount REAL NOT NULL,
    balance_after REAL NOT NULL,
    pick_id INTEGER REFERENCES picks (id)
);
CREATE UNIQUE INDEX ux_bankroll_pick ON bankroll_entries (pick_id) WHERE pick_id IS NOT NULL;

CREATE TABLE blend_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    settings_json TEXT NOT NULL -- devig, forma y peso de la mezcla, calibrador y ventana de validación
);

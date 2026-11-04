-- Los retiros del bankroll (ADR 012): SQLite no cambia un CHECK, así que se recrea la tabla.
CREATE TABLE bankroll_entries_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('deposito', 'retiro', 'liquidacion')),
    amount REAL NOT NULL, -- con signo: el retiro y la pérdida son negativos
    balance_after REAL NOT NULL,
    pick_id INTEGER REFERENCES picks (id)
);
INSERT INTO bankroll_entries_new SELECT id, at, kind, amount, balance_after, pick_id FROM bankroll_entries;
DROP TABLE bankroll_entries;
ALTER TABLE bankroll_entries_new RENAME TO bankroll_entries;
CREATE UNIQUE INDEX ux_bankroll_pick ON bankroll_entries (pick_id) WHERE pick_id IS NOT NULL;

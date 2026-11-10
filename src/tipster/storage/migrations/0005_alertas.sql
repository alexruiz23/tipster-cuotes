-- 0005: avisos ya enviados (`tipster notify --alerts`): cada aviso se manda una sola vez por clave.
CREATE TABLE alerts_sent (
    key TEXT PRIMARY KEY,
    sent_at TEXT NOT NULL
);

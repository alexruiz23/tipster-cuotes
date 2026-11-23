"""Exportación puntual de solo lectura de los picks a CSV (análisis por casa, 23/11/2026)."""

import csv
import sqlite3
import sys

conn = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
cur = conn.execute(
    "SELECT p.id, p.created_at, e.competition_id, e.kickoff_utc, q.market_id, q.selection,"
    " q.bookmaker_id, q.price, q.provider_last_update, p.fair_odds, p.p_final, p.ev, p.stake,"
    " p.label, p.devig_method, p.status, p.result, p.profit, p.closing_odds, p.closing_fair_odds,"
    " p.closing_captured_at, p.closing_reliable, p.clv, p.taken_price, p.clv_taken,"
    " (SELECT MAX(r.provider_last_update) FROM odds_quotes r WHERE r.event_id = q.event_id"
    "  AND r.market_id = q.market_id AND r.bookmaker_id = 'pinnacle'"
    "  AND r.captured_at = q.captured_at) AS pinnacle_last_update"
    " FROM picks p JOIN odds_quotes q ON q.id = p.quote_id JOIN events e ON e.id = q.event_id"
    " ORDER BY p.id"
)
out = csv.writer(sys.stdout)
print("=== CSV ===")
out.writerow([d[0] for d in cur.description])
out.writerows(cur)
print("=== FIN ===")

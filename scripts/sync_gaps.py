"""Medición puntual (solo lectura): desfase entre el `last_update` de Pinnacle y el de la cuota de
cada pick, en la misma captura. Decide si hace falta un límite de sincronización (auditoría 23/11)."""

import sqlite3
import sys
from datetime import datetime

conn = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
rows = conn.execute(
    "SELECT p.id, p.stake, q.bookmaker_id, q.provider_last_update,"
    " MAX(r.provider_last_update), MIN(r.provider_last_update)"
    " FROM picks p JOIN odds_quotes q ON q.id = p.quote_id"
    " JOIN odds_quotes r ON r.event_id = q.event_id AND r.market_id = q.market_id"
    " AND r.bookmaker_id = 'pinnacle' AND r.captured_at = q.captured_at"
    " GROUP BY p.id"
).fetchall()


def ts(text: str | None) -> datetime | None:
    return None if text is None else datetime.fromisoformat(text)


gaps, spreads, missing = [], [], 0
for _pid, stake, book, lu, pin_max, pin_min in rows:
    a, b, c = ts(lu), ts(pin_max), ts(pin_min)
    if a is None or b is None or c is None:
        missing += 1
        continue
    gaps.append((abs((a - b).total_seconds()), bool(stake), book))
    spreads.append((b - c).total_seconds())

print(f"picks con referencia de Pinnacle en la misma captura: {len(rows)} (sin last_update: {missing})")
print(f"diferencia máxima entre las selecciones de Pinnacle: {max(spreads, default=0):.0f} s")
for label, subset in (("todos", gaps), ("con stake", [g for g in gaps if g[1]])):
    secs = sorted(g[0] for g in subset)
    if not secs:
        continue
    over = {t: sum(s > t for s in secs) for t in (60, 120, 180, 300, 600)}
    print(
        f"{label}: n={len(secs)} · mediana {secs[len(secs) // 2]:.0f} s · máx {secs[-1]:.0f} s · "
        + " · ".join(f">{t}s: {n}" for t, n in over.items())
    )
by_book: dict[str, list[float]] = {}
for g, _, book in gaps:
    by_book.setdefault(book, []).append(g)
for book, secs in sorted(by_book.items()):
    secs.sort()
    print(f"  {book}: n={len(secs)} · mediana {secs[len(secs) // 2]:.0f} s · máx {secs[-1]:.0f} s")

"""Textos de las notificaciones de Telegram (`tipster notify`)."""

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from tipster.storage.db import from_iso

_PICK_COLS = """
    e.home_team, e.away_team, e.kickoff_utc, q.market_id, q.selection, q.bookmaker_id, q.price,
    p.ev, p.stake, p.feed_es, p.status, p.profit"""
_FROM = """
    FROM picks p JOIN odds_quotes q ON q.id = p.quote_id JOIN events e ON e.id = q.event_id"""


def picks_text(conn: sqlite3.Connection, tz: ZoneInfo) -> str:
    """Picks con stake del último scan que siguen abiertos."""
    run = conn.execute("SELECT MAX(id) FROM runs WHERE command = 'scan'").fetchone()[0]
    rows = (
        conn.execute(
            f"SELECT {_PICK_COLS} {_FROM} WHERE p.run_id = ? AND p.stake > 0 "
            "AND p.status = 'abierto' ORDER BY e.kickoff_utc, p.ev DESC",
            (run,),
        ).fetchall()
        if run is not None
        else []
    )
    if not rows:
        return "Último scan: sin picks con stake."
    lines = [f"Último scan: {len(rows)} picks con stake"]
    for home, away, ko, market, sel, book, price, ev, stake, feed_es, _, _ in rows:
        when = from_iso(ko).astimezone(tz).strftime("%d/%m %H:%M")
        warn = "" if feed_es else " · verifica la cuota en la web .es"
        lines.append(
            f"{home} – {away} ({when})\n  {market} {sel} @ {price:g} en {book} · "
            f"EV {ev * 100:+.1f} % · stake {stake:.2f} €{warn}"
        )
    return "\n".join(lines)


def settled_text(
    conn: sqlite3.Connection, tz: ZoneInfo, now: datetime, balance: float
) -> str | None:
    """Resumen de los picks con stake liquidados hoy; None si no hay ninguno."""
    rows = conn.execute(
        f"SELECT {_PICK_COLS}, p.settled_at {_FROM} WHERE p.stake > 0 AND p.status <> 'abierto' "
        "AND p.settled_at IS NOT NULL ORDER BY p.settled_at"
    ).fetchall()
    today = now.astimezone(tz).date()
    rows = [r for r in rows if from_iso(r[-1]).astimezone(tz).date() == today]
    if not rows:
        return None
    lines = [f"Liquidados hoy: {len(rows)}"]
    total = 0.0
    for home, away, _, market, sel, _, price, _, stake, _, status, profit in (r[:-1] for r in rows):
        total += profit or 0.0
        lines.append(
            f"{status.upper()} {home} – {away}: {market} {sel} @ {price:g} · "
            f"stake {stake:.2f} € → {profit or 0.0:+.2f} €"
        )
    lines.append(f"Resultado del día {total:+.2f} € · bankroll {balance:.2f} €")
    return "\n".join(lines)

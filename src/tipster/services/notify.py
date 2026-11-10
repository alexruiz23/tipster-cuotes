"""Textos de las notificaciones de Telegram (`tipster notify`)."""

import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from tipster.storage.db import from_iso, iso

CLOSE_GRACE = timedelta(minutes=5)  # tras el inicio, `close` ya no puede capturar
ALERT_LOOKBACK = timedelta(days=3)  # no se avisa de cierres perdidos más viejos que esto
SCAN_STALE = timedelta(days=8)  # el scan es semanal: más de 8 días sin correr es un fallo

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
            f"SELECT {_PICK_COLS}, p.id {_FROM} WHERE p.run_id = ? AND p.stake > 0 "
            "AND p.status = 'abierto' ORDER BY e.kickoff_utc, p.ev DESC",
            (run,),
        ).fetchall()
        if run is not None
        else []
    )
    if not rows:
        return "Último scan: sin picks con stake."
    lines = [f"Último scan: {len(rows)} picks con stake (cuota real: tipster take ID --price X)"]
    for home, away, ko, market, sel, book, price, ev, stake, feed_es, _, _, pick_id in rows:
        when = from_iso(ko).astimezone(tz).strftime("%d/%m %H:%M")
        warn = "" if feed_es else " · verifica la cuota en la web .es"
        lines.append(
            f"#{pick_id} {home} – {away} ({when})\n  {market} {sel} @ {price:g} en {book} · "
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


Alert = tuple[str, str]  # (clave única, línea de texto)


def alerts(
    conn: sqlite3.Connection,
    tz: ZoneInfo,
    now: datetime,
    *,
    low_credits: int,
) -> list[Alert]:
    """Problemas del paper trading que no se ven solos. Cada uno lleva una clave estable: el aviso
    se manda una sola vez (ver `unsent`)."""
    found: list[Alert] = []

    # 1. picks con stake cuyo partido empezó sin cierre fiable: ese CLV ya no se recupera
    rows = conn.execute(
        "SELECT p.id, e.home_team, e.away_team, e.kickoff_utc, q.market_id, q.selection, q.price,"
        " p.closing_captured_at FROM picks p JOIN odds_quotes q ON q.id = p.quote_id"
        " JOIN events e ON e.id = q.event_id"
        " WHERE p.stake > 0 AND p.status <> 'nulo' AND p.clv IS NULL"
        " AND julianday(e.kickoff_utc) <= julianday(?) AND julianday(e.kickoff_utc) >= julianday(?)"
        " ORDER BY e.kickoff_utc",
        (iso(now - CLOSE_GRACE), iso(now - ALERT_LOOKBACK)),
    ).fetchall()
    for pick_id, home, away, ko, market, sel, price, captured in rows:
        why = "cierre capturado fuera de ventana (no fiable)" if captured else "sin cierre"
        when = from_iso(ko).astimezone(tz).strftime("%d/%m %H:%M")
        found.append(
            (
                f"sin-clv:{pick_id}",
                f"Sin CLV: {home} – {away} ({when}) {market} {sel} @ {price:g}: {why}",
            )
        )

    # 2. ejecuciones que terminaron en error
    for run_id, command, started in conn.execute(
        "SELECT id, command, started_at FROM runs WHERE status = 'error' "
        "AND command IN ('scan', 'close', 'settle') AND julianday(started_at) >= julianday(?) "
        "ORDER BY id",
        (iso(now - ALERT_LOOKBACK),),
    ):
        when = from_iso(started).astimezone(tz).strftime("%d/%m %H:%M")
        found.append((f"run:{run_id}", f"`{command}` terminó en error ({when}); mira data/logs/"))

    # 3. el scan semanal no ha corrido (Mac dormido, agente caído)
    last = conn.execute("SELECT MAX(started_at) FROM runs WHERE command = 'scan'").fetchone()[0]
    if last is not None and now - from_iso(last) > SCAN_STALE:
        days = (now - from_iso(last)).days
        found.append(
            (f"scan-parado:{from_iso(last).date()}", f"El scan no corre desde hace {days} días")
        )

    # 4. créditos de The Odds API a punto de agotarse
    left = conn.execute(
        "SELECT credits_remaining FROM provider_requests WHERE credits_remaining IS NOT NULL "
        "AND from_cache = 0 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if left is not None and left[0] < low_credits:
        month = now.astimezone(tz).strftime("%Y-%m")
        found.append((f"creditos:{month}", f"Quedan {left[0]} créditos de The Odds API"))
    return found


def unsent(conn: sqlite3.Connection, found: list[Alert]) -> list[Alert]:
    """Los avisos cuya clave aún no se ha enviado."""
    sent = {r[0] for r in conn.execute("SELECT key FROM alerts_sent")}
    return [a for a in found if a[0] not in sent]


def mark_sent(conn: sqlite3.Connection, found: list[Alert], now: datetime) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO alerts_sent (key, sent_at) VALUES (?, ?)",
        [(key, iso(now)) for key, _ in found],
    )
    conn.commit()


def alerts_text(found: list[Alert]) -> str:
    return "\n".join(["⚠️ Avisos del tipster", *(line for _, line in found)])

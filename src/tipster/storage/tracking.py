"""Bankroll de papel y seguimiento de picks: stakes, exposición, cierre y liquidación (ADR 012)."""

import json
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

from tipster.storage.db import from_iso, iso


class SqliteBankrollRepository:
    """Libro de movimientos: un depósito inicial y una liquidación por pick (idempotente)."""

    def __init__(self, conn: sqlite3.Connection, clock: Callable[[], datetime]) -> None:
        self._conn = conn
        self._clock = clock

    def balance(self) -> float:
        row = self._conn.execute(
            "SELECT balance_after FROM bankroll_entries ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return float(row[0]) if row else 0.0

    def ensure_initial(self, amount: float) -> None:
        if self._conn.execute("SELECT 1 FROM bankroll_entries LIMIT 1").fetchone():
            return
        self._conn.execute(
            "INSERT INTO bankroll_entries (at, kind, amount, balance_after)"
            " VALUES (?, 'deposito', ?, ?)",
            (iso(self._clock()), amount, amount),
        )
        self._conn.commit()

    def settle(self, pick_id: int, amount: float) -> float:
        """Anota el resultado de un pick; si ya estaba liquidado no cambia nada."""
        if self._conn.execute(
            "SELECT 1 FROM bankroll_entries WHERE pick_id = ?", (pick_id,)
        ).fetchone():
            return self.balance()
        balance = round(self.balance() + amount, 2)
        self._conn.execute(
            "INSERT INTO bankroll_entries (at, kind, amount, balance_after, pick_id)"
            " VALUES (?, 'liquidacion', ?, ?, ?)",
            (iso(self._clock()), amount, balance, pick_id),
        )
        self._conn.commit()
        return balance

    def pnl_between(self, start: datetime, end: datetime) -> float:
        """Resultado de las liquidaciones anotadas en [start, end); el depósito no cuenta."""
        row = self._conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM bankroll_entries WHERE kind = 'liquidacion'"
            " AND julianday(at) >= julianday(?) AND julianday(at) < julianday(?)",
            (iso(start), iso(end)),
        ).fetchone()
        return float(row[0])


@dataclass(frozen=True)
class OpenPick:
    id: int
    event_id: str
    competition_id: str
    home_team: str
    away_team: str
    kickoff: datetime
    market_id: str
    selection: str
    price: float
    stake: float | None


class SqliteTrackingRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def set_stakes(
        self,
        run_id: int,
        stakes: Mapping[int, float],
        reasons: Mapping[int, tuple[str, ...]] | None = None,
    ) -> None:
        """Stake de cada pick de la ejecución, por id de cuota, y sus motivos si cambian."""
        for quote_id, stake in stakes.items():
            self._conn.execute(
                "UPDATE picks SET stake = ? WHERE run_id = ? AND quote_id = ?",
                (stake, run_id, quote_id),
            )
            if reasons is not None and quote_id in reasons:
                self._conn.execute(
                    "UPDATE picks SET reasons_json = ? WHERE run_id = ? AND quote_id = ?",
                    (json.dumps(list(reasons[quote_id]), ensure_ascii=False), run_id, quote_id),
                )
        self._conn.commit()

    def open_picks(self) -> list[OpenPick]:
        rows = self._conn.execute(
            "SELECT p.id, q.event_id, e.competition_id, e.home_team, e.away_team, e.kickoff_utc,"
            " q.market_id, q.selection, q.price, p.stake FROM picks p"
            " JOIN odds_quotes q ON q.id = p.quote_id JOIN events e ON e.id = q.event_id"
            " WHERE p.status = 'abierto' ORDER BY e.kickoff_utc, p.id"
        ).fetchall()
        return [
            OpenPick(
                r["id"],
                r["event_id"],
                r["competition_id"],
                r["home_team"],
                r["away_team"],
                from_iso(r["kickoff_utc"]),
                r["market_id"],
                r["selection"],
                r["price"],
                r["stake"],
            )
            for r in rows
        ]

    def stake_by_open_event(self) -> dict[str, float]:
        """Stake abierto por evento (picks con stake > 0): un evento ya apostado no se repite."""
        rows = self._conn.execute(
            "SELECT q.event_id, SUM(p.stake) FROM picks p JOIN odds_quotes q ON q.id = p.quote_id"
            " WHERE p.status = 'abierto' AND p.stake > 0 GROUP BY q.event_id"
        ).fetchall()
        return {r[0]: float(r[1]) for r in rows}

    def exposure(self, start: datetime, end: datetime) -> float:
        """Suma de stakes abiertos de partidos que empiezan en [start, end)."""
        row = self._conn.execute(
            "SELECT COALESCE(SUM(p.stake), 0) FROM picks p JOIN odds_quotes q ON q.id = p.quote_id"
            " JOIN events e ON e.id = q.event_id WHERE p.status = 'abierto' AND p.stake > 0"
            " AND julianday(e.kickoff_utc) >= julianday(?)"
            " AND julianday(e.kickoff_utc) < julianday(?)",
            (iso(start), iso(end)),
        ).fetchone()
        return float(row[0])

    def set_closing(
        self,
        pick_id: int,
        *,
        closing_odds: float,
        closing_fair_odds: float,
        captured_at: datetime,
        last_update: datetime | None,
        reliable: bool,
        clv: float | None,
    ) -> None:
        self._conn.execute(
            "UPDATE picks SET closing_odds = ?, closing_fair_odds = ?, closing_captured_at = ?,"
            " closing_last_update = ?, closing_reliable = ?, clv = ? WHERE id = ?",
            (
                closing_odds,
                closing_fair_odds,
                iso(captured_at),
                None if last_update is None else iso(last_update),
                int(reliable),
                clv,
                pick_id,
            ),
        )
        self._conn.commit()

    def settle(
        self, pick_id: int, *, result: str, status: str, profit: float | None, settled_at: datetime
    ) -> None:
        self._conn.execute(
            "UPDATE picks SET result = ?, status = ?, profit = ?, settled_at = ? WHERE id = ?",
            (result, status, profit, iso(settled_at), pick_id),
        )
        self._conn.commit()

    def clv_values(self) -> list[tuple[float, float]]:
        """(CLV, stake) de los picks con stake y cierre fiable."""
        rows = self._conn.execute(
            "SELECT clv, stake FROM picks"
            " WHERE closing_reliable = 1 AND clv IS NOT NULL AND stake > 0 ORDER BY id"
        ).fetchall()
        return [(float(r[0]), float(r[1])) for r in rows]

"""Bankroll de papel y seguimiento de picks: stakes, exposición, cierre y liquidación (ADR 012)."""

import json
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

from tipster.storage.db import from_iso, iso


class SqliteBankrollRepository:
    """Libro de movimientos: depósitos, retiros y una liquidación por pick (idempotente).

    El saldo es la suma de los `amount` (con signo); `balance_after` es el saldo acumulado."""

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

    def deposit(self, amount: float) -> float:
        return self._move("deposito", amount)

    def withdraw(self, amount: float) -> float:
        """Retira `amount`; falla si supera el saldo."""
        if amount > self.balance() + 1e-9:
            raise ValueError(
                f"no se puede retirar {amount:.2f}: el bankroll es {self.balance():.2f}"
            )
        return self._move("retiro", -amount)

    def _move(self, kind: str, amount: float) -> float:
        balance = round(self.balance() + amount, 2)
        self._conn.execute(
            "INSERT INTO bankroll_entries (at, kind, amount, balance_after) VALUES (?, ?, ?, ?)",
            (iso(self._clock()), kind, amount, balance),
        )
        self._conn.commit()
        return balance

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
    has_closing: bool = False
    closing_captured_at: datetime | None = None
    taken_price: float | None = None  # cuota real registrada con `tipster take`

    @property
    def effective_price(self) -> float:
        """La cuota a la que se apostó de verdad: la real si se registró, si no la del feed."""
        return self.taken_price or self.price


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
            " q.market_id, q.selection, q.price, p.stake,"
            " p.closing_captured_at IS NOT NULL AS has_closing, p.closing_captured_at,"
            " p.taken_price FROM picks p"
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
                bool(r["has_closing"]),
                None if r["closing_captured_at"] is None else from_iso(r["closing_captured_at"]),
                r["taken_price"],
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
        clv_taken: float | None = None,
    ) -> None:
        self._conn.execute(
            "UPDATE picks SET closing_odds = ?, closing_fair_odds = ?, closing_captured_at = ?,"
            " closing_last_update = ?, closing_reliable = ?, clv = ?, clv_taken = ? WHERE id = ?",
            (
                closing_odds,
                closing_fair_odds,
                iso(captured_at),
                None if last_update is None else iso(last_update),
                int(reliable),
                clv,
                clv_taken,
                pick_id,
            ),
        )
        self._conn.commit()

    def set_taken(self, pick_id: int, *, price: float, bookmaker: str | None, at: datetime) -> bool:
        """Registra la cuota real de un pick abierto con stake. Si ya hay un cierre fiable calcula
        el CLV real al momento. Devuelve False si el pick no existe, no está abierto o no tiene
        stake (no hay nada apostado que registrar)."""
        cur = self._conn.execute(
            "UPDATE picks SET taken_price = ?, taken_bookmaker = ?, taken_at = ?,"
            " clv_taken = CASE WHEN closing_reliable = 1 AND closing_fair_odds IS NOT NULL"
            " THEN ? / closing_fair_odds - 1 END"
            " WHERE id = ? AND status = 'abierto' AND stake > 0",
            (price, bookmaker, iso(at), price, pick_id),
        )
        self._conn.commit()
        return cur.rowcount == 1

    def stake_picks(self) -> list[sqlite3.Row]:
        """Picks abiertos con stake, para `tipster take --list`."""
        return self._conn.execute(
            "SELECT p.id, e.home_team, e.away_team, e.kickoff_utc, q.market_id, q.selection,"
            " q.bookmaker_id, q.price, p.stake, p.taken_price, p.taken_bookmaker"
            " FROM picks p JOIN odds_quotes q ON q.id = p.quote_id"
            " JOIN events e ON e.id = q.event_id"
            " WHERE p.status = 'abierto' AND p.stake > 0 ORDER BY e.kickoff_utc, p.id"
        ).fetchall()

    def clv_taken_values(self) -> list[tuple[float, float, float]]:
        """(CLV real, CLV del feed, stake) de los picks con cuota real y cierre fiable."""
        rows = self._conn.execute(
            "SELECT clv_taken, clv, stake FROM picks WHERE closing_reliable = 1"
            " AND clv_taken IS NOT NULL AND clv IS NOT NULL AND stake > 0 ORDER BY id"
        ).fetchall()
        return [(float(r[0]), float(r[1]), float(r[2])) for r in rows]

    def settle(
        self,
        pick_id: int,
        *,
        result: str | None,
        status: str,
        profit: float | None,
        settled_at: datetime,
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

    def events_by_external(self, provider: str) -> dict[str, str]:
        """id del evento en el proveedor → id canónico."""
        rows = self._conn.execute(
            "SELECT external_id, event_id FROM event_external_ids WHERE provider = ?", (provider,)
        ).fetchall()
        return {r[0]: r[1] for r in rows}


class SqliteBlendConfigRepository:
    """Configuraciones de mezcla elegidas en la validación; `model_version` de un pick es su id."""

    def __init__(self, conn: sqlite3.Connection, clock: Callable[[], datetime]) -> None:
        self._conn = conn
        self._clock = clock

    def save(self, settings: Mapping[str, object]) -> int:
        cursor = self._conn.execute(
            "INSERT INTO blend_configs (created_at, settings_json) VALUES (?, ?)",
            (iso(self._clock()), json.dumps(settings, ensure_ascii=False)),
        )
        self._conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def latest(self) -> tuple[int, dict[str, object]] | None:
        row = self._conn.execute(
            "SELECT id, settings_json FROM blend_configs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return None if row is None else (row[0], json.loads(row[1]))

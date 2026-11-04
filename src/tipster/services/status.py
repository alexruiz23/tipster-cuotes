"""Estado del paper trading de un vistazo (ADR 012): bankroll, picks abiertos, ROI y CLV."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from tipster.storage.db import from_iso
from tipster.storage.tracking import SqliteTrackingRepository
from tipster.tracking.clv import ClvSummary, summarize_clv

MIN_SAMPLE = 50  # picks liquidados con stake para que el ROI diga algo


@dataclass(frozen=True)
class PaperStatus:
    started: datetime | None
    balance: float
    deposits: float
    withdrawals: float
    profit: float  # suma de las liquidaciones
    open_picks: int  # con stake
    open_exposure: float
    won: int
    lost: int
    void: int
    staked_settled: float
    clv: ClvSummary

    @property
    def settled(self) -> int:
        return self.won + self.lost + self.void

    @property
    def roi(self) -> float | None:
        return self.profit / self.staked_settled if self.staked_settled > 0 else None


def paper_status(conn: sqlite3.Connection) -> PaperStatus:
    def one(sql: str) -> tuple[float, ...]:
        return tuple(float(v or 0) for v in conn.execute(sql).fetchone())

    first = conn.execute("SELECT MIN(at) FROM bankroll_entries").fetchone()[0]
    balance, deposits, withdrawals, profit = one(
        "SELECT (SELECT balance_after FROM bankroll_entries ORDER BY id DESC LIMIT 1),"
        " SUM(CASE WHEN kind = 'deposito' THEN amount END),"
        " -SUM(CASE WHEN kind = 'retiro' THEN amount END),"
        " SUM(CASE WHEN kind = 'liquidacion' THEN amount END) FROM bankroll_entries"
    )
    n_open, exposure = one(
        "SELECT COUNT(*), SUM(stake) FROM picks WHERE status = 'abierto' AND stake > 0"
    )
    won, lost, void, staked = one(
        "SELECT SUM(status = 'ganado'), SUM(status = 'perdido'), SUM(status = 'nulo'),"
        " SUM(stake) FROM picks WHERE status != 'abierto' AND stake > 0"
    )
    return PaperStatus(
        started=None if first is None else from_iso(first),
        balance=balance,
        deposits=deposits,
        withdrawals=withdrawals,
        profit=profit,
        open_picks=int(n_open),
        open_exposure=exposure,
        won=int(won),
        lost=int(lost),
        void=int(void),
        staked_settled=staked,
        clv=summarize_clv(SqliteTrackingRepository(conn).clv_values()),
    )

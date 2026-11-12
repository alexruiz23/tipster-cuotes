"""Estado del paper trading de un vistazo (ADR 012): bankroll, picks abiertos, ROI y CLV."""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from tipster.storage.db import from_iso, iso
from tipster.storage.tracking import SqliteTrackingRepository
from tipster.tracking.clv import ClvSummary, summarize_clv

MIN_SAMPLE = 50  # picks liquidados con stake para que el ROI diga algo
MIN_CLV_SAMPLE = 30  # picks con CLV para que su media y su error típico digan algo


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
    staked_settled: float  # sin los nulos: su stake se devuelve
    clv: ClvSummary
    clv_eligible: int = 0  # picks con stake cuyo partido ya empezó (los que deberían tener cierre)
    taken_picks: int = 0  # picks con stake que tienen cuota real registrada
    stake_picks: int = 0  # picks con stake (no nulos)
    clv_taken: ClvSummary | None = None  # CLV con la cuota real
    clv_feed_same: float | None = None  # CLV medio del feed en esos mismos picks

    @property
    def settled(self) -> int:
        return self.won + self.lost + self.void

    @property
    def roi(self) -> float | None:
        return self.profit / self.staked_settled if self.staked_settled > 0 else None


def paper_status(conn: sqlite3.Connection, now: datetime | None = None) -> PaperStatus:
    now = now or datetime.now(UTC)

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
        " SUM(CASE WHEN status != 'nulo' THEN stake END)"
        " FROM picks WHERE status != 'abierto' AND stake > 0"
    )
    eligible = conn.execute(
        "SELECT COUNT(*) FROM picks p JOIN odds_quotes q ON q.id = p.quote_id"
        " JOIN events e ON e.id = q.event_id WHERE p.stake > 0 AND p.status != 'nulo'"
        " AND julianday(e.kickoff_utc) <= julianday(?)",
        (iso(now),),
    ).fetchone()[0]
    taken = SqliteTrackingRepository(conn).clv_taken_values()
    taken_picks, stake_picks = (
        int(v)
        for v in conn.execute(
            "SELECT COALESCE(SUM(taken_price IS NOT NULL), 0), COUNT(*) FROM picks"
            " WHERE stake > 0 AND status != 'nulo'"
        ).fetchone()
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
        clv_eligible=int(eligible),
        taken_picks=taken_picks,
        stake_picks=stake_picks,
        clv_taken=summarize_clv([(c, s) for c, _, s in taken]) if taken else None,
        clv_feed_same=sum(f for _, f, _ in taken) / len(taken) if taken else None,
    )


def status_lines(st: PaperStatus, tz: ZoneInfo) -> list[str]:
    since = "-" if st.started is None else st.started.astimezone(tz).strftime("%Y-%m-%d")
    roi = "-" if st.roi is None else f"{st.roi:+.1%} sobre {st.staked_settled:.2f} € apostados"
    lines = [
        f"PAPER TRADING desde {since}",
        f"Bankroll:   {st.balance:9.2f} €",
        f"  depósitos {st.deposits:.2f} · retiros {st.withdrawals:.2f} · "
        f"profit acumulado {st.profit:+.2f}",
        f"Abiertos:   {st.open_picks} picks con stake · exposición {st.open_exposure:.2f} €",
        f"Liquidados: {st.settled} (ganados {st.won} · perdidos {st.lost} · nulos {st.void})",
        f"ROI:        {roi}",
    ]
    if st.settled < MIN_SAMPLE:
        lines.append(
            f"  Muestra insuficiente: {st.settled} < {MIN_SAMPLE} picks; el ROI aún no dice nada."
        )
    if st.clv.mean is None:
        lines.append("CLV medio:  sin datos de cierre fiable todavía")
    else:
        err = "" if st.clv.stderr is None else f" ± {st.clv.stderr * 100:.2f}"
        positive = "" if st.clv.share_positive is None else f" · {st.clv.share_positive:.0%} > 0"
        lines.append(
            f"CLV medio:  {st.clv.mean * 100:+.2f} %{err} (error típico) en {st.clv.n} picks"
            f"{positive}"
        )
        if st.clv.n < MIN_CLV_SAMPLE:
            lines.append(
                f"  Muestra insuficiente: {st.clv.n} < {MIN_CLV_SAMPLE} picks con CLV; "
                "la media aún no dice nada."
            )
    if st.taken_picks:  # opcional: sin cuotas reales registradas no se dice nada
        lines.append(f"Cuota real registrada: {st.taken_picks} de {st.stake_picks} picks con stake")
    if st.clv_taken is not None and st.clv_taken.mean is not None:
        feed = (
            "" if st.clv_feed_same is None else f" · el feed daba {st.clv_feed_same * 100:+.2f} %"
        )
        lines.append(
            f"CLV real:   {st.clv_taken.mean * 100:+.2f} % en {st.clv_taken.n} picks{feed}"
        )
    if st.clv_eligible:
        lines.append(
            f"Cobertura CLV: {st.clv.n} de {st.clv_eligible} picks con stake ya jugados"
            f" ({st.clv.n / st.clv_eligible:.0%})"
        )
    return lines

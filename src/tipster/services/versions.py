"""Versiones de la estrategia: qué configuración generó cada pick (auditoría del 23/11/2026).

Cada scan guarda en `runs.settings_json` la configuración completa con la que corrió, y cada pick
apunta a su scan: esa es la referencia inmutable. La versión es un hash de las claves que deciden
qué se apuesta y cuánto; las operativas (rutas, caché, ventanas de cierre, backups…) no cuentan.
Una clave nueva en la configuración crea una versión nueva: mejor separar de más que mezclar.

`strategy_logic_version` (config.py) añade la versión de la lógica en Python: los scans anteriores
a que existiera la clave cuentan como lógica 1. `bankroll_initial` no cuenta: solo siembra una base
vacía (`ensure_initial`); el stake sale del saldo real, no de ese parámetro.

El intervalo del CLV es un bootstrap por semanas de partido (tracking/bootstrap.py), igual que en
el backtest; con menos de 4 semanas no se da.
"""

import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from tipster.tracking.bootstrap import MIN_BLOCKS, block_bootstrap_ci

OPERATIONAL = frozenset(
    {
        "backup_dir",
        "backup_keep",
        "bankroll_initial",
        "cache_ttl_seconds",
        "closing_refresh_minutes",
        "closing_window_minutes",
        "db_path",
        "low_credits_alert",
        "max_credits_per_run",
        "min_request_interval_s",
        "raw_dir",
        "shadow_closing",
        "timezone",
    }
)
BASELINE_LOGIC = 1  # la lógica de los scans guardados antes de existir la clave


def strategy_part(snapshot: Mapping[str, object]) -> dict[str, object]:
    part = {k: v for k, v in snapshot.items() if k not in OPERATIONAL}
    part.setdefault("strategy_logic_version", BASELINE_LOGIC)
    return part


def strategy_hash(snapshot: Mapping[str, object]) -> str:
    text = json.dumps(strategy_part(snapshot), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()[:8]


@dataclass
class VersionStats:
    config_hash: str
    first_seen: str  # fecha del primer scan con esta configuración
    config: dict[str, object]
    label: str = ""
    current: bool = False
    changes: list[str] = field(default_factory=list)
    detected: int = 0
    staked: int = 0
    # CLV por semana ISO del partido: con stake y cierre fiable, abierto o no
    clv_weeks: dict[tuple[int, int], list[float]] = field(default_factory=dict)
    taken_weeks: dict[tuple[int, int], list[float]] = field(default_factory=dict)
    settled_stake: float = 0.0
    settled_profit: float = 0.0

    @property
    def clv(self) -> list[float]:
        return [x for week in self.clv_weeks.values() for x in week]

    @property
    def clv_taken(self) -> list[float]:
        return [x for week in self.taken_weeks.values() for x in week]

    @property
    def roi(self) -> float | None:
        return self.settled_profit / self.settled_stake if self.settled_stake > 0 else None


def _diff(old: Mapping[str, object], new: Mapping[str, object]) -> list[str]:
    out = []
    for key in sorted(set(old) | set(new)):
        a, b = old.get(key), new.get(key)
        if a != b:
            out.append(f"{key} {'(nuevo)' if key not in old else a}→{b}")
    return out


def version_stats(conn: sqlite3.Connection, current: Mapping[str, object]) -> list[VersionStats]:
    rows = conn.execute(
        "SELECT r.settings_json, r.started_at, p.stake, p.status, p.profit, p.clv,"
        " p.closing_reliable, p.clv_taken, e.kickoff_utc FROM picks p"
        " JOIN runs r ON r.id = p.run_id JOIN odds_quotes q ON q.id = p.quote_id"
        " JOIN events e ON e.id = q.event_id ORDER BY r.started_at, p.id"
    ).fetchall()
    versions: dict[str, VersionStats] = {}
    for settings_json, started, stake, status, profit, clv, reliable, clv_taken, kickoff in rows:
        snapshot = json.loads(settings_json)
        key = strategy_hash(snapshot)
        v = versions.setdefault(key, VersionStats(key, started[:10], strategy_part(snapshot)))
        v.detected += 1
        if not stake:
            continue
        v.staked += 1
        if reliable == 1 and clv is not None:
            iso = datetime.fromisoformat(kickoff).isocalendar()
            week = (iso.year, iso.week)
            v.clv_weeks.setdefault(week, []).append(float(clv))
            if clv_taken is not None:
                v.taken_weeks.setdefault(week, []).append(float(clv_taken))
        if status in ("ganado", "perdido") and profit is not None:
            v.settled_stake += float(stake)
            v.settled_profit += float(profit)
    current_hash = strategy_hash(current)
    ordered = list(versions.values())
    previous: Mapping[str, object] | None = None
    for i, v in enumerate(ordered, start=1):
        v.label = f"v{i}"
        v.current = v.config_hash == current_hash
        v.changes = [] if previous is None else _diff(previous, v.config)
        previous = v.config
    return ordered


def _clv_text(weeks: Mapping[tuple[int, int], Sequence[float]]) -> str:
    values = [x for week in weeks.values() for x in week]
    if not values:
        return "sin CLV todavía"
    mean = sum(values) / len(values)
    positive = sum(x > 0 for x in values)
    ci = block_bootstrap_ci(list(weeks.values()))
    interval = (
        f"IC 95 % por semanas: muestra insuficiente ({len(weeks)} < {MIN_BLOCKS} semanas)"
        if ci is None
        else f"IC 95 % por semanas [{ci[0] * 100:+.1f}, {ci[1] * 100:+.1f}]"
    )
    return (
        f"CLV {mean * 100:+.1f} % en {len(values)} ({positive} > 0, {len(values) - positive} ≤ 0)"
        f" · {interval}"
    )


def version_lines(
    conn: sqlite3.Connection, current: Mapping[str, object], max_changes: int = 4
) -> list[str]:
    versions = version_stats(conn, current)
    lines = ["", "Versiones de la estrategia (configuración guardada en cada scan):"]
    for v in versions:
        roi = "" if v.roi is None else f" · ROI {v.roi * 100:+.0f} %"
        tag = " (vigente)" if v.current else ""
        lines.append(
            f"  {v.label}{tag} desde {v.first_seen} [{v.config_hash}]: {v.detected} detectados · "
            f"{v.staked} con stake · {_clv_text(v.clv_weeks)}{roi}"
        )
        if v.changes:
            shown = v.changes[:max_changes]
            more = f" (+{len(v.changes) - max_changes} más)" if len(v.changes) > max_changes else ""
            lines.append(f"    cambia: {'; '.join(shown)}{more}")
    live = next((v for v in versions if v.current), None)
    if live is None:
        lines.append("Estrategia vigente: aún no ha generado ningún pick.")
        return lines
    lines.append(
        f"Estrategia vigente ({live.label}): {live.detected} detectados · {live.staked} con stake"
        f" · {len(live.clv)} con cierre fiable · {_clv_text(live.clv_weeks)}"
    )
    if live.clv_taken:
        lines.append(f"  con cuota real: {_clv_text(live.taken_weeks)}")
    return lines


def shadow_lines(conn: sqlite3.Connection, current: Mapping[str, object]) -> list[str]:
    """CLV de los VALUE SIN stake de la estrategia vigente, por motivo de descarte (BACKLOG 60).

    Responde a «¿las reglas descartan valor real?» sin apostar nada. Si un mismo pronóstico se
    detectó en varios scans, cuenta una vez, con el motivo del último."""
    from tipster.services.notify import discard_label  # noqa: PLC0415 (evita import circular)

    current_hash = strategy_hash(current)
    rows = conn.execute(
        "SELECT r.settings_json, p.reasons_json, p.clv, q.event_id, q.market_id, q.selection"
        " FROM picks p JOIN runs r ON r.id = p.run_id JOIN odds_quotes q ON q.id = p.quote_id"
        " WHERE p.label = 'VALUE' AND (p.stake IS NULL OR p.stake = 0)"
        " AND p.closing_reliable = 1 AND p.clv IS NOT NULL ORDER BY p.id"
    ).fetchall()
    latest: dict[tuple[str, str, str], tuple[str, float]] = {}
    for settings_json, reasons_json, clv, event, market, selection in rows:
        if strategy_hash(json.loads(settings_json)) != current_hash:
            continue
        reason = (json.loads(reasons_json) or [""])[-1]
        latest[(event, market, selection)] = (discard_label(reason), float(clv))
    if not latest:
        return ["Descartes (sombra, sin stake): aún sin cierres capturados."]
    by_reason: dict[str, list[float]] = {}
    for label, value in latest.values():
        by_reason.setdefault(label, []).append(value)
    lines = [f"Descartes (sombra, sin stake) de la vigente: {len(latest)} con cierre"]
    for label, values in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
        mean = sum(values) / len(values)
        positive = sum(v > 0 for v in values)
        lines.append(f"  {label}: CLV {mean * 100:+.1f} % en {len(values)} ({positive} > 0)")
    return lines

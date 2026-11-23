"""Versiones de la estrategia: qué configuración generó cada pick (auditoría del 23/11/2026).

Cada scan guarda en `runs.settings_json` la configuración completa con la que corrió, y cada pick
apunta a su scan: esa es la referencia inmutable. La versión es un hash de las claves que deciden
qué se apuesta y cuánto; las operativas (rutas, caché, ventanas de cierre, backups…) no cuentan.
Una clave nueva en la configuración crea una versión nueva: mejor separar de más que mezclar.
"""

import hashlib
import json
import math
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

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
        "timezone",
    }
)
Z95 = 1.96


def strategy_part(snapshot: Mapping[str, object]) -> dict[str, object]:
    return {k: v for k, v in snapshot.items() if k not in OPERATIONAL}


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
    clv: list[float] = field(default_factory=list)  # con stake y cierre fiable, abierto o no
    clv_taken: list[float] = field(default_factory=list)
    settled_stake: float = 0.0
    settled_profit: float = 0.0

    @property
    def roi(self) -> float | None:
        return self.settled_profit / self.settled_stake if self.settled_stake > 0 else None


def _mean_ci(values: Sequence[float]) -> tuple[float, float, float] | None:
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    se = math.sqrt(sum((x - mean) ** 2 for x in values) / (n - 1) / n)
    return mean, mean - Z95 * se, mean + Z95 * se


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
        " p.closing_reliable, p.clv_taken FROM picks p JOIN runs r ON r.id = p.run_id"
        " ORDER BY r.started_at, p.id"
    ).fetchall()
    versions: dict[str, VersionStats] = {}
    for settings_json, started, stake, status, profit, clv, reliable, clv_taken in rows:
        snapshot = json.loads(settings_json)
        key = strategy_hash(snapshot)
        v = versions.setdefault(key, VersionStats(key, started[:10], strategy_part(snapshot)))
        v.detected += 1
        if not stake:
            continue
        v.staked += 1
        if reliable == 1 and clv is not None:
            v.clv.append(float(clv))
            if clv_taken is not None:
                v.clv_taken.append(float(clv_taken))
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


def _clv_text(values: Sequence[float]) -> str:
    if not values:
        return "sin CLV todavía"
    stats = _mean_ci(values)
    if stats is None:
        return f"CLV {values[0] * 100:+.1f} % (1 pick)"
    mean, lo, hi = stats
    positive = sum(x > 0 for x in values)
    return (
        f"CLV {mean * 100:+.1f} % [IC 95 % {lo * 100:+.1f}, {hi * 100:+.1f}] en {len(values)} "
        f"({positive} > 0, {len(values) - positive} ≤ 0)"
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
            f"{v.staked} con stake · {_clv_text(v.clv)}{roi}"
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
        f" · {len(live.clv)} con cierre fiable · {_clv_text(live.clv)}"
    )
    if live.clv_taken:
        lines.append(f"  con cuota real: {_clv_text(live.clv_taken)}")
    return lines

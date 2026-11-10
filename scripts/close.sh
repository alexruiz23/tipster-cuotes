#!/bin/bash
# Captura el cierre de Pinnacle (BACKLOG 32). Pensado para dispararse cada 5 min.
# Antes de llamar a Python mira la base local: sin picks con stake que empiecen en la ventana,
# no ejecuta nada (0 créditos y sin filas en `runs`). Con alguno, `tipster close` pide solo las
# competiciones afectadas (1 crédito por mercado y competición).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PATH="/usr/bin:/bin"
DB="${TIPSTER_DB_PATH:-data/tipster.sqlite}"
WINDOW="${TIPSTER_CLOSING_WINDOW_MINUTES:-15}"
REFRESH="${TIPSTER_CLOSING_REFRESH_MINUTES:-5}"

# Cierres perdidos: pick con stake cuyo partido empezó hace más de 5 min sin CLV y sin avisar. Es una
# comprobación local (0 créditos); solo si hay alguno se lanza `notify --alerts`.
missed=$(sqlite3 "$DB" "
  SELECT COUNT(*) FROM picks p JOIN odds_quotes q ON q.id = p.quote_id JOIN events e ON e.id = q.event_id
  WHERE p.stake > 0 AND p.status <> 'nulo' AND p.clv IS NULL
    AND e.kickoff_utc <= strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now', '-5 minutes')
    AND e.kickoff_utc >= strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now', '-3 days')
    AND NOT EXISTS (SELECT 1 FROM alerts_sent a WHERE a.key = 'sin-clv:' || p.id)" 2>/dev/null) || missed=0
if [ "${missed:-0}" -gt 0 ]; then
  mkdir -p data/logs
  PYTHONPATH="$ROOT/src" "$ROOT/.venv/bin/python" -m tipster notify --alerts >>data/logs/notify.log 2>&1 || true
fi

due=$(sqlite3 "$DB" "
  SELECT COUNT(*) FROM picks p JOIN odds_quotes q ON q.id = p.quote_id JOIN events e ON e.id = q.event_id
  WHERE p.status = 'abierto' AND p.stake > 0
    AND (p.closing_captured_at IS NULL
         OR (julianday(e.kickoff_utc) - julianday(p.closing_captured_at)) * 1440 > $REFRESH)
    AND e.kickoff_utc >= strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')
    AND e.kickoff_utc <= strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now', '+$WINDOW minutes')")
[ "$due" -gt 0 ] || exit 0

mkdir -p data/logs
{
  echo "== $(date -u +%FT%TZ) close ($due picks en ventana)"
  # PYTHONPATH: macOS marca como oculto el .pth editable del .venv y Python 3.12 lo ignora
  PYTHONPATH="$ROOT/src" "$ROOT/.venv/bin/python" -m tipster close
} >>data/logs/close.log 2>&1

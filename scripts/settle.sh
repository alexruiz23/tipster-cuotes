#!/bin/bash
# Liquida los picks terminados (BACKLOG 32). Una vez al día: /scores solo llega a 3 días atrás.
# Sin picks abiertos con inicio entre hace 3 días y hace 2 h no llama a la API; los más viejos
# quedan fuera de /scores y se liquidan a mano (`tipster settle --result EVENTO=GL-GV`).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PATH="/usr/bin:/bin"
DB="${TIPSTER_DB_PATH:-data/tipster.sqlite}"

todo=$(sqlite3 "$DB" "
  SELECT COUNT(*) FROM picks p JOIN odds_quotes q ON q.id = p.quote_id JOIN events e ON e.id = q.event_id
  WHERE p.status = 'abierto'
    AND e.kickoff_utc <= strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now', '-2 hours')
    AND e.kickoff_utc >= strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now', '-3 days')")
[ "$todo" -gt 0 ] || exit 0

mkdir -p data/logs
{
  echo "== $(date -u +%FT%TZ) settle ($todo picks por liquidar)"
  PYTHONPATH="$ROOT/src" "$ROOT/.venv/bin/python" -m tipster settle
} >>data/logs/settle.log 2>&1
# Aviso por Telegram: opcional, nunca hace fallar el cron
PYTHONPATH="$ROOT/src" "$ROOT/.venv/bin/python" -m tipster notify --settle >>data/logs/notify.log 2>&1 || true

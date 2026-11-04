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

due=$(sqlite3 "$DB" "
  SELECT COUNT(*) FROM picks p JOIN odds_quotes q ON q.id = p.quote_id JOIN events e ON e.id = q.event_id
  WHERE p.status = 'abierto' AND p.stake > 0 AND p.closing_captured_at IS NULL
    AND e.kickoff_utc >= strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')
    AND e.kickoff_utc <= strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now', '+$WINDOW minutes')")
[ "$due" -gt 0 ] || exit 0

mkdir -p data/logs
{
  echo "== $(date -u +%FT%TZ) close ($due picks en ventana)"
  # PYTHONPATH: macOS marca como oculto el .pth editable del .venv y Python 3.12 lo ignora
  PYTHONPATH="$ROOT/src" "$ROOT/.venv/bin/python" -m tipster close
} >>data/logs/close.log 2>&1

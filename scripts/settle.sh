#!/bin/bash
# Liquida los picks terminados (BACKLOG 32). Una vez al día: /scores solo llega a 3 días atrás.
# Sin picks abiertos con inicio entre hace 3 días y hace 2 h no llama a la API; los más viejos
# quedan fuera de /scores y se liquidan a mano (`tipster settle --result EVENTO=GL-GV`, o
# `--void EVENTO` si el partido se aplazó).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PATH="/usr/bin:/bin"
DB="${TIPSTER_DB_PATH:-data/tipster.sqlite}"
mkdir -p data/logs
PY=(env PYTHONPATH="$ROOT/src" "$ROOT/.venv/bin/python" -m tipster)

# Copia diaria de la base (BACKLOG 40): un fallo se queda en el log y no para el cron.
"${PY[@]}" backup >>data/logs/backup.log 2>&1 || true

todo=$(sqlite3 "$DB" "
  SELECT COUNT(*) FROM picks p JOIN odds_quotes q ON q.id = p.quote_id JOIN events e ON e.id = q.event_id
  WHERE p.status = 'abierto'
    AND e.kickoff_utc <= strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now', '-2 hours')
    AND e.kickoff_utc >= strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now', '-3 days')")
if [ "$todo" -gt 0 ]; then
  {
    echo "== $(date -u +%FT%TZ) settle ($todo picks por liquidar)"
    "${PY[@]}" settle
  } >>data/logs/settle.log 2>&1 || true
  # Aviso por Telegram: opcional, nunca hace fallar el cron
  "${PY[@]}" notify --settle >>data/logs/notify.log 2>&1 || true
fi
# Fallos nuevos (cierres perdidos, errores, scan parado, pocos créditos): solo avisa de lo no avisado
"${PY[@]}" notify --alerts >>data/logs/notify.log 2>&1 || true

#!/bin/bash
# Busca picks nuevos (BACKLOG 32). Pensado para los viernes a las 12:00: ~14 créditos por scan
# completo; `max_credits_per_run` (30) corta el gasto de una ejecución.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PATH="/usr/bin:/bin"
mkdir -p data/logs
PY=(env PYTHONPATH="$ROOT/src" "$ROOT/.venv/bin/python" -m tipster)
# Copia de la base antes de tocarla (BACKLOG 40). Un fallo se queda en el log y no para el cron.
"${PY[@]}" backup >>data/logs/backup.log 2>&1 || true
rc=0
{
  echo "== $(date -u +%FT%TZ) scan"
  "${PY[@]}" scan
} >>data/logs/scan.log 2>&1 || rc=$?
# Avisos por Telegram: opcionales, nunca hacen fallar el cron (sin token solo dejan un aviso en el
# log). Se envían aunque el scan haya fallado: `--alerts` avisa de la ejecución en error.
"${PY[@]}" notify --picks >>data/logs/notify.log 2>&1 || true
"${PY[@]}" notify --alerts >>data/logs/notify.log 2>&1 || true
exit "$rc"

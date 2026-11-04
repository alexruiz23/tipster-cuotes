#!/bin/bash
# Busca picks nuevos (BACKLOG 32). Pensado para los viernes a las 12:00: ~14 créditos por scan
# completo; `max_credits_per_run` (30) corta el gasto de una ejecución.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PATH="/usr/bin:/bin"
mkdir -p data/logs
{
  echo "== $(date -u +%FT%TZ) scan"
  PYTHONPATH="$ROOT/src" "$ROOT/.venv/bin/python" -m tipster scan
} >>data/logs/scan.log 2>&1

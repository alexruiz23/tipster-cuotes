#!/bin/bash
# Instala (o con `desinstalar`, retira) los agentes launchd de `close` y `settle`.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
UID_="$(id -u)"
mkdir -p "$AGENTS" "$ROOT/data/logs"
for name in close settle; do
  label="com.tipster.$name"
  plist="$AGENTS/$label.plist"
  launchctl bootout "gui/$UID_/$label" 2>/dev/null || true
  if [ "${1:-}" = "desinstalar" ]; then rm -f "$plist"; echo "retirado $label"; continue; fi
  sed "s|__ROOT__|$ROOT|g" "$ROOT/scripts/launchd/$label.plist" >"$plist"
  launchctl bootstrap "gui/$UID_" "$plist"
  echo "instalado $label"
done

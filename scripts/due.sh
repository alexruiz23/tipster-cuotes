#!/bin/bash
# ¿Toca ejecutar este trabajo ahora? Código 0 = sí, 1 = no. Lo usa cron.yml (ADR 013) para no instalar
# dependencias en los disparos ociosos; solo shell y el CLI sqlite3. Con FORCE=<trabajo> (disparo manual) siempre toca.
# Las comprobaciones de settle y close repiten las de settle.sh y close.sh: mantenerlas en sincronía.
set -euo pipefail
cd "$(dirname "$0")/.."
DB="${TIPSTER_DB_PATH:-data/tipster.sqlite}"
WINDOW="${TIPSTER_CLOSING_WINDOW_MINUTES:-15}"
REFRESH="${TIPSTER_CLOSING_REFRESH_MINUTES:-5}"
job="${1:?uso: due.sh scan|settle|close}"
[ "${FORCE:-}" = "$job" ] && exit 0

q() { sqlite3 "$DB" "$1"; }
mad_dow="$(TZ=Europe/Madrid date +%u)" # 1 = lunes … 7 = domingo
mad_h=$((10#$(TZ=Europe/Madrid date +%H)))
today="$(date -u +%F)" # runs.started_at está en UTC
ran_today() { [ "$(q "SELECT COUNT(*) FROM runs WHERE command = '$1' AND started_at >= '${today}T00:00:00'")" -gt 0 ]; }

case "$job" in
  scan) # martes y viernes desde las 12:00 de Madrid, una vez al día
    { [ "$mad_dow" = 2 ] || [ "$mad_dow" = 5 ]; } && [ "$mad_h" -ge 12 ] && [ "$mad_h" -lt 15 ] && ! ran_today scan
    ;;
  settle) # entre las 04:00 y las 07:00 de Madrid, una vez al día, y solo con picks por liquidar
    [ "$mad_h" -ge 4 ] && [ "$mad_h" -lt 8 ] && ! ran_today settle && [ "$(q "
      SELECT COUNT(*) FROM picks p JOIN odds_quotes q ON q.id = p.quote_id JOIN events e ON e.id = q.event_id
      WHERE p.status = 'abierto'
        AND e.kickoff_utc <= strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now', '-2 hours')
        AND e.kickoff_utc >= strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now', '-3 days')")" -gt 0 ]
    ;;
  close) # captura pendiente en la ventana, o cierre perdido sin avisar (como close.sh)
    due="$(q "
      SELECT COUNT(*) FROM picks p JOIN odds_quotes q ON q.id = p.quote_id JOIN events e ON e.id = q.event_id
      WHERE p.status = 'abierto' AND p.stake > 0
        AND (p.closing_captured_at IS NULL
             OR (julianday(e.kickoff_utc) - julianday(p.closing_captured_at)) * 1440 > $REFRESH)
        AND e.kickoff_utc >= strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')
        AND e.kickoff_utc <= strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now', '+$WINDOW minutes')")"
    missed="$(q "
      SELECT COUNT(*) FROM picks p JOIN odds_quotes q ON q.id = p.quote_id JOIN events e ON e.id = q.event_id
      WHERE p.stake > 0 AND p.status <> 'nulo' AND p.clv IS NULL
        AND e.kickoff_utc <= strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now', '-5 minutes')
        AND e.kickoff_utc >= strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now', '-3 days')
        AND NOT EXISTS (SELECT 1 FROM alerts_sent a WHERE a.key = 'sin-clv:' || p.id)")"
    [ "$due" -gt 0 ] || [ "$missed" -gt 0 ]
    ;;
  *) echo "uso: due.sh scan|settle|close" >&2; exit 2 ;;
esac

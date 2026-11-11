#!/bin/bash
# Descarga (pull) y sube (push) la base SQLite a Cloudflare R2 (ADR 013). Lo usan el workflow cron.yml y,
# desde el Mac, cualquier comando que escriba: `r2.sh pull`, el comando, `r2.sh push`.
# Variables: R2_BUCKET, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION=auto y
# AWS_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com. R2_BOOTSTRAP=1 permite crear la base si no existe.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${R2_BUCKET:?falta R2_BUCKET}"
KEY=tipster.sqlite
DB="${TIPSTER_DB_PATH:-data/tipster.sqlite}"
S="$(dirname "$DB")/.r2" # estado entre pull y push: .etag, .sha, .counts, .err
s3api() { aws s3api "$1" --bucket "$R2_BUCKET" "${@:2}"; } # s3api <subcomando> [opciones]

counts() { sqlite3 -separator ' ' "$DB" 'SELECT (SELECT COUNT(*) FROM picks), (SELECT COUNT(*) FROM bankroll_entries)'; }
healthy() { [ "$(sqlite3 "$DB" 'PRAGMA integrity_check')" = ok ]; }

pull() {
  mkdir -p "$(dirname "$DB")"
  rm -f "$S".*
  if s3api get-object --key "$KEY" "$DB" --query ETag --output text >"$S.etag" 2>"$S.err"; then
    healthy || { echo "::error::La base descargada de R2 no pasa integrity_check"; exit 1; }
    sha256sum "$DB" 2>/dev/null | cut -d' ' -f1 >"$S.sha" || shasum -a 256 "$DB" | cut -d' ' -f1 >"$S.sha"
    counts >"$S.counts"
    echo "R2 -> $DB ($(cut -d' ' -f1 "$S.counts") picks, $(cut -d' ' -f2 "$S.counts") movimientos de bankroll)"
  elif grep -qE 'NoSuchKey|Not Found|404' "$S.err" && [ "${R2_BOOTSTRAP:-0}" = 1 ]; then
    : >"$S.etag" # la primera subida será «solo si sigue sin existir»
    echo "R2 no tiene $KEY: se creará una base nueva (bootstrap)"
  else
    # cualquier otro fallo (403, red, bucket mal escrito) para: nunca se crea una base en blanco
    cat "$S.err" >&2
    echo "::error::No se pudo leer $KEY de R2. Si es la primera vez, siembra la base (ADR 013) o lanza con bootstrap"
    exit 1
  fi
}

push() {
  [ -f "$DB" ] || { echo "sin base local: nada que subir"; exit 0; }
  healthy || { echo "::error::La base local no pasa integrity_check: no se sube"; exit 1; }
  local now
  now="$(sha256sum "$DB" 2>/dev/null | cut -d' ' -f1 || shasum -a 256 "$DB" | cut -d' ' -f1)"
  if [ "$now" = "$(cat "$S.sha" 2>/dev/null || true)" ]; then echo "base sin cambios: no se sube"; exit 0; fi
  # la base nunca puede encoger: protege contra subir una base vacía o truncada
  local picks bank picks0 bank0
  read -r picks bank < <(counts)
  read -r picks0 bank0 < <(cat "$S.counts" 2>/dev/null || echo "0 0")
  if [ "$picks" -lt "$picks0" ] || [ "$bank" -lt "$bank0" ]; then
    echo "::error::La base local tiene menos filas que la descargada (picks $picks<$picks0 o bankroll $bank<$bank0): no se sube"
    exit 1
  fi
  local etag cond
  etag="$(cat "$S.etag" 2>/dev/null || true)"
  if [ -n "$etag" ]; then
    # primera copia del día = estado anterior a los cambios del día (caduca por regla de ciclo de vida)
    local day="backups/tipster-$(date -u +%F).sqlite"
    s3api head-object --key "$day" >/dev/null 2>&1 ||
      s3api copy-object --copy-source "$R2_BUCKET/$KEY" --key "$day" >/dev/null
    cond=(--if-match "$etag") # solo si nadie la cambió desde el pull
  else
    cond=(--if-none-match '*') # bootstrap: solo si sigue sin existir
  fi
  if ! s3api put-object --key "$KEY" --body "$DB" "${cond[@]}" >/dev/null 2>"$S.err"; then
    cat "$S.err" >&2
    local spare="conflictos/tipster-$(date -u +%FT%H%M%S)-${GITHUB_RUN_ID:-local}.sqlite"
    s3api put-object --key "$spare" --body "$DB" >/dev/null
    echo "::error::R2 cambió durante la ejecución o rechazó la subida. Mi copia está en $spare; reconcilia a mano"
    exit 1
  fi
  echo "$DB -> R2 ($picks picks, $bank movimientos de bankroll)"
}

case "${1:-}" in
  pull) pull ;;
  push) push ;;
  *) echo "uso: r2.sh pull|push" >&2; exit 2 ;;
esac

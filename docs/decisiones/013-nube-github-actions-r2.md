# 013 — Ejecución en la nube: GitHub Actions + SQLite en Cloudflare R2

**Estado:** Aceptada e implementada (2026-11-11); el corte desde el Mac está pendiente · **Fecha:** 2026-11-11

Quita la dependencia del Mac: `scan`, `close` y `settle` pasan a ejecutarse en GitHub Actions. La base sigue siendo un
fichero SQLite, guardado en un bucket de Cloudflare R2 (compatible con S3). Cada ejecución lo descarga, trabaja con
`sqlite3` estándar y lo vuelve a subir. Implementado en `scripts/r2.sh`, `scripts/due.sh` y `.github/workflows/cron.yml`.
Retoma el BACKLOG nº 33 y [reemplaza la propuesta inicial (Turso)](#alternativas-descartadas).

## Contexto

- Hoy tres agentes launchd (`close` cada 5 min, `settle` 04:00, `scan` martes y viernes 12:00) escriben en
  `data/tipster.sqlite` (4,5 MB). Solo funcionan con el Mac despierto (BACKLOG 32).
- Un runner de Actions nace sin disco, y la base no puede ir a git (`.gitignore`; términos del proveedor de cuotas).
- Decisión del usuario (2026-11-11): no tocar la capa de datos (`storage/sqlite.py`) ni añadir dependencias de Python.
- Los scripts actuales (`scripts/scan.sh`, `settle.sh`, `close.sh`) ya hacen sus comprobaciones previas con el CLI
  `sqlite3` y llaman a `.venv/bin/python -m tipster …`: sirven tal cual en el runner.

## Decisión

1. **La base vive en R2** como un único objeto, `tipster.sqlite`, en un bucket privado. Credenciales y claves, solo
   como Secrets de GitHub.
2. **Un solo workflow, `cron.yml`, con una sola cola** (`concurrency: tipster-db`, sin cancelar el que está en curso).
   GitHub guarda **una única** ejecución pendiente por grupo y la sustituye por la siguiente; por eso el workflow es
   **«por nivel»**: en cada disparo decide qué toca ahora mirando la base (no mira qué cron lo lanzó). Si un disparo
   se pierde, se retrasa o lo sustituyen en la cola, el siguiente hace lo mismo y no se pierde ningún trabajo.
3. **Dos scripts de shell nuevos** (sin Python): `scripts/r2.sh pull|push` (descarga y subida seguras) y
   `scripts/due.sh scan|settle|close` (¿toca ahora?). Sirven igual desde el Mac para operar sobre la base de la nube.
4. **Repositorio privado** (decisión del usuario) para no exponer picks ni cuotas en los registros de Actions.
5. **El Mac deja de escribir.** Antes del corte se retiran los agentes launchd; la base local queda como copia.
   Los comandos que escriben (`take`, `bankroll deposit/withdraw`, `settle --result/--void`) se ejecutan con
   `r2.sh pull` → comando → `r2.sh push`, nunca contra la base local vieja.

## `scripts/r2.sh` (lógica y comandos)

Variables: `R2_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION=auto`,
`AWS_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com` y, por precaución con el AWS CLI reciente,
`AWS_REQUEST_CHECKSUM_CALCULATION=when_required` y `AWS_RESPONSE_CHECKSUM_VALIDATION=when_required`.
Se usa `aws s3api` (no `aws s3 cp`) para controlar el ETag y evitar subidas multiparte.

**pull**
```bash
mkdir -p data
if aws s3api get-object --bucket "$R2_BUCKET" --key tipster.sqlite data/tipster.sqlite \
     --query ETag --output text >data/.r2-etag 2>data/.r2-err; then
  sqlite3 data/tipster.sqlite 'PRAGMA integrity_check' | grep -qx ok          # base descargada sana
  sha256sum data/tipster.sqlite | cut -d' ' -f1 >data/.r2-sha                  # huella antes de trabajar
  sqlite3 -separator ' ' data/tipster.sqlite \
    'SELECT (SELECT COUNT(*) FROM picks), (SELECT COUNT(*) FROM bankroll_entries)' >data/.r2-counts
elif grep -qE 'NoSuchKey|404' data/.r2-err && [ "${R2_BOOTSTRAP:-0}" = 1 ]; then
  : >data/.r2-etag                      # no existe y se pidió crearla: la primera subida será «solo si no existe»
else
  cat data/.r2-err; exit 1              # cualquier otro fallo (403, red, bucket mal escrito) PARA, nunca crea una base en blanco
fi
```

**push**
```bash
[ -f data/tipster.sqlite ] || exit 0
sqlite3 data/tipster.sqlite 'PRAGMA integrity_check' | grep -qx ok
[ "$(sha256sum data/tipster.sqlite | cut -d' ' -f1)" != "$(cat data/.r2-sha 2>/dev/null)" ] \
  || { echo "base sin cambios: no se sube"; exit 0; }                          # los disparos ociosos no suben nada
# la base nunca puede encoger (protege contra subir una base vacía o truncada)
read -r picks bank < <(sqlite3 -separator ' ' data/tipster.sqlite \
  'SELECT (SELECT COUNT(*) FROM picks), (SELECT COUNT(*) FROM bankroll_entries)')
read -r picks0 bank0 < <(cat data/.r2-counts 2>/dev/null || echo "0 0")
[ "$picks" -ge "$picks0" ] && [ "$bank" -ge "$bank0" ]
etag="$(cat data/.r2-etag)"
if [ -n "$etag" ]; then
  day="backups/tipster-$(date -u +%F).sqlite"                                  # primera copia del día = estado anterior
  aws s3api head-object --bucket "$R2_BUCKET" --key "$day" >/dev/null 2>&1 || \
    aws s3api copy-object --bucket "$R2_BUCKET" --copy-source "$R2_BUCKET/tipster.sqlite" --key "$day" >/dev/null
  cond=(--if-match "$etag")                                                    # solo si nadie la cambió desde el pull
else
  cond=(--if-none-match '*')                                                   # bootstrap: solo si sigue sin existir
fi
if ! aws s3api put-object --bucket "$R2_BUCKET" --key tipster.sqlite --body data/tipster.sqlite "${cond[@]}" >/dev/null; then
  aws s3api put-object --bucket "$R2_BUCKET" --key "conflictos/tipster-$(date -u +%FT%H%M%S)-${GITHUB_RUN_ID:-local}.sqlite" \
    --body data/tipster.sqlite >/dev/null
  echo "::error::R2 cambió durante la ejecución (412). Mi copia está en conflictos/; reconcilia a mano"; exit 1
fi
```

R2 evalúa `If-Match`/`If-None-Match` en `PutObject` de forma atómica
([documentación de compatibilidad S3 de R2](https://developers.cloudflare.com/r2/api/s3/api/)), así que incluso con
una ejecución manual desde el Mac a la vez nadie pisa a nadie. **A verificar en la primera ejecución:** que el AWS CLI
del runner tiene `--if-match` en `put-object` (`aws s3api put-object help | grep if-match`) y que `sqlite3` y `jq`
están instalados (lo normal en `ubuntu-24.04`). Si el CLI no tiene las opciones condicionales, el plan es actualizarlo
o usar `boto3` en un script aparte; no se cambia el diseño.

Cuenta de R2: bucket **privado** (sin acceso público), token de API con permiso *Object Read & Write* limitado a ese
bucket (nunca de administrador), y reglas de ciclo de vida: `backups/` caduca a los 14 días y `conflictos/` a los 30.

## `scripts/due.sh` (lógica)

`due.sh <scan|settle|close>` termina con 0 si toca ejecutar ese trabajo ahora. Si `FORCE=<trabajo>` (viene del
disparo manual), devuelve 0 sin más. Los límites horarios usan Madrid (`TZ=Europe/Madrid date`), y «hoy» es el día UTC
(`runs.started_at` está en UTC):

- **scan:** martes o viernes, hora de Madrid entre 12 y 14, y ningún `runs` con `command='scan'` desde las 00:00 UTC de hoy.
- **settle:** hora de Madrid entre 4 y 7, ningún `settle` hoy, y alguna de las comprobaciones de `settle.sh`
  (hay picks abiertos con inicio entre hace 3 días y hace 2 h).
- **close:** la comprobación de `close.sh` (picks con stake que empiezan dentro de la ventana y necesitan captura).

`close.sh` y `settle.sh` pasan a llamar a `due.sh` para esa comprobación (se mueve el SQL, no se duplica).

## `.github/workflows/cron.yml` (diseño)

Los cron de Actions van en **UTC**. Las franjas salen de los inicios reales de los partidos en la base (viernes y
lunes 19–20 UTC; martes y miércoles 17–20; sábado 12–20; domingo 11–20; jueves ninguno).

```yaml
name: Cron
on:
  schedule:
    - cron: "0 10-12 * * 2,5"       # scan: martes y viernes; due.sh espera a las 12:00 de Madrid (invierno y verano)
    - cron: "0 3-5 * * *"           # settle: tres intentos; solo corre el primero que encuentre trabajo
    - cron: "*/15 11-22 * * 0,2,3,5,6" # close: martes, miércoles, viernes, sábado y domingo, 11:00-22:45 UTC
  workflow_dispatch:
    inputs:
      accion:
        description: "Forzar un trabajo (auto = decide solo)"
        type: choice
        options: [auto, scan, settle, close, status]
        default: auto
      bootstrap:
        description: "Crear la base en R2 si no existe (solo la primera vez)"
        type: boolean
        default: false

permissions:
  contents: read

concurrency:
  group: tipster-db
  cancel-in-progress: false

jobs:
  tick:
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    env:
      R2_BUCKET: ${{ secrets.R2_BUCKET_NAME }}
      R2_BOOTSTRAP: ${{ inputs.bootstrap && '1' || '0' }}
      AWS_ACCESS_KEY_ID: ${{ secrets.R2_ACCESS_KEY_ID }}
      AWS_SECRET_ACCESS_KEY: ${{ secrets.R2_SECRET_ACCESS_KEY }}
      AWS_DEFAULT_REGION: auto
      AWS_ENDPOINT_URL: https://${{ secrets.R2_ACCOUNT_ID }}.r2.cloudflarestorage.com
      AWS_REQUEST_CHECKSUM_CALCULATION: when_required
      AWS_RESPONSE_CHECKSUM_VALIDATION: when_required
      FORCE: ${{ inputs.accion }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1

      - name: Descargar la base de R2
        run: bash scripts/r2.sh pull

      - name: ¿Qué toca ahora?
        id: due
        run: |
          any=0
          for job in scan settle close; do
            if bash scripts/due.sh "$job"; then echo "$job=1" >> "$GITHUB_OUTPUT"; any=1; fi
          done
          [ "$FORCE" = status ] && any=1
          echo "any=$any" >> "$GITHUB_OUTPUT"

      # Solo se instalan dependencias si hay trabajo: un disparo ocioso dura segundos
      - if: steps.due.outputs.any == '1'
        uses: astral-sh/setup-uv@1c37ad07a6a961277cf70c0d37d6f313000f5884 # v10.3.0
        with:
          version: "0.11.32"
          python-version: "3.12"
      - if: steps.due.outputs.any == '1'
        run: uv sync --locked

      - name: Ejecutar lo que toca
        if: steps.due.outputs.any == '1'
        env:
          ODDS_API_KEY: ${{ secrets.ODDS_API_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: |
          rc=0
          [ "${{ steps.due.outputs.settle }}" = 1 ] && { bash scripts/settle.sh || rc=$?; }
          [ "${{ steps.due.outputs.close }}" = 1 ]  && { bash scripts/close.sh  || rc=$?; }
          [ "${{ steps.due.outputs.scan }}" = 1 ]   && { bash scripts/scan.sh   || rc=$?; }
          [ "$FORCE" = status ] && { PYTHONPATH=src .venv/bin/python -m tipster status || rc=$?; }
          exit "$rc"

      - name: Subir la base a R2 (aunque el paso anterior fallara)
        if: always() && steps.due.outputs.any == '1'
        run: bash scripts/r2.sh push

      - name: Últimas líneas del registro si algo falló
        if: failure()
        run: tail -n 30 data/logs/*.log 2>/dev/null || true

      - name: Avisar por Telegram del fallo
        if: failure()
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: |
          curl -sS --max-time 15 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
            --data-urlencode "text=Tipster: falló el workflow (run ${GITHUB_RUN_ID}). Revisa Actions." >/dev/null || true
```

Orden dentro de un disparo: `settle`, `close`, `scan`. El `scan` va el último porque es el más largo y el único que
gasta créditos de forma relevante.

### Secretos y registros

- Secrets de GitHub (Settings → Secrets and variables → Actions): `R2_ACCOUNT_ID`, `R2_BUCKET_NAME`, `R2_ACCESS_KEY_ID`,
  `R2_SECRET_ACCESS_KEY`, `ODDS_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Cada uno se pasa por `env` solo al
  paso que lo necesita; GitHub los enmascara (`***`) en los registros.
- Nada de `set -x`, `env` ni `printenv` en los pasos. Los scripts de `scripts/` ya mandan su salida a
  `data/logs/*.log` (efímero) y solo se enseñan 30 líneas si falla.
- El repositorio es privado, pero el diseño no confía en eso: el detalle de picks, stakes y bankroll va a Telegram,
  no a los registros.

## Coste en minutos de Actions

Cada disparo cuesta al menos 1 minuto facturable en ubuntu (se redondea hacia arriba por trabajo). Los cron de arriba
dan unos **1 930 disparos de `close` al mes** (444 a la semana) más ~100 entre `settle` y `scan`: **≈ 2 050 min/mes**,
justo por encima de los **2 000 min gratis** de un repositorio privado en el plan Free. Opciones, en este orden:

1. Empezar así y mirar *Settings → Billing → Usage* tras la primera semana, con el **límite de gasto en 0 $** (los
   trabajos se detienen al agotar la cuota; no hay cobro por sorpresa).
2. Recortar horas muertas: por ejemplo, el primer disparo de cada franja no hace falta hasta 15 min antes del primer
   partido (`45-55/5` en la primera hora).
3. Pasar `close` a `*/10` fuera de las horas punta (mitad de coste; el cierre queda más lejos del inicio).
4. Plan Pro (3 000 min).

## Riesgos

1. **`close` en Actions no es puntual.** Los cron se retrasan a menudo 5–15 min y pueden saltarse disparos con carga
   (el motivo por el que el BACKLOG 33 lo descartó). La recaptura cada 5 min hasta el inicio
   (`TIPSTER_CLOSING_REFRESH_MINUTES`, BACKLOG 42) amortigua la pérdida de un disparo, pero el cierre llegará más lejos
   del inicio y el CLV será más ruidoso. **Medir** durante dos semanas `kickoff − closing_captured_at` y, si no
   basta, mover solo `close` a una máquina siempre encendida.
2. **Si un runner muere antes de subir**, se pierden los cambios de ese disparo (créditos gastados, avisos
   enviados). El paso de subida corre con `always()`, comprueba la integridad y se repite en el siguiente disparo.
3. **Cron de Actions solo en la rama por defecto**; GitHub puede retrasarlo o saltar disparos en horas punta.
4. **El cambio de hora** mueve 1 h el `scan` y el `settle` respecto a UTC; `due.sh` lo absorbe usando la hora de Madrid.
5. **Compatibilidad del AWS CLI con R2** (checksums, `--if-match`): se comprueba en la primera ejecución manual (ver arriba).
6. **Doble escritor.** Un agente launchd olvidado o un comando de escritura contra la base local dejaría las bases
   distintas. El corte retira los agentes y `If-Match` impide que dos escrituras se pisen.

## Plan de implementación (cada paso con su comprobación)

1. **Cloudflare:** crear el bucket privado, el token limitado y las reglas de ciclo de vida.
2. **GitHub:** pasar el repositorio a privado y cargar los 7 Secrets.
3. **Scripts:** escribir `r2.sh` y `due.sh`, y hacer que `close.sh`/`settle.sh` usen `due.sh`. Prueba: ejecutarlos en el Mac contra
   un bucket de pruebas con una copia de la base, incluido el caso 412 y el de «base vacía».
4. **Sembrar R2** desde el Mac, con los agentes launchd ya retirados (`scripts/launchd/instalar.sh desinstalar`):
   `tipster backup` y
   `aws s3api put-object --bucket B --key tipster.sqlite --body data/tipster.sqlite --if-none-match '*'`.
5. **Workflow solo con `workflow_dispatch`** (sin `schedule`) y lanzar `accion=status`: debe imprimir el bankroll
   vigente (hoy 96,00 €) y no subir nada.
6. **Lanzar `accion=settle` y `accion=close`** sin trabajo pendiente: terminan en segundos y no suben.
7. **Segundo commit:** añadir el bloque `schedule`. Vigilar el primer `scan` del viernes y la primera tanda de `close`.
8. **Dos semanas de observación** (puntualidad de `close`, minutos, créditos); anotar el resultado en el BACKLOG nº 33.

## Alternativas descartadas

- **Turso (libSQL):** obligaba a cambiar `connect()` y las anotaciones de tipo en ~9 módulos, y el paquete que se
  propuso, `libsql-client`, [está deprecado](https://github.com/libsql/libsql-client-py) (los actuales son `libsql` y
  `pyturso`); la compatibilidad de `row_factory`, `executescript` y claves foráneas había que comprobarla en un
  *spike*. El usuario prefirió no tocar la capa de datos.
- **Mantener launchd en el Mac:** no cumple el objetivo.
- **Repositorio público con registros mínimos:** descartado por el usuario (cuotas del proveedor).

## Fuera de alcance

Bot interactivo, webhooks, varios usuarios, y cualquier cambio en el modelo, el sizing o los límites.

## Implementación (2026-11-11)

- **Interruptor del corte:** el job solo corre en los cron si la variable del repositorio `CLOUD_ENABLED` vale `true`
  (el disparo manual funciona siempre). Así el workflow puede estar en `main` antes de sembrar la base y sirve de
  freno de emergencia. Un job saltado no gasta minutos.
- **`r2.sh`** probado en local con un `aws s3api` simulado: base ausente sin `bootstrap` (para), pull, push sin cambios
  (no sube), push con cambios (copia diaria en `backups/`), cambio ajeno entre pull y push (412, copia en
  `conflictos/`), base que encoge (no sube), base corrupta (no la acepta) y `bootstrap`. Para el AWS CLI real, el
  subcomando va antes de las opciones (`aws s3api put-object --bucket …`), cosa que la simulación ahora exige.
- **Limitación conocida:** `settle` solo toca si hay picks por liquidar, así que en los días sin ellos no se ejecuta
  `notify --alerts` a las 04:00 (los avisos salen igualmente en el siguiente `scan` o `close`).
- Pendiente de verificar en la primera ejecución real: AWS CLI, `sqlite3` y `--if-match` en el runner.

### Horario definitivo del `close` por presupuesto (2026-11-11)

Decisión del usuario, con el límite de gasto de Actions en 0 $ («Stop usage»): `close` pasa a
`*/15 11-22 * * 0,2,3,5,6` (martes, miércoles, viernes, sábado y domingo, 11:00–22:45 UTC; el lunes casi no hay
partidos, la Champions es martes y miércoles y los partidos de la mañana del fin de semana empiezan desde las 11:30 UTC),
unos 1 040 disparos al mes. Con `settle` y `scan` son **≈ 1 160 min de los 2 000 gratis**. Consecuencias: con un
disparo cada 15 min y ventana de 15 min cada pick tiene como mucho **una** captura (a 0–15 min del inicio) y un
retraso del cron la pierde; los partidos de lunes y jueves quedan sin cierre, es decir, sin CLV.

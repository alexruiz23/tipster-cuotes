# 013 — Ejecución en la nube: GitHub Actions + Turso

**Estado:** Propuesta (2026-11-11), pendiente del OK del usuario · **Fecha:** 2026-11-11

Quita la dependencia del Mac: `scan`, `close` y `settle` pasan a ejecutarse en GitHub Actions y la base de datos
pasa de un fichero local a Turso (libSQL, compatible con SQLite). **Este ADR es solo diseño: no hay código.**
Retoma el BACKLOG nº 33 (Actions descartado entonces para `close` y por la persistencia de la SQLite).

## Contexto

- Hoy tres agentes launchd (`close` cada 5 min, `settle` 04:00, `scan` martes y viernes 12:00) escriben en
  `data/tipster.sqlite` (4,5 MB; 22 644 partidos históricos, ~2 600 cuotas, 21 picks). Solo funcionan con el Mac
  despierto (BACKLOG 32, README).
- Un runner de Actions nace sin disco: la base tiene que vivir fuera. No puede ir a git (`.gitignore`; términos del
  proveedor sobre redistribuir cuotas).
- El acceso a datos ya está aislado: `storage/db.py:connect()` es el único sitio que abre la base; los repositorios
  (`storage/sqlite.py`, `storage/tracking.py`) reciben la conexión y usan SQL estándar con `?`.

## Decisión

1. **Base de datos en Turso** (una base, un solo escritor: los workflows). Migrar el fichero actual con
   `turso db create --from-file`, tras `tipster backup` y con `data/tipster.sqlite.bak` y `.old` intactos.
2. **Cliente: `libsql`, no `libsql-client`.** El paquete que se pidió, `libsql-client`, está
   [deprecado](https://github.com/libsql/libsql-client-py) (repo archivado en jun-2025). Turso ofrece ahora
   [`libsql` y `pyturso`](https://docs.turso.tech/sdk/python), ambos con API estilo `sqlite3`; `pyturso` es el que
   recomiendan para proyectos nuevos y `libsql` el que mantiene las réplicas embebidas. Se elige entre los dos
   en un **spike previo** (ver Riesgos), no a ciegas.
3. **Réplica embebida:** cada ejecución abre un fichero local sincronizado con Turso (lecturas locales, escrituras al
   primario). La base pesa MB, así que la sincronización inicial es de segundos.
4. **Tres workflows** (`scan.yml`, `settle.yml`, `close.yml`) con `concurrency: { group: tipster-db,
   cancel-in-progress: false }`: nunca hay dos a la vez escribiendo.
5. **Secretos de Actions:** `ODDS_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TURSO_DATABASE_URL`,
   `TURSO_AUTH_TOKEN`. Nada en el código ni en el repositorio.
6. **Apagar el Mac:** antes del traspaso se retiran los agentes launchd (`scripts/launchd/instalar.sh desinstalar`).
   Dos escritores sobre la misma base duplicarían scans y gastarían créditos de The Odds API.

## Cambios en la capa de datos (plan, sin escribir)

| Pieza | Cambio |
|---|---|
| `storage/db.py` `connect()` | Si hay `TURSO_DATABASE_URL`, abre la réplica embebida (fichero temporal + URL + token + `sync()`); si no, `sqlite3` como hoy. Misma firma, mismo `row_factory`, mismo `PRAGMA foreign_keys = ON`. |
| Tipo de conexión | Los ~9 módulos anotan `sqlite3.Connection`/`sqlite3.Row`. Se define un alias/Protocol en `db.py` y se cambian las anotaciones; el SQL no cambia. |
| `apply_migrations` | Hoy usa `executescript("BEGIN; … COMMIT;")`. Comprobar en el spike que el driver lo soporta; si no, ejecutar las sentencias de cada migración una a una en una transacción. |
| `sqlite.py` / `tracking.py` | Sin cambios de lógica. Verificar `lastrowid`, `commit()` y `Row` por nombre de columna. |
| `services/backup.py` | Usa `sqlite3.backup()` e `integrity_check`. En la nube el respaldo pasa a `turso db shell .dump` o a un workflow semanal que sube el volcado como artefacto cifrado; el backup local sigue valiendo para el modo local. |
| `scripts/close.sh`, `settle.sh` | Sus comprobaciones previas usan el CLI `sqlite3` contra el fichero. Se sustituyen por un subcomando de Python (`tipster due close\|settle`, código de salida 0/1) para que sirvan igual en local y en Actions. |
| Tests | La suite sigue en `:memory:` con `sqlite3` (CI sin red). Un test de contrato ejecuta los repositorios contra el driver nuevo en fichero local, sin Turso. |

## Workflows (plan)

Cron de Actions va en UTC. Hoy `settle` corre a las 03:00 UTC (04:00 Madrid en invierno).

- **`scan.yml`:** `cron` martes y viernes a las 11:00 UTC (12:00 Madrid en invierno; en verano 13:00). Pasos: checkout,
  `uv sync --locked`, `tipster scan`, `tipster notify --picks`, `tipster notify --alerts`. `workflow_dispatch` para
  lanzarlo a mano.
- **`settle.yml`:** `cron` diario 03:00 UTC. Un primer paso, `tipster due settle`, corta la ejecución si no hay
  picks por liquidar (0 créditos, como `settle.sh`). Luego `tipster settle` y `tipster notify --settle`.
- **`close.yml`:** `cron: "*/5 * * * *"` con el mismo corte previo, `tipster due close`. Es el punto débil (ver Riesgos).
- Todos: `permissions: contents: read`, acciones fijadas por SHA como en `ci.yml`, y `timeout-minutes` corto.

## Riesgos y cómo se tratan

1. **`close` en Actions es impreciso.** El cron de Actions se retrasa a menudo 5–15 min y puede saltarse disparos
   con carga (el motivo por el que el BACKLOG 33 lo descartó). Con ventana de 15 min y recaptura cada 5 min
   (`TIPSTER_CLOSING_REFRESH_MINUTES`, BACKLOG 42) se seguirá capturando algo, pero el cierre llegará más lejos del
   inicio y el CLV será más ruidoso. **Medirlo antes de fiarse:** comparar `closing_captured_at` contra el inicio
   durante dos semanas y, si hace falta, ampliar la ventana. Alternativa si no basta: dejar solo `close` en una
   máquina siempre encendida.
2. **El repositorio es público** (`alexruiz23/tipster-cuotes`): los registros de Actions son públicos. `scan`,
   `settle` y `notify` imprimen picks, stakes y bankroll. Hay que silenciar esa salida en CI (solo contadores y
   errores; el detalle va a Telegram), o pasar el repo a privado, donde las 2 000 min/mes gratis no alcanzan para
   un cron de 5 min (~8 600 ejecuciones/mes de al menos 1 min).
3. **Actions desactiva los cron de repos públicos tras 60 días sin actividad.** Hay que dejar un aviso (`notify`)
   si pasa un tiempo sin ejecuciones, o un commit/latido periódico.
4. **Compatibilidad del driver:** `row_factory`, `executescript`, claves foráneas y tipos de `Row`. Un **spike de
   media jornada** (abrir la base real en fichero, pasar los repositorios y la suite de contrato) decide entre
   `libsql` y `pyturso` antes de tocar nada más. Si ninguno pasa, se aborta sin cambios en producción.
5. **Latencia y fallos de red** en escrituras al primario: `scan` hace ~decenas de INSERT; se agrupan en una
   transacción por lote y, si Turso falla, el workflow termina en error y `notify --alerts` avisa. La réplica local
   no sirve de fuente de verdad: lo que no llegó al primario se repite en la siguiente ejecución.
6. **Un solo escritor.** Si por error siguen activos los agentes del Mac, hay dos escritores. El plan de traspaso
   los retira antes.
7. **Dependencia nueva** en `pyproject.toml`/`uv.lock` (CI usa `uv sync --locked`): comprobar que hay ruedas para
   Linux x86-64 (Actions) y macOS arm64 (desarrollo).

## Plan de traspaso (cada paso con su comprobación)

1. Spike del driver → los repositorios pasan contra el fichero local. **Si falla, parar.**
2. `connect()` dual + alias de tipo + `tipster due` → 461 tests siguen en verde en CI; el modo local no cambia.
3. Crear la base en Turso desde un volcado reciente → mismos recuentos (picks, `bankroll_entries`, partidos) y mismo
   `tipster status` en local y contra Turso.
4. Secretos en GitHub y workflows con solo `workflow_dispatch` → una ejecución manual de `settle` y de `scan` en
   modo prueba (`--offline` cuando aplique) sin gastar créditos de más.
5. **Corte:** retirar los agentes launchd, un último `tipster backup`, activar los `cron`. A partir de aquí la base
   local deja de ser la fuente de verdad.
6. Dos semanas de observación: puntualidad de `close`, avisos y consumo de créditos. Documentar el resultado en el
   BACKLOG (nº 33).

## Alternativa más simple, para decidir con datos

**Base SQLite en un almacén de objetos** (p. ej. Cloudflare R2): cada workflow descarga el fichero, ejecuta con
`sqlite3` estándar y lo vuelve a subir, serializado por `concurrency` y con escritura condicional por ETag. **No toca
la capa de datos ni añade dependencias** y mantiene `backup`, los scripts y los tests tal cual; a cambio sube y baja
~5 MB por ejecución (cada 5 min en `close`, aunque el corte previo evita la mayoría). Si el spike de Turso sale mal,
es el plan B.

## Fuera de alcance

Bot interactivo, webhooks, varios usuarios, y cualquier cambio en el modelo, el sizing o los límites.

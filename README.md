# tipster-cuotes

> **Juego responsable.** Solo para mayores de 18 años. Este proyecto no garantiza ningún
> beneficio: apostar implica un riesgo real de perder dinero. Si el juego deja de ser un
> entretenimiento, pide ayuda en [jugarbien.es](https://www.jugarbien.es).

Tipster automático de fútbol que **solo recomienda** apuestas. Nunca las coloca, nunca inicia
sesión en una casa de apuestas y nunca guarda credenciales de casas.

## Qué es

Un **sistema de detección de valor basado en la referencia sharp de Pinnacle**: toma la
probabilidad sin margen del cierre/precio de Pinnacle como la mejor estimación disponible y busca
casas cuya cuota se desvíe de ella a tu favor. **No tiene un modelo estadístico propio que bata al
mercado**: Dixon-Coles y Elo se midieron contra el cierre de Pinnacle en walk-forward estricto y
quedaron peor (≈ +0,023 de log-loss, unos 6 errores típicos), y la mezcla óptima da `w_mercado = 1`
([ADR 012](docs/decisiones/012-fase-3-probabilidad-stake-clv.md)). Dixon-Coles queda congelado.
El beneficio de esto no está demostrado: el CLV y el ROI solo se pueden medir hacia adelante con
picks reales en papel.

## Estado

**Paper trading desde el 2026-11-04, ejecutándose en la nube (GitHub Actions + R2, ver más abajo).** `tipster status` muestra de un vistazo el bankroll, los picks abiertos, los liquidados, el ROI (con aviso de «muestra insuficiente» por debajo de 50 picks) y el CLV medio.

**Notificaciones por Telegram (opcionales, solo salientes; implementadas y probadas con envío real).** Define `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` en `.env` y usa `tipster notify --picks | --settle | --status`. `scripts/scan.sh` y `scripts/settle.sh` lo llaman al terminar (el resultado va a `data/logs/notify.log`); si Telegram falla o no está configurado, el cron no se ve afectado. `settle` solo avisa si hubo picks con stake liquidados ese día.

**Copias, avisos de fallos y cierre más cercano.** `tipster backup` copia la base a `data/backups/` (una copia por día, se conservan 14; `settle.sh` y `scan.sh` la lanzan solos). `tipster notify --alerts` avisa por Telegram, una sola vez cada uno, de: picks con stake que empezaron sin cierre fiable (CLV perdido), `scan`/`close`/`settle` terminados en error, scan sin correr en más de 8 días y menos de `TIPSTER_LOW_CREDITS_ALERT` (60) créditos. `close` repite la captura mientras la última esté a más de `TIPSTER_CLOSING_REFRESH_MINUTES` (5) del inicio, así que el cierre guardado queda a 0–5 min. `tipster settle --void EVENTO` anula el pick de un partido aplazado (stake devuelto, bankroll sin mover, fuera del ROI). `tipster status` muestra el CLV con su error típico, el % de picks con CLV > 0 y la cobertura (picks con CLV sobre picks con stake ya jugados).

**Cuota real de la web .es.** El feed de The Odds API no es la web española de la casa, así que la cuota que ves puede ser otra. `tipster notify --picks` ahora lleva el id de cada pick (`#12`); `tipster take 12 --price 2.05 --bookmaker bwin.es` registra la cuota a la que lo tomas de verdad (`tipster take --list` enseña los abiertos). Si hay cuota real, manda sobre la del feed en la liquidación (profit y bankroll) y en un CLV «real» que `status` y `clv` muestran junto al del feed en los mismos picks. **Es opcional:** sin registrar nada, el paper trading usa la cuota del feed como hasta ahora; solo aporta saber cuánto se desvía el feed de la web real (sirve registrarla en unos pocos picks, no en todos) y será útil el día que apuestes dinero real. Solo se puede registrar en picks abiertos con stake; `status` solo menciona las cuotas reales si hay alguna.

**Fase 3 cerrada** (probabilidad final, stake de Kelly, bankroll de papel, `close`, `settle`, `clv`):
implementada y validada con datos pasados (`w = 1`; el cierre de Pinnacle se mantiene bien calibrado en
2024/25, [ADR 012](docs/decisiones/012-fase-3-probabilidad-stake-clv.md)). **Pendiente: paper trading en
vivo** para medir ROI y CLV, que el histórico no permite. Las llamadas reales de `close` y `settle` están
**sin verificar** (solo proveedores simulados). La Fase 4 (combinadas) no se ha abierto.

**Fase 1 cerrada (2026-10-29).** F1–F10 y R1–R4 cumplidos. Las llamadas reales se hicieron en una
máquina local con `ODDS_API_KEY`: un escaneo completo de 7 competiciones (118 partidos, 11 picks)
costó 14 créditos, y 28 en toda la sesión de cierre. Detalle y evidencia de cada criterio en
[docs/fase-1/plan.md §9](docs/fase-1/plan.md#9-estado).

> **Limitación del proveedor, no del código:** el O/U 2.5 tiene muy poca cobertura de referencia.
> Pinnacle solo da la línea 2.5 en 21 de 118 eventos y Betfair no da totales
> ([verificación §13.4](docs/fase-0/verificacion-proveedores.md)). Pendiente: BACKLOG nº 13.

**Fase 0: puerta de salida no cumplida.** Sin código no había tests, ruff, mypy ni CI que ejecutar
(detalle en [PLAN §0](docs/PLAN.md#0-estado-real-de-la-puerta-de-salida-de-la-fase-0)).

| Documento | Contenido |
|---|---|
| [Plan de la Fase 1](docs/fase-1/plan.md) | Plan aprobado, criterios de aceptación y estado (handoff) |
| [Verificación de proveedores](docs/fase-0/verificacion-proveedores.md) | Qué casas, mercados, consumo y precios cubre cada proveedor, con su nivel de verificación |
| [Arquitectura](docs/ARQUITECTURA.md) | Carpetas, módulos, interfaces y modelo de datos |
| [Plan general](docs/PLAN.md) | Fases y decisiones D1–D7 |
| [Decisiones](docs/decisiones/README.md) | Registros de decisión (ADR) |
| [Backlog](docs/BACKLOG.md) | Ideas fuera de alcance |

## Instalación

Requiere Python 3.12 y [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env    # y rellena ODDS_API_KEY si vas a usar datos en vivo
```

## Uso

```bash
# Con datos grabados (no llama a la red ni gasta créditos). Las fixtures del repositorio son
# inventadas: la salida lo indica y va marcada «DATOS GRABADOS, NO EN VIVO».
uv run tipster scan --offline tests/fixtures/the_odds_api/sintetico

# En vivo (necesita ODDS_API_KEY y acceso de red a api.the-odds-api.com)
uv run tipster scan
uv run tipster scan --competicion laliga --competicion premier --max-creditos 10
```

```bash
# Fase 2: histórico de partidos y cierre de Pinnacle (descarga ~16 MB una sola vez)
uv run tipster ingest --from 2016 --to 2025
```

El histórico viene de [eatpizzanot/soccer-dataset](https://huggingface.co/datasets/eatpizzanot/soccer-dataset)
(CC-BY-4.0), compilado a partir de API-Football y football-data.co.uk. Hay que citarlos en
cualquier informe que lo use. Detalle en el [ADR 007](docs/decisiones/007-historico-y-dixon-coles.md).

```bash
# Fase 2–3: evaluación, selección de la mezcla y seguimiento de picks
uv run tipster evaluate            # Dixon-Coles y Elo frente a Pinnacle (walk-forward estricto)
uv run tipster select-blend        # diagnóstico: devig, calibrador y mezcla en validación (siempre da w = 1 hoy; no toca 2024/25)
uv run tipster close               # cierre de Pinnacle de los picks con stake a punto de empezar
uv run tipster settle              # liquida con los resultados del proveedor (o --result EVENTO=GL-GV)
uv run tipster settle --void EVENTO  # anula el pick de un partido aplazado (nulo; stake devuelto)
uv run tipster take ID --price X   # registra la cuota real que ves en la web .es (ID: ver notify --picks o take --list)
uv run tipster backup              # copia diaria de la base a data/backups/ (rotación de 14)
uv run tipster clv                 # CLV de los picks con cierre fiable
```

`tipster scan` muestra, por cada oportunidad: partido, mercado, selección, casa (con la
jurisdicción de su feed), cuota, cuota justa, p_modelo («—»: con `w = 1` no se usa), p_mercado, EV, stake
(1/4 de Kelly con tope del 2 %, solo en los VALUE), etiqueta, referencia usada y hora de captura. Etiquetas:

- **VALUE**: EV de al menos el mínimo configurado (3 % por defecto). Solo recibe stake si además cumple su nivel (principal o improbable) y el partido empieza en los próximos 4 días; si no, se muestra con el motivo.
- **POSIBLE ERROR · RIESGO DE ANULACIÓN**: cuota más de un 15 % por encima de la justa.
- **FEED NO-ES · VERIFICA LA CUOTA EN LA WEB .ES**: acompaña a toda cuota que no viene de la web
  española de la casa. Hoy son todas: The Odds API no tiene feeds .es (D1).

La referencia es Pinnacle si su cuota está fresca y completa; si no, Betfair Exchange (D2).
Ninguna de las dos es una casa en la que apostar desde España: solo sirven para estimar la
probabilidad justa.

Códigos de salida: 0 (ejecución completa o parcial), 1 (error del proveedor), 2 (configuración).

## Datos, logs y backup

- **Base de datos:** `data/tipster.sqlite` (ignorada por git). Guarda cada ejecución, cada
  petición al proveedor con su consumo de créditos, todos los eventos y cuotas (con hora de
  captura y origen) y los picks emitidos con las cuotas exactas de su referencia. Con `--offline`
  la base va en memoria salvo que se pase `--db`.
- **Respuestas crudas:** `data/raw/`, sin la clave.
- **Logs y métricas:** en la Fase 1 solo se escribe a stdout; el consumo queda en las tablas
  `runs` y `provider_requests`.
- **Backup:** `tipster backup` (BACKLOG 40): copia consistente con la API de SQLite, comprobada con `integrity_check`, una por día en `data/backups/` (`TIPSTER_BACKUP_DIR`, `TIPSTER_BACKUP_KEEP`). Los scripts de cron la hacen antes de `scan` y de `settle`. La carpeta está dentro de `data/` (fuera de git) y en el mismo disco: no protege de perder el Mac; para eso, copia esa carpeta a otro sitio (iCloud, disco externo).

## Desarrollo

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit install    # opcional: gitleaks y ruff antes de cada commit
```

La CI de GitHub Actions ejecuta lo mismo y además gitleaks en cada push y PR.

No hay `CHANGELOG.md`: el historial de commits de `main` hace de changelog. El estado de
cada fase (handoff) está en su plan; el de la Fase 1, en
[docs/fase-1/plan.md §9](docs/fase-1/plan.md#9-estado).

## Limitaciones conocidas

- The Odds API no tiene ninguna web .es: solo feeds de otras jurisdicciones de 888sport, William
  Hill, Marathonbet, Betfair y Winamax, que pueden no coincidir con la web española.
- Pinnacle cerró su API pública el 23/07/2025; The Odds API la obtiene de su web pública con
  posible retraso, y en el histórico de football-data.co.uk no es fiable desde esa fecha.
- El O/U 2.5 tiene muy poca cobertura de referencia: Pinnacle solo da la línea 2.5 en 21 de 118
  eventos y Betfair no da totales (limitación del proveedor; BACKLOG nº 13).
- La estructura de las respuestas y las 7 claves de competición están verificadas con una llamada
  real (2026-10-29), pero en una sola captura: la frescura y las casas por liga en otros días u
  horas son NO VERIFICADO ([§13](docs/fase-0/verificacion-proveedores.md)).
- The Odds API no da liquidez ni límites: toda cuota lleva «liquidez desconocida».
- No hay ninguna fuente verificada de cuotas de Ambos Marcan para fútbol europeo, ni histórico
  verificado de la Champions.

## Qué no hará

- Colocar apuestas, iniciar sesión en casas o guardar sus credenciales.
- Hacer scraping de webs de casas de apuestas.
- Prometer beneficios: con pocas apuestas, ningún ROI demuestra nada.

## Ejecución en la nube (GitHub Actions + Cloudflare R2)

Desde el 2026-11-11 el bot corre sin depender del Mac ([ADR 013](docs/decisiones/013-nube-github-actions-r2.md)). El workflow `.github/workflows/cron.yml` descarga la base SQLite de un bucket privado de Cloudflare R2, ejecuta lo que toque con `scripts/scan.sh`, `settle.sh` y `close.sh`, y la vuelve a subir (`scripts/r2.sh pull|push`).

| Trabajo | Cuándo (cron en UTC) | Notas |
|---|---|---|
| `scan` | martes y viernes, a las 12:00 de Madrid | ~14 créditos; `scripts/due.sh` ajusta invierno y verano |
| `settle` | una vez al día, en el primer disparo que llegue (sin franja horaria) | solo si hay picks abiertos de entre 2 h y 3 días atrás; si falla se reintenta en el siguiente disparo |
| `close` | cada 15 min, de 11:00 a 22:45 UTC martes, miércoles y viernes a domingo, y de 17:00 a 21:45 UTC los lunes | una captura por pick a 0–15 min del inicio; sin cierre los partidos de jueves. Lo dispara con puntualidad el [Worker de Cloudflare](cloudflare/dispatcher/README.md); el cron de Actions es de respaldo |

- **Cada disparo decide por el estado de la base**, así que si GitHub retrasa o se salta un cron no se pierde trabajo. Los disparos sin tarea duran segundos y no instalan dependencias.
- **Una sola cola** (`concurrency: tipster-db`) y subida con `If-Match`: nunca hay dos escritores. La base no se sube si no cambió, si no pasa `integrity_check` o si tiene menos filas que al descargarla. La primera copia del día va a `backups/` en R2, y un conflicto deja una copia en `conflictos/`.
- **Secretos de Actions:** `R2_ACCOUNT_ID`, `R2_BUCKET_NAME`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `ODDS_API_KEY`, `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`. El repositorio es privado y los registros solo enseñan contadores; el detalle de picks y bankroll va a Telegram.
- **Interruptor:** los cron solo actúan con la variable del repositorio `CLOUD_ENABLED=true`. Para pararlo, bórrala o ponla en `false`.
- **Prueba manual:** *Actions → Cron → Run workflow* con `accion = status` lee la base y muestra el estado (y envía el aviso) sin tocar nada. También permite forzar `scan`, `settle` o `close`.
- **Presupuesto:** ≈ 1 160 min/mes de los 2 000 gratis del repositorio privado; con el límite de gasto en 0 $ los trabajos se detienen al agotarlos. Revisa *Settings → Billing → Usage*.
- **Aviso:** `close` disparado por el cron de Actions no es puntual (el 12/11 solo llegó 1 de unos 17 disparos, con casi 3 h de retraso): un cierre perdido deja el pick sin CLV. Por eso existe el [Worker de Cloudflare](cloudflare/dispatcher/README.md) (ADR 013); una vez desplegado y comprobado, comenta el cron de `close` en `cron.yml` para no pagar los minutos dos veces.
- **`take` y `void` desde el móvil:** *Actions → Cron → Run workflow* con `accion = take` (más `pick_id`, `precio` y, si quieres, `casa`) registra la cuota real de un pick; con `accion = void` y `pick_id` anula el de un partido aplazado. El id del pick sale en el aviso de Telegram. Imprime el `status` al terminar.
- **Picks abiertos por Telegram:** `accion = abiertos` (o `tipster notify --open`) manda la lista de todos los picks abiertos con stake, con fecha y hora de cada partido.
- **Un scan o settle que falló se reintenta** en el siguiente disparo del día; solo cuenta como hecho si terminó bien.
- **Comandos que escriben desde el Mac** (`bankroll deposit/withdraw`, `settle --result`, y `take`/`void` si prefieres la terminal): no valen contra la base local, que quedó como copia. Se hacen con `scripts/r2.sh pull`, el comando y `scripts/r2.sh push` (con las variables `R2_BUCKET` y `AWS_*` de R2; hace falta `awscli`).

**El paper trading empieza el 2026-11-04 con 100 €** (base nueva; la anterior, de pruebas, está en `data/tipster.sqlite.old`). Devig Shin; nivel principal de cuota 1,5 a 4 (EV ≥ 3 %) y nivel improbable de 4 a 8 (EV ≥ 6 %, como mucho 2 abiertos a la vez); solo partidos de los próximos 4 días ([ADR 014](docs/decisiones/014-niveles-shin-horizonte.md)), stake del 1 % del bankroll entre 0,50 € y 5 € ([ADR 012](docs/decisiones/012-fase-3-probabilidad-stake-clv.md)).

## Alternativa local (macOS, retirada)

Los agentes launchd (`scripts/launchd/instalar.sh`, `instalar.sh desinstalar`) siguen en el repositorio pero **están retirados**: con la nube activa, tenerlos a la vez duplicaría scans y gastaría créditos de The Odds API. Si algún día se vuelve al modo local, hay que poner `CLOUD_ENABLED` en `false`, traer la base con `scripts/r2.sh pull` y reinstalar los agentes. En ese modo el Mac debe estar despierto (o con `caffeinate -s`) y el repo fuera de Desktop/Documents/Downloads (TCC de macOS).

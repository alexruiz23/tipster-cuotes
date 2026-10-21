# Fase 1 — Plan aprobado: `tipster scan`

**Estado:** aprobado (incluye las correcciones (a′), 2 y 3 de la revisión). Donde este documento
difiera de [ARQUITECTURA](../ARQUITECTURA.md), manda este. Decisiones de base: D1–D7 en
[PLAN §3](../PLAN.md), y P1 (tabla `picks` en la F1) y P2 (`--offline`) aprobadas.

## 1. Objetivo y alcance

`tipster scan` lee de The Odds API las cuotas de 1X2 y O/U 2.5 de las 7 competiciones y las guarda
con su hora de captura y su origen. Elige la referencia según D2, calcula p_mercado con el devig
configurado, el EV de cada cuota y su etiqueta, y guarda los picks emitidos. En la F1 no hay
modelo (p_final = p_mercado) ni stake.

**Fuera de la F1:** modelo propio, p_final mezclada, Kelly, liquidación y CLV, combinadas,
backtest, BTTS (D5), OddsPapi (F1b), la etiqueta «SIN MODELO» de la Champions (D6; sin modelo no
aplica hasta la F3), Telegram y dashboard.

**Cambios respecto a ARQUITECTURA:**
1. La caché vive en la BD: si hay una petición idéntica con respuesta 200 dentro del TTL, se
   reutiliza su respuesta cruda. Las cuotas reutilizadas conservan su `captured_at` original.
2. La tabla `picks` existe desde la F1 (P1).
3. No hay opción para ocultar los feeds no españoles: D1 los muestra siempre etiquetados.

## 2. Árbol

```
pyproject.toml · uv.lock · .python-version (3.12) · .env.example · .pre-commit-config.yaml
.github/workflows/ci.yml            ruff check, ruff format --check, mypy --strict, pytest, gitleaks
src/tipster/
  __init__.py                       versión + texto del aviso de juego responsable
  __main__.py                       python -m tipster
  config.py                         Settings (pydantic-settings)
  errors.py                         jerarquía de excepciones
  domain/       sports.py · competitions.py · markets.py · bookmakers.py · models.py
  pricing/      devig.py · value.py · classify.py
  providers/    base.py · http.py · budget.py
                the_odds_api/  client.py · schemas.py · mapping.py · offline.py
  storage/      db.py · migrations/0001_inicial.sql · repositories.py · sqlite.py
  services/     reference.py · scan.py
  cli/          app.py · render.py
tests/
  unit/         test_devig.py · test_value.py · test_classify.py · test_reference.py
                test_registries.py · test_config.py
  integration/  test_http_client.py · test_the_odds_api.py · test_sqlite.py
                test_scan_service.py · test_cli.py
  fixtures/the_odds_api/
                sintetico/   estructura según la documentación (NO VERIFICADA), cuotas de prueba
                real/        grabadas y saneadas, cuando haya red y clave (R3)
```

Dependencias de ejecución: httpx, pydantic, pydantic-settings, typer y scipy. De desarrollo:
pytest, ruff, mypy y pre-commit. Las versiones las fija `uv.lock`.

## 3. Interfaces

### OddsProvider (`providers/base.py`)

```python
class OddsProvider(Protocol):
    name: str
    def list_competitions(self) -> CompetitionListing: ...    # /v4/sports, gratis [B]
    def fetch_odds(self, request: OddsRequest) -> OddsBatch: ...

@dataclass(frozen=True)
class OddsRequest:
    competition_id: str              # canónico: "laliga"
    market_ids: tuple[str, ...]      # ("1x2", "ou_2.5")
    bookmaker_ids: tuple[str, ...]   # canónicos; ≤ 10 → 1 grupo de casas [B]

class RequestRecord(BaseModel):
    provider: str; endpoint: str; params_key: str        # parámetros ordenados, sin apiKey
    http_status: int | None; from_cache: bool
    cost: int | None; credits_used: int | None; credits_remaining: int | None
    requested_at: AwareDatetime; duration_ms: int | None
    raw_path: str | None; error: str | None

class OddsBatch(BaseModel):
    competition_id: str
    events: list[Event]
    quotes: list[OddsQuote]
    request: RequestRecord
    warnings: list[str]              # casa desconocida, línea ≠ 2.5, selección no reconocida…
```

**Errores** (heredan de `TipsterError`):

| Excepción | Cuándo | ¿Reintenta? | Efecto en `scan` |
|---|---|---|---|
| `ProviderAuthError` | 401/403 | No | Aborta la ejecución |
| `QuotaExhaustedError` | Error `OUT_OF_USAGE_CREDITS` [B] (código HTTP NO VERIFICADO: se detecta por el cuerpo) | No | Aborta |
| `BudgetExceededError` | El coste estimado supera lo que queda de `--max-creditos` | No (no se llega a llamar) | Para; muestra lo ya leído |
| `RateLimitedError` | 429 tras agotar los reintentos | Sí, antes de lanzarse | Salta esa competición |
| `ProviderUnavailableError` | Red, timeout o 5xx tras los reintentos | Sí, antes de lanzarse | Salta esa competición |
| `ProviderResponseError` | JSON inválido, que no cumple el esquema, u otro 4xx | No | Salta esa competición |

**Rate limit y reintentos:** intervalo mínimo de 1 s entre peticiones (provisional; el límite real
es NO VERIFICADO). Hasta 3 reintentos con backoff de 1, 2 y 4 s más *jitter* de hasta 0,5 s,
respetando `Retry-After`. Reloj, `sleep` y aleatoriedad inyectables. La clave se elimina de todo
lo que se registra (parámetros, mensajes de error, BD, respuestas crudas y fixtures).

Estado de la ejecución: `ok`, `parcial` (alguna competición falló y otras no) o `error`.

### Repositorios (`storage/repositories.py`)

```python
class EventRepository(Protocol):
    def upsert(self, event: Event, provider: str, external_id: str) -> None: ...
    def get(self, event_id: str) -> Event | None: ...

class OddsRepository(Protocol):
    def add_batch(self, request_id: int, quotes: Sequence[OddsQuote]) -> list[int]: ...
    def latest(self, event_id: str, market_id: str) -> list[OddsQuote]: ...

class PickRepository(Protocol):
    def add(self, run_id: int, picks: Sequence[Pick]) -> None: ...
    def for_run(self, run_id: int) -> list[Pick]: ...

class RunRepository(Protocol):
    def start(self, command: str, settings_snapshot: Mapping[str, object]) -> int: ...
    def record_request(self, run_id: int, record: RequestRecord) -> int: ...
    def finish(self, run_id: int, status: Literal["ok", "parcial", "error"]) -> None: ...

class ResponseCache(Protocol):
    def lookup(self, provider: str, endpoint: str, params_key: str,
               max_age: timedelta, now: datetime) -> CachedResponse | None: ...
```

### Configuración (`config.py`)

`Settings(BaseSettings)` lee `.env`. Variables: `ODDS_API_KEY` (`SecretStr`, solo obligatoria en un
`scan` en vivo) y, con prefijo `TIPSTER_`, `DB_PATH`, `RAW_DIR`, `CACHE_TTL_SECONDS` (60),
`MAX_CREDITS_PER_RUN` (30), `MIN_REQUEST_INTERVAL_S` (1.0), `COMPETITIONS`, `MARKETS`
(`1x2,ou_2.5`), `BOOKMAKERS`, `REFERENCE_ORDER` (`pinnacle,betfair_ex_no_es`), `DEVIG_METHOD`
(`multiplicativo`, provisional), `EV_MIN` (0.03), `ERROR_MARGIN` (0.15),
`MAX_QUOTE_AGE_MINUTES` (10), `MAX_REFERENCE_AGE_MINUTES` (10) y `TIMEZONE` (`Europe/Madrid`).

Validadores: `ev_min < error_margin`; competiciones, mercados y casas deben existir en los
registros; `btts` se rechaza citando D5; el orden de referencia solo admite casas con rol `sharp`
o `exchange`.

## 4. Modelo de datos (`0001_inicial.sql`)

Fechas en texto ISO-8601 UTC; `PRAGMA foreign_keys = ON`.

| Tabla | Columnas | Claves e índices |
|---|---|---|
| `schema_version` | version, applied_at | PK version |
| `runs` | id, command, started_at, finished_at, status (`en_curso`/`ok`/`parcial`/`error`), settings_json (umbrales usados, nunca la clave) | PK id |
| `provider_requests` | id, run_id, provider, endpoint, params_key, http_status, from_cache (0/1), cost, credits_used, credits_remaining, requested_at, duration_ms, raw_path, error | PK id; FK run_id; índices (provider, endpoint, params_key, requested_at) y (run_id) |
| `events` | id (UUID canónico), sport, competition_id, home_team, away_team, kickoff_utc, created_at | PK id; índice (competition_id, kickoff_utc) |
| `event_external_ids` | provider, external_id, event_id | PK (provider, external_id); FK event_id; índice (event_id) |
| `odds_quotes` | id, request_id, event_id, bookmaker_id, market_id, selection, price (> 1), **captured_at**, **provider_last_update**, **source** | PK id; FK request_id y event_id; UNIQUE (request_id, event_id, bookmaker_id, market_id, selection); índice (event_id, market_id, bookmaker_id, captured_at) |
| `picks` | id, run_id, quote_id, label (`VALUE`/`POSIBLE_ERROR`), feed_es (D1), reference_bookmaker_id, reference_captured_at, **reference_odds_json**, devig_method, p_market, p_model, p_final, fair_odds, ev, stake (NULL hasta F3), reasons_json, created_at | PK id; FK run_id y quote_id; UNIQUE (run_id, quote_id); índice (run_id) |

`reference_odds_json` (TEXT NOT NULL): lista JSON `[[selección, cuota], …]` con las cuotas exactas de
la referencia que entraron en el devig, en el orden de las selecciones del mercado. Permite
reconstruir p_market aunque se roten las filas de `odds_quotes`.

## 5. Devig (`pricing/devig.py`)

```python
def devig_multiplicative(odds: Sequence[float]) -> tuple[float, ...]
def devig_additive(odds: Sequence[float]) -> tuple[float, ...]
def devig_power(odds: Sequence[float], *, tol: float = 1e-12, max_iter: int = 200) -> tuple[float, ...]
def devig_shin(odds: Sequence[float], *, tol: float = 1e-12, max_iter: int = 200) -> tuple[float, ...]
def devig(odds: Sequence[float], method: DevigMethod) -> tuple[float, ...]   # despacho por diccionario
```

- Multiplicativo: pᵢ = qᵢ / Q, con qᵢ = 1/cuotaᵢ y Q = Σq.
- Aditivo: pᵢ = qᵢ − (Q − 1)/n; `DevigError` si algún pᵢ ≤ 0.
- Power: pᵢ = qᵢᵏ, con k tal que Σ qᵢᵏ = 1.
- Shin: pᵢ = (√(z² + 4(1−z)·qᵢ²/Q) − z) / (2(1−z)), con z ∈ [0, 1) tal que Σp = 1.
- Comunes: mismo orden que la entrada; `DevigError` con menos de 2 cuotas, alguna ≤ 1 o no finita,
  Q < 1 (anomalía de datos: la oportunidad se descarta) o sin convergencia. Si Q = 1 (±1e-12),
  devuelven q.

## 6. Tests con casos calculados a mano

Caso base: referencia 1X2 **2.00 / 3.50 / 4.00** → q = 1/2, 2/7, 1/4 → Q = 29/28.
Las constantes de power y Shin se calcularon fuera del código del proyecto, por bisección con 50
dígitos; el test las fija, así que no compara la implementación consigo misma.

| Test | Entrada | Esperado |
|---|---|---|
| multiplicativo | caso base | 14/29, 8/29, 7/29 |
| aditivo | caso base | 41/84, 23/84, 20/84 |
| aditivo inválido | 1.40 / 2.90 / 100.0 | `DevigError` (p₃ = 0.01 − 0.023038 < 0) |
| power | caso base | k = 1.034636783579; p = 0.488138759924 / 0.273581791137 / 0.238279448940 (tolerancia 1e-9) |
| power, 2 resultados | 1.80 / 2.10 | k = 1.047439088610; p = 0.540278393592 / 0.459721606408 |
| Shin | caso base | z = 0.017891311770; p = 0.486733634763 / 0.274328396123 / 0.238937969114. **Distinto del aditivo** (0.488095 / 0.273810 / 0.238095): es el test que detecta una implementación que haga aditivo y lo llame Shin |
| Shin, 2 resultados | 1.80 / 2.10 y 1.50 / 2.50 | z exacto 407/12818 → p = 34/63, 29/63; z exacto 14/209 → p = 19/30, 11/30. Calculado con la ecuación de Shin, no copiado del aditivo |
| Shin = aditivo en n = 2 | 1.80/2.10, 1.50/2.50 y 1.25/4.50 | Coinciden a 1e-12: **equivalencia exacta para n = 2, demostrada en el docstring del test** |
| invariantes (×4) | caso base, 1.80/2.10, 1.90/1.90 | Σp = 1; pᵢ > 0; orden conservado; 1.90/1.90 → 0.5/0.5; Q = 1 → q; errores de entrada |
| cuota justa y EV | p = 14/29 | cuota justa 29/14; con 2.20, EV = 9/145 ≈ 0.0620690 |
| clasificación | p = 14/29 | 2.10 → SIN VALOR (+1.38 %); 2.20 → VALUE; 1.03 × 29/14 → VALUE (3 % exacto, incluido); 2.40 → POSIBLE ERROR (+15.86 %); 1.15 × 29/14 → VALUE (15 % no es «más de» 15 %) |
| descarte | cuota 2.20 con 10 min 1 s de antigüedad (máximo 10 min) | DESCARTADA; con 10 min exactos, VALUE |
| referencia (D2) | Pinnacle de hace 12 min y Betfair de hace 2 min | Se usa Betfair y queda en el pick; si a Pinnacle le falta el empate, también se pasa a Betfair; sin ninguna válida, se descarta |
| `reference_odds_json` | pick guardado | Contiene exactamente las cuotas de entrada del devig, en orden; `devig(reference_odds_json, devig_method)` reproduce `p_market` |

**Prueba de la equivalencia para n = 2** (va en el docstring). La ecuación de Shin equivale a
(1−z)·p² + z·p = q²/Q, es decir, z = (q²/Q − p²) / (p(1−p)). Con p del aditivo, pᵢ = qᵢ − (Q−1)/2,
el denominador es el mismo para las dos selecciones (p₂ = 1 − p₁), y los numeradores también:
(q₁² − q₂²)/Q = q₁ − q₂ = p₁² − p₂². Hay, por tanto, un único z que hace que el resultado aditivo
cumpla Shin exactamente.

Otros tests: registros completos; *mapping* de `h2h` por nombre de equipo y de totales solo con
línea 2.5; reintentos con `sleep` falso; 401 sin reintento; cabeceras de consumo; la clave nunca
aparece en parámetros, BD ni respuestas crudas; presupuesto; ida y vuelta UTC en SQLite; `upsert`
idempotente; restricciones `CHECK`/`UNIQUE`; CLI con el aviso, columnas «ref.» (D2) y «feed»
(D1), y salida «DATOS GRABADOS, NO EN VIVO» con `--offline` (P2).

## 7. Criterios de aceptación

**[F] = fixtures, sin red. [R] = exige llamada real.**

| # | Criterio | Tipo |
|---|---|---|
| F1 | `uv sync --locked`, `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` y `uv run mypy` limpios | F |
| F2 | CI en verde en `main` (calidad + gitleaks). Riesgo NO VERIFICADO: que el token del entorno permita subir `.github/workflows/` | F |
| F3 | Devig: los 4 métodos pasan los casos del §6 y las invariantes | F |
| F4 | EV y clasificación pasan los casos frontera | F |
| F5 | Referencia según D2 y etiqueta «FEED NO-ES · VERIFICA LA CUOTA EN LA WEB .ES» en todo feed no español (D1) | F |
| F6 | Toda cuota guardada tiene `captured_at`, `source` y `request_id`; `provider_last_update` nulo solo con aviso | F |
| F7 | Cliente HTTP: reintentos, errores, presupuesto y caché por TTL con transporte simulado | F |
| F8 | La clave nunca aparece en BD, respuestas crudas, mensajes ni fixtures | F |
| F9 | `tipster scan --offline` de principio a fin con fixtures sintéticas: tabla, picks con `reference_odds_json`, aviso | F |
| F10 | `.env.example` documentado; README con instalación, configuración, uso y aviso | F |
| R1 | `tipster scan` contra la API real muestra la tabla y los créditos gastados y restantes | R |
| R2 | Un segundo `scan` dentro del TTL gasta 0 créditos según el registro real | R |
| R3 | Fixture real grabada y saneada; los tests de parseo pasan también con ella | R |
| R4 | Verificación a nivel A: claves de las 7 competiciones, casas por liga, líneas de totales y frescura de `pinnacle` y `betfair_ex_eu` | R |

**Con D4 = B no se pueden cerrar R1–R4, y por tanto tampoco la Fase 1.**

## 8. Puerta de salida de la Fase 1

Además de tests, ruff, mypy, CI, README y push a `main`:
- **Handoff:** nota de estado de la fase en README y en este documento (§9).
- **Logs y métricas:** en la F1 solo se escribe a stdout (tabla y resumen de la ejecución). El
  consumo de créditos queda en `provider_requests` y `runs`. Declarado en README y `config.py`.
- **Backup de `data/tipster.sqlite`:** no se hace backup en la F1; se decide en la F3, cuando haya
  picks con resultado que merezca conservar.
- **Decisiones:** ADR 001–005 en «Aceptada» y PLAN §3 con D1–D7 confirmadas.

## 9. Estado

**Fase 1 construida, no cerrada: pendiente de red y clave para cerrar R1–R4** (2026-10-21).
Durante toda la construcción la red de este entorno bloqueó `api.the-odds-api.com` y no hubo
`ODDS_API_KEY`, así que se trabajó como D4 = B.

| # | Estado | Cómo comprobarlo |
|---|---|---|
| F1 | Cumplido | `uv sync --locked && uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy` |
| F2 | Cumplido: CI en verde (calidad + gitleaks) en el HEAD revisado, `c9384af` (ejecución 9). Se vuelve a comprobar tras cada push. El token del entorno sí permitió subir el workflow | Pestaña Actions del repositorio |
| F3 | Cumplido | `tests/unit/test_devig.py` |
| F4 | Cumplido | `tests/unit/test_value.py`, `tests/unit/test_classify.py` |
| F5 | Cumplido | `tests/unit/test_reference.py`, `tests/integration/test_scan_service.py`, `tests/integration/test_cli.py` |
| F6 | Cumplido | `tests/integration/test_sqlite.py` (NOT NULL y origen), `test_scan_service.py` |
| F7 | Cumplido | `tests/integration/test_http_client.py`, `test_scan_service.py::test_segundo_scan_dentro_del_ttl_no_gasta_creditos` |
| F8 | Cumplido | Tests de clave en http, config y scan; gitleaks sin fugas en historial y árbol (ver incidencia) |
| F9 | Cumplido | `uv run tipster scan --offline tests/fixtures/the_odds_api/sintetico` |
| F10 | Cumplido | `.env.example`, README |
| R1 | **Abierto** | Necesita red y clave |
| R2 | **Abierto** | Necesita red y clave (el comportamiento está probado con transporte simulado en F7) |
| R3 | **Abierto** | Necesita red y clave; mientras, las fixtures son sintéticas y su estructura NO VERIFICADA |
| R4 | **Abierto** | Necesita red y clave; las claves de 6 de las 7 competiciones siguen NO VERIFICADAS |

**Para cerrar la fase:** abrir `api.the-odds-api.com` en la red del entorno, definir
`ODDS_API_KEY` como secreto y, en la sesión siguiente: `uv run tipster scan` (R1); repetirlo antes
de 60 s (R2); grabar y sanear una respuesta en `tests/fixtures/the_odds_api/real/` y pasar los
tests de parseo con ella (R3); actualizar la verificación de proveedores a nivel A (R4). Coste
estimado: unos 14 créditos por escaneo completo.

**Incidencia de CI resuelta.** La ejecución de `8cf20f7` falló en el job de gitleaks por la clave
falsa de un test (`generic-api-key`). Se reprodujo en local con gitleaks 8.30.1, binario
verificado con su checksum, sobre el historial completo. Se corrigió con `gitleaks:allow` en las
claves falsas de los tests y con la huella del commit ya publicado en `.gitleaksignore`, sin
reescribir historia (commit `f29fdfe`).

**Precisiones respecto al plan aprobado** (ninguna amplía el alcance):
1. `OddsBatch` lleva también `external_ids` (id canónico → id del proveedor), que necesita
   `EventRepository.upsert`.
2. **`captured_at` cambió respecto a ARQUITECTURA** («cuándo la recibimos»): es el **inicio del
   intento HTTP** que trajo la respuesta (con reintentos, el del intento con éxito), porque es el
   instante más antiguo posible y nunca presenta un dato como más reciente de lo que es. La
   antigüedad que comparan `max_quote_age_minutes` y `max_reference_age_minutes` se mide contra
   `provider_last_update`, y solo si falta, contra `captured_at`. La caché conserva el
   `captured_at` original: está cubierta por un test. No hay test de «petición lenta»; queda
   propuesto, pendiente de OK, en [ADR 006](../decisiones/006-hora-de-captura-y-antiguedad.md). Las
   cuotas reutilizadas se guardan otra vez, enlazadas a la petición `from_cache = 1`.
3. `power_exponent` y `shin_z` se exponen para que los tests puedan fijar k y z.
4. Las peticiones del modo offline se registran con `http_status` NULL, así que nunca sirven
   como caché, y `--offline` usa una base en memoria salvo que se pase `--db`.
5. Toda oportunidad lleva el motivo «liquidez desconocida» (ADR 001). **Interpretación
   provisional:** aviso y no descarte, porque The Odds API no expone liquidez ni límites; la regla
   «descartar por liquidez o límite bajo» queda pendiente de tu confirmación. Si se descartara,
   hoy no habría ningún pick.
6. `tipster scan` admite `--competicion` (repetible) y `--max-creditos`. Códigos de salida:
   0 (completa o parcial), 1 (error del proveedor) y 2 (configuración).
7. La CLI se escribió con Rich (incluido en Typer): la tabla necesita un terminal ancho
   (unas 230 columnas) para no partir celdas.

**Notas de la revisión del cierre** (2026-10-21):
- **Recuento de commits:** `git rev-list --count main` = 43 = `origin/main`;
  `git rev-list --count 317bd61..HEAD` = 41, porque excluye `317bd61` y `670d4ed`. Desglose: 1
  (`670d4ed`, Sección 0) + 7 (Fase 0, `317bd61`…`da0c568`) + 1 (`2b3994c`) + 2 (`a372366`,
  `dd17795`) + 32 (Fase 1, `dfe2ebd`…`c9384af`) = 43. El informe anterior decía «30» para la Fase 1:
  era un error y son 32. Este commit de revisión suma uno más.
- **gitleaks y licencias:** el CLI de gitleaks es MIT (`LICENSE` de
  github.com/gitleaks/gitleaks). La acción `gitleaks/gitleaks-action` usada en la CI tiene licencia
  propia (`LICENSE.txt`, «GITLEAKS-ACTION END-USER LICENSE AGREEMENT»): exige una *License Key*
  para repositorios de organizaciones y no para cuentas personales. De ahí sale la nota del
  workflow, que se mantiene.
- **Segunda «saltada» en offline:** no es un fallo de mapeo ni un hallazgo sobre el proveedor. El
  `sports.json` sintético solo lista LaLiga y Premier, a propósito, para probar el camino de
  competición no listada. Si The Odds API cubre la Segunda (y con qué clave) es parte de R4.
- **Changelog:** no hay `CHANGELOG.md`; el historial de commits de `main` hace de changelog.


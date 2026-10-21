# Arquitectura propuesta

**Estado:** propuesta de la Fase 0, pendiente de aprobación. Nada de esto está implementado.
Las firmas de código son de diseño y pueden ajustarse al implementar, siempre documentándolo.

## 1. Principios

1. **Núcleo puro, bordes con E/S.** Las fórmulas (devig, EV, Kelly, Dixon-Coles, combinadas y
   CLV) son funciones puras, sin red ni base de datos, y se prueban con casos calculados a mano.
   La red, la BD y la CLI son adaptadores alrededor de ese núcleo.
2. **Todo dato lleva origen y hora.** Cada cuota guarda el proveedor, la casa canónica, la hora
   de captura (UTC) y el `last_update` que da el proveedor.
3. **Deporte, mercado y casa son datos, no `if/else`.** Viven en registros tipados
   ([ADR 005](decisiones/005-deporte-y-mercado-como-registros.md)). Añadir un mercado o un
   deporte consiste en registrar su especificación, sin tocar el flujo.
4. **Proveedores intercambiables.** El resto del sistema solo conoce el protocolo `OddsProvider`
   y los modelos canónicos ([ADR 001](decisiones/001-proveedor-de-cuotas-inicial.md)).
5. **Persistencia detrás de repositorios**
   ([ADR 004](decisiones/004-persistencia-sqlite-repositorios.md)).
6. **Nada se presenta como lo que no es.** La cuota de un feed no español nunca se muestra como
   la de la web .es ([ADR 003](decisiones/003-registro-de-casas-y-jurisdiccion.md)).
7. **El sistema nunca coloca apuestas** ni guarda credenciales de casas. No existe ningún módulo
   capaz de iniciar sesión en una casa.

## 2. Estructura de carpetas

Entre corchetes, la fase que introduce cada parte.

```
tipster-cuotes/
├── README.md
├── pyproject.toml              [F1] uv, ruff, mypy, pytest
├── uv.lock                     [F1]
├── .python-version             [F1] 3.12
├── .env.example                [F1] variables sin valores reales
├── .gitignore                  [F0]
├── .pre-commit-config.yaml     [F1] gitleaks + ruff
├── .github/workflows/ci.yml    [F1] lint, tipos, tests y escaneo de secretos
├── docs/
│   ├── PLAN.md · ARQUITECTURA.md · BACKLOG.md
│   ├── fase-0/verificacion-proveedores.md
│   └── decisiones/NNN-titulo.md
├── src/tipster/
│   ├── config.py               [F1] Settings (pydantic-settings, lee .env)
│   ├── domain/                 [F1] modelos canónicos, sin E/S
│   │   ├── sports.py           SportSpec, CompetitionSpec y su registro
│   │   ├── markets.py          MarketSpec (1X2, O/U 2.5, BTTS) y su registro
│   │   ├── bookmakers.py       BookmakerSpec (jurisdicción, rol, ¿web .es?) y su registro
│   │   └── models.py           Event, OddsQuote, Opportunity (pydantic)
│   ├── pricing/                [F1] matemáticas puras
│   │   ├── devig.py            multiplicativo, aditivo, power y Shin
│   │   ├── value.py            cuota justa y EV
│   │   └── classify.py         value / posible error / revisión manual / descartada
│   ├── providers/              [F1]
│   │   ├── base.py             protocolo OddsProvider y tipos de petición/respuesta
│   │   ├── http.py             httpx + caché + rate limit + reintentos + registro de créditos
│   │   └── the_odds_api/       client.py, schemas.py (JSON del proveedor), mapping.py
│   ├── storage/                [F1]
│   │   ├── db.py               conexión y aplicación de migraciones
│   │   ├── migrations/         0001_inicial.sql, ...
│   │   └── repositories.py     protocolos + implementación SQLite
│   ├── services/scan.py        [F1] orquestación de `tipster scan`
│   ├── cli/                    [F1] app.py (Typer) y render.py (tablas + aviso de juego responsable)
│   ├── history/                [F2] football_data.py: descarga con caché y parseo
│   ├── models/                 [F2] dixon_coles.py, elo.py, calibration.py
│   ├── evaluation/             [F2] metrics.py (Brier, log-loss), walk_forward.py
│   ├── staking/                [F3] kelly.py, limits.py (topes, pérdida diaria, bankroll)
│   ├── tracking/               [F3] picks.py (registro y liquidación), clv.py
│   ├── combos/                 [F4] builder.py, correlation.py
│   └── backtest/               [F5] engine.py, baselines.py, report.py
├── tests/
│   ├── unit/                   fórmulas y reglas, con casos calculados a mano
│   ├── integration/            proveedor con fixtures, repositorios con SQLite temporal, CLI
│   └── fixtures/               respuestas reales grabadas y saneadas (sin claves)
└── data/                       (ignorado por git) BD SQLite, caché HTTP, CSV descargados
```

## 3. Flujo de `tipster scan` (Fase 1)

```
tipster scan [--competiciones …] [--mercados …] [--max-creditos N]
 1. Settings (.env): umbrales, competiciones, mercados, referencia y método de devig
 2. RunRepository.start("scan")
 3. Para cada competición: OddsProvider.fetch_odds(OddsRequest)
      HttpClient: caché con TTL → rate limit → GET → reintentos con backoff
                  → lectura de créditos en las cabeceras → registro de la petición
      schemas (pydantic) → mapping → Event + OddsQuote
      (casa canónica, selección canónica, solo línea 2.5 en totales)
 4. EventRepository.upsert(eventos) · OddsRepository.add(cuotas con captured_at y source)
 5. Por (evento, mercado): cuotas de la referencia con todas sus selecciones
      (Pinnacle si está fresca; si no, Betfair Exchange) → devig → p_mercado
 6. Por cada cuota de cada casa que no sea de referencia:
      cuota justa = 1 / p_mercado · EV = p_final × cuota − 1 · classify → Opportunity
      (en la Fase 1, p_final = p_mercado: todavía no hay modelo)
 7. render: aviso de juego responsable + tabla + resumen
      (créditos gastados y restantes, cuotas leídas, descartes por motivo)
 8. RunRepository.finish(consumo, estado)
```

## 4. Interfaces clave (Fase 1)

```python
# domain/sports.py
class SportId(StrEnum):
    FOOTBALL = "futbol"            # F6: TENNIS, BASKETBALL

@dataclass(frozen=True)
class CompetitionSpec:
    id: str                        # "laliga", "segunda", "premier", "serie_a", "bundesliga", "ligue_1", "champions"
    sport: SportId
    name: str
    provider_keys: Mapping[str, str]   # {"the_odds_api": "<clave pendiente de nivel A>"}

# domain/markets.py
@dataclass(frozen=True)
class MarketSpec:
    id: str                        # "1x2", "ou_2.5", "btts"
    sport: SportId
    selections: tuple[str, ...]    # ("local", "empate", "visitante") | ("mas", "menos") | ("si", "no")
    line: float | None             # 2.5 en O/U 2.5; None si no aplica
    # Estrategias que se añaden en fases posteriores (registradas, nunca if/else):
    #   F2 probabilities(score_matrix) -> Mapping[str, float]
    #   F3 settle(home_goals, away_goals) -> str
    #   F4 correlation_group: str

# domain/bookmakers.py
class Role(StrEnum):
    SHARP = "sharp"                # referencia (Pinnacle)
    EXCHANGE = "exchange"          # referencia (Betfair Exchange)
    RETAIL = "casa"                # casa en la que se podría apostar

@dataclass(frozen=True)
class BookmakerSpec:
    id: str                        # canónico: "888sport_no_es", "codere_es", "pinnacle"…
    brand: str                     # "888sport"
    jurisdiction: str              # "ES", "UK", "FR", "DE", "NO-ES" (si no se sabe cuál)
    role: Role
    es_site: bool                  # True solo si el feed es el de la web .es con licencia DGOJ
    provider_keys: Mapping[str, str]   # {"the_odds_api": "sport888"}

# domain/models.py (pydantic, inmutables)
class Event(BaseModel):
    id: str                        # canónico (UUID); los ids de cada proveedor van aparte
    sport: SportId
    competition: str
    home_team: str
    away_team: str
    kickoff: AwareDatetime         # UTC

class OddsQuote(BaseModel):
    event_id: str
    bookmaker_id: str
    market_id: str
    selection: str
    price: float                   # cuota decimal > 1
    captured_at: AwareDatetime     # UTC: cuándo la recibimos
    provider_last_update: AwareDatetime | None   # UTC: cuándo la vio el proveedor en la casa
    source: str                    # "the_odds_api"

class Opportunity(BaseModel):
    quote: OddsQuote
    reference_bookmaker_id: str
    devig_method: DevigMethod
    p_market: float
    p_model: float | None          # F2
    p_final: float                 # F1: igual a p_market
    fair_odds: float               # 1 / p_market
    ev: float                      # p_final × price − 1
    stake: float | None            # F3
    label: Label
    reasons: tuple[str, ...]       # p. ej. ("cuota con 14 min de antigüedad",)

# providers/base.py
@dataclass(frozen=True)
class OddsRequest:
    competition: str
    markets: tuple[str, ...]
    bookmakers: tuple[str, ...]    # ids canónicos; el proveedor los traduce

class ProviderUsage(BaseModel):
    provider: str
    requests: int
    cache_hits: int
    credits_spent: int | None      # suma de x-requests-last
    credits_remaining: int | None  # último x-requests-remaining

class OddsBatch(BaseModel):
    events: list[Event]
    quotes: list[OddsQuote]
    usage: ProviderUsage

class OddsProvider(Protocol):
    name: str
    def fetch_odds(self, request: OddsRequest) -> OddsBatch: ...

# pricing/devig.py
class DevigMethod(StrEnum):
    MULTIPLICATIVE = "multiplicativo"   # p_i = q_i / Σq
    ADDITIVE = "aditivo"                # p_i = q_i − (Σq − 1) / n
    POWER = "power"                     # p_i = q_i^k, con k tal que Σ q_i^k = 1
    SHIN = "shin"                       # modelo de Shin (proporción z de apostadores informados)

def devig(odds: Sequence[float], method: DevigMethod) -> tuple[float, ...]:
    """q_i = 1 / cuota_i. Lanza DevigError si hay menos de 2 cuotas, alguna ≤ 1,
    o el método no da probabilidades válidas (p. ej. aditivo con algún p_i < 0)."""

# pricing/value.py
def fair_odds(p: float) -> float: ...                     # 1 / p
def expected_value(p: float, odds: float) -> float: ...   # p × odds − 1

# pricing/classify.py
class Label(StrEnum):
    VALUE = "VALUE"
    POSIBLE_ERROR = "POSIBLE ERROR · RIESGO DE ANULACIÓN"
    REVISION_MANUAL = "REVISIÓN MANUAL"   # se activa cuando exista p_modelo (F2–F3)
    DESCARTADA = "DESCARTADA"
    SIN_VALOR = "SIN VALOR"

@dataclass(frozen=True)
class Thresholds:
    ev_min: float = 0.03
    error_margin: float = 0.15
    max_quote_age: timedelta = timedelta(minutes=10)      # valor provisional
    max_reference_age: timedelta = timedelta(minutes=10)  # valor provisional

def classify(...) -> Classification: ...
# Orden fijo: 1) DESCARTADA (cuota antigua, referencia ausente, incompleta o antigua, cuota inválida)
#             2) REVISIÓN MANUAL (si hay p_modelo y |p_mercado − p_modelo| supera el umbral)
#             3) POSIBLE ERROR (cuota / cuota_justa − 1 > error_margin)
#             4) VALUE (EV ≥ ev_min)
#             5) SIN VALOR
# Las comparaciones con los umbrales usan una tolerancia explícita (1e-9) para que los casos
# frontera no dependan del redondeo en coma flotante.

# storage/repositories.py
class EventRepository(Protocol):
    def upsert(self, events: Sequence[Event], provider: str, external_ids: Mapping[str, str]) -> None: ...

class OddsRepository(Protocol):
    def add(self, run_id: int, quotes: Sequence[OddsQuote]) -> None: ...
    def latest(self, event_id: str, market_id: str) -> list[OddsQuote]: ...

class RunRepository(Protocol):
    def start(self, command: str) -> int: ...
    def finish(self, run_id: int, usage: Sequence[ProviderUsage], status: str) -> None: ...
```

**Cliente HTTP** (`providers/http.py`):
- **Caché** en disco (`data/cache/`), con clave = método + ruta + parámetros ordenados *sin*
  `apiKey`, y TTL configurable. Un segundo `scan` dentro del TTL no gasta créditos.
- **Rate limit** en el cliente: un intervalo mínimo configurable entre peticiones (el límite real
  del proveedor está sin verificar).
- **Reintentos** con backoff exponencial y *jitter* ante errores de red, 429 y 5xx, respetando
  `Retry-After` si llega. Nunca se reintenta un 401/403/422.
- **Consumo:** se leen `x-requests-last` y `x-requests-remaining` de cada respuesta, se guardan
  por petición y por ejecución, y se muestran al final del `scan`.
- **Presupuesto:** antes de cada petición se estima su coste (mercados × grupos de casas). Si
  supera lo que queda de `--max-creditos`, no se hace y se avisa.
- **La clave nunca aparece** en logs, en la caché ni en la BD (se redacta).
- Reloj y `sleep` inyectables para poder probar reintentos y TTL sin esperas reales.

## 5. Modelo de datos (Fase 1)

SQL portable (sin extensiones propias de SQLite). Fechas en texto ISO-8601 con zona UTC.

```sql
runs               (id INTEGER PK, command TEXT, started_at TEXT, finished_at TEXT, status TEXT)
provider_requests  (id INTEGER PK, run_id → runs, provider TEXT, endpoint TEXT,
                    params_redacted TEXT, http_status INTEGER, from_cache INTEGER,
                    cost INTEGER NULL, remaining INTEGER NULL, used INTEGER NULL,
                    requested_at TEXT)
events             (id TEXT PK, sport TEXT, competition TEXT, home_team TEXT,
                    away_team TEXT, kickoff_utc TEXT)
event_external_ids (event_id → events, provider TEXT, external_id TEXT,
                    PRIMARY KEY (provider, external_id))
odds_quotes        (id INTEGER PK, run_id → runs, event_id → events, bookmaker_id TEXT,
                    market_id TEXT, line REAL NULL, selection TEXT, price REAL,
                    captured_at TEXT, provider_last_update TEXT NULL, source TEXT)
-- índice: odds_quotes (event_id, market_id, bookmaker_id, captured_at)
```

Se guardan **todas** las cuotas leídas, no solo las que generan oportunidad: son la materia
prima del CLV (F3) y de cualquier auditoría. Los picks recomendados y sus resultados llegan en
la F3, con su propia tabla.

## 6. Configuración (`.env`)

Valores provisionales; los umbrales definitivos se ajustarán solo con datos de validación (F5).

| Variable | Por defecto | Uso |
|---|---|---|
| `ODDS_API_KEY` | (vacía) | Clave de The Odds API. Obligatoria para un `scan` real. Nunca en git |
| `TIPSTER_DB_PATH` | `data/tipster.sqlite` | Base de datos |
| `TIPSTER_CACHE_DIR` | `data/cache` | Caché HTTP |
| `TIPSTER_CACHE_TTL_SECONDS` | `60` | Vida de la caché (la actualización del proveedor es de ~60 s [B]) |
| `TIPSTER_MAX_CREDITS_PER_RUN` | `30` | Presupuesto máximo por ejecución |
| `TIPSTER_COMPETITIONS` | las 7 | Competiciones a escanear |
| `TIPSTER_MARKETS` | `1x2,ou_2.5` | Mercados (BTTS fuera hasta tener fuente: D5) |
| `TIPSTER_REFERENCE` | `pinnacle` | Referencia; respaldo `betfair_ex` (D2) |
| `TIPSTER_DEVIG_METHOD` | `multiplicativo` | Provisional: el más simple. El método final se elegirá por log-loss en validación (F2) |
| `TIPSTER_EV_MIN` | `0.03` | EV mínimo de un value |
| `TIPSTER_ERROR_MARGIN` | `0.15` | Margen sobre la cuota justa para marcar posible error |
| `TIPSTER_MAX_QUOTE_AGE_MINUTES` | `10` | Antigüedad máxima de una cuota |
| `TIPSTER_MAX_REFERENCE_AGE_MINUTES` | `10` | Antigüedad máxima de la referencia |
| `TIPSTER_SHOW_NON_ES_FEEDS` | según D1 | Mostrar o no feeds no españoles (siempre etiquetados) |
| `TIPSTER_TIMEZONE` | `Europe/Madrid` | Solo para mostrar horas; en BD todo va en UTC |

En la F3 se añaden el bankroll, la fracción de Kelly, el tope por apuesta, la exposición diaria
y la pérdida diaria máxima.

## 7. Calidad y seguridad

- **ruff** (lint y formato) y **mypy `--strict`** sobre `src/` y `tests/`.
- **pytest**: unitarios para la lógica pura, integración con SQLite temporal y fixtures
  grabadas. Las invariantes (suma 1, orden de probabilidades, identidad con un libro sin margen)
  se prueban con parametrización de pytest, sin dependencias extra.
- **CI (GitHub Actions)** en cada push y PR: `uv sync --locked`, `ruff check`,
  `ruff format --check`, `mypy`, `pytest` y **gitleaks** (escaneo de secretos). Las acciones se
  fijan por SHA.
- **pre-commit** opcional en local, con gitleaks y ruff.
- **Secretos** solo en `.env`, ignorado por git; `.env.example` sin valores. Las fixtures se
  sanean antes de commitearlas (sin claves ni cabeceras de autenticación).

## 8. Cómo se extiende

- **Nuevo proveedor** (p. ej. OddsPapi): implementar `OddsProvider` en
  `providers/<nombre>/`, añadir sus claves a los registros de casas y competiciones, y escribir
  sus tests de parseo con una fixture real. Nada más cambia. Hará falta casar sus eventos con los
  de otros proveedores (competición + hora de inicio con tolerancia + equipos normalizados):
  `event_external_ids` existe para eso.
- **Nuevo mercado:** registrar su `MarketSpec` (selecciones, línea y, según la fase, cómo se
  calcula desde la matriz de goles, cómo se liquida y su grupo de correlación). Un test recorre
  el registro y falla si falta alguna estrategia obligatoria.
- **Nuevo deporte** (F6): `SportSpec`, sus competiciones y mercados, y un modelo que implemente
  el protocolo de probabilidad de ese deporte (en fútbol, la matriz de goles; en tenis será
  otra cosa). El flujo de `scan`, la clasificación, el stake y las combinadas no cambian.

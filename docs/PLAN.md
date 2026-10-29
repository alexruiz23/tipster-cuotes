# Plan por fases (afinado en la Fase 0)

**Estado:** aprobado. D1–D7 confirmadas (§3); la Fase 1 sigue [docs/fase-1/plan.md](fase-1/plan.md).
Base: [verificación de proveedores](fase-0/verificacion-proveedores.md) ·
[arquitectura](ARQUITECTURA.md) · [decisiones](decisiones/README.md).

## 0. Estado real de la puerta de salida de la Fase 0

**La puerta de salida de la Fase 0 no se cumplió.** La fase solo produjo documentación y
`.gitignore`; al no haber código, no hay tests, ruff, mypy ni CI que ejecutar, así que esos
cuatro requisitos no aplican y no se pueden dar por cumplidos. Sí se cumplieron el README
actualizado y el push a `main`. La CI (ruff, mypy, pytest y gitleaks) se crea en el **primer
commit de la Fase 1** y desde ese momento la puerta se aplica completa.

## 1. Reglas de trabajo (resumen)

- Plan antes que código: cada fase empieza con su propuesta (carpetas, módulos, interfaces,
  tests y criterios de aceptación) y no avanza sin tu OK.
- **Puerta de salida** de cada fase: tests en verde, ruff y mypy limpios, CI en verde, README
  actualizado, push a `main` e informe corto (qué funciona y con qué comando, qué falla, qué
  decidí yo y qué decides tú).
- Commits pequeños, uno por cambio lógico, en español y con prefijo convencional (`feat:`,
  `test:`, `docs:`, `ci:`, `chore:`). En la lógica crítica, el commit del test va antes que el
  de la implementación.
- Cada fórmula tiene al menos un test con un caso calculado a mano.
- Cero invención: lo no comprobado se marca NO VERIFICADO. Las decisiones no triviales van a
  `docs/decisiones/` y lo que quede fuera de alcance, a `docs/BACKLOG.md`.

## 2. Bloqueos y lo que necesito

| Necesito | Para qué | Fase |
|---|---|---|
| Permitir en la red de este entorno `api.the-odds-api.com` y `the-odds-api.com` | Verificación de nivel A y `scan` real | F1 |
| `ODDS_API_KEY` (el plan gratuito basta para desarrollar), como secreto del entorno y nunca en git | `scan` real y fixture grabada | F1 |
| Permitir `www.football-data.co.uk` | Descargar el histórico | F2 (y verificación previa) |
| Opcional: clave gratuita de OddsPapi y permitir `oddspapi.io` | Verificar feeds .es | F1b |
| Opcional: permitir `www.ordenacionjuego.es` | Confirmar las licencias DGOJ en el registro oficial | F1 |

Sin red ni clave puedo construir y probar toda la F1 con fixtures, pero no cerrarla: tres
criterios de aceptación exigen llamadas reales (ver §4.5).

*(Superado: la Fase 1 se cerró el 2026-10-29 con red y clave en la máquina local del usuario.
Los bloqueos de esta tabla siguen vigentes solo para `www.football-data.co.uk` y los opcionales.)*

## 3. Decisiones (confirmadas el 2026-10-21)

| # | Decisión | Estado | Qué se hace |
|---|---|---|---|
| D1 | Feeds no españoles | CONFIRMADA (a) | Se muestran siempre etiquetados «FEED NO-ES · VERIFICA LA CUOTA EN LA WEB .ES»; Fase 1b con OddsPapi en cuanto se verifique |
| D2 | Referencia para el devig y el CLV | CONFIRMADA (c) | Pinnacle si está fresca; si no, Betfair Exchange. Cada pick indica la referencia usada |
| D3 | Plan de The Odds API | CONFIRMADA | Gratuito en F1–F2; se vuelve a decidir en la F3 |
| D4 | Dónde se hacen las llamadas reales | A, provisional. **Cumplida el 2026-10-29 en la máquina local del usuario, no en el entorno gestionado** | En este entorno, cuando estén abiertos los dominios y definida `ODDS_API_KEY`. Si al empezar una sesión siguen bloqueados o falta la clave, se trabaja como B: fixtures y sin cerrar la Fase 1 |
| D5 | Ambos Marcan | CONFIRMADA (a) | Solo como salida del modelo hasta tener una fuente de cuotas verificada |
| D6 | Champions | CONFIRMADA (a) | Solo con p_mercado y etiqueta «SIN MODELO» hasta tener histórico verificado |
| D7 | Persistencia | A | `sqlite3` de la librería estándar + repositorios, sin SQLAlchemy. Se revisa en F2–F3 solo si el acceso a datos se complica |

Además, para la Fase 1: **P1** (tabla `picks` desde la F1) y **P2** (`tipster scan --offline DIR`,
con la salida marcada «DATOS GRABADOS, NO EN VIVO») aprobadas.

## 4. Fase 1 — MVP: `tipster scan`

> **Sustituido por [docs/fase-1/plan.md](fase-1/plan.md)**, el plan aprobado de la Fase 1. Este
> apartado queda como la propuesta original de la Fase 0; donde difieran, manda el plan nuevo.

### 4.1 Objetivo

`tipster scan` lee de The Odds API las cuotas de 1X2 y O/U 2.5 de las competiciones
configuradas y las guarda con su hora de captura y su origen. Después calcula la probabilidad
justa de la referencia con el método de devig elegido, calcula el EV de cada cuota de cada casa
y la clasifica. Todavía no hay modelo propio (p_final = p_mercado) ni stake (llega en la F3).

### 4.2 Alcance

**Entra:** estructura del proyecto (uv, ruff, mypy, pytest), CI con escaneo de secretos,
`.env.example`, registros de deporte, mercado, casa y competición, modelos pydantic, devig (4
métodos), cuota justa, EV, clasificación, cliente HTTP (caché, rate limit, reintentos y registro
de créditos), proveedor The Odds API, SQLite con repositorios, `tipster scan` y el aviso de
juego responsable en la CLI.

**No entra:** modelo propio, p_final mezclada, Kelly, registro de picks, CLV, combinadas,
backtest, BTTS (D5), OddsPapi (F1b), Telegram y dashboard.

### 4.3 Módulos e interfaces

Los de la F1 en [ARQUITECTURA §2 y §4](ARQUITECTURA.md): `config`, `domain/*`, `pricing/*`,
`providers/*`, `storage/*`, `services/scan.py` y `cli/*`.

Salida de `tipster scan` (una fila por oportunidad VALUE, POSIBLE ERROR o REVISIÓN MANUAL; el
resto se resume en contadores): partido · mercado · selección · casa (con jurisdicción del
feed) · cuota · cuota justa · p_modelo («—» hasta la F3) · p_mercado · EV% · stake («—» hasta
la F3) · etiqueta · hora de captura y antigüedad. Al final: créditos gastados y restantes,
cuotas leídas y descartes por motivo.

### 4.4 Tests (con casos calculados a mano)

Caso base: cuotas 1X2 de la referencia **2.00 / 3.50 / 4.00** → q = 1/2, 2/7 y 1/4 → Σq = 29/28.

| Área | Casos |
|---|---|
| Devig multiplicativo | p = 14/29, 8/29, 7/29 (0.482759 / 0.275862 / 0.241379) |
| Devig aditivo | p = 41/84, 23/84, 20/84 (0.488095 / 0.273810 / 0.238095). Con 1.40 / 2.90 / 100.0 da p₃ < 0 → `DevigError` |
| Devig power y Shin | Valor resuelto por bisección independiente y documentado en el propio test, más comprobación de la restricción (Σ q_i^k = 1; Σ p_i = 1 en Shin) |
| Invariantes (los 4) | Σp = 1; 0 < p < 1; se conserva el orden; un libro sin margen (Σq = 1) devuelve q; error con menos de 2 cuotas o con alguna ≤ 1 |
| Cuota justa y EV | cuota justa del local = 29/14 ≈ 2.0714. EV con 2.10 = +1.38 % (SIN VALOR), con 2.20 = +6.21 % (VALUE) y con 2.40 = +15.86 % (POSIBLE ERROR) |
| Fronteras de la clasificación | VALUE desde la cuota 1.03 × 29/14 ≈ 2.13357 (EV = 3 % exacto, incluido). POSIBLE ERROR por encima de 1.15 × 29/14 ≈ 2.38214. Antigüedad igual al máximo: válida; un segundo más: DESCARTADA. Referencia incompleta o antigua: DESCARTADA |
| Mercados | 1X2 completo; en totales solo vale la línea 2.5 (una 2.25 se ignora); las selecciones de `h2h` se asignan a local/empate/visitante por el nombre del equipo |
| Proveedor | Parseo de una fixture real (grabada en cuanto haya red y clave); casa desconocida → se ignora con aviso; `last_update` y hora de captura en UTC |
| Cliente HTTP | Reintenta 429/5xx con backoff (sleep falso); no reintenta 401/422; un acierto de caché no gasta créditos; lectura de cabeceras de consumo; la clave nunca aparece en logs, caché ni BD; el presupuesto corta antes de pasarse |
| Repositorios | Ida y vuelta de cuotas con hora UTC; `upsert` de eventos idempotente; consumo por ejecución guardado |
| Servicio y CLI | Con un proveedor falso: clasificación esperada, descartes por antigüedad, feeds no-ES etiquetados (D1). La CLI muestra el aviso de juego responsable y termina con código 0 |

### 4.5 Criterios de aceptación

1. `uv sync --locked`, `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` y
   `uv run mypy` limpios.
2. CI en verde en `main` (calidad + gitleaks).
3. Los 4 métodos de devig con al menos un caso calculado a mano cada uno y las invariantes; EV
   y clasificación con tests en las fronteras.
4. **[requiere red y clave]** `tipster scan` contra la API real muestra la tabla de §4.3 y el
   resumen de créditos de esa ejecución.
5. Toda cuota guardada tiene `captured_at` (UTC), `provider_last_update` y `source`.
6. **[requiere red y clave]** Repetir `scan` dentro del TTL gasta 0 créditos (comprobado en el
   registro de consumo).
7. Sin secretos en el repo (gitleaks en CI); `.env.example` documentado.
8. README con instalación, configuración, uso y aviso de juego responsable.
9. **[requiere red y clave]** Verificación actualizada a nivel A: claves de las competiciones,
   casas por liga, líneas de totales y frescura de Pinnacle y Betfair Exchange.

### 4.6 Orden de trabajo (commits previstos)

1. `chore: estructura del proyecto con uv, ruff, mypy y pytest`
2. `ci: calidad (ruff, mypy, pytest) y escaneo de secretos con gitleaks`
3. `chore: .env.example y pre-commit`
4. `feat(domain): registros de deporte, competición, mercado y casa`
5. `test(pricing)` → `feat(pricing)`: devig multiplicativo y aditivo
6. `test(pricing)` → `feat(pricing)`: devig power y Shin
7. `test(pricing)` → `feat(pricing)`: cuota justa, EV y clasificación
8. `feat(storage): esquema SQLite y repositorios`
9. `feat(providers): cliente HTTP con caché, rate limit, reintentos y consumo`
10. `feat(providers): The Odds API`
11. `feat(cli): tipster scan con aviso de juego responsable`
12. `test(providers): fixture real saneada` **[requiere red y clave]**
13. `docs: verificación de nivel A y README de la Fase 1`

Los pares test → implementación se suben juntos, así la CI se ejecuta en verde sobre el último
commit.

## 5. Fase 1b (propuesta, depende de D1) — segundo proveedor con feeds .es

OddsPapi detrás del mismo `OddsProvider`, solo si la verificación de nivel A confirma sus
identificadores .es. Incluye casar eventos entre proveedores (competición + hora de inicio con
tolerancia + nombres de equipo normalizados). **Aceptación:** `scan` muestra cuotas de webs
.es junto a la referencia, con fixture real de cada proveedor y tests de emparejamiento.

## 6. Fase 2 — Histórico y modelos

- `history/football_data.py`: descarga con caché de los CSV de las 6 ligas, parseo validado con
  pydantic y normalización de nombres de equipo.
- `models/dixon_coles.py`: ataque y defensa por equipo, ventaja de campo, decaimiento temporal
  (vida media configurable) y corrección ρ de marcadores bajos. Matriz de goles → 1X2, O/U 2.5 y
  BTTS a través de los `MarketSpec`.
- `models/elo.py`: Elo como segundo modelo. Cómo convertir Elo en 1X2 (el Elo no da probabilidad
  de empate por sí solo) se decidirá en un ADR antes de implementarlo.
- `models/calibration.py`: isotónica y Platt, ajustadas solo con datos de validación.
- `evaluation/metrics.py` (Brier y log-loss multiclase, tabla de fiabilidad) y
  `evaluation/walk_forward.py` (particiones temporales sin fuga de datos).
- **Tests:** suma 1 de la matriz de goles; corrección ρ a mano en 0-0, 1-0, 0-1 y 1-1; mercados a
  mano desde una matriz 3×3; actualización Elo a mano; Brier y log-loss a mano; un test que
  falla si alguna fecha de entrenamiento no es anterior a todas las de predicción.
- **Aceptación:** informe reproducible por liga que compara Dixon-Coles, Elo y la probabilidad
  del mercado (cierre de Pinnacle sin margen, hasta 2024/25) en temporadas de test. Si el
  mercado gana a los modelos, el informe lo dice tal cual. Se lanza con
  `uv run python -m tipster.evaluation` (en la F5 pasa a `tipster report`).
- **Limitaciones ya conocidas:** sin BTTS en el histórico, sin Champions y sin Pinnacle fiable
  desde el 23/07/2025.

## 7. Fase 3 — Probabilidad final, stake, picks y CLV

> **Cerrada (2026-10-29): implementada y validada con datos pasados.** Pendiente de paper trading en
> vivo para ROI y CLV (el histórico no tiene cuotas de otras casas ni cuotas tomadas). Resultados en el
> [ADR 012](decisiones/012-fase-3-probabilidad-stake-clv.md).

- **Resultado (ADR 012):** la validación 2021/22–2022/23 da `w = 1`, es decir `p_final = p_mercado`.
  El proyecto es un detector de valor frente a la referencia de Pinnacle, no un modelo que bate al
  mercado; Dixon-Coles queda congelado. Lo que sigue describe el diseño general.
- `p_final = w · p_mercado + (1 − w) · p_modelo`, con w configurable y más peso al mercado por
  defecto. «REVISIÓN MANUAL» cuando |p_mercado − p_modelo| supere un umbral.
- Kelly fraccionado: f* = (p·o − 1)/(o − 1). Caso a mano: p = 0.5 y o = 2.20 → f* = 1/12; con
  1/4 de Kelly, 2.08 % del bankroll; con tope del 2 %, se queda en el 2 %.
- Tope por apuesta, exposición diaria, bankroll y pérdida diaria máxima. Si se alcanza un
  límite, ese día no se recomienda nada más (test obligatorio).
- Registro en BD de cada pick recomendado, liquidación con el resultado y CLV =
  cuota_tomada × p_cierre_justa − 1. Caso a mano: 2.20 contra un cierre justo de 2.00 → +10 %.
- **A decidir en la propuesta de la F3:** cómo capturar el cierre (ejecución programada cerca
  del inicio y qué parámetros de filtrado ofrece la API), la fuente de resultados (`/scores` de
  The Odds API o football-data.co.uk) y el plan de pago (D3).

## 8. Fase 4 — Combinadas (`tipster combos`)

- Solo patas con EV > 0; nunca dos del mismo partido ni mercados correlacionados (grupo de
  correlación en el registro de mercados), salvo que se modele la correlación.
- Probabilidad = producto (independencia); cuota = producto, en una sola casa que ofrezca todas
  las patas. De 2 a 4 patas, probabilidad mínima configurable (~20 %), orden por EV y varianza.
- Se muestra siempre el EV de la combinada frente al de jugar las patas en simple; la forma
  exacta de compararlos (por unidad apostada y con varianza) se fija en un ADR de la F4.
- **Tests:** combinadas de 2 y 3 patas a mano, exclusión por correlación, restricción de una
  sola casa y filtro de probabilidad mínima.

## 9. Fase 5 — Backtest walk-forward, baselines y report

- Apuestas simuladas a cuota de precierre del histórico, CLV contra el cierre y resultado real.
- Baselines obligatorios: «siempre al favorito» y «al azar» (con semilla y muchas réplicas).
- Métricas: ROI, yield, CLV medio con intervalo de confianza, drawdown máximo, Brier y número de
  apuestas, con aviso explícito si la muestra es pequeña.
- Umbrales y pesos ajustados solo en validación; el tramo final de test no se toca hasta el
  final.
- El informe declara siempre las limitaciones: las cuotas del histórico no son cuotas que
  hubieras podido coger, sus horas son aproximadas y Pinnacle no es fiable desde el 23/07/2025.
- `tipster backtest --from --to` y `tipster report`.

## 10. Fase 6 (opcional)

API/dashboard, Telegram, tenis y baloncesto. Antes de publicar recomendaciones (Telegram) hay
que revisar la normativa española de comunicaciones comerciales del juego (NO VERIFICADO; ver
[BACKLOG](BACKLOG.md)).

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
uv run tipster clv                 # CLV de los picks con cierre fiable
```

`tipster scan` muestra, por cada oportunidad: partido, mercado, selección, casa (con la
jurisdicción de su feed), cuota, cuota justa, p_modelo («—»: con `w = 1` no se usa), p_mercado, EV, stake
(1/4 de Kelly con tope del 2 %, solo en los VALUE), etiqueta, referencia usada y hora de captura. Etiquetas:

- **VALUE**: EV de al menos el mínimo configurado (3 % por defecto).
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
- **Backup:** no se hace en la Fase 1; se decidirá en la Fase 3.

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

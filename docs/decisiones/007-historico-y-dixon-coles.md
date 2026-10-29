# 007 — Histórico (dataset de Hugging Face), referencia de mercado, Dixon-Coles, Elo y validación walk-forward

**Estado:** Aceptada (2026-10-29) · **Fecha:** 2026-10-29

Aceptada por el usuario el 2026-10-29 con tres condiciones: 9 temporadas con mercado (2016/17 a
2024/25), solo 1X2 y una sola referencia de cierre. Datos verificados en la
[verificación §15](../fase-0/verificacion-proveedores.md#15-verificación-de-nivel-a-del-dataset-eatpizzanotsoccer-dataset-fase-2-2026-10-29).
La ingesta (sección 2) está implementada; Dixon-Coles y Elo, no.

**Historial de este ADR.** La primera versión descargaba los CSV de football-data.co.uk. Se
descartó el 2026-10-29 porque sus términos limitan el uso a «private individuals only, NOT
commerical or data training products using automated bots/scrapers/AI» (verificación §14.4). Esta
versión toma la fuente histórica de un dataset de Hugging Face. No hay descargador de CSV.

## Contexto

La Fase 2 (PLAN §6) construye el histórico, **dos modelos, Dixon-Coles y Elo (este como segundo
modelo)**, y una evaluación sin fuga de datos que compara ambos con la probabilidad del mercado.
Lo observado en el dataset (verificación §15) condiciona el diseño:

- Tiene resultados de las 6 ligas desde 2010/11 y la Champions, pero **cuotas solo desde 2016/17**
  (0 filas en 2010/11 a 2015/16) y en la Champions desde 2020/21, con cobertura parcial.
- La tabla `odds` es **solo 1X2**: una fila por casa y partido, sin O/U 2.5, sin Betfair Exchange
  relevante (86 filas en todo el dataset) y sin `Max`/`Avg`.
- El cierre de Pinnacle procede de **API-Football** (`source = API-Football-closing`), no de
  football-data.co.uk. Cubre el 96,3 % de los partidos jugados de las 6 ligas entre 2016/17 y
  2024/25 (21 035 de 21 843, contando duplicados).
- `known_at` de las cuotas es **igual a la hora del partido** en todas las filas observadas: no es
  la hora real de captura de la cuota.
- Hay **entidades de equipo duplicadas** (por ejemplo «Ath Bilbao» e «Athletic Club» en LaLiga
  2024/25), que duplican 38 partidos de esa temporada.

## 1. Fuente histórica y licencia

### Opciones
1. CSV de football-data.co.uk (descartada: términos de uso, ver arriba).
2. Dataset de Hugging Face `eatpizzanot/soccer-dataset`.
3. Histórico de pago de The Odds API u otra API (no evaluadas).

### Decisión: la 2 (decidida por el usuario el 2026-10-29)
- **Fuente:** `https://huggingface.co/datasets/eatpizzanot/soccer-dataset`. Tablas usadas:
  `fixtures`, `odds`, `leagues` y `teams` (≈16 MB en Parquet). El resto (alineaciones, jugadores,
  `xg_training`…) no se usa.
- **Licencia:** CC-BY-4.0 según la ficha del dataset y la etiqueta `license:cc-by-4.0` de su API.
  Exige atribución.
- **Atribución obligatoria** (la ficha dice «cite API-Football and football-data.co.uk»; se añade el
  autor del dataset). Va en el README y en cada informe que use estos datos:
  *«Datos: eatpizzanot/soccer-dataset (CC-BY-4.0), compilado a partir de API-Football y
  football-data.co.uk.»*
- **Versión fijada:** la ingesta registra el `sha` de la revisión del dataset (hoy
  `f0cbe86bee3f28cc4b803f735a5287968741c471`, 2026-07-05) y el `sha256` de cada Parquet, de modo que
  cada informe dice con qué versión se hizo.
- **Ingesta:** desde los Parquet (descarga con `huggingface_hub` o `datasets`, o HTTP directo), con
  caché local en `data/raw/hf_soccer/` (ignorado por git). No hay descarga de CSV ni scraping.

### Riesgo legal que esta decisión NO elimina (NO VERIFICADO)
- La licencia CC-BY-4.0 es la que pone **quien compila** el dataset. El propio dataset declara que
  mezcla datos de football-data.co.uk y de API-Football. Una etiqueta CC-BY del compilador no puede
  conceder derechos que no tiene sobre datos de terceros.
- En las 7 competiciones, 10 011 de 38 489 partidos jugados llevan `merged_football_data = true`, y
  las 8 849 cuotas de Bet365 proceden de `source = CSV` (es decir, de football-data.co.uk). Las
  cuotas de Pinnacle proceden de API-Football, cuyos términos **no se han revisado**.
- Esto no se puede cerrar con una lectura de la ficha. Queda como pregunta abierta (BACKLOG nº 19) y
  la respuesta del autor de football-data.co.uk sigue siendo relevante. **Mitigación de diseño:** el
  modelo no usa las cuotas como entrada y el ingestor filtra por `source`, así que excluir las filas
  `CSV` es un cambio de una línea si hiciera falta.

## 2. Almacenamiento en SQLite (migración `0002_historico.sql`, implementada)

La primera versión de este ADR proponía cuotas en formato largo y cuatro tablas. Se implementó
una versión más simple, a petición del usuario: solo se guarda el cierre de Pinnacle, así que va
en columnas del propio partido.

```
teams              (id, name)                      -- id del dataset ya canónico
historical_matches (id, competition_id, match_date,   -- AAAA-MM-DD, sin hora
                    home_team_id, away_team_id, home_goals, away_goals,
                    pinnacle_home, pinnacle_draw, pinnacle_away,   -- NULL si no hay cuota
                    odds_source,                      -- columna `source` del dataset
                    source_fixture_id, run_id,        -- trazabilidad (fixtures.id; ejecución)
                    UNIQUE (competition_id, match_date, home_team_id, away_team_id))
```
- **Solo 1X2 de Pinnacle.** Las demás casas (Bet365, etc.) no se guardan; con ello tampoco entra
  ninguna cuota de `source = CSV` (football-data.co.uk). Una cuota ≤ 1 cuenta como ausente. Si el
  partido tiene varias filas de Pinnacle se prefiere `API-Football-closing`.
- **Un partido sin cuota de Pinnacle se guarda igual,** con las tres columnas y `odds_source` a
  `NULL` (una restricción `CHECK` obliga a que sean todas nulas o ninguna). Sirve para entrenar, y
  solo se descarta al comparar con el mercado.
- **Fecha:** solo el día. No se guarda hora de partido ni `known_at`, ni se inventa una hora de
  captura para el histórico.
- **Solo partidos jugados** de las 6 ligas (`leagues.fd_code` E0, SP1, SP2, I1, D1, F1). La
  Champions no se carga todavía.
- **Rango:** `tipster ingest --from A --to B` carga las fechas entre el 1 de agosto de A y el 31 de
  julio de B+1. No hay columna `season` (el corte de agosto parte mal las temporadas terminadas en
  agosto de 2020).
- **Duplicados de equipo:** `src/tipster/history/team_aliases.csv` (a mano, 13 filas) lleva
  `alias_id, alias_name, canonical_id, canonical_name`. Si un id del fichero tiene otro nombre en
  el dataset, la carga **falla** (los ids habrían cambiado). Los alias salieron de buscar, por liga,
  partidos del mismo día y marcador con un equipo en común y el otro distinto.
- **Colapso de copias:** tras unificar equipos, dos filas son el mismo partido si coinciden
  competición, local y visitante y sus fechas distan **como mucho un día** (el CSV de origen a veces
  fecha un día antes). Si discrepan en el marcador, la carga falla con los dos ids. De cada grupo
  se conserva la copia de **fecha más tardía**, por prudencia: nunca da un resultado por conocido
  antes de tiempo. La cuota se toma de la primera copia del grupo que la tenga.
- **Carga idempotente:** `INSERT … ON CONFLICT DO UPDATE` y una transacción; ejecutarla dos veces
  deja las mismas filas. Cada ejecución queda en `runs` (`command = ingest`) con la revisión del
  dataset y el sha256 de cada Parquet.
- **Crudos y trazabilidad:** los Parquet van a `data/raw/huggingface/<revisión[:12]>/` (ignorado
  por git) con un fichero `<nombre>.parquet.sha256`. La revisión está fijada, así que no se
  vuelven a descargar; si el sha256 de un fichero cambia en disco, la ingesta falla.
- **Fixtures de test:** Parquet sintéticos e inventados creados en el propio test.
- **Dependencia nueva:** `pyarrow` (lectura de Parquet). Es la mínima que hace falta.

### Resultado de la ingesta real (2026-10-29, revisión `f0cbe86…`, `--from 2016 --to 2025`)
24 216 partidos leídos, 1 572 duplicados eliminados y **22 644 cargados**, de los que 21 971
(97,0 %) tienen el cierre de Pinnacle completo. Fechas del 2016-08-12 al 2026-06-20. Por temporada,
el porcentaje con Pinnacle es del 98,8 % al 100 % entre 2016/17 y 2024/25 y del 72,9 % en 2025/26.

## 3. Referencia de mercado y la ruptura de Pinnacle

### Qué cambia respecto al dataset
- **Solo hay una referencia: el cierre de Pinnacle en 1X2.** No hay Betfair Exchange, `Avg` ni
  `Max`, y por tanto **no hay baseline de mercado para O/U 2.5**. La Fase 2 compara con el mercado
  únicamente el 1X2. El O/U 2.5 de Dixon-Coles se evalúa solo contra los resultados (Brier y
  log-loss del propio modelo), sin comparación con el mercado.
- **Tramo con mercado:** 2016/17 a 2024/25 (9 temporadas por liga). Son 4 menos que las 13 que
  suponía la primera versión de este ADR.

### Decisión
- **El corte seguro sigue siendo 2024/25 para la comparación con el mercado.** Ese es el último
  tramo con Pinnacle completo en esta fuente (96 %+ de los partidos).
- **Precisión sobre el entrenamiento.** El corte afecta a la **referencia de mercado**, no a los
  modelos: Dixon-Coles y Elo se entrenan con resultados, y los resultados de 2025/26 son válidos.
  Los modelos pueden entrenar con todo lo anterior a cada fecha de predicción, 2025/26 incluido; lo
  que no se hace es comparar con el mercado a partir de 2025/26.
- **2025/26 y 2026/27:** en el dataset hay cuotas de Pinnacle posteriores al 23/07/2025, pero la
  cobertura cae (217 de 295 partidos en enero de 2026, 162 de 257 en febrero, 64 de 233 en abril y
  1 de 248 en mayo) y si son fiables es **NO VERIFICADO**: el aviso del 23/07/2025 es de
  football-data.co.uk sobre la API pública de Pinnacle y no sabemos qué fuente usa API-Football.
  Esos partidos se excluyen de la comparación y se cuentan en el informe.
- **Nunca se empalman series en silencio.** Cada comparación modelo-mercado usa **una sola
  referencia** sobre el **mismo conjunto de partidos**; los partidos sin cuota se excluyen y se
  cuentan.
- **Champions:** hay cuotas de Pinnacle desde 2020/21, pero solo para el 47-59 % de los partidos.
  Se puede incluir como liga adicional, sin que condicione el diseño.

## 4. Dixon-Coles

### Modelo
Para un partido de local *i* y visitante *j* en una liga:

```
log λ = h + a_i + d_j          goles esperados del local
log μ =     a_j + d_i          goles esperados del visitante
P(x, y) = τ(x, y; λ, μ, ρ) · Poisson(x; λ) · Poisson(y; μ)

τ(0,0) = 1 − λμρ    τ(0,1) = 1 + λρ    τ(1,0) = 1 + μρ    τ(1,1) = 1 − ρ    τ = 1 en el resto
```
`a` es el ataque y `d` la propensión a encajar (más alto = peor defensa).

### Parámetros que se estiman
| Parámetro | Alcance | Notas |
|---|---|---|
| `a_i` ataque | por equipo | restricción `Σ a_i = 0` por liga para que sea identificable |
| `d_i` defensa | por equipo | restricción `Σ d_i = 0` |
| `h` ventaja de campo | uno por liga | |
| `ρ` | uno por liga | corrige los marcadores 0-0, 1-0, 0-1 y 1-1; el rango admisible depende de λ y μ y se comprueba |
| `ξ` decaimiento | hiperparámetro | peso `exp(−ξ·Δt)`, con Δt en días desde el partido hasta la fecha de predicción; se configura como **vida media** (`ln2/ξ`) |
| penalización L2 sobre `a`, `d` | hiperparámetro | acerca a la media de la liga a los equipos con poco historial (ascendidos); valor 0 incluido en la malla |

- **Una liga, un modelo:** no se comparten parámetros entre ligas.
- **Ajuste:** máxima verosimilitud ponderada con `scipy.optimize` (ya es dependencia). Los valores
  de vida media y penalización **no se fijan aquí**: se eligen por malla en el tramo de validación y
  se registran. Cualquier número que aparezca ahora sería una invención.
- **Matriz de marcadores:** hasta 10-10 goles; el test falla si la masa fuera de la matriz es mayor
  que 1e-6; se renormaliza.
- **Mercados:** 1X2 = triángulo inferior, diagonal y superior; O/U 2.5 = P(goles totales ≥ 3);
  BTTS = 1 − P(local 0) − P(visitante 0) + P(0,0). BTTS no se evalúa en la F2: no hay cuotas.
- **Equipos nuevos:** un ascendido sin partidos en la liga entra con ataque y defensa de la media
  (penalización L2). Es una limitación declarada.

### Elo (segundo modelo, dentro del alcance de la Fase 2)

PLAN §6 incluye `models/elo.py` como segundo modelo. Su papel es comparar con Dixon-Coles y con el
mercado y, si los resultados lo justifican, servir de ensamble o de respaldo de Dixon-Coles. **Cómo
se usa en conjunto (ensamble o respaldo) no se diseña aquí:** depende de los resultados de la
comparación y se decide después.

- **Qué fija este ADR:** Elo se alimenta solo de resultados anteriores a la fecha de predicción,
  entra en las mismas reglas de validación (sección 5: mismos tramos, mismos partidos, mismas
  métricas, ninguna cuota como entrada) y se informa junto a Dixon-Coles y el mercado.
- **Hiperparámetros** (factor K, ventaja de campo y rating inicial de los equipos nuevos): se
  eligen en el tramo de validación. No se fija ningún valor aquí.
- **Qué falta y requiere un ADR propio (008) antes de implementar:** cómo convertir la diferencia
  de Elo en probabilidades de 1X2. El Elo no da la probabilidad de empate por sí solo.
- **Tests a mano:** actualización de rating tras un resultado concreto (PLAN §6); la suma de las
  probabilidades 1X2 es 1; y un test que falla si Elo usa un resultado de fecha igual o posterior a
  la que predice.
- **Nota:** `teams.rating_mu` del dataset es un rating Glicko-2 precalculado con un procedimiento
  que no conocemos. **No se usa**: no se puede garantizar que no contenga información posterior a la
  fecha de predicción.

### Tests de Dixon-Coles (casos a mano, como en la F1)
La matriz suma 1; la corrección τ a mano en 0-0, 1-0, 0-1 y 1-1; los tres mercados a mano desde una
matriz 3×3; con ρ = 0 la matriz coincide con dos Poisson independientes.

## 5. Validación walk-forward sin fuga de datos

Reglas, todas con test:

1. **La unidad de tiempo es el día del partido.** Para predecir los partidos de una fecha *D* solo
   se entrena con partidos de fecha **estrictamente anterior** a *D*. Los partidos del mismo día no
   se usan entre sí (hay horas ausentes y la zona horaria de `date_utc` es la que declara el
   dataset). Hay un test que **falla** si alguna fecha de entrenamiento no es anterior a todas las
   de predicción (PLAN §6).
2. **Se reajusta por bloques de jornada** (por ejemplo cada 7 días), con ventana expansiva y pesos
   de decaimiento medidos hasta el inicio del bloque. No se reajusta partido a partido.
3. **Tres tramos separados por fecha,** fijados antes de ver resultados y escritos en el informe:
   calentamiento (solo entrenar), **validación** (se eligen los hiperparámetros) y **prueba** (se
   informa; no se vuelve a tocar nada tras verla). Los tramos con mercado solo pueden caer entre
   2016/17 y 2024/25; qué temporadas van en cada tramo se decide con el usuario con la cantidad
   real de datos limpios.
4. **Las cuotas nunca entran como variable del modelo.** El cierre es lo que se compara; meterlo
   contaminaría la comparación y sería fuga de información. Tampoco se usan `known_at`, `xg` de
   `match_stats` ni `rating_mu` como entradas.
5. **La calibración** (isotónica o Platt) se ajusta solo con predicciones de validación anteriores
   al tramo de prueba, y se aplica después.
6. **Comparación justa:** modelo y mercado se evalúan sobre los **mismos partidos**; los que no
   tienen cuota de Pinnacle o resultado se excluyen y se cuentan en el informe.
7. **Métricas:** Brier multiclase, log-loss y tabla de fiabilidad para el 1X2; para O/U 2.5, solo
   frente a los resultados. Diferencias pareadas modelo-mercado con intervalo por remuestreo por
   jornada. El informe compara Dixon-Coles, Elo y el mercado sobre los mismos partidos; si el
   mercado gana, lo dice tal cual.
8. **Reproducibilidad:** el informe incluye la revisión de Hugging Face, los `sha256` de los
   Parquet, la referencia usada y la semilla; ejecutar dos veces da el mismo resultado.

## Consecuencias globales

- **Riesgo legal abierto** (sección 1): la licencia CC-BY del dataset no resuelve por sí sola los
  términos de football-data.co.uk ni los de API-Football.
- **Dependencia de un tercero:** el dataset es un repositorio de una persona; puede cambiar o
  desaparecer. La caché local con `sha256` evita que un cambio altere un informe ya hecho.
- **Menos mercado del previsto:** 9 temporadas con referencia, una sola referencia y solo 1X2.
- **Calidad de datos:** el dataset necesita un paso de deduplicación de equipos antes de usarse; la
  garantía de calidad que declara («54/54 checks») no lo detecta.
- **Qué no cubre:** BTTS, lesiones/alineaciones, xG ni ligas inferiores.
- **Coste de cómputo:** un ajuste por bloque y liga; con unos 20 equipos y miles de partidos es
  manejable, pero no está medido (NO VERIFICADO).
- **Riesgo conocido:** el mercado probablemente gane a un Dixon-Coles sencillo. El valor de la
  Fase 2 es medirlo con honestidad, no obtener un modelo ganador.

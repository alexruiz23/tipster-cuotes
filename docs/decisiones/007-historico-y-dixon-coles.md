# 007 — Histórico, ruptura de Pinnacle, Dixon-Coles y validación walk-forward

**Estado:** Propuesta (2026-10-29) · **Fecha:** 2026-10-29

Pendiente de dos cosas antes de pasar a *Aceptada*: tu OK a este diseño y la respuesta del autor de
football-data.co.uk sobre sus términos de uso (BACKLOG nº 19). **No se escribe código de la Fase 2
hasta entonces.** Los datos que se citan salen de la
[verificación §14](../fase-0/verificacion-proveedores.md#14-verificación-de-nivel-a-de-football-datacouk-fase-2-2026-10-29).

## Contexto

La Fase 2 (PLAN §6) construye el histórico, un Dixon-Coles y una evaluación sin fuga de datos que
compara el modelo con la probabilidad del mercado. Lo verificado condiciona el diseño:

- Las 6 ligas están en `mmz4281/<temporada>/<E0|SP1|SP2|I1|D1|F1>.csv`, de 1993/94 a 2026/27. No hay
  Champions ni cuotas de Ambos Marcan.
- El cierre de Pinnacle (`PSCH/D/A`) está completo de 2012/13 a 2024/25, a medias en 2025/26 (última
  fecha el 14/01/2026) y ausente en 2026/27. Betfair Exchange (`BFECH/D/A`) existe solo desde
  2024/25. `Max*`/`Avg*` de cierre existen desde 2019/20 y excluyen a Pinnacle desde el 23/07/2025.
- Las fechas vienen en `dd/mm/yy` o `dd/mm/yyyy` según la temporada, hay BOM en unas y no en otras,
  y la zona horaria de la columna `Time` no está verificada.
- Los términos del sitio limitan el uso a «private individuals only, NOT commerical or data
  training products using automated bots/scrapers/AI». Hasta aclararlo, nada de lo de abajo se
  implementa.

## 1. Almacenamiento en SQLite (migración `0002_historico.sql`)

### Opciones
1. Una tabla ancha con una columna por cuota del CSV (`psch`, `psd`, …).
2. Resultados en una tabla y cuotas en formato largo, como `odds_quotes`.
3. Seguir guardando solo los CSV crudos y leerlos al vuelo.

### Decisión: la 2
```
history_files    (id, competition_id, season, url, fetched_at, last_modified, sha256, n_rows, raw_path)
teams            (id, name)                                  -- nombre canónico
team_aliases     (source, raw_name, team_id)  PK (source, raw_name)
historical_matches (
  id, competition_id, season, match_date,                     -- fecha ISO, sin hora
  kickoff_time_raw,                                           -- tal como viene; zona NO VERIFICADA
  home_team_id, away_team_id, fthg, ftag, ftr, hthg, htag,    -- medio tiempo puede ser NULL
  file_id REFERENCES history_files, source_row,               -- trazabilidad hasta la fila del CSV
  UNIQUE (competition_id, season, match_date, home_team_id, away_team_id) )
historical_odds  (
  match_id, bookmaker_code, moment, market_id, selection, price,
  PRIMARY KEY (match_id, bookmaker_code, moment, market_id, selection),
  CHECK (moment IN ('open','close')), CHECK (price > 1) )
```
- **Por qué largo:** las columnas aparecen y desaparecen según la temporada (`BFE*` desde 2024/25,
  `PS*` hasta 2025/26); con filas, una cuota que no existe es una fila que no existe, no un `NULL`
  que alguien puede confundir con un dato. Reutiliza los `market_id` y `selection` de Fase 1.
- **Qué se carga:** solo 1X2 y O/U 2.5 de `PS`, `BFE`, `Max` y `Avg`, apertura y cierre. El resto de
  casas, el hándicap asiático y las estadísticas de partido no se cargan (YAGNI).
- **`bookmaker_code`** conserva el prefijo del CSV (`PS`, `BFE`, `Max`, `Avg`): no se mezcla con los
  `bookmaker_id` de `domain/bookmakers.py`, que son feeds de la API en vivo.
- **Nombres de equipo:** `team_aliases` se rellena con un fichero versionado en el repo (CSV a mano).
  Si el CSV trae un nombre sin alias, la carga **falla con el nombre y la fila**; no hay
  emparejamiento difuso silencioso. Ese mismo fichero servirá en la F3 para enlazar con los nombres
  de The Odds API.
- **Crudos y caché:** el CSV se guarda tal cual en `data/raw/football_data/` (ignorado por git) y se
  descarga de nuevo solo si ha caducado el TTL; se registra su `sha256` y `last_modified`, de modo
  que cada informe puede decir con qué versión de los datos se hizo.
- **Fixtures de test:** sintéticas e inventadas, nunca CSV reales (por los términos del sitio).

### Consecuencias
- La carga es idempotente (`UNIQUE` y `INSERT … ON CONFLICT`); recargar una temporada en curso
  actualiza resultados y cuotas nuevas sin duplicar.
- Una consulta «cierre de Pinnacle de un partido» son 3 filas; es más verboso que una columna, pero
  la ruptura de Pinnacle se ve como ausencia de filas, no como una columna vacía.

## 2. La ruptura de Pinnacle (25/26 en adelante)

### Opciones
1. Usar `Avg*`/`Max*` de cierre como referencia desde 2025/26.
2. Usar Betfair Exchange (`BFEC*`) desde 2025/26.
3. Limitar la evaluación a ≤ 2024/25 y no evaluar lo posterior.
4. Capturar el cierre en vivo con The Odds API (ADR 002; es trabajo de la F3).

### Decisión
- **Evaluación principal (la que decide):** solo con las temporadas en que el cierre de Pinnacle es
  completo, **2012/13 a 2024/25**. Es lo que ya decía PLAN §6.
- **Betfair Exchange como referencia secundaria**, no sustituta, y solo tras comprobarlo: en
  2024/25 hay a la vez `PSC*` y `BFEC*` al 100 % en las 6 ligas. Con esas temporadas se mide cuánto
  se parecen las probabilidades sin margen de ambos (diferencia de log-loss y de Brier del mismo
  modelo contra una y otra referencia). **Criterio de aceptación:** si la diferencia es material, la
  extensión a 2025/26 se marca como no comparable. Qué es «material» se fija **antes** de mirar
  2025/26, en el informe de esa comprobación.
- **2025/26 se informa por separado,** con `BFEC*` como referencia y la etiqueta de su fuente en
  cada fila del informe. `BFECH` baja a ~70 % en abril-mayo de 2026: los partidos sin referencia
  se excluyen y se cuenta cuántos.
- **`Avg*` solo como respaldo marcado** (es una media de casas con margen, y desde el 23/07/2025 ya
  no incluye a Pinnacle: hay ruptura de serie). **`Max*` nunca como probabilidad:** el máximo de
  varias casas no es un libro coherente y no suma 1 tras quitar el margen.
- **2026/27 no se usa para decidir** (63 a 121 partidos por liga a 26/10/2026).
- **Nunca se empalman series en silencio:** cada comparación modelo-mercado usa **una sola
  referencia** sobre el **mismo conjunto de partidos**.

### Consecuencias
- El número de temporadas con referencia *sharp* completa es 13 por liga; con Betfair, 2 completas
  más la actual. Alcanza para evaluar, no para calibrar con Betfair.
- Si la F3 captura cierres en vivo, esos datos propios resolverán el tramo posterior al corte.

## 3. Dixon-Coles

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

- **Una liga, un modelo:** no hay datos de ligas distintas relacionados (sin Champions), así que no
  se comparten parámetros entre ligas.
- **Ajuste:** máxima verosimilitud ponderada con `scipy.optimize` (ya es dependencia). Los valores
  concretos de vida media y penalización **no se fijan aquí**: se eligen por malla en las
  temporadas de validación (sección 4) y se registran. Cualquier número que aparezca ahora sería
  una invención.
- **Matriz de marcadores:** hasta 10-10 goles; se comprueba que la masa fuera de la matriz es
  despreciable (el test falla si la suma es menor que 1 − 1e-6) y se renormaliza.
- **Mercados:** 1X2 = triángulo inferior, diagonal y superior; O/U 2.5 = P(goles totales ≥ 3);
  BTTS = 1 − P(local 0) − P(visitante 0) + P(0,0). Sin cuotas de BTTS en el histórico, BTTS no se
  evalúa en la F2.
- **Equipos nuevos:** un ascendido sin partidos en la liga entra con ataque y defensa de la media
  (penalización L2). Es una limitación declarada; no se carga la segunda división para evitarla.
- **Elo** queda fuera de este ADR: PLAN §6 exige un ADR propio sobre cómo obtener el empate.

### Tests (casos a mano, como en la F1)
La matriz suma 1; la corrección τ a mano en 0-0, 1-0, 0-1 y 1-1; los tres mercados a mano desde una
matriz 3×3; con ρ = 0 la matriz coincide con dos Poisson independientes.

## 4. Validación walk-forward sin fuga de datos

Reglas, todas con test:

1. **La unidad de tiempo es el día del partido.** Para predecir los partidos de una fecha *D* solo
   se entrena con partidos de fecha **estrictamente anterior** a *D*. Los partidos del mismo día no
   se usan entre sí (la zona horaria de `Time` no está verificada). Hay un test que **falla** si
   alguna fecha de entrenamiento no es anterior a todas las de predicción (PLAN §6).
2. **Se reajusta por bloques de jornada** (por ejemplo cada 7 días), con ventana expansiva y pesos
   de decaimiento medidos hasta el inicio del bloque. No se reajusta partido a partido.
3. **Tres tramos separados por fecha,** fijados antes de ver resultados y escritos en el informe:
   calentamiento (solo entrenar), **validación** (se eligen vida media y penalización) y
   **prueba** (se informa; no se vuelve a tocar nada tras verla). Qué temporadas van en cada tramo
   se decide con el usuario cuando se vea la cantidad real de datos limpios.
4. **Las cuotas nunca entran como variable del modelo.** Ni cierre ni apertura: el cierre es lo que
   se compara. Meterlas contaminaría la comparación y sería fuga de información.
5. **La calibración** (isotónica o Platt) se ajusta solo con predicciones de validación anteriores
   al tramo de prueba, y se aplica después.
6. **Comparación justa:** modelo y mercado se evalúan sobre los **mismos partidos**; los que no
   tienen referencia o resultado se excluyen y se cuentan en el informe.
7. **Métricas:** Brier multiclase, log-loss y tabla de fiabilidad para 1X2 (y para O/U 2.5 con la
   cuota de cierre de Pinnacle de `PC>2.5`/`PC<2.5`, donde exista). Diferencias pareadas modelo-mercado con
   intervalo por remuestreo por jornada. Si el mercado gana, el informe lo dice tal cual.
8. **Reproducibilidad:** el informe incluye los `sha256` de los CSV, la referencia usada y la
   semilla; ejecutar dos veces da el mismo resultado.

## Consecuencias globales

- **Bloqueo:** sin respuesta sobre la licencia no se escribe el descargador. Si la respuesta es
  negativa, las alternativas son cambiar de fuente (por ejemplo, el histórico de pago de The Odds
  API, o la API por suscripción que menciona el propio sitio; ninguna evaluada aún) o reducir el
  alcance. Se decidiría en otro ADR.
- **Qué no cubre:** Champions, BTTS, lesiones/alineaciones, xG ni ligas inferiores.
- **Coste de cómputo:** un ajuste por bloque y liga; con unos 20 equipos y miles de partidos es
  manejable, pero no está medido (NO VERIFICADO).
- **Riesgo conocido:** el mercado probablemente gane a un Dixon-Coles sencillo. El valor de la
  Fase 2 es medirlo con honestidad, no obtener un modelo ganador.

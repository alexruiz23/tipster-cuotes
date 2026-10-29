# 010 — Elo con empate (Elo-Davidson) como segundo modelo

**Estado:** Aceptada (2026-10-29) · **Fecha:** 2026-10-29

Diseño del segundo modelo de la Fase 2 (PLAN §6, ADR 007 §4), aceptado por el usuario el 2026-10-29
(las cinco decisiones de la sección final).

**Nota de numeración.** Pediste «ADR 009», pero el 009 ya es el del decaimiento y la L2. Este es el
**010**. El ADR 007 decía que el Elo necesitaría el «008»; ese número lo ocupó el núcleo de
Dixon-Coles, y la referencia se corrige al 010.

## 1. Formulación

Un Elo por liga (no hay partidos entre ligas cargados). Rating `R_i`, en puntos, y escala estándar
de 400 puntos. Para un partido de local *h* y visitante *a*:

```
d = R_h + H − R_a                 diferencia con la ventaja de campo H (en puntos)
E = P(local) + ½·P(empate)        puntuación esperada del local, de las probabilidades del apartado 2
S = 1 (gana el local) · ½ (empate) · 0 (gana el visitante)
R_h ← R_h + K·(S − E)             R_a ← R_a − K·(S − E)        (suma cero)
```

- **Ventaja de campo:** un bono fijo `H` al local antes de calcular las probabilidades (no se suma a
  su rating guardado). `H` no se fija a mano en +100: se **estima** (apartado 4) por liga.
- **K constante.** Razones: los partidos son todos de liga, con la misma importancia (no hay
  torneos que ponderar); la regresión entre temporadas (más abajo) ya cumple la función que tendría
  un K alto para equipos con poco historial; y cada parámetro de más hay que estimarlo con unos 1 900
  partidos. Se reconsideraría un K variable (por ejemplo, mayor en los primeros partidos de un equipo
  nuevo) solo si la validación muestra que los ascendidos están mal calibrados. Tampoco se usa el
  multiplicador por diferencia de goles de otros sistemas Elo: el Elo aquí se alimenta solo del
  resultado 1X2, que es lo que lo distingue de Dixon-Coles (que usa los goles) y lo hace útil como
  segundo modelo.
- **Regresión entre temporadas:** al empezar cada temporada, `R ← R̄ + c·(R − R̄)`, con `R̄` la
  media de los equipos que jugaron la temporada anterior y `c ∈ [0, 1]` («carry», a estimar). La
  regresión se aplica en cada cambio de temporada a todos los equipos con rating (si ninguno jugó la
  temporada que acaba, hacia la media de todos), así que un equipo que reaparece tras `k` temporadas
  fuera acumula `c^k`. Es la contrapartida del decaimiento
  temporal de Dixon-Coles: las plantillas cambian.
- **Temporada:** el 1 de agosto es el corte (misma regla que usa el ADR 007; los 10 partidos de
  agosto de 2020 de la Serie A pertenecen a 2019/20 y reciben la regresión antes, un efecto
  despreciable).
- **Equipos ascendidos / sin historial:** entran con `R̄ + δ`, con `δ` a estimar (se espera ≤ 0: los
  ascendidos suelen ser más débiles que la media; no hay datos de segunda división para
  inicializarlos mejor). Un equipo sin rating en el momento de predecir usa el mismo `R̄ + δ`, igual
  que el «equipo medio» de Dixon-Coles. El primer año todos empiezan en 1 500.
- **Orden:** los partidos se procesan por días: todas las predicciones de un día se hacen antes de
  aplicar las actualizaciones de ese día (regla de «estrictamente anterior» del ADR 007).

## 2. Del Elo a (local, empate, visitante): la opción b, Davidson

**Elegida: el modelo de Davidson.** Con `γ_h = 10^{(R_h + H)/400}` y `γ_a = 10^{R_a/400}`:

```
Z = γ_h + γ_a + ν·√(γ_h·γ_a)
P(local) = γ_h/Z      P(empate) = ν·√(γ_h·γ_a)/Z      P(visitante) = γ_a/Z
```

Un solo parámetro nuevo, `ν > 0` (propensión al empate). Con `ν = 0` es el Elo de dos resultados;
la probabilidad de empate es `ν/(2+ν)` con equipos iguales y baja al crecer `|d|`.

**Por qué esta y no las otras:**

- **Un único modelo coherente.** La derivada de `log P(resultado)` respecto a `ln γ_h` es
  exactamente `S − E` en los tres casos: local `1 − E`, empate `½ − E`, visitante `−E` (con
  `E = P(local) + ½·P(empate)`, comprobado a mano). Por tanto, la actualización de Elo con ese `E`
  **es un paso de gradiente de la log-verosimilitud** del propio modelo, y el mismo `E` sirve para
  actualizar y para predecir. Un test lo comprueba contra diferencias finitas.
- **(a) Regresión logística ordinal:** necesita dos parámetros (escala y umbral de empate), y la
  actualización usaría un `E` distinto del que produce las probabilidades. Es una pieza separada del
  Elo, no una extensión.
- **(c) Fórmula empírica de `P(empate)`:** obliga a elegir una forma funcional a mano, y las tres
  probabilidades podrían no ser coherentes con el `E` de la actualización.
- Davidson devuelve directamente un vector de tres probabilidades que suman 1.

## 3. Estimación de los hiperparámetros

Cinco parámetros: `K`, `H`, `ν`, `c` (carry) y `δ`. Se estiman por **máxima verosimilitud
prequential** sobre el periodo de entrenamiento: se recorre la historia en orden, cada partido se
predice con lo anterior y se acumula `−log P(resultado real)`. No ve nada posterior. Se descartan las
dos primeras temporadas como calentamiento (2016/17 y 2017/18) y se puntúa 2018/19–2022/23 (unos
1 900 partidos por liga). Optimizador: Nelder-Mead sobre `(ln K, H, ln ν, logit c, δ)` desde tres
puntos de partida distintos; se informa si convergen al mismo sitio. Los puntos de partida
(K = 20, H = 60, ν = 0,7, c = 0,75, δ = 0) son solo eso, no valores finales; `ν = 0,70` correspondería
a un 26 % de empates con equipos iguales.

**Aviso de justicia en la comparación.** La vida media de Dixon-Coles (730 días) se eligió con la
temporada 2023/24; los hiperparámetros del Elo se elegirán solo con el entrenamiento. La ventaja
de selección favorece a Dixon-Coles y se dirá en el informe. La evaluación definitiva será 2024/25.

## 4. Evaluación y comparación

- **Mismo walk-forward que Dixon-Coles:** entrenar/actualizar hasta el 2023-07-31 y probar los 380
  partidos de 2023/24 de cada liga, con log-loss y Brier del 1X2, diferencia pareada con su error
  típico (`paired_difference`) y la referencia de Pinnacle sin margen.
- **Dos variantes, para no confundir información:**
  - **Congelado (principal):** los ratings se fijan el 2023-07-31 y no cambian durante 2023/24. Es la
    misma información que tiene Dixon-Coles, que no se reajusta en la temporada.
  - **En línea (secundaria):** se actualiza tras cada partido de 2023/24. Usa información que
    Dixon-Coles no ve en este protocolo. La comparación justa es la evaluación formal con reajuste
    semanal para los dos modelos, que viene después.
- **Calibración: no se aplica Platt ni isotónica en este paso.** Davidson ya es un modelo
  probabilístico estimado por verosimilitud, y calibrar exige un bloque de validación separado del de
  prueba (regla 5 del ADR 007): con una sola temporada de prueba, calibrar a Elo y a Dixon-Coles para
  «hacerlos comparables» mediría los calibradores más que los modelos. En su lugar se publican
  **diagnósticos de calibración** de los dos modelos: tabla de fiabilidad (probabilidad media prevista
  frente a frecuencia real por tramos) y tasa media de empates prevista frente a la observada. Si
  salen descalibrados, la calibración se hace en la evaluación formal con un tramo de validación
  anterior al de prueba.
- **Fuera de este ADR:** ensamble o respaldo entre Elo y Dixon-Coles. Se decide con los resultados de
  la evaluación formal.

## 5. Interfaz y ficheros

- `src/tipster/models/elo.py`: `EloParams(k, home_advantage, nu, carry, newcomer_offset)`,
  `davidson_probs(d, nu)`, `run(matches, params, until=None)` (recorre los partidos por días y
  devuelve el estado de los ratings y la probabilidad prevista de cada partido),
  `fit_params(train)` y `EloFit.predict_proba(home_id, away_id)` con el mismo formato que
  Dixon-Coles (`local`, `empate`, `visitante`) y `knows(team_id)`.
- Reutiliza `Match` (con fecha) y `load_matches`; `predict_matches` y las métricas ya sirven.
- Sin dependencias nuevas.

## 6. Tests (primero los tests; casos a mano)

Con `K = 20`, `ν = 0,7`:

| Caso | Valores a mano |
|---|---|
| `d = 0`, `ν = 0,5` | P = (0,4; 0,2; 0,4), `E = 0,5`; el local que gana sube `20·0,5 = +10` y el visitante baja 10 |
| `d = +100`, `ν = 0,7` | P = (0,479095; 0,251490; 0,269415), `E = 0,604840` |
| `d = −100`, `ν = 0,7` | la imagen especular: P = (0,269415; 0,251490; 0,479095) |
| actualización con `d = +100` | gana el local `+7,9032`; empate `−2,0968`; pierde `−12,0968` |
| regresión con `c = 0,5` | un 1 600 con media 1 500 pasa a 1 550; tras 2 temporadas fuera, `c² = 0,25` |

Además: las tres probabilidades suman 1; la actualización conserva la suma de ratings; con
`ν` fijo, `P(empate)` es máxima en `d = 0`; el score del log-verosimilitud coincide con `S − E` por
diferencias finitas; **las predicciones de un partido no cambian si se alteran partidos posteriores**
(sin fuga); las predicciones de un mismo día no usan los resultados de ese día; un equipo sin rating
usa `R̄ + δ`; y `fit_params` recupera `K`, `H`, `ν`, `c` y `δ` de datos simulados con el propio modelo
(la tolerancia se fija midiendo el error típico en varias semillas, como en el ADR 008).

## Qué espero y qué no

Un Elo basado solo en el resultado tiene menos información que Dixon-Coles (que ve los goles), así
que lo esperable es que **no gane** a Dixon-Coles en log-loss. Su valor es ser un segundo modelo
distinto, barato y estable, con el que comparar y, quizá, combinar. Si queda claramente peor, se dirá
tal cual.

## Decisiones tomadas por el usuario
1. ¿Vale Davidson (opción b) con el `E` de la actualización tomado del mismo modelo?
2. ¿Vale K constante, sin multiplicador por goles?
3. ¿Vale estimar `K`, `H`, `ν`, `c` y `δ` por verosimilitud prequential con calentamiento de dos
   temporadas, en lugar de fijar `H = 100` y `K` a mano?
4. ¿Vale no calibrar todavía y publicar solo diagnósticos de calibración?
5. ¿Vale que la comparación principal sea la variante congelada, con la en línea como secundaria?

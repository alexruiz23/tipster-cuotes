# 012 — Fase 3: probabilidad final, Kelly, picks y CLV

**Estado:** Aceptada (2026-10-29) · **Fecha:** 2026-10-29

Diseño de la Fase 3 (PLAN §7), aceptado por el usuario el 2026-10-29 con sus nueve puntos. Parte de lo cerrado en la Fase 2
([ADR 011](011-evaluacion-formal.md)): Dixon-Coles y Elo empatan con la misma información y el mercado
(Pinnacle sin margen) los supera en las 6 ligas (+0,023 de log-loss, unos 6 errores típicos).

## 0. Tres hechos que condicionan todo el diseño

1. **El modelo aporta poca información sobre el mercado.** Si la mezcla óptima da casi todo el peso al
   mercado, `p_final ≈ p_mercado` y los picks serán, sobre todo, **precios de otras casas por encima de
   la cuota justa de Pinnacle** (comparar precios), no «el modelo ve algo que el mercado no ve». Es el
   comportamiento actual de `tipster scan` (`p_final = p_mercado`). El diseño lo acepta y lo mide.
2. **El valor y el CLV no se pueden retroprobar con los datos que hay.** El dataset histórico solo tiene
   el cierre de Pinnacle: no hay cuotas de otras casas antes del cierre, así que no hay «cuota tomada»
   histórica. El EV y el CLV solo se miden **hacia delante**, con picks reales registrados semana a semana.
   El backtest de la Fase 5 solo podrá evaluar probabilidades, no beneficio.
3. **Las cuotas de `scan` son de feeds que no son de las webs .es** (D1). Los picks llevan la etiqueta
   «FEED NO-ES» y el CLV se reporta por separado para feeds .es cuando exista la Fase 1b.

## 1. Probabilidad final

### 1.0 Antes de mezclar: qué `devig` usa `p_mercado` (pendiente desde la Fase 1)
`TIPSTER_DEVIG_METHOD` sigue «provisional» (multiplicativo). El multiplicativo suele inflar el EV en
cuotas largas (en el primer escaneo real, los picks más largos eran de 11 a 17). Se **decide con datos**:
log-loss del cierre de Pinnacle sin margen contra los resultados, con los cuatro métodos, en la validación
(2021/22 y 2022/23). Gana el de menor log-loss; si la diferencia es menor de un error típico, se mantiene
el multiplicativo (el más simple).

### 1.1 Mezcla
Convención del PLAN: `w` es el peso del **mercado**.

- **Lineal (PLAN):** `p_final = w · p_mercado + (1 − w) · p_modelo`.
  Ejemplo a mano: `p_mercado = (0,5; 0,25; 0,25)`, `p_modelo = (0,6; 0,2; 0,2)`, `w = 0,7` →
  `(0,530; 0,235; 0,235)`.
- **Logarítmica:** `p_final ∝ p_mercado^w · p_modelo^(1−w)`, normalizada. Mismo ejemplo → `(0,5304; 0,2348;
  0,2348)`.
- **Se elige por datos, con la regla fijada antes de mirar:** la forma con menor log-loss en la validación;
  en caso de empate (< 1 error típico), la lineal.
- **Solo Dixon-Coles**, como propones (730 días, `λ₂ = 0,01`, reajustado). Elo queda fuera por ahora, pero
  la puerta sigue abierta sin cambiar el esquema: el pick guarda `model_name` (por ejemplo
  `dixon_coles` o, más adelante, `dixon_coles+elo`) y `p_modelo` es la probabilidad del conjunto.

### 1.2 Pesos: calibrados, no fijos
Un 60/40 fijo probablemente **empeore** al mercado: Dixon-Coles queda +0,023 de log-loss por detrás. Por
eso `w` se **ajusta** minimizando el log-loss en la validación (un único `w` global, `w ∈ [0,5; 1]`, es
decir, el modelo nunca pesa más que el mercado). Si el ajuste da `w > 0,95`, se fija `w = 1`
(`p_final = p_mercado`) y se dice así.

**Limitación honesta:** los pesos se ajustan con el cierre de Pinnacle, que es el precio más informado.
En vivo, `p_mercado` será de horas antes del partido, menos informado, y el modelo podría pesar más. Usar
el cierre es el lado conservador (más peso al mercado). No hay cuotas anteriores al cierre para
comprobarlo (hecho 2); se podrá medir con las capturas en vivo.

### 1.3 Calibración del modelo
Platt binario no sirve para 3 resultados. Se usa la extensión directa, con **3 parámetros**:

`p'_k ∝ exp(β · ln p_k + b_k)`, con `b_local = 0`; parámetros `β`, `b_empate`, `b_visitante`.

Ejemplo a mano: `p = (0,5; 0,3; 0,2)`, `β = 1`, `b_empate = ln 2` → `(0,3846; 0,4615; 0,1538)`.
Corrige a la vez la confianza (`β`) y el sesgo del empate (el hallazgo de la Fase 2: Dixon-Coles predice
0,255 de empates frente a 0,272 observado). La isotónica (una escalera por resultado) necesita más datos y
no garantiza que sumen 1: queda como alternativa si las tablas de fiabilidad muestran un patrón no lineal.

- **Validación = 2021/22 y 2022/23** (≈ 4 600 partidos). El calibrador y `w` se ajustan ahí, en este orden:
  calibrador del modelo, luego `w` sobre el modelo ya calibrado.
- **Validación cruzada por temporada** (se ajusta con una y se puntúa en la otra) para no confundir mejora
  con sobreajuste. **El calibrador solo se activa si mejora el log-loss más de un error típico** en esa
  validación cruzada; si no, identidad.
- **Prueba = 2023/24 y 2024/25.** Se aplican congelados (sin reajustar). 2023/24 ya se usó para elegir la
  vida media de Dixon-Coles, así que **no es ciega**; **2024/25 sí lo es y se evalúa una sola vez**, con
  esta configuración fijada antes de mirarla.
- **Criterio de aceptación (fijado ahora):** la mezcla debe mejorar el log-loss del mercado solo
  (diferencia pareada) en más de un error típico en 2023/24 y no empeorarlo en 2024/25. Si no se cumple,
  `w = 1` (picks por comparación de precios) y se documenta; no se fuerza.
- Las predicciones de validación salen del walk-forward ya implementado (`walk_forward_dixon_coles`, con
  historial desde 2016-08-01); no hay fuga.

### 1.4 Datos que faltan para operar en vivo (prerrequisitos)
- **Resultados de la temporada en curso.** El dataset de Hugging Face es una foto (julio de 2026) y
  Dixon-Coles necesita los resultados recientes. Fuente propuesta: `/scores` de The Odds API (1 crédito, 2
  con `daysFrom` según la documentación de nivel C; **hay que verificarlo con una llamada real**). Con
  inserción manual como respaldo. football-data.co.uk queda excluido (ADR 007).
- **Nombres de equipo de The Odds API** → `teams.id`: fichero de alias a mano, como el de las duplicadas.
  Un nombre sin alias **no se adivina**: ese partido se ignora con aviso y su pick lleva `p_modelo = NULL`
  (`p_final = p_mercado`).

## 2. Kelly fraccionado y bankroll

- **Fracción de Kelly:** `f* = (p · o − 1) / (o − 1)`, con `p = p_final` y `o` = cuota ofrecida; stake
  bruto = `0,25 · f*` del bankroll. Si `f* ≤ 0`, no hay apuesta.
- **Tope por apuesta:** 2 % del bankroll.
- **Un pick por evento:** el de mayor EV. Las selecciones de un mismo partido son excluyentes y las de
  mercados distintos están correlacionadas; el tratamiento conjunto queda para la Fase 4.
- **Tope diario de exposición:** 10 % del bankroll por día de partido (zona Europe/Madrid, suma de los
  stakes de ese día). Se reparte por EV decreciente; el que no cabe se recorta al hueco restante y, si
  queda por debajo del **stake mínimo (0,25 % del bankroll)**, se descarta.
- **Pérdida diaria máxima (del PLAN §7, que tu lista no mencionaba):** si las pérdidas liquidadas en un día
  alcanzan el 5 % del bankroll (valor provisional), no se recomienda nada más ese día. Test obligatorio.
- **Solo VALUE lleva stake.** «POSIBLE ERROR», «REVISIÓN MANUAL», «DESCARTADA» y «SIN VALOR» no apuestan.
- **Bankroll:** como el programa solo recomienda y nunca apuesta, es un **bankroll de papel**: capital
  inicial configurable (`TIPSTER_BANKROLL`, por defecto 1 000) más el resultado de los picks
  recomendados y liquidados. Tabla de movimientos `bankroll_entries (id, at, kind, amount, balance_after,
  pick_id)`; el saldo actual es el último `balance_after`. Los stakes pendientes cuentan como exposición pero
  no se descuentan hasta liquidar. El usuario podrá marcar después qué picks apostó de verdad.

### Casos a mano de Kelly (1 000 de bankroll)
| p | cuota | f* | 1/4 de Kelly | Tope 2 % | Stake |
|---|---|---|---|---|---|
| 0,50 | 2,20 | 1/12 = 0,08333 | 2,083 % = 20,83 | 20,00 | **20,00** (manda el tope; caso del PLAN) |
| 0,55 | 2,00 | 0,10 | 2,5 % = 25,00 | 20,00 | **20,00** (manda el tope) |
| 0,52 | 2,00 | 0,04 | 1 % = 10,00 | 20,00 | **10,00** (sin tope) |

**Ojo con tu ejemplo de test** (`p = 0,55`, cuota 2,0, bankroll 1 000): el cuarto de Kelly es 25,00, pero
con el tope del 2 % el stake final es **20,00**, no 25. Los tests comprueban las dos cifras por separado
(la función de Kelly sin tope da 25,00 y el stake con tope da 20,00) y añaden `p = 0,52` como caso sin tope.

## 3. Clasificación

Orden fijo (el actual): DESCARTADA → REVISIÓN MANUAL → POSIBLE ERROR → VALUE → SIN VALOR.

- **POSIBLE ERROR:** cuota > cuota justa **del mercado** más de un 15 % (`TIPSTER_ERROR_MARGIN`).
  **Se aparta de lo que pides** (`fair_odds = 1 / p_final`): un error de cuota es un desajuste con el
  mercado de referencia, no con el modelo; si dependiera de `p_final`, un modelo equivocado fabricaría o
  taparía errores. Se mantiene sobre `p_mercado`, como en la Fase 1.
- **VALUE:** `EV = p_final · cuota − 1 ≥ 3 %` (`TIPSTER_EV_MIN`), con `fair_odds = 1 / p_final`, como pides.
  Cuando `p_final = p_mercado` las dos cuotas justas coinciden.
- **REVISIÓN MANUAL:** `|p_mercado − p_modelo| >` umbral. El umbral no se fija a mano: es el **percentil 98**
  de esa diferencia en la validación (se escribe el valor resultante en el ADR); un modelo que discrepa
  del mercado más de lo habitual se revisa antes de apostar.
- **Cada pick guarda:** `p_final`, `p_mercado`, `p_modelo` (Dixon-Coles calibrado), `p_modelo_bruto` (sin
  calibrar), `w_mercado`, `model_name`, `model_version` (identifica el ajuste y el calibrador), `fair_odds`,
  `ev` y `stake`.

## 4. Tracking y CLV

Migración `0003`: se amplía `picks` con `result` (`local`/`empate`/`visitante`), `status`
(`abierto`/`ganado`/`perdido`/`nulo`), `settled_at`, `profit`, `closing_odds` (cuota **cruda** de cierre de
Pinnacle de la selección), `closing_fair_odds` (sin margen), `closing_captured_at` y `clv`, además de las
columnas de la sección 3.

- **CLV = cuota_tomada / cuota_justa_de_cierre − 1 = cuota_tomada · p_cierre_justa − 1.** Es tu fórmula con
  `cuota_cierre` = cuota **sin margen**, tal como la definió el ADR 002. Con la cuota cruda del cierre el CLV
  saldría sistemáticamente menor (el margen de Pinnacle, ~3 %). Caso a mano (PLAN): 2,20 frente a un cierre
  justo de 2,00 → **+10 %**; cierre crudo `1,80 / 3,60 / 3,60` → p justa del local 0,5 → cuota justa 2,00.
- **Informe del CLV:** media, media ponderada por stake, mediana, % de picks con CLV > 0, nº de picks y error
  típico de la media (`sd/√n`), por liga y por feed. Ejemplo a mano: CLV `+0,10; −0,05; +0,02` → media
  0,0233, desviación 0,0751, error típico 0,0433. **Sin cierre, el CLV es NULL; nunca se imputa.**
- **Captura del cierre** (pendiente del PLAN §7). `tipster close`, ejecutado por `cron`/`launchd` cada vez que
  un pick abierto está a ≤ 15 minutos del inicio: una petición por competición con `bookmakers=pinnacle` y
  solo `h2h`, que cuesta **1 crédito** (mercados × grupos de 10 casas, nivel A). Se guarda la hora de
  captura; si es de más de 30 minutos antes del inicio, el cierre se marca «no fiable» y no entra en el CLV.
  **Estimación (sin verificar):** unas 3–4 jornadas útiles por semana y 2–3 competiciones por jornada son
  unos 6–12 créditos a la semana, unos 25–50 al mes; con 14 créditos por escaneo completo y unos 8 escaneos
  al mes (≈ 110), el total entra en los 500 gratuitos. **NO VERIFICADO:** que Pinnacle actualice su cuota en
  la última media hora (la propia documentación avisa de posible retraso: verificación §3 y §13.5).
  El plan de pago (D3) solo haría falta si esas cifras se quedan cortas.
- **Liquidación:** `tipster settle` lee los resultados (`/scores` o manual), marca ganado/perdido, calcula
  `profit` (`stake · (cuota − 1)` o `−stake`) y añade el movimiento al bankroll. Es idempotente.
- **Tamaño de muestra:** el error típico del CLV medio es `sd/√n`. No se conoce la desviación por pick;
  se estimará con las primeras semanas y se calculará cuántos picks hacen falta para distinguir un CLV
  medio de 1 %. Hasta entonces el CLV es un indicador, no una conclusión.

## 5. Tests (primero los tests; casos a mano)

- **Kelly:** los tres casos de la tabla; `f* ≤ 0` no apuesta; y una propiedad: para cualquier `p` y cuota,
  el stake nunca supera el 2 % del bankroll.
- **Límites:** seis picks con stakes brutos del 2 %, 2 %, 2 %, 2 %, 1,5 % y 1 % → los cinco primeros suman
  9,5 % y el sexto se recorta al 0,5 % restante (el tope diario es 10 %); un sexto bajo el 0,25 % se
  descarta; con pérdidas del día en el límite, no se recomienda nada más (obligatorio, PLAN).
- **Mezcla:** el ejemplo lineal y el logarítmico; `w = 1` devuelve `p_mercado`; las probabilidades suman 1.
- **Calibrador:** identidad con `β = 1`, `b = 0`; el ejemplo a mano; el ajuste solo recibe partidos de la
  validación (**sin fuga**, con espía como en el ADR 011).
- **Clasificación:** POSIBLE ERROR sobre `p_mercado` aunque `p_final` sea otra; VALUE sobre `p_final`; el
  orden fijo; REVISIÓN MANUAL por el umbral.
- **CLV:** +10 % a mano; con cierre crudo se usa la cuota justa; sin cierre es NULL; cierre «no fiable» no
  cuenta; la media y el error típico del ejemplo.
- **Bankroll:** el saldo tras una secuencia de liquidaciones a mano; la liquidación es idempotente.

## 6. Fuera de este ADR
Combinadas y correlaciones (Fase 4), backtest de probabilidades (Fase 5), Elo en la mezcla, el feed de
casas .es (Fase 1b) y la notificación por Telegram (Fase 6).

## Decisiones tomadas por el usuario
1. ¿Vale decidir el `devig` por log-loss en la validación (1.0)?
2. ¿Vale elegir forma de la mezcla (lineal o logarítmica) y `w` por datos, con la regla fijada antes de
   mirar, aceptando que `w` puede quedar en 1 (sin modelo)?
3. ¿Vale calibrar con 3 parámetros y activarlo solo si mejora más de un error típico en validación cruzada?
4. ¿Valen estos valores: cuarto de Kelly, tope 2 %, exposición diaria 10 %, pérdida diaria 5 % (provisional),
   stake mínimo 0,25 % y un pick por evento?
5. ¿Vale que POSIBLE ERROR siga midiéndose contra el mercado (y no contra `p_final`)?
6. ¿Vale el CLV con la cuota **justa** de cierre y la captura con `tipster close` (≈ 1 crédito por
   competición), sabiendo que la cadencia real está sin verificar?
7. ¿Vale `/scores` de The Odds API como fuente de resultados (a verificar) con inserción manual de respaldo?
8. ¿Vale un bankroll de papel, dado que el programa nunca apuesta?
9. ¿Vale evaluar 2024/25 una sola vez, con la configuración y el criterio de aceptación fijados aquí?

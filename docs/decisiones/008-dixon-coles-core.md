# 008 — Núcleo de Dixon-Coles: verosimilitud y máxima verosimilitud por liga

**Estado:** Aceptada (2026-10-29) · **Fecha:** 2026-10-29

Desarrolla el apartado 4 del [ADR 007](007-historico-y-dixon-coles.md) para el primer paso de
implementación. Diseño aceptado por el usuario el 2026-10-29 (las cuatro propuestas de la sección «Decisiones»).

**Alcance de este paso:** verosimilitud, ajuste por máxima verosimilitud para **una liga** y
`predict_proba` de 1X2. **Fuera de este paso:** decaimiento temporal, penalización L2, Elo,
walk-forward, calibración y los mercados O/U 2.5 y BTTS (los dos últimos salen de la misma matriz de
marcadores y se añaden después).

## 1. Formulación

Equipos *i* = 1…n de una liga. Parámetros: ataque `a_i`, **debilidad defensiva** `d_i`, ventaja de
local `γ` y `ρ`. Para un partido de local *h* y visitante *v*:

```
λ = exp(a_h + d_v + γ)        goles esperados del local
μ = exp(a_v + d_h)            goles esperados del visitante
```

`d_i` es «cuánto encaja el equipo *i*»: **más alto = peor defensa**. Es lo que pide la fórmula
`defensa_visitante` sumando en λ. Por tanto, las «mejores defensas» del informe son las de `d` más
negativo, y se dice así en la salida.

Probabilidad de un marcador (x, y):

```
P(x, y) = τ(x, y; λ, μ, ρ) · Poisson(x; λ) · Poisson(y; μ)

τ(0,0) = 1 − λ·μ·ρ     τ(0,1) = 1 + λ·ρ     τ(1,0) = 1 + μ·ρ     τ(1,1) = 1 − ρ
τ(x,y) = 1 en cualquier otro marcador
```

Log-verosimilitud (con las constantes `log x!`, para que el valor sea la verosimilitud real y se
pueda comparar entre modelos):

```
ℓ = Σ_partidos [ log τ + x·log λ − λ − log x! + y·log μ − μ − log y! ]       f = −ℓ  (se minimiza)
```

**Dominio de τ.** Debe ser > 0 en los marcadores observados. Fuera de ese dominio el optimizador
usa `log(max(τ, 1e-12))` para poder retroceder, y **al terminar se comprueba** que τ > 0 en todos los
partidos de 0-0, 0-1, 1-0 y 1-1; si no, falla (sección 4).

## 2. Identificabilidad: una sola restricción

Las transformaciones `a_i → a_i + c`, `d_i → d_i − c` dejan λ y μ intactos, así que sobra **un**
grado de libertad. La restricción es `mean(a) = 0`, como pides.

**Esto corrige el ADR 007**, que ponía además `Σ d_i = 0`. Con las dos restricciones no queda
ninguna constante global y la media geométrica de los goles esperados del visitante quedaría
forzada a `exp(0) = 1`.
Con solo `mean(a) = 0`, el nivel medio lo absorben las `d`.

**Cómo se impone:** reparametrización exacta, sin restricciones en el optimizador. Los parámetros
libres son `a_1…a_{n−1}`, `d_1…d_n`, `γ`, `ρ` (2n + 1 en total), y `a_n = −(a_1 + … + a_{n−1})`.

**Valores iniciales:** `a = 0`; `d_i = log(media de goles del visitante)`;
`γ = log(media local) − log(media visitante)`; `ρ = 0`. Es un punto cercano al óptimo y determinista.

## 3. Optimizador: `scipy.optimize.minimize(method="L-BFGS-B")` con gradiente analítico

- **L-BFGS-B y no SLSQP.** Tras la reparametrización no hay restricciones de igualdad, así que
  SLSQP (que resuelve un subproblema cuadrático denso en cada iteración) no aporta nada. L-BFGS-B
  admite **cotas** (`ρ ∈ [−0.5, 0.5]`) y escala bien con unos 70 parámetros (Premier, ~33 equipos en
  8 temporadas). `scipy` ya es dependencia.
- **Gradiente analítico,** no por diferencias finitas. Las diferencias finitas dan gradientes
  ruidosos y L-BFGS-B suele terminar con «ABNORMAL_TERMINATION_IN_LNSRCH»; además la F2 va a
  reajustar cientos de veces (walk-forward). Con η_h = log λ y η_v = log μ, por partido:
  `∂ℓ/∂η_h = x − λ + (∂log τ/∂η_h)`, `∂ℓ/∂η_v = y − μ + (∂log τ/∂η_v)`, y las derivadas de τ son
  triviales: en (0,0), `−λμρ/τ` para ambos y `−λμ/τ` para ρ; en (0,1), `λρ/τ` en η_h y `λ/τ` en ρ;
  en (1,0), `μρ/τ` en η_v y `μ/τ` en ρ; en (1,1), `−1/τ` en ρ. Después se propagan a `a`, `d`, `γ` y,
  por la reparametrización, `∂/∂a_k = g_{a_k} − g_{a_n}`. **Un test lo compara con diferencias
  finitas.**
- **Criterios de convergencia** (provisionales; se ajustan con evidencia, nunca a mano):
  `max|∇f| ≤ 1e-4` (optimalidad de primer orden, con `ftol = 0` para que el criterio de parada de
  scipy no pare antes; el `success` de scipy no se exige porque L-BFGS-B termina con «ABNORMAL» en el
  límite de precisión aun con el gradiente en ~1e-6: visto en 1 de 200 ajustes simulados); `ρ` a más de `1e-6` de las cotas; τ > 0 en los marcadores bajos
  observados; y ningún `|a_i|` o `|d_i|` mayor que 6 (λ fuera de [0,0025; 400] indica divergencia,
  típica de un equipo que nunca marca o nunca encaja). **Si falla cualquiera, `fit` lanza
  `FitError` con el motivo.** No hay reintentos silenciosos ni parámetros a mano.

## 4. Ascensos, descensos y equipos sin historial

- **Descendidos:** no requieren nada. Sus partidos pasados siguen informando a los rivales y no se
  predicen.
- **Equipos que aparecen por primera vez** (ascendidos sin partidos en la ventana de entrenamiento;
  de segunda división no hay datos cargados): `predict_proba` usa el **equipo medio**: `a = 0` (que
  por la restricción es la media de la liga) y `d = mean(d_i)`. El resultado lo marca: `fit.knows(id)`
  permite al llamador saber si un equipo es desconocido. Es una aproximación explícita; la penalización
  L2 del siguiente paso es la forma correcta de encogerlos.
- **Equipos con muy pocos partidos:** sin penalización, el MLE de un equipo con 5 partidos es
  ruidoso. No se arregla ahora; el criterio de divergencia (sección 3) lo detecta en los casos
  extremos y el siguiente paso lo resuelve con L2.

## 5. Interfaz y ficheros

- `src/tipster/models/dixon_coles.py`: funciones puras con NumPy: `tau`, `log_likelihood`,
  `fit(matches) -> DixonColesFit`, `score_matrix(λ, μ, ρ, max_goals=10)`. `DixonColesFit`
  (dataclass congelada) guarda `a`, `d`, `γ`, `ρ`, el `ℓ` final y el estado del optimizador, y
  expone `predict_proba(home_id, away_id) -> {"local": p, "empate": p, "visitante": p}` y
  `knows(team_id)`.
- La matriz de marcadores llega hasta **20-20** goles y se renormaliza; un test falla si la masa fuera
  de ella supera 1e-6 para λ y μ de hasta 5. Con 10 goles, P(X > 10) es 8,3e-6 para λ = 2 y 2,9e-4
  para λ = 3 (`scipy.stats.poisson.sf`); con 20 es 1,2e-11 para λ = 3 y 8,1e-8 para λ = 5.
- `src/tipster/history/matches.py`: `load_matches(conn, competition_id, start, end)` lee
  `historical_matches` con **ambas fechas en el `WHERE`**, de modo que el ajuste no puede ver partidos
  posteriores a `end`.
- `FitError` en `tipster/errors.py`. Sin CLI en este paso.

## 6. Tests (primero los tests, luego el código; casos a mano)

**Dataset de 4 equipos y 6 partidos** (todos contra todos, una vuelta), con `a = d = 0`, `γ = 0,2`,
`ρ = −0,1` (λ = e^0,2 = 1,2214028, μ = 1):

| Partido | Marcador | τ | log P |
|---|---|---|---|
| A–B | 1-0 | 0,9000000 | −2,1267633 |
| A–C | 0-0 | 1,1221403 | −2,1061649 |
| A–D | 2-1 | 1,0000000 | −2,5145499 |
| B–C | 1-1 | 1,1000000 | −1,9260926 |
| B–D | 0-1 | 0,8778597 | −2,3516712 |
| C–D | 3-2 | 1,0000000 | −4,1063094 |
| **Total** | | | **ℓ = −15,1315514** |

Calculado con `math` aparte del código (`log P = log τ + x·0,2 − λ − log x! − 1 − log y!`).

1. **`tau`:** 1,1221403 en (0,0), 0,8778597 en (0,1), 0,9 en (1,0), 1,1 en (1,1) y 1 en (2,1) y
   (0,2), con λ = e^0,2, μ = 1, ρ = −0,1.
2. **Verosimilitud:** `−ℓ = 15,1315514` con una tolerancia de 1e-6 sobre ese dataset.
3. **Invariancia:** sumar c a todos los `a` y restarlo a todos los `d` no cambia ℓ.
4. **Gradiente:** coincide con las diferencias finitas (`scipy.optimize.check_grad`).
5. **Ajuste:** los 6 partidos **no se pueden ajustar** (9 parámetros para 12 goles: el MLE no
   existe, y el criterio de divergencia lo detecta; hay un test de ello). Para comprobar el ajuste se
   simulan, con semilla fija, 600 partidos de 4 equipos (cada par ordenado 50 veces) con parámetros
   conocidos. Comprobaciones: converge; `mean(a) = 0`; los parámetros recuperados están dentro de
   unos 3 errores típicos de los verdaderos (la tolerancia se fija midiendo ese error típico y se
   escribe en el test, no se elige a ojo); y el ℓ del ajuste no es menor que el de los parámetros
   verdaderos.
6. **`predict_proba`:** suma 1; con equipos idénticos y γ = 0 local y visitante son iguales; un equipo
   desconocido usa `a = 0` y `d = mean(d)`.
7. **Carga:** `load_matches` no devuelve partidos posteriores a `end`.

## 7. Prueba real (Premier League, ciega en 2024/25)

- **Entrenamiento:** Premier, fechas del 2016-08-01 al 2024-07-31 (8 temporadas). 2024/25 no se lee
  en el ajuste.
- **Salida:** `γ`, `ρ`, los 5 mejores ataques y las 5 mejores defensas (las de `d` más negativo),
  el tiempo del ajuste y el estado del optimizador.
- **Tres partidos de 2024/25 elegidos con una regla mecánica,** no a mano: el primer partido como
  local del Manchester City, del Arsenal y del Liverpool. Se muestran junto a la probabilidad
  implícita del cierre de Pinnacle sin margen, solo para contrastar (no es una evaluación). Un rival
  ascendido sin historial usa el equipo medio y se marca.
- Si el optimizador no converge, se para y se informa.

## Decisiones tomadas por el usuario

1. ¿Vale la reparametrización (suma de ataques = 0) en vez de una restricción en el optimizador?
2. ¿Vale el gradiente analítico, verificado contra diferencias finitas?
3. ¿Vale el «equipo medio» para equipos sin historial hasta tener la penalización L2?
4. ¿Vale que el ajuste con 6 partidos se pruebe solo como fallo controlado, y el de recuperación de
   parámetros se haga con datos simulados?

## Estabilidad de ρ (añadido el 2026-10-29)

En la Premier, el ρ ajustado pasó de −0,029 (pesos iguales) a −0,0014 al añadir el decaimiento
(ADR 009). No es un problema de identificación; es **ruido de estimación** que crece al bajar el
número efectivo de partidos. Medido con la Hessiana numérica del coste (entrenamiento hasta
2024-07-31, 3 040 partidos):

| Vida media | N efectivo (Σw)²/Σw² | ρ ± error típico |
|---|---|---|
| sin decaimiento | 3 040 | −0,029 ± 0,025 |
| 730 días | 1 944 | −0,005 ± 0,041 |
| 365 días | 1 109 | −0,001 ± 0,055 |
| 180 días | 574 | −0,015 ± 0,079 |
| 90 días | 315 | −0,048 ± 0,115 |

- **El error típico se duplica al pasar de 3 040 a 1 109 partidos efectivos,** y todas las
  estimaciones son compatibles entre sí: fijar ρ = −0,03 en el ajuste con vida media 365 baja la
  log-verosimilitud solo 0,27 (2·Δ, frente a 3,84 del umbral al 95 %).
- **Identificación:** la correlación de ρ con cualquier otro parámetro es ≤ 0,05 en todos los
  ajustes. Sin decaimiento, el perfil de verosimilitud sigue la forma esperada: 2·ΔlogL a ρ = 0, −0,10
  y −0,15 es 1,41, 8,4 y 24,8, frente a ((ρ − ρ̂)/error típico)² = 1,4, 8,3 y 24,2 (no se comprobó con
  decaimiento). No hay indicios de un problema de identificación, solo pocos datos para un parámetro
  que afecta a cuatro marcadores.
- **Además podría haber un cambio real en el tiempo,** no demostrado. Sin decaimiento y por bloques
  de dos temporadas, el ρ de la Premier es −0,103, −0,064, −0,017 y +0,006 (cada uno ± 0,05); la
  diferencia entre el primero y el último es 0,109 ± 0,072. El decaimiento da más peso a los bloques
  recientes, donde ρ está más cerca de 0.
- **No es un rasgo de todas las ligas:** sin decaimiento, 2016-2024, ρ vale −0,042 (LaLiga), −0,052
  (Serie A), −0,045 (Ligue 1), −0,056 (Segunda) y **−0,135 ± 0,026 (Bundesliga)**, claramente negativo.
  La Premier (−0,029 ± 0,025) es la más débil.
- **Consecuencia práctica:** con decaimiento corto, ρ queda mal determinado, pero su efecto en las
  probabilidades es pequeño (afecta a 0-0, 0-1, 1-0 y 1-1). Una alternativa, **no implementada**, es
  estimar ρ sin decaimiento o compartirlo entre ligas (BACKLOG nº 27).

## Hiperparámetros finales (2026-10-29)

Elegidos con el walk-forward simple de las seis ligas (entrenar hasta 2022/23, probar 2023/24). **No se
ha usado 2024/25**, que sigue siendo el test ciego.

| Hiperparámetro | Valor final | Evidencia |
|---|---|---|
| Vida media | **730 días**, global | Mejor media ponderada del log-loss (1,0010). Frente a 365: ninguna liga se separa más de 0,005; frente a 1 095 es un empate estadístico (+0,0003 ± 0,0005 a favor de 730), y gana la regla acordada. No hay base para valores por liga ([ADR 009](009-decaimiento-l2-y-malla.md)) |
| λ₂ | **0** | La mejor en cada malla probada (0 a 10, y 0,001 a 0,1 con vida media 365 y 730); la regularización no aporta (BACKLOG nº 26) |
| ρ | **se estima con el mismo decaimiento** | Estimarlo con pesos iguales (el resto con decaimiento) no mejora |

**Experimento de ρ sin decaimiento** (vida media 730; positivo = peor que decaer también ρ):

| Liga | ρ con decaimiento | ρ sin decaimiento | Δ log-loss ± error típico |
|---|---|---|---|
| Premier | −0,0010 | −0,0362 | +0,0009 ± 0,0010 |
| Bundesliga | −0,1379 | −0,1324 | −0,0002 ± 0,0016 |
| Conjunto 6 ligas | | | +0,00006 ± 0,0003 |

(Con vida media 365 el conjunto es +0,0021 ± 0,0018, también peor.) El criterio acordado era una
mejora de más de un error típico: **no se cumple en ninguna de las dos ligas**, así que la opción se
**quitó del código** (se implementó con pesos distintos en `log τ` y se revirtió; queda en el
commit `efb1ca9`). Sí hizo lo esperado con la variabilidad: en 40 simulaciones, la desviación de ρ
bajó a 0,60 de la de decaer (0,060 frente a 0,100), sin sesgo apreciable. Menos varianza en ρ no se
traduce en mejor predicción a esta escala (BACKLOG nº 27).

**Límites.** Con vida media 730 el ρ de la Premier (−0,001) y el de LaLiga (−0,020) quedan casi en 0;
el error típico del de la Premier es ± 0,041 (el de LaLiga no se midió). La elección de 730 frente a 1 095 es un empate
estadístico, y la ganancia global frente a no decaer (−0,0023 ± 0,0016) sigue sin ser concluyente.

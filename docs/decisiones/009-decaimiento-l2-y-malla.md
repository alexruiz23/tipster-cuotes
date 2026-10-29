# 009 — Decaimiento temporal, penalización L2 y malla de hiperparámetros

**Estado:** Aceptada (2026-10-29) · **Fecha:** 2026-10-29

Completa el [ADR 008](008-dixon-coles-core.md) con las dos piezas que dejó fuera, tal como las
pidió el usuario el 2026-10-29. El modelo base no cambia.

## 1. Decaimiento temporal

- **Peso de un partido:** `w = exp(−ξ · Δt) = 0,5^(Δt / vida_media)`, con `ξ = ln 2 / vida_media` y
  `Δt` en días **desde la fecha del partido hasta la del último partido del entrenamiento** (no hasta
  hoy). El último partido pesa 1.
- **La verosimilitud pasa a ser** `ℓ = Σ w · [log τ + log Poisson + log Poisson]` y el gradiente se
  pondera igual. Sin decaimiento (`vida_media = None`) todos los pesos valen 1 y el resultado es el
  del ADR 008.
- **Cambio respecto al ADR 007**, que medía `Δt` hasta la fecha de predicción: con la referencia en
  el último partido de entrenamiento el ajuste solo depende de sus propios datos. Una referencia
  distinta solo multiplica todos los pesos por una constante, y eso importa con L2 (sección 2),
  porque cambia el peso relativo de la penalización.
- `Match` gana un campo opcional `day`; `load_matches` lo rellena con `match_date`. Pedir
  decaimiento sin fechas es un error.

## 2. Penalización L2 centrada

La penalización es `λ₂ · (Σ aᵢ² + Σ (dᵢ − d̄)²)`, con `d̄ = mean(d)`, y se suma al coste (−ℓ).

**Se aparta de la fórmula literal pedida** (`λ₂·(Σ a² + Σ d²)`). En este modelo las `d` llevan el
nivel medio de goles (la restricción es solo `mean(a) = 0`, ADR 008), así que penalizar `d` hacia 0
empuja a la baja los goles esperados de **todos** los equipos y no solo de los extremos. Centrar la
penalización deja libre el nivel medio y encoge cada equipo hacia la media de la liga, que es lo que
se busca con los ascendidos. Un test comprueba que los goles esperados totales siguen igualando a los
observados con una penalización fuerte. **Magnitud medida** (600 partidos simulados, `λ₂ = 50`):
con la penalización centrada, 0,0 % de diferencia; con la literal, −0,4 %. Es pequeña en ese caso; con
decaimiento corto (menos partidos efectivos) no se ha medido.

La penalización no afecta a `γ` ni a `ρ`. El gradiente de la penalización es `2·λ₂·a` (propagado
por la reparametrización de la suma cero) y `2·λ₂·(d − d̄)`.

## 3. Malla y validación walk-forward simple

- **Malla:** vida media ∈ {90, 180, 365, 730 días y sin decaimiento} × `λ₂` ∈ {0, 0,1, 1, 5, 10}.
  Se incluyen «sin decaimiento» y `λ₂ = 0` para que el modelo base del ADR 008 aparezca como
  referencia.
- **Protocolo:** entrenar del 2016-08-01 al 2023-07-31 (hasta el final de 2022/23) y predecir los 380
  partidos de la Premier de 2023/24 **sin reajustar durante la temporada**.
- **Métricas** sobre el 1X2: *log-loss* = media de `−log p(resultado real)` y *Brier multiclase* =
  media de `Σ_k (p_k − o_k)²` (suma de los tres términos, sin dividir entre 3). Gana la combinación
  de menor log-loss. Como referencia se calcula la misma métrica con la probabilidad del cierre de
  Pinnacle sin margen (multiplicativo) sobre los mismos partidos.
- **Qué NO se hace:** 2024/25 sigue **ciega**. No participa en la elección de hiperparámetros ni se
  evalúa completa aquí; queda para la evaluación formal. Solo se predicen los tres partidos fijados.
- **Sesgo de selección:** elegir el mejor de 25 combinaciones y presentar su nota en los mismos
  partidos es optimista. El informe lo dice. Si el mejor cae en un borde de la malla se indica.
- **Equipos desconocidos** de 2023/24 (ascendidos sin historial) usan el equipo medio y se cuentan.

## Tests (casos a mano)
Peso con vida media 180: 0,5 a 180 días, 0,25 a 360 y `2^(−365/180) = 0,2455` a 365, mayor a 10
días (0,9625); verosimilitud ponderada a mano con los 6 partidos; gradiente contra diferencias
finitas con pesos y L2; el decaimiento acerca los parámetros a lo reciente; L2 reduce un equipo con
3 partidos y conserva el nivel de goles; log-loss `−ln 0,5 = 0,693147` y Brier `0,38` de
`(0,5; 0,3; 0,2)` con resultado local.

## Resultados (2026-10-29, Premier, entrenamiento 2016-08-01 a 2023-07-31, prueba 2023/24)

`tipster tune`: 2 660 partidos de entrenamiento, 380 de prueba. 38 partidos de prueba (Luton, sin
historial en la ventana) usan el equipo medio.

| Vida media | λ₂ | Log-loss | Brier |
|---|---|---|---|
| **365 días** | **0** | **0,9336** | **0,5505** |
| 365 | 0,1 | 0,9346 | 0,5511 |
| 730 | 0 | 0,9361 | 0,5517 |
| 180 | 0 | 0,9392 | 0,5550 |
| sin decaimiento | 0 (modelo base del ADR 008) | 0,9466 | 0,5582 |
| 90 | 0 | 0,9551 | 0,5667 |
| *Cierre de Pinnacle sin margen* | | *0,8995* | *0,5258* |

- **Gana vida media 365 y λ₂ = 0.** Con vida media corta (90) todas las celdas empeoran, y con λ₂ ≥ 1
  también casi todas: en este reparto la penalización no ayuda. La mejor λ₂ es **el borde de la
  malla** (0), así que no se ha comprobado si algo por debajo de 0,1 distinto de 0 mejoraría.
- **La mejora no es concluyente.** Diferencia pareada de log-loss mejor − base: **−0,0130 con error
  típico 0,0092** (1,4 errores típicos). Además es el mejor de 25 combinaciones evaluado sobre los
  mismos 380 partidos, así que es optimista.
- **El mercado sigue ganando:** mejor − mercado = +0,0341 (error típico 0,0116, unos 3 errores
  típicos); base − mercado = +0,0471.
- **Ajuste final** (entrenado hasta 2024-07-31, vida media 365, λ₂ = 0; 3 040 partidos, 0,19 s, 305
  iteraciones, `max|∇| = 1,1e-5`): `γ = 0,2016` y **`ρ = −0,0014`** (con pesos iguales era −0,029, así
  que ρ no es estable). Mejores ataques: Man City 0,708, Arsenal 0,572, Liverpool 0,569, Newcastle
  0,431, Tottenham 0,430. Mejores defensas: Man City −0,479, Arsenal −0,348, Liverpool −0,241.

Tres partidos de 2024/25 (no se usaron para elegir nada), local / empate / visitante:

| Partido | Final | Base (ADR 008) | Pinnacle sin margen |
|---|---|---|---|
| Man City – Ipswich (equipo medio) | 0,838 / 0,110 / 0,051 | 0,826 / 0,119 / 0,055 | 0,881 / 0,088 / 0,031 |
| Arsenal – Wolves | 0,761 / 0,157 / 0,082 | 0,623 / 0,222 / 0,155 | 0,841 / 0,107 / 0,052 |
| Liverpool – Brentford | 0,686 / 0,179 / 0,135 | 0,700 / 0,178 / 0,122 | 0,797 / 0,125 / 0,078 |

La brecha del Arsenal se acorta (victoria local 0,623 → 0,761 frente a 0,841). En Liverpool no
mejora (0,700 → 0,686 frente a 0,797). Tres partidos no son una evaluación; **2024/25 completa
sigue sin tocar** y se usa en la evaluación formal.

## Validación cruzada de la vida media en las 6 ligas (2026-10-29)

Mismo protocolo (entrenar del 2016-08-01 al 2023-07-31, probar 2023/24), `λ₂ = 0`. Log-loss:

| Liga | 90 | 180 | 365 | 730 | sin decaimiento | Pinnacle | Gana |
|---|---|---|---|---|---|---|---|
| Premier | 0,9551 | 0,9392 | **0,9336** | 0,9361 | 0,9466 | 0,8995 | 365 |
| LaLiga | 0,9946 | 0,9808 | **0,9760** | 0,9768 | 0,9793 | 0,9510 | 365 |
| Serie A | 1,0161 | 1,0106 | 1,0050 | **1,0024** | 1,0028 | 0,9639 | 730 |
| Bundesliga | 1,0232 | 1,0121 | 1,0039 | 0,9995 | **0,9993** | 0,9460 | sin decaimiento |
| Ligue 1 | 1,0618 | 1,0409 | 1,0335 | 1,0315 | **1,0298** | 1,0142 | sin decaimiento |
| Segunda | 1,0703 | 1,0602 | 1,0548 | **1,0533** | 1,0545 | 1,0437 | 730 |
| **Media ponderada (2 224 partidos)** | 1,0207 | 1,0081 | 1,0021 | **1,0010** | 1,0033 | | |

Partidos de prueba con un equipo sin historial: Premier 38, Ligue 1 34, Segunda 82, resto 0. Brier
sigue el mismo orden.

Diferencia pareada de log-loss respecto a «sin decaimiento» (negativo = mejor), con error típico:

| Liga | 90 | 180 | 365 | 730 |
|---|---|---|---|---|
| Premier | +0,0084 ± 0,0180 | −0,0074 ± 0,0141 | −0,0130 ± 0,0092 | −0,0105 ± 0,0052 |
| LaLiga | +0,0153 ± 0,0106 | +0,0015 ± 0,0083 | −0,0032 ± 0,0061 | −0,0024 ± 0,0039 |
| Serie A | +0,0133 ± 0,0117 | +0,0078 ± 0,0082 | +0,0022 ± 0,0054 | −0,0004 ± 0,0033 |
| Bundesliga | +0,0239 ± 0,0124 | +0,0128 ± 0,0095 | +0,0046 ± 0,0066 | +0,0002 ± 0,0039 |
| Ligue 1 | +0,0320 ± 0,0181 | +0,0111 ± 0,0121 | +0,0037 ± 0,0079 | +0,0017 ± 0,0047 |
| Segunda | +0,0158 ± 0,0092 | +0,0057 ± 0,0067 | +0,0003 ± 0,0044 | −0,0012 ± 0,0025 |
| **Conjunto (6 ligas)** | **+0,0174 ± 0,0054** | +0,0048 ± 0,0040 | −0,0012 ± 0,0027 | −0,0023 ± 0,0016 |

**Lectura.**
- **La ganadora cambia de liga en liga** (365 en 2, 730 en 2, sin decaimiento en 2), pero casi
  todas las diferencias entre 365, 730 y sin decaimiento están **dentro de un error típico**. No hay
  evidencia para una vida media por liga.
- **Lo único claro es que 90 días es peor** (conjunto +0,0174 ± 0,0054, unos 3 errores típicos), y
  180 es dudoso.
- **Propuesta: un valor global de 730 días.** Tiene la mejor media ponderada (1,0010), la mejor
  diferencia conjunta frente a no decaer (−0,0023 ± 0,0016, 1,4 errores típicos: no concluyente) y el
  menor arrepentimiento en el peor caso (0,0025 en la Premier frente a 0,0046 de 365 en la
  Bundesliga). Es el borde superior de la malla y en dos ligas no decaer iguala o supera: no se ha
  probado una vida media mayor (por ejemplo 1 095 días). **La mejora global sobre no decaer es
  pequeña y sigue sin ser concluyente.** La decisión de fijarlo queda para el usuario; el código no
  tiene un valor por defecto.
- **El mercado gana en las 6 ligas** (entre 0,013 y 0,057 de log-loss).

## Malla de λ₂ cerca de 0 (Premier, 2023/24)

| λ₂ | 0 | 0,001 | 0,01 | 0,05 | 0,1 |
|---|---|---|---|---|---|
| Vida media 365: log-loss | **0,9336** | 0,9337 | 0,9338 | 0,9342 | 0,9346 |
| Vida media 730: log-loss | **0,9361** | 0,9361 | 0,9361 | 0,9362 | 0,9363 |

Crece de forma monótona con λ₂: **la mejor sigue siendo 0**. En este dataset la regularización no
aporta. Explicación posible, **no probada**: el equipo medio ya cubre a los equipos sin historial y
el resto tiene decenas de partidos. Se deja implementada (BACKLOG nº 26) pero **no se usa por
defecto** (`l2 = 0`).

## Vida media de 1 095 días frente a 730 (2026-10-29)

Mismo protocolo y `λ₂ = 0`. Regla acordada de antemano: si 1 095 es mejor o igual que 730, se usa
1 095; si 730 sigue ganando, se fija 730. Log-loss:

| Liga | 365 | 730 | 1 095 | 1 460 | sin decaimiento |
|---|---|---|---|---|---|
| Premier | 0,9336 | 0,9361 | 0,9385 | 0,9401 | 0,9466 |
| LaLiga | 0,9760 | 0,9768 | 0,9777 | 0,9781 | 0,9793 |
| Serie A | 1,0050 | 1,0024 | 1,0020 | 1,0020 | 1,0028 |
| Bundesliga | 1,0039 | 0,9995 | 0,9988 | 0,9986 | 0,9993 |
| Ligue 1 | 1,0335 | 1,0315 | 1,0309 | 1,0306 | 1,0298 |
| Segunda | 1,0548 | 1,0533 | 1,0534 | 1,0535 | 1,0545 |
| **Media ponderada** | 1,0021 | **1,0010** | 1,0014 | 1,0017 | 1,0033 |

Diferencia pareada 1 095 − 730 (negativo = 1 095 mejor): Premier +0,0024 ± 0,0016, LaLiga +0,0008 ±
0,0011, Serie A −0,0004 ± 0,0010, Bundesliga −0,0008 ± 0,0012, Ligue 1 −0,0006 ± 0,0014, Segunda
+0,0001 ± 0,0008. **Conjunto: +0,0003 ± 0,0005.**

**730 sigue ganando en la media (1,0010 frente a 1,0014)**, aunque la diferencia es 0,6 errores
típicos: es un empate estadístico, con un óptimo muy plano entre 730 y 1 095. Se aplica la regla y
se fija **730 días**. (1 095 gana en tres ligas por menos de 0,001, y 1 460 no mejora.)

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

# 011 — Evaluación formal con reajuste (walk-forward estricto) y cierre de la Fase 2

**Estado:** Aceptada (2026-10-29) · **Fecha:** 2026-10-29

Es la prueba de aceptación de la Fase 2 (PLAN §6): Dixon-Coles y Elo con **la misma información**
frente a Pinnacle, reproducible con `uv run tipster evaluate`. (El PLAN hablaba de
`python -m tipster.evaluation`; se usó un comando de la CLI, como `ingest` y `tune`.)

## 1. Protocolo

- **Prueba:** 2023/24 completa en las 6 ligas (2 224 partidos). Entrenamiento y calentamiento:
  desde el 2016-08-01. **2024/25 sigue sin usarse** y es el test ciego.
- **Dixon-Coles** se reajusta **antes de cada día de partidos** (765 ajustes en total) con el
  historial y todo lo de la prueba **estrictamente anterior** a ese día; vida media 730 días
  (ADR 008), decaimiento relativo al último partido del entrenamiento.
- **Elo** se actualiza partido a partido; las predicciones de un día se hacen antes de actualizar con
  ese día. Sus cinco hiperparámetros se estiman **una sola vez**, solo con el historial anterior a la
  prueba, por liga y con el mejor de 3 inicios de Nelder-Mead. No se usan los de otra liga.
- **Misma información:** con bloques diarios, los dos modelos ven exactamente los resultados con fecha
  anterior a cada partido.
- **Sin fuga, con tests** (`tests/unit/test_walk_forward.py`): un espía comprueba que cada ajuste solo
  recibe partidos anteriores al bloque y todos los anteriores; cambiar los resultados posteriores no
  altera ninguna predicción anterior (Dixon-Coles y Elo); el primer bloque coincide con el ajuste
  directo; prueba y historial no pueden solaparse. Tres mutaciones de fuga las hacen fallar.
- **No se corrige a mano el sesgo del empate** (ni se calibra): la calibración queda para la Fase 3
  con datos de validación separados.

## 2. Excepción justificada: λ₂ = 0,01 en el walk-forward

El ADR 008 fijó `λ₂ = 0`. En el walk-forward diario, la primera ejecución falló en la **Segunda**
con `FitError: algún ataque o defensa diverge`: en 6 de 161 bloques (el primero, el 2023-08-13) un
ascendido (el Ferrol) tenía un único partido en el entrenamiento y su defensa no tiene máximo
finito sin penalización. Es el caso que la L2 debía cubrir; la validación anterior no lo veía porque
allí los ascendidos eran equipos sin historial («equipo medio»), nunca equipos con 1 o 2 partidos.

Se aprobó `λ₂ = 0,01` en todas las ligas. No altera lo que ya convergía (bloques semanales, diferencia
pareada de log-loss entre `λ₂ = 0` y 0,01: +0,00001, −0,00000, −0,00000, +0,00001 y −0,00002, todas
con error típico ≤ 0,00003) y resuelve el fallo. Se descartaron «equipo medio para quien tenga menos
de N partidos» (una regla arbitraria que sesga) y «reutilizar el modelo del bloque anterior»
(esconde el fallo). BACKLOG nº 26.

## 3. Resultados

Log-loss (Brier), prueba 2023/24:

| Liga | Partidos | Dixon-Coles sin reajuste | **Dixon-Coles** | **Elo** | **Pinnacle** |
|---|---|---|---|---|---|
| Premier | 380 | 0,9361 (0,5517) | 0,9248 (0,5445) | 0,9295 (0,5477) | 0,8995 (0,5258) |
| LaLiga | 380 | 0,9768 (0,5811) | 0,9649 (0,5735) | 0,9638 (0,5745) | 0,9510 (0,5659) |
| Serie A | 380 | 1,0024 (0,6017) | 0,9914 (0,5930) | 0,9873 (0,5914) | 0,9639 (0,5751) |
| Bundesliga | 308 | 0,9996 (0,5976) | 0,9842 (0,5881) | 0,9944 (0,5937) | 0,9460 (0,5596) |
| Ligue 1 | 308 | 1,0315 (0,6193) | 1,0343 (0,6219) | 1,0296 (0,6196) | 1,0142 (0,6105) |
| Segunda | 468 | 1,0533 (0,6367) | 1,0604 (0,6395) | 1,0542 (0,6365) | 1,0437 (0,6290) |
| **Todas** | 2 224 | 1,0011 (0,5989) | **0,9950 (0,5945)** | **0,9943 (0,5947)** | **0,9719 (0,5791)** |

(Pinnacle: 2 221 partidos con cuota.) Diferencia pareada de log-loss ± error típico (negativo = el
primero es mejor):

| Comparación | Premier | LaLiga | Serie A | Bundesliga | Ligue 1 | Segunda | **Conjunto** |
|---|---|---|---|---|---|---|---|
| Elo − Dixon-Coles | +0,0047 ± 0,0085 | −0,0010 ± 0,0064 | −0,0041 ± 0,0059 | +0,0101 ± 0,0093 | −0,0047 ± 0,0083 | −0,0063 ± 0,0090 | **−0,0006 ± 0,0033** |
| Dixon-Coles reajustado − sin reajuste | −0,0113 ± 0,0069 | −0,0120 ± 0,0062 | −0,0110 ± 0,0050 | −0,0153 ± 0,0074 | +0,0028 ± 0,0048 | +0,0072 ± 0,0088 | −0,0061 ± 0,0029 |
| Dixon-Coles − Pinnacle | +0,0253 ± 0,0092 | +0,0139 ± 0,0085 | +0,0275 ± 0,0081 | +0,0383 ± 0,0119 | +0,0201 ± 0,0099 | +0,0163 ± 0,0107 | **+0,0229 ± 0,0040** |
| Elo − Pinnacle | +0,0299 ± 0,0095 | +0,0128 ± 0,0095 | +0,0234 ± 0,0088 | +0,0484 ± 0,0115 | +0,0154 ± 0,0083 | +0,0103 ± 0,0072 | **+0,0223 ± 0,0037** |

Tasa de empates (prevista media / observada):

| Liga | Observada | Dixon-Coles | Elo | Pinnacle |
|---|---|---|---|---|
| Premier | 0,216 | 0,226 | 0,219 | 0,225 |
| LaLiga | 0,282 | 0,256 | 0,271 | 0,263 |
| Serie A | 0,295 | 0,249 | 0,258 | 0,263 |
| Bundesliga | 0,263 | 0,238 | 0,244 | 0,228 |
| Ligue 1 | 0,266 | 0,261 | 0,263 | 0,258 |
| Segunda | 0,301 | 0,292 | 0,311 | 0,303 |
| **Todas** | **0,272** | 0,255 | 0,264 | |

Cómputo (portátil con macOS, un hilo): Dixon-Coles 765 ajustes en **62,3 s** (0,07–0,11 s por ajuste;
Premier 8,5 s, LaLiga 11,5, Serie A 14,5, Bundesliga 7,4, Ligue 1 7,2, Segunda 13,2) y la estimación
del Elo (3 inicios por liga) 119,7 s (15–23 s por liga): unos 3 minutos en total.

## 4. Veredicto

- **¿Gana Dixon-Coles al Elo con la misma información? No.** Es un empate estadístico: Elo − Dixon-Coles
  = −0,0006 ± 0,0033 en conjunto (0,2 errores típicos), con medias de 0,9950 y 0,9943. Por liga hay
  signos mixtos y ninguna diferencia supera 1,1 errores típicos. Hay un matiz que favorece a Dixon-Coles:
  su vida media se eligió con 2023/24 y los hiperparámetros del Elo no.
- **Reajustar importa más que el modelo:** Dixon-Coles mejora 0,0061 ± 0,0029 (2,1 errores típicos)
  respecto a ajustarlo una vez; en Premier, LaLiga, Serie A y Bundesliga mejora más de 0,011 y en Ligue 1 y
  Segunda no mejora (+0,0028 y +0,0072, no concluyentes).
- **Distancia al mercado:** Dixon-Coles queda a **+0,0229 ± 0,0040 (5,7 errores típicos)** y el Elo a
  **+0,0223 ± 0,0037 (6,0)** de Pinnacle; por liga, entre 1,5 y 3,4 errores típicos para Dixon-Coles
  (Segunda 1,5, LaLiga 1,6, Ligue 1 2,0, Premier 2,7, Bundesliga 3,2, Serie A 3,4). El mercado gana a los
  dos en todas las ligas, como se esperaba.
- **Empates:** los dos subestiman la tasa observada (0,255 y 0,264 frente a 0,272), sobre todo
  Dixon-Coles en LaLiga (0,256 frente a 0,282) y Serie A (0,249 frente a 0,295). Pinnacle falla igual en Serie
  A (0,263). No se ha corregido.

## 5. Límites

- 2023/24 **no es ciega**: la vida media de Dixon-Coles se eligió con ella. Una comparación limpia es la
  de 2024/25, que no se ha tocado.
- Los hiperparámetros del Elo no se identifican bien (3 inicios con hasta 4,6 unidades de −logL de
  diferencia en la Premier; `δ` de −18 a −165): BACKLOG nº 28.
- Una sola temporada de prueba: un error típico de ~0,003–0,004 en el conjunto y de ~0,01 por liga.

## 6. Qué cierra y qué deja abierto

Cumple el criterio de aceptación de la Fase 2 (informe reproducible por liga que compara Dixon-Coles,
Elo y el mercado; el mercado gana y el informe lo dice). Queda para después: el test ciego 2024/25, la
calibración, el ensamble o respaldo entre modelos y la Fase 3 (mezcla con el mercado, stake y picks).

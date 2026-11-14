# 014 — Picks probables: devig Shin, dos niveles y horizonte de 4 días

**Estado:** Aceptada e implementada (2026-11-14) · Sustituye en parte al ADR 012 (devig y `max_odds`)

## Contexto

Auditoría tras el scan del 14/11 (9 picks con stake): 5 eran cuotas de 7 a 12,5, 7 venían de `marathonbet_no_es`,
todos eran de partidos a 7–15 días, y el CLV de los 3 primeros cierres era −14 % (± 6,2; muestra insuficiente). El usuario
pide picks con valor **y** estadísticamente probables, dejando sitio a algún improbable.

Tres causas en el diseño:

1. **El devig multiplicativo infla el EV de las cuotas largas** si Pinnacle carga más margen en los resultados
   improbables (sesgo favorito-longshot, ya reconocido en el ADR 012). Simulación con `pricing/devig.py`, un pick que el
   multiplicativo ve con EV +5 % y un margen de Pinnacle del 2,5–4 %:

   | Cuota | EV multiplicativo | EV Shin | EV power |
   |---|---|---|---|
   | ~3,5 | +5 % | +4,4 a +4,6 % | +4,2 a +4,5 % |
   | ~6 | +5 % | +1,9 a +3,0 % | +1,1 a +2,5 % |
   | ~8 | +5 % | 0 a +1,7 % | −1,0 a +1,2 % |
   | ~11,5 | +5 % | −2,9 a −0,2 % | −4,2 a −1,0 % |

   La simulación **supone** el sesgo (genera la línea cargando más margen en la cuota larga); no lo demuestra. No se pudo
   contrastar con el histórico en esta sesión (descarga bloqueada).
2. **Selección adversa:** como el error crece con la cuota, los improbables superan el umbral del 3 % con más facilidad.
3. **Antelación:** el scan daba stake a partidos a 15 días y un partido con pick abierto no se reevalúa.

## Decisión

| Parámetro | Antes | Ahora |
|---|---|---|
| `devig_method` | multiplicativo | **shin** (también en el CLV de `close`) |
| Nivel principal | — | cuota 1,5–4,0 (`longshot_odds`), EV ≥ 3 % (`ev_min`) |
| Nivel improbable | — | cuota > 4,0 y ≤ 8,0 (`max_odds`), EV ≥ 6 % (`longshot_ev_min`), como mucho 2 abiertos a la vez (`max_open_longshots`) |
| `max_days_ahead` | sin límite | **4 días** |

- Un VALUE que no cumple se sigue mostrando, sin stake y con el motivo escrito; y no compite por el stake de su partido.
- Los improbables entran por orden de EV; los ya abiertos consumen hueco.
- `tipster status` desglosa el CLV por nivel y por casa (`CLV por nivel`, `CLV por casa`).
- Shin empató en log-loss con los demás métodos en la validación (0,98716 frente a 0,98719, ADR 012): no empeora la
  calibración global y es más prudente en la cola.

## Consecuencias

- **Menos picks** (estimación: 2–4 por scan en vez de 9) y más tiempo hasta tener ≈ 30 con CLV.
- **Los picks abiertos con las reglas anteriores se dejan correr** (decisión del usuario). Su CLV se calculará con Shin
  al cierre, es decir, algo más bajo que con el multiplicativo con el que se eligieron; los 3 CLV ya guardados no cambian.
  El desglose por nivel permite separarlos.
- Los 2 huecos de improbables están hoy ocupados por los picks abiertos de cuota > 4 del scan del 14/11: no entrarán
  improbables nuevos hasta que se liquiden.
- **Umbrales elegidos por prudencia, no ajustados con datos** (4,0; 6 %; 2; 4 días). Revisar con ≈ 30 picks con CLV usando
  el desglose por nivel y por casa. Nada de esto demuestra que haya valor: lo decide el CLV.
- Los tests antiguos calculados a mano fijan las reglas anteriores en su configuración; las nuevas se prueban en
  `tests/integration/test_scan_niveles.py`.

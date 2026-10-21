# 005 — Deporte y mercado como registros tipados

**Estado:** Aceptada (2026-10-21) · **Fecha:** 2026-10-21

## Contexto

El alcance inicial es fútbol (1X2, O/U 2.5 y BTTS), pero el diseño debe poder ampliarse a tenis
y baloncesto sin repartir `if deporte == …` o `if mercado == …` por el código.

## Opciones

1. Ramas condicionales donde haga falta.
2. Jerarquía de clases por deporte y mercado.
3. Registros de especificaciones inmutables (`SportSpec`, `CompetitionSpec`, `MarketSpec`) con
   estrategias asociadas.

## Decisión

Opción 3. Cada mercado se registra una vez con sus selecciones y su línea y, según la fase, sus
estrategias:

- cómo obtener su probabilidad desde la salida del modelo (F2);
- cómo se liquida con el resultado (F3);
- su grupo de correlación para las combinadas (F4).

El flujo (`scan`, clasificación, stake, combinadas) consulta el registro y no conoce mercados
concretos. Un test recorre el registro y falla si algún mercado carece de una estrategia que su
fase exige.

## Consecuencias

- Añadir un mercado o un deporte es registrar datos y estrategias, no modificar el flujo.
- La F1 tiene un pequeño coste inicial de estructura, limitado a lo que la propia F1 usa
  (selecciones y línea); las estrategias se añaden en su fase, no antes.

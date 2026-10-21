# 001 — Proveedor de cuotas inicial y estrategia multiproveedor

**Estado:** Propuesta · **Fecha:** 2026-10-21

## Contexto

El tipster debe leer cuotas de casas con licencia DGOJ solo por API (nada de scraping) y
necesita una referencia *sharp* para la probabilidad justa. La
[verificación de la Fase 0](../fase-0/verificacion-proveedores.md), sin llamadas reales, dice
que:

- The Odds API no tiene ninguna web .es. Sí tiene Pinnacle (con posible retraso), Betfair
  Exchange y feeds no españoles de 888sport, William Hill, Marathonbet y Winamax. Su modelo de
  costes está bien documentado y actualiza cada ~60 s (exchanges, ~20 s). [B]
- OddsPapi es el único con indicios de feeds .es (codere.es, bwin.es, 888sport.es, betway.es,
  leovegas.es, paf.es). [C]
- API-Football actualizaría las cuotas una vez al día [C] y no se conoce su lista de casas.
- La API de Betfair exige credenciales de casa y no permite el uso solo de lectura con la clave
  Live. [B]

## Opciones

1. Solo The Odds API.
2. Solo OddsPapi.
3. The Odds API primero y OddsPapi después, ambos detrás de `OddsProvider`.
4. API-Football.
5. API de Betfair directa.

## Decisión (propuesta)

Opción 3. Se empieza con The Odds API, como pediste, detrás del protocolo `OddsProvider`. El
diseño es multiproveedor desde el primer día: modelos canónicos, registro de casas con
jurisdicción ([ADR 003](003-registro-de-casas-y-jurisdiccion.md)) e ids externos por proveedor.
OddsPapi se añade en cuanto se verifique a nivel A (Fase 1b). API-Football queda descartada
como fuente de cuotas y la API de Betfair directa, descartada del todo.

## Consecuencias

- Mientras no haya un segundo proveedor no habrá cuotas de webs .es. Según D1, los feeds no
  españoles se muestran etiquetados o se ocultan.
- Hará falta casar eventos entre proveedores (competición, hora y equipos normalizados).
- Coste estimado: 14 créditos por escaneo completo (7 competiciones × 2 mercados × 1 grupo de
  casas).
- La regla de descarte por «liquidez o límite bajo» no se puede aplicar con The Odds API (no se
  encontró ese dato): esas cuotas llevarán el motivo «liquidez desconocida».

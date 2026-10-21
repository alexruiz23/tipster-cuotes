# 002 — Referencia *sharp* para el devig y el CLV

**Estado:** Aceptada (2026-10-21) · **Fecha:** 2026-10-21

## Contexto

El plan original usa Pinnacle para la probabilidad justa y su cuota de cierre para el CLV, la
métrica principal de calidad. La verificación encontró que:

- Pinnacle cerró su API pública el 23/07/2025. [B]
- The Odds API da `pinnacle` «desde la web pública, con posible retraso». [B]
- football-data.co.uk avisa de que las cuotas de Pinnacle son poco fiables y van desfasadas
  desde el 23/07/2025 [B]. Según terceros, desaparecen tras el 08/01/2026 y no existen en
  2026/27 [C].
- Betfair Exchange llega por The Odds API (`betfair_ex_eu`, `betfair_ex_uk`, ~20 s) y por
  football-data.co.uk (`BFEH/BFED/BFEA`; las columnas de cierre están sin verificar).

## Opciones

1. Solo Pinnacle.
2. Solo Betfair Exchange.
3. Pinnacle si está fresca y, si no, Betfair Exchange.
4. Consenso de varias casas.

## Decisión

Opción 3.

- **En vivo:** la referencia de cada (evento, mercado) es Pinnacle si su `last_update` no supera
  `TIPSTER_MAX_REFERENCE_AGE_MINUTES`; si no, Betfair Exchange con el mismo método de devig; si
  ninguna está fresca, la oportunidad se descarta. Cada oportunidad guarda qué referencia usó.
- **Histórico:** cierre de Pinnacle (`PSC*`) hasta 2024/25. Desde 2025/26, cierre de Betfair
  Exchange (`BFEC*`) si se confirma que existe; si no, esas temporadas quedan fuera del cálculo
  del CLV.
- **Definición:** CLV = cuota_tomada × p_cierre_justa − 1, donde p_cierre_justa es el devig de
  la última captura de la referencia antes del inicio (con antigüedad máxima). Ejemplo: 2.20
  contra un cierre justo de 2.00 da +10 %.

## Consecuencias

- La métrica deja de ser «CLV contra Pinnacle» en sentido estricto cuando se usa el respaldo.
  Los informes separan el CLV por referencia.
- Medir el cierre en vivo exige capturar cuotas cerca del inicio de cada partido; se diseña en
  la Fase 3.
- El exchange tiene diferencia entre precio de compra y de venta y comisión (sin verificar):
  como referencia se usa el precio a favor (*back*) con devig, y se documentará al implementar.

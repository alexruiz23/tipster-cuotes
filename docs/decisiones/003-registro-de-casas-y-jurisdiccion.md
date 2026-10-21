# 003 — Registro canónico de casas y jurisdicción del feed

**Estado:** Aceptada (2026-10-21) · **Fecha:** 2026-10-21

## Contexto

Una misma marca puede tener cuotas distintas según la jurisdicción. The Odds API da feeds
internacionales, británicos, franceses o alemanes de marcas que también operan en España
(888sport, William Hill, Marathonbet, Winamax), pero ninguno de su web .es. Recomendar «888sport
a 2.10» cuando en 888sport.es está a 2.05 sería engañoso.

## Opciones

1. Usar la clave del proveedor tal cual (por ejemplo, `sport888`).
2. Un registro canónico de casas que distinga jurisdicción y rol.

## Decisión

Opción 2. Cada casa es un `BookmakerSpec` con id canónico (`888sport_no_es`, `codere_es`…),
marca, jurisdicción del feed, rol (`sharp`, `exchange` o `casa`), `es_site` (verdadero solo si el
feed es el de la web .es con licencia DGOJ) y su clave en cada proveedor.

- Toda oportunidad muestra la jurisdicción del feed.
- Si `es_site` es falso, la etiqueta incluye siempre «FEED NO-ES · VERIFICA LA CUOTA EN LA WEB
  .ES». No hay opción para ocultarlos (D1 confirmada).
- Las referencias (Pinnacle y Betfair Exchange internacional) nunca se presentan como casas en
  las que apostar.

## Consecuencias

- La salida es honesta, a costa de tener menos picks «limpios» hasta contar con feeds .es.
- Añadir un proveedor implica mapear sus claves en el registro; un test falla si el proveedor
  devuelve una casa que el registro no conoce y no se ha decidido ignorarla.

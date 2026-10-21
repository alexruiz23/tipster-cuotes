# 006 — Hora de captura y antigüedad de las cuotas

**Estado:** Aceptada (2026-10-21) · **Fecha:** 2026-10-21

## Contexto

ARQUITECTURA describía `captured_at` como «cuándo la recibimos». Al implementar la Fase 1 se
guardó otro instante, y hay que dejar escrito cuál y qué efecto tiene en la antigüedad, que
decide los descartes.

## Opciones

1. Inicio de la petición HTTP.
2. Fin de la petición (recepción de la respuesta).
3. `provider_last_update` del proveedor.

## Decisión

- **`captured_at` = instante de inicio del intento HTTP que trajo la respuesta**: el reloj se lee
  justo antes de enviarla (`providers/http.py`); con reintentos, el del intento que tuvo éxito.
  Si la respuesta sale de la caché, se conserva el `captured_at` de la petición original.
- **Por qué:** es el instante más antiguo en que pudo tomarse la foto de las cuotas, así que nunca
  presenta un dato como más reciente de lo que es.
- **`provider_last_update` se guarda aparte** y es lo que se usa para la antigüedad.
- **La antigüedad** (`OddsQuote.age`), que comparan `TIPSTER_MAX_QUOTE_AGE_MINUTES` y
  `TIPSTER_MAX_REFERENCE_AGE_MINUTES`, se mide contra `provider_last_update`; solo si falta se mide
  contra `captured_at`, y la oportunidad lo dice en sus motivos.

## Consecuencias

- En el caso normal, con `provider_last_update`, la latencia de la petición no afecta a la
  antigüedad.
- En el caso de respaldo, sin `provider_last_update`, una petición lenta infla la antigüedad como
  mucho en su duración (`duration_ms`, guardada en `provider_requests`). Es un error del lado
  prudente: puede descartar de más, nunca de menos.
- La reutilización desde la caché sí envejece la cuota, que es lo correcto: el dato es el de la
  petición original.
- **Tests** (`tests/integration/test_http_client.py`):
  - `test_acierto_de_cache_no_llama_ni_gasta_y_conserva_la_hora_original`: la caché conserva el
    `captured_at` original.
  - `test_peticion_lenta_sin_last_update_la_antiguedad_cubre_toda_la_duracion`: con una petición de
    30 s y sin `provider_last_update`, `captured_at` es el inicio del intento y la antigüedad nunca
    es menor que la duración real. Una mutación que guarda el fin de la petición hace fallar este
    test.
  - `test_peticion_lenta_con_last_update_mide_contra_el_proveedor`: con `provider_last_update`, la
    antigüedad se mide contra el proveedor y no contra `captured_at`.

# tipster-cuotes

> **Juego responsable.** Solo para mayores de 18 años. Este proyecto no garantiza ningún
> beneficio: apostar implica un riesgo real de perder dinero. Si el juego deja de ser un
> entretenimiento, pide ayuda en [jugarbien.es](https://www.jugarbien.es).

Tipster automático de fútbol que **solo recomienda** apuestas. Nunca las coloca, nunca inicia
sesión en una casa de apuestas y nunca guarda credenciales de casas.

## Estado

**Fase 0 — verificación y diseño, pendiente de aprobación.** Todavía no hay código.

**Puerta de salida de la Fase 0: no cumplida.** Sin código no hay tests, ruff, mypy ni CI que
ejecutar, así que esos requisitos no aplican. La CI se crea en el primer commit de la Fase 1
(detalle en [PLAN §0](docs/PLAN.md#0-estado-real-de-la-puerta-de-salida-de-la-fase-0)).

| Documento | Contenido |
|---|---|
| [Verificación de proveedores](docs/fase-0/verificacion-proveedores.md) | Qué casas, mercados, cuotas de peticiones y precios cubre cada proveedor, con su nivel de verificación |
| [Arquitectura](docs/ARQUITECTURA.md) | Carpetas, módulos, interfaces y modelo de datos |
| [Plan](docs/PLAN.md) | Fases, criterios de aceptación, bloqueos y decisiones pendientes |
| [Decisiones](docs/decisiones/README.md) | Registros de decisión (ADR) |
| [Backlog](docs/BACKLOG.md) | Ideas fuera de alcance |

## Qué hará

1. Leer cuotas por API (nunca por scraping), guardando siempre la hora de captura y el origen.
2. Calcular la probabilidad justa a partir de una referencia *sharp* (Pinnacle o Betfair
   Exchange) con cuatro métodos de devig: multiplicativo, aditivo, power y Shin.
3. Contrastar cada oportunidad con un modelo propio (Dixon-Coles y Elo, calibrados).
4. Recomendar apuestas simples con stake (Kelly fraccionado con topes) y combinadas formadas
   solo por patas de valor positivo.
5. Medir la calidad por CLV y con un backtest walk-forward contra baselines, sin maquillar
   resultados.

## Limitaciones conocidas tras la Fase 0

- The Odds API no tiene ninguna web .es: solo feeds de otras jurisdicciones de 888sport, William
  Hill, Marathonbet, Betfair y Winamax, que pueden no coincidir con la web española.
- Pinnacle cerró su API pública el 23/07/2025, y sus cuotas en el histórico de
  football-data.co.uk no son fiables desde entonces.
- No hay ninguna fuente verificada de cuotas de Ambos Marcan para fútbol europeo, ni histórico
  verificado de la Champions.
- Ningún dato de la verificación procede todavía de una llamada real a una API.

## Qué no hará

- Colocar apuestas, iniciar sesión en casas o guardar sus credenciales.
- Hacer scraping de webs de casas de apuestas.
- Prometer beneficios: con pocas apuestas, ningún ROI demuestra nada.

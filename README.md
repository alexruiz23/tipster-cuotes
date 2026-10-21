# tipster-cuotes

> **Juego responsable.** Solo para mayores de 18 años. Este proyecto no garantiza ningún
> beneficio: apostar implica un riesgo real de perder dinero. Si el juego deja de ser un
> entretenimiento, pide ayuda en [jugarbien.es](https://www.jugarbien.es).

Tipster automático de fútbol que **solo recomienda** apuestas. Nunca las coloca, nunca inicia
sesión en una casa de apuestas y nunca guarda credenciales de casas.

## Estado

**Fase 1 construida, no cerrada: pendiente de red y clave para cerrar R1–R4.** Todo lo que no
depende de una llamada real a The Odds API está hecho y probado con fixtures. Los cuatro criterios
que exigen llamada real siguen abiertos porque la red de este entorno bloquea el proveedor y no hay
`ODDS_API_KEY` (D4 = B). Detalle y estado de cada criterio en
[docs/fase-1/plan.md §9](docs/fase-1/plan.md#9-estado).

**Fase 0: puerta de salida no cumplida.** Sin código no había tests, ruff, mypy ni CI que ejecutar
(detalle en [PLAN §0](docs/PLAN.md#0-estado-real-de-la-puerta-de-salida-de-la-fase-0)).

| Documento | Contenido |
|---|---|
| [Plan de la Fase 1](docs/fase-1/plan.md) | Plan aprobado, criterios de aceptación y estado (handoff) |
| [Verificación de proveedores](docs/fase-0/verificacion-proveedores.md) | Qué casas, mercados, consumo y precios cubre cada proveedor, con su nivel de verificación |
| [Arquitectura](docs/ARQUITECTURA.md) | Carpetas, módulos, interfaces y modelo de datos |
| [Plan general](docs/PLAN.md) | Fases y decisiones D1–D7 |
| [Decisiones](docs/decisiones/README.md) | Registros de decisión (ADR) |
| [Backlog](docs/BACKLOG.md) | Ideas fuera de alcance |

## Instalación

Requiere Python 3.12 y [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env    # y rellena ODDS_API_KEY si vas a usar datos en vivo
```

## Uso

```bash
# Con datos grabados (no llama a la red ni gasta créditos). Las fixtures del repositorio son
# inventadas: la salida lo indica y va marcada «DATOS GRABADOS, NO EN VIVO».
uv run tipster scan --offline tests/fixtures/the_odds_api/sintetico

# En vivo (necesita ODDS_API_KEY y acceso de red a api.the-odds-api.com)
uv run tipster scan
uv run tipster scan --competicion laliga --competicion premier --max-creditos 10
```

`tipster scan` muestra, por cada oportunidad: partido, mercado, selección, casa (con la
jurisdicción de su feed), cuota, cuota justa, p_modelo («—» hasta la Fase 3), p_mercado, EV, stake
(«—» hasta la Fase 3), etiqueta, referencia usada y hora de captura. Etiquetas:

- **VALUE**: EV de al menos el mínimo configurado (3 % por defecto).
- **POSIBLE ERROR · RIESGO DE ANULACIÓN**: cuota más de un 15 % por encima de la justa.
- **FEED NO-ES · VERIFICA LA CUOTA EN LA WEB .ES**: acompaña a toda cuota que no viene de la web
  española de la casa. Hoy son todas: The Odds API no tiene feeds .es (D1).

La referencia es Pinnacle si su cuota está fresca y completa; si no, Betfair Exchange (D2).
Ninguna de las dos es una casa en la que apostar desde España: solo sirven para estimar la
probabilidad justa.

Códigos de salida: 0 (ejecución completa o parcial), 1 (error del proveedor), 2 (configuración).

## Datos, logs y backup

- **Base de datos:** `data/tipster.sqlite` (ignorada por git). Guarda cada ejecución, cada
  petición al proveedor con su consumo de créditos, todos los eventos y cuotas (con hora de
  captura y origen) y los picks emitidos con las cuotas exactas de su referencia. Con `--offline`
  la base va en memoria salvo que se pase `--db`.
- **Respuestas crudas:** `data/raw/`, sin la clave.
- **Logs y métricas:** en la Fase 1 solo se escribe a stdout; el consumo queda en las tablas
  `runs` y `provider_requests`.
- **Backup:** no se hace en la Fase 1; se decidirá en la Fase 3.

## Desarrollo

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit install    # opcional: gitleaks y ruff antes de cada commit
```

La CI de GitHub Actions ejecuta lo mismo y además gitleaks en cada push y PR.

No hay `CHANGELOG.md`: el historial de commits de `main` hace de changelog. El estado de
cada fase (handoff) está en su plan; el de la Fase 1, en
[docs/fase-1/plan.md §9](docs/fase-1/plan.md#9-estado).

## Limitaciones conocidas

- The Odds API no tiene ninguna web .es: solo feeds de otras jurisdicciones de 888sport, William
  Hill, Marathonbet, Betfair y Winamax, que pueden no coincidir con la web española.
- Pinnacle cerró su API pública el 23/07/2025; The Odds API la obtiene de su web pública con
  posible retraso, y en el histórico de football-data.co.uk no es fiable desde esa fecha.
- La estructura de las respuestas de The Odds API y las claves de 6 de las 7 competiciones están
  sin verificar con una llamada real.
- The Odds API no da liquidez ni límites: toda cuota lleva «liquidez desconocida».
- No hay ninguna fuente verificada de cuotas de Ambos Marcan para fútbol europeo, ni histórico
  verificado de la Champions.

## Qué no hará

- Colocar apuestas, iniciar sesión en casas o guardar sus credenciales.
- Hacer scraping de webs de casas de apuestas.
- Prometer beneficios: con pocas apuestas, ningún ROI demuestra nada.

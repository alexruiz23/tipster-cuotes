# Fase 0 — Verificación de proveedores de datos

**Fecha:** 2026-10-21 · **Estado:** completada con limitaciones (lee la §0 antes que nada).

**Actualización 2026-10-29:** la §13 recoge la verificación de nivel A de The Odds API (criterio
R4 de la Fase 1), hecha con llamadas reales, la §14 la de football-data.co.uk y la §15 la del
dataset de Hugging Face (Fase 2). Las §0–§12 se dejan como se escribieron; donde las §13 a §15 las
contradicen o las completan, mandan ellas.

## 0. Limitaciones de esta verificación

1. **Red bloqueada.** La política de red del entorno en el que trabajo bloquea el acceso directo
   a todas las webs y APIs revisadas: `the-odds-api.com`, `api.the-odds-api.com`, `oddspapi.io`,
   `www.api-football.com`, `developer.betfair.com`, `www.football-data.co.uk`,
   `www.ordenacionjuego.es`, `understat.com` y `fbref.com` (el proxy responde 403 y la
   herramienta de descarga de páginas tampoco las resuelve). No pude abrir ninguna página ni
   descargar ningún fichero.
2. **Sin API keys.** No hay clave de ningún proveedor, así que no he hecho ninguna llamada real.
3. **Única vía disponible: un buscador web.** Todo lo que sigue sale de extractos de páginas que
   devuelve un buscador. Esos extractos pueden estar cortados (por ejemplo, listas de casas
   incompletas) o venir de copias en caché antiguas.

Por eso cada dato lleva un **nivel de verificación**:

| Nivel | Significado |
|---|---|
| **A** | Comprobado con una llamada real a la API o descargando el fichero. **Ningún dato de este informe tiene nivel A.** |
| **B** | Página oficial del proveedor, leída en extractos del buscador. Fiable, pero puede estar incompleta o desactualizada. |
| **C** | Fuente secundaria: blog o marketing del propio proveedor, comparadores, foros o análisis de terceros. Es un indicio, no una prueba. |
| **NO VERIFICADO** | No he podido comprobarlo. |

En la §11 están las comprobaciones que suben estos datos a nivel A. Son la primera tarea de la
Fase 1 en cuanto haya red y clave.

## 1. Resumen

1. **The Odds API no cubre ninguna web española (.es).** De las 12 casas de tu lista aparecen
   5 marcas, todas con feeds de otras jurisdicciones (internacional, Reino Unido, Francia o
   Alemania): 888sport, William Hill, Marathonbet, Betfair y Winamax. bet365 solo existe para
   Australia. Codere, Sportium, Bwin, Luckia, Kirolbet y Retabet no constan. [B]
2. **De los proveedores revisados, solo OddsPapi tiene indicios de feeds .es.** Un artículo
   suyo (medición del 24/08/2026) dice que 9 casas con licencia española dan cuotas de LaLiga
   y nombra 6: 888sport.es, betway.es, bwin.es, codere.es, leovegas.es y paf.es. [C]
3. **Pinnacle cerró su API pública el 23/07/2025.** The Odds API sigue ofreciendo `pinnacle`,
   pero avisa de que la obtiene de la web pública y puede ir con retraso. [B]
4. **Las cuotas de Pinnacle en football-data.co.uk se degradan desde el 23/07/2025.** Lo avisa
   el propio sitio [B]. Según un análisis de terceros, desaparecen tras el 08/01/2026 y no
   existen en 2026/27 [C]. El CLV contra el cierre de Pinnacle solo es fiable en el histórico
   hasta la temporada 2024/25.
5. **Betfair Exchange:** su API exige iniciar sesión con una cuenta de Betfair, es decir,
   credenciales de casa, que el proyecto prohíbe. Sus precios sí llegan por The Odds API
   (`betfair_ex_eu`, `betfair_ex_uk`) y por football-data.co.uk (`BFEH/BFED/BFEA`). [B]
6. **Ambos Marcan (BTTS) no tiene fuente de cuotas verificada.** En The Odds API es un mercado
   adicional que solo se puede pedir evento a evento, y la documentación dice que esos mercados
   están limitados a deportes de EE. UU. y a casas seleccionadas [B]. En football-data.co.uk no
   consta (NO VERIFICADO).
7. **API-Football no sirve como fuente principal de value bets.** Sus cuotas se actualizarían una
   vez al día [C] y no pude ver su lista de casas (NO VERIFICADO).

## 2. Matriz: casas de tu lista × proveedor

Leyenda: **NO CONSTA** = no aparece en lo leído de la documentación (las listas se leyeron de
forma parcial, así que puede haber omisiones). **FEED NO-ES** = la marca está, pero su feed no
corresponde a su web española.

| Casa | Licencia DGOJ (comparadores) [C] | The Odds API [B] | OddsPapi [C] | API-Football |
|---|---|---|---|---|
| Bet365 | Sí | NO CONSTA para fútbol europeo (solo `bet365_au`: AFL/NRL, planes de pago) | «bet365 ES» en su directorio | NO VERIFICADO |
| Codere | Sí | NO CONSTA | codere.es con cuotas de LaLiga | NO VERIFICADO |
| Sportium | Sí | NO CONSTA | «Sportium» en el directorio, sin jurisdicción | NO VERIFICADO |
| Bwin | Sí | NO CONSTA | bwin.es con cuotas de LaLiga | NO VERIFICADO |
| William Hill | Sí (WHG Ceuta, S.A.) | FEED NO-ES: `williamhill` (eu, uk) | NO VERIFICADO | NO VERIFICADO |
| Betfair | Sí (Betfair International Spain, S.A.) | FEED NO-ES: `betfair_ex_eu`, `betfair_ex_uk` (exchange), `betfair_sb_uk` (casa UK) | NO VERIFICADO | NO VERIFICADO |
| Luckia | Sí | NO CONSTA | NO CONSTA | NO VERIFICADO |
| Kirolbet | Sí (Artxibet 2022, S.A.) | NO CONSTA | NO CONSTA | NO VERIFICADO |
| Retabet | Indicio débil | NO CONSTA | NO CONSTA | NO VERIFICADO |
| Marathonbet | Sí | FEED NO-ES: `marathonbet` (eu) | «Marathonbet» en el directorio | NO VERIFICADO |
| Winamax | NO VERIFICADO para apuestas deportivas (§9) | FEED NO-ES: `winamax_fr`, `winamax_de` (eu) | «Winamax» en el directorio | NO VERIFICADO |
| 888sport | Sí (888 Online Games España, S.A.) | FEED NO-ES: `sport888` (eu, uk) | 888sport.es con cuotas de LaLiga | NO VERIFICADO |

OddsPapi nombra además tres casas .es que no estaban en tu lista: **betway.es, leovegas.es y
paf.es** [C]. Otras marcas de The Odds API (Unibet, Betsson, LeoVegas…) podrían operar también
en España, pero igualmente con feeds de otras jurisdicciones (NO VERIFICADO).

**Por qué importa «FEED NO-ES».** Que la marca aparezca no significa que su cuota sea la de su
web española: las cuotas de una misma marca pueden variar entre jurisdicciones, y no he podido
comprobar en qué medida (NO VERIFICADO). Por eso el sistema nunca presentará la cuota de un
feed no español como si fuera la de la web .es (ver
[ADR 003](../decisiones/003-registro-de-casas-y-jurisdiccion.md)).

## 3. The Odds API

| Aspecto | Dato | Nivel |
|---|---|---|
| Casas de la región `eu` | `onexbet` (1xBet), `sport888` (888sport), `betclic_fr`, `betfair_ex_eu`, `betsson`, `coolbet`, `everygame`, `gtbets`, `leovegas_se`, `marathonbet`, `matchbook`, `nordicbet`, `pinnacle`, `tipico_de`, `unibet_fr`, `unibet_nl`, `unibet_se`, `williamhill`, `winamax_de`, `winamax_fr` | B (lista posiblemente incompleta) |
| Casas de la región `uk` (parcial) | `sport888`, `betfair_ex_uk`, `betfair_sb_uk`, `betano_uk`, `betfred_uk`, `betvictor`, `leovegas`, `williamhill` | B. Coral, Ladbrokes, Paddy Power, Sky Bet y Betway: NO VERIFICADO |
| Pinnacle | `pinnacle` en `eu`, con la nota «Odds are from public website which may incur a delay» | B |
| Mercados principales | `h2h` (en fútbol incluye el empate), `spreads`, `totals` | B |
| Mercados adicionales | `btts`, `draw_no_bet`, `h2h_3_way`, `alternate_totals`… Solo por `/v4/sports/{sport}/events/{eventId}/odds`, un evento por llamada. La documentación dice que están «currently limited to US sports and selected bookmakers» | B |
| Línea de `totals` | Cada casa da su línea principal; no está garantizado que sea 2.5 | NO VERIFICADO (requiere llamada real) |
| Competiciones | `soccer_epl` confirmada. La página de fútbol cita la Premier, la FA Cup, la Bundesliga, la Champions, la Europa League, la Serie A y LaLiga | B |
| Claves de LaLiga, Segunda, Serie A, Bundesliga, Ligue 1 y Champions | Salen del endpoint `/v4/sports`, que es gratuito pero requiere clave y solo lista competiciones en temporada. No sé si Segunda División está cubierta | NO VERIFICADO |
| Coste de `/odds` | Mercados × regiones. Cada grupo de 10 casas en `bookmakers` equivale a 1 región, y `bookmakers` tiene prioridad sobre `regions` | B |
| Coste de `/events/{id}/odds` | Mercados únicos devueltos × regiones | B |
| Coste de `/sports` y `/events` | Gratis | B / C |
| Coste de `/scores` | 1 crédito; 2 si se usa `daysFrom` (de 1 a 3 días hacia atrás) | C |
| Coste del histórico | 10 × mercados × regiones | B |
| Cabeceras de consumo | `x-requests-remaining`, `x-requests-used` y `x-requests-last`. Al agotar el saldo, error `OUT_OF_USAGE_CREDITS` | B |
| Planes | Gratis: 500 créditos/mes · 20K: 30 $/mes · 100K: 59 $/mes · 5M: 119 $/mes · 15M: 249 $/mes | B (posible copia en caché antigua) |
| Histórico | Solo en planes de pago. Mercados principales desde el 06/06/2020, con instantáneas cada 10 min (cada 5 min desde septiembre de 2022). Mercados adicionales desde mayo de 2023 | B |
| Frecuencia de actualización | Antes del partido: ~60 s en mercados principales, ~5 min en apuestas a largo plazo y ~20 s en exchanges. El intervalo se acorta en las 6 h previas al inicio | B |
| `last_update` | Por mercado: la última vez que el proveedor vio la cuota en la casa. Los mercados suspendidos desaparecen a los ~15 min | B |
| Liquidez y límites | No encontré información | NO VERIFICADO (probablemente no los da) |
| Límite de peticiones por segundo | No encontré información | NO VERIFICADO |
| Términos | Prohibido revender o redistribuir los datos como producto | B |

**Estimación de consumo** (cálculo propio con las reglas de nivel B). Un escaneo completo de las
7 competiciones con `h2h` y `totals`, pidiendo como máximo 10 casas en `bookmakers`, cuesta
7 × 2 × 1 = **14 créditos**. Con `regions=eu,uk` en vez de `bookmakers` cuesta 28. El plan
gratuito (500 créditos/mes) da para unos **35 escaneos completos al mes**, sin contar las
capturas de cierre para el CLV ni los mercados por evento (BTTS: 1 crédito por evento y grupo
de casas).

## 4. OddsPapi

| Aspecto | Dato | Nivel |
|---|---|---|
| Cobertura | «350+» casas; 361 identificadores en `/v4/bookmakers` | C |
| Casas .es | Artículo «La Liga Odds API», con medición del 24/08/2026: 192 casas cotizan LaLiga y 9 tienen licencia española. Nombra 888sport.es, betway.es, bwin.es, codere.es, leovegas.es y paf.es; las otras 3 no salen en el extracto | C |
| Pinnacle | Presente en 7 de los 8 partidos de su tabla | C |
| Plan gratuito | 250 peticiones/mes; cada petición devuelve todas las casas de un partido | C |
| Planes de pago | A medida o por presupuesto; un tercero habla de ~49 $/mes | C (contradictorio) |
| Histórico | Su blog dice que es gratis (hasta 3 casas por llamada); un competidor dice que es de pago | C (contradictorio) |
| Identificadores de mercado para 1X2, O/U 2.5 y BTTS | — | NO VERIFICADO |
| Límites por minuto o por segundo | — | NO VERIFICADO |
| Términos | Prohibido revender o redistribuir los datos como producto independiente; no garantizan la exactitud | B |
| Origen de los datos (¿acuerdos con las casas o scraping?) | — | NO VERIFICADO |

**Riesgo a decidir:** el proyecto prohíbe hacer scraping de webs de casas. Si OddsPapi obtiene
sus datos así, usarlo no rompe esa regla, pero hereda su fragilidad. Queda anotado.

## 5. API-Football

| Aspecto | Dato | Nivel |
|---|---|---|
| Plan gratuito | 100 peticiones/día, con acceso a todos los endpoints | B |
| Planes | «Mega»: 39 $/mes, 150.000 peticiones/día [B]. Pro: 19 $/mes, 7.500/día; Ultra: 29 $/mes, 75.000/día [C] | B / C |
| Cuotas | Antes del partido (la portada menciona también en directo) | B |
| Frecuencia | «Actualizadas una vez al día», con una llamada diaria recomendada (lo dice el blog de un competidor) | C |
| Casas | Endpoint `/odds/bookmakers`; no he podido ver la lista | NO VERIFICADO |
| Límite por minuto | Existe; un tercero habla de 10/min en el plan gratuito | C |

**Conclusión:** con una actualización al día no sirve para detectar value bets, que se mueven en
minutos. Podría servir para calendario y resultados más adelante (NO VERIFICADO).

## 6. Betfair Exchange

| Aspecto | Dato | Nivel |
|---|---|---|
| Acceso a la API | Cuenta de Betfair + *application key* | B |
| Clave «Delayed» | Gratis, para desarrollo; datos con entre 1 y 180 s de retraso | B |
| Clave «Live» | Pago único de 499 £ (artículo de soporte reciente) o 299 £ (documentación antigua) | B (contradictorio) |
| Uso solo de lectura | No permitido con la clave Live | B |
| Uso permitido | Solo apuestas personales; el uso comercial requiere aprobación | B |
| Condiciones para cuentas españolas o endpoints de betfair.es | — | NO VERIFICADO |
| Vía The Odds API | `betfair_ex_eu` (eu) y `betfair_ex_uk` (uk), con actualización de ~20 s | B |
| Liquidez | — | NO VERIFICADO |
| Comisión aplicable | — | NO VERIFICADO |

**Conclusión:** descarto la integración directa porque exige credenciales de casa y Betfair no
permite el uso solo de lectura. Su precio entra como referencia a través de un agregador (ADR
001 y 002). El exchange internacional no es donde apostaría un usuario español (betfair.es):
sirve como referencia de probabilidad justa, no como cuota que puedas coger.

## 7. Pinnacle (referencia *sharp*)

| Aspecto | Dato | Nivel |
|---|---|---|
| API pública | Cerrada al público desde el 23/07/2025. El acceso se concede caso a caso escribiendo a api@pinnacle.com (apostadores de alto valor, socios comerciales y académicos) | B (documentación oficial en GitHub) |
| Credenciales | La API exige cuenta de Pinnacle, así que la regla de seguridad la descarta de todos modos | B |
| Vía The Odds API | `pinnacle` (eu), «desde la web pública, puede tener retraso» | B |
| Vía OddsPapi | Presente | C |

**Consecuencia:** la referencia necesita un control de frescura (`last_update`) y una referencia
de respaldo (Betfair Exchange). Ver [ADR 002](../decisiones/002-referencia-sharp-y-clv.md).

## 8. Histórico: football-data.co.uk

| Aspecto | Dato | Nivel |
|---|---|---|
| Cierre 1X2 de Pinnacle | `PSCH`, `PSCD`, `PSCA`: últimas cuotas antes del inicio; disponibles desde 2012/13 | B |
| Dos tomas de cuotas (desde 2019/20) | **Precierre**, tras la apertura del mercado: el viernes por la tarde (no más tarde de las 17:00, hora británica) para los partidos de fin de semana, y el martes (no más tarde de las 13:00) para los de entre semana. **Cierre**: columnas con «C», por ejemplo `B365CH`. Antes de 2019/20 solo hay precierre | B |
| Pinnacle desde el 23/07/2025 | «Poco fiable… sistemáticamente desfasada… usar con precaución»; ya no entra en la media ni en el máximo del mercado | B |
| Pinnacle en 2025/26 y 2026/27 | Premier 2025/26: Pinnacle en 210 de 380 partidos, con el último precio el 08/01/2026. 2026/27: sin columnas de Pinnacle, pero con bet365 y Betfair Exchange | C (análisis de terceros del 18/10/2026) |
| Betfair Exchange | `BFEH`, `BFED`, `BFEA` [B]. Cierre `BFECH/BFECD/BFECA` «desde 2019/20» según un tercero; otro dice que desde 2024/25 | B / NO VERIFICADO |
| Over/Under 2.5 (`P>2.5`, `PC>2.5`, `B365C>2.5`…) | — | NO VERIFICADO |
| Ambos Marcan | No consta | NO VERIFICADO |
| Ficheros y códigos de liga (`E0`, `SP1`, `SP2`, `I1`, `D1`, `F1`) | — | NO VERIFICADO |
| Champions League | Sin indicios de cobertura: los envoltorios de terceros solo listan ligas nacionales | C (probablemente no está) |
| Términos de uso | Terceros lo describen como gratuito; no encontré los términos del propio sitio | NO VERIFICADO |
| Horas de captura | Las de precierre y cierre son aproximadas | B (ventanas) / C (análisis) |

**Consecuencias para el diseño:**
- El backtest puede medir CLV contra el cierre de Pinnacle hasta 2024/25. De 2025/26 en
  adelante, la alternativa es el cierre de Betfair Exchange (columnas pendientes de verificar).
- Sin cuotas históricas de BTTS, solo se podrá evaluar la calibración del modelo en ese mercado
  (Brier y log-loss), no si hay valor.
- Sin histórico de la Champions, el modelo propio no podrá validarse en esa competición (ver
  [PLAN](../PLAN.md), D6).
- Ni las cuotas de precierre ni las de cierre del histórico son cuotas que hubieras podido coger.
  Esta limitación irá en todos los informes.

## 9. Licencias DGOJ

No pude consultar el registro oficial (red bloqueada), así que **todo este apartado es NO
VERIFICADO a nivel oficial.** Comparadores y sitios de afiliados [C] dan como licenciadas a
bet365, Codere, Sportium, Bwin, William Hill (WHG Ceuta, S.A., williamhill.es), Betfair
(Betfair International Spain, S.A.: apuestas deportivas, exchange e hípica), Luckia (Luckia
Games, S.A.), Kirolbet (Artxibet 2022, S.A.), Marathonbet y 888 (888 Online Games España,
S.A., 888sport.es), y, con menos respaldo, a Retabet.

**Winamax:** un comparador la da como licenciada en España [C], pero las resoluciones recientes
de la DGOJ que recoge la prensa le conceden licencias de ruleta, blackjack y máquinas, no de
apuestas deportivas [C]. Su licencia de apuestas deportivas: NO VERIFICADO.

## 10. Datos de xG (opcional)

| Fuente | Dato | Nivel |
|---|---|---|
| FBref | En enero de 2026 retiró las estadísticas avanzadas de Opta (xG, xA, PSxG…) porque el proveedor le cortó el acceso | B (blog de Sports Reference) |
| Understat | No encontré sus términos de uso; solo scrapers de terceros | NO VERIFICADO |

**Consecuencia:** el xG queda fuera hasta verificar los términos de Understat (ver
[BACKLOG](../BACKLOG.md)).

## 11. Qué falta comprobar con red y claves (paso a nivel A)

Entre paréntesis, el coste en créditos (cálculo propio con las reglas de nivel B):

1. **The Odds API** `GET /v4/sports` (gratis): claves reales de las 7 competiciones, Segunda y
   Champions incluidas.
2. **The Odds API** `GET /v4/sports/{sport}/odds?regions=eu,uk&markets=h2h,totals&oddsFormat=decimal`
   por competición (4 créditos por competición; 28 las 7): qué casas dan cuotas en cada liga,
   qué línea de `totals` dan (¿2.5?) y lo frescas que están las de `pinnacle` y `betfair_ex_eu`.
3. **The Odds API** `GET /v4/sports/{sport}/events/{id}/odds?markets=btts&regions=eu` en un
   par de partidos (como mucho 1 crédito por evento): si hay BTTS en fútbol europeo.
4. **OddsPapi** `/v4/bookmakers` con una clave gratuita: identificadores .es reales (¿Sportium?
   ¿Luckia? ¿Kirolbet? ¿Retabet? ¿bet365? ¿Winamax? ¿William Hill? ¿Marathonbet?).
5. **football-data.co.uk**: `notes.txt` y los CSV de 2024/25, 2025/26 y 2026/27 de las 6
   ligas, para ver las columnas `PSC*`, `BFEC*` y O/U 2.5.
6. **Registro oficial de la DGOJ**: licencias vigentes de las 12 casas.
7. Si aceptas feeds no españoles (decisión D1 del plan): comparar a mano, en 5–10 partidos, la
   cuota del feed (por ejemplo, `williamhill` en `eu`) con la de la web .es de la misma marca.

## 12. Fuentes

Todas consultadas el 2026-10-21 a través del buscador; entre corchetes, el nivel.

**The Odds API**
- [B] https://the-odds-api.com/sports-odds-data/bookmaker-apis.html
- [B] https://the-odds-api.com/liveapi/guides/v4/
- [B] https://the-odds-api.com/liveapi/guides/v4/api-error-codes.html
- [B] https://the-odds-api.com/sports-odds-data/betting-markets.html
- [B] https://the-odds-api.com/sports-odds-data/epl-odds.html
- [B] https://the-odds-api.com/sports-odds-data/football-odds.html
- [B] https://the-odds-api.com/sports-odds-data/update-intervals.html
- [B] https://the-odds-api.com/historical-odds-data/
- [B] https://the-odds-api.com/ (planes y precios)
- [B] https://the-odds-api.com/terms-and-conditions.html
- [C] https://oddsapir.sportsdataverse.org/articles/oddsapiR.html

**OddsPapi**
- [C] https://oddspapi.io/blog/la-liga-odds-api/
- [C] https://oddspapi.io/sportsbooks
- [C] https://oddspapi.io/blog/free-odds-api-350-bookmakers/
- [C] https://oddspapi.io/blog/odds-api-pricing-2026-comparison/
- [B] https://oddspapi.io/legal/terms
- [C] https://sharpapi.io/compare/oddspapi-alternative

**API-Football**
- [B] https://www.api-football.com/
- [B] https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide
- [C] https://oddspapi.io/blog/api-football-alternative/

**Betfair**
- [B] https://support.developer.betfair.com/hc/en-us/articles/115003864531-Are-there-any-costs-associated-with-API-access
- [B] https://docs.developer.betfair.com/display/1smk3cen4v3lu3yomq5qye0ni/Application+Keys
- [B] https://developer.betfair.com/en/exchange-api/faq/

**Pinnacle**
- [B] https://github.com/pinnacleapi/pinnacleapi-documentation

**football-data.co.uk**
- [B] https://www.football-data.co.uk/notes.txt
- [B] https://football-data.co.uk/data.php
- [C] https://github.com/Acusick1/odds/issues/511
- [C] https://py.sportsdataverse.org/docs/soccer/reference/football_data
- [C] https://penaltyblog.readthedocs.io/en/master/scrapers/footballdata.html

**xG**
- [B] https://www.sports-reference.com/blog/2026/01/fbref-stathead-data-update/

**Licencias DGOJ (comparadores y prensa)**
- [C] https://www.winga.es/operadores/
- [C] https://apuestasseguras.bet/casas-apuestas-licencia-dgoj
- [C] https://www.legalsportsbetting.es/reviews/william-hill-spain-review
- [C] https://focusgn.com/latinoamerica/la-dgoj-concede-nuevas-licencias-a-iberix-gaming-y-winamax-y-homologa-sistemas-de-codere-online
- [C] https://www.eurosport.es/apuestas/winamax/

**Otros candidatos (backlog)**
- [C] https://odds-api.io/sportsbooks

## 13. Verificación de nivel A de The Odds API (R4, 2026-10-29)

**Cómo se obtuvo.** `tipster scan --max-creditos 14` (ejecución 1 de `runs`) con las 7
competiciones, `markets=h2h,totals`, `oddsFormat=decimal` y `bookmakers=` con 8 casas
(`pinnacle`, `betfair_ex_eu`, `sport888`, `williamhill`, `marathonbet`, `winamax_fr`,
`winamax_de`, `betfair_sb_uk`). Tres cosas condicionan lo que sigue:

- Solo se vieron las 8 casas pedidas. **Qué otras casas devuelve cada liga: NO VERIFICADO**
  (no se pidió `regions=`).
- Es **una sola captura**, el jueves 29/10/2026 hacia las 09:24 UTC. No dice nada de otros días
  ni de otras horas.
- Evidencia: la tabla `provider_requests` (ids 1–8, `data/tipster.sqlite`) y las respuestas
  crudas de `data/raw/the_odds_api/` (ambos en `.gitignore`). Una copia de LaLiga y Premier está
  en `tests/fixtures/the_odds_api/real/` (R3), **solo en local y fuera de git** (BACKLOG nº 18).

Las edades son `hora de inicio de la petición − last_update` de la propia respuesta.

### 13.1 Créditos (nivel A)

| Dato | Observado |
|---|---|
| `GET /v4/sports` | HTTP 200, `x-requests-last: 0`, `x-requests-used: 0`, `x-requests-remaining: 500` (llamada directa, 09:20:04 GMT); 87 deportes |
| `GET /v4/sports/{sport}/odds` con 8 casas en `bookmakers`, `h2h,totals` | `x-requests-last` = **2** en las 7 peticiones (columna `cost`) |
| Escaneo completo | `x-requests-used` pasa de 0 a **14**; `x-requests-remaining` queda en 486 (columnas `credits_used` y `credits_remaining`) |
| Modelo de coste | Confirma el §3: mercados × grupos de 10 casas (2 × 1). Con `regions=eu,uk` serían 4 por liga (28), **no probado** |
| Caché por TTL (R2) | Segundo `scan` a los ~1 min: 8 filas con `from_cache = 1` y `cost = 0` |

### 13.2 Claves de las 7 competiciones (`/v4/sports`)

Las 7 existen y llevan `active: true`. Ninguna clave alternativa hizo falta.

| Competición | Clave | `title` en `/v4/sports` | Eventos devueltos |
|---|---|---|---|
| LaLiga | `soccer_spain_la_liga` | La Liga - Spain | 20 |
| Segunda | `soccer_spain_segunda_division` | La Liga 2 - Spain | 11 |
| Premier | `soccer_epl` | EPL | 21 |
| Serie A | `soccer_italy_serie_a` | Serie A - Italy | 12 |
| Bundesliga | `soccer_germany_bundesliga` | Bundesliga - Germany | 18 |
| Ligue 1 | `soccer_france_ligue_one` | Ligue 1 - France | 18 |
| Champions | `soccer_uefa_champs_league` | UEFA Champions League | 18 |

Esto cierra el NO VERIFICADO del §3 sobre la Segunda y las claves de las otras cinco.

### 13.3 Casas por liga (eventos con esa casa / eventos de la liga)

| Casa (clave de la API) | LaLiga | Segunda | Premier | Serie A | Bundesliga | Ligue 1 | Champions |
|---|---|---|---|---|---|---|---|
| `pinnacle` | 20/20 | 11/11 | 20/21 | 12/12 | 18/18 | 18/18 | 18/18 |
| `betfair_ex_eu` | 15/20 | 11/11 | 21/21 | 12/12 | 18/18 | 18/18 | 18/18 |
| `marathonbet` | 20/20 | 11/11 | 20/21 | 12/12 | 18/18 | 18/18 | 18/18 |
| `williamhill` | 20/20 | 11/11 | 20/21 | 12/12 | 18/18 | 17/18 | 18/18 |
| `sport888` | 0 | 0 | 20/21 | 12/12 | 18/18 | 17/18 | 18/18 |
| `winamax_fr` | 20/20 | 10/11 | 20/21 | 12/12 | 18/18 | 18/18 | 18/18 |
| `winamax_de` | 20/20 | 10/11 | 20/21 | 12/12 | 18/18 | 18/18 | 18/18 |
| `betfair_sb_uk` | 9/20 | 9/11 | 9/21 | 9/12 | 9/18 | 9/18 | 8/18 |

- `betfair_ex_eu` es la clave real (la que usa `domain/bookmakers.py`); `betfair_ex_no_es` es solo
  el id interno del proyecto.
- Ninguna casa devuelta es de una web .es: las 8 son feeds no españoles (D1 sigue vigente). Si
  existe algún feed .es en este proveedor, **NO VERIFICADO**.
- `sport888` no aparece en LaLiga ni en Segunda aunque se pidió.

### 13.4 Mercados y líneas de `totals`

| Casa | Mercados que devuelve | Líneas (`point`) observadas |
|---|---|---|
| `pinnacle` | `h2h`, `totals` | **una línea por evento**, distinta según el partido: 2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 3.75, 4.0 |
| `betfair_ex_eu` | `h2h`, **`h2h_lay`**; **sin `totals`** en ninguna liga | — |
| `williamhill` | `h2h`, `totals` | solo 2.5 |
| `marathonbet` | `h2h`, `totals` | 1.5, 2.5, 3.5, 4.5 (según el evento) |
| `sport888`, `winamax_fr`, `winamax_de`, `betfair_sb_uk` | solo `h2h` | — |

Eventos cuyo `totals` de Pinnacle es la línea 2.5, sobre el total de la liga:

| LaLiga | Segunda | Premier | Serie A | Bundesliga | Ligue 1 | Champions | Total |
|---|---|---|---|---|---|---|---|
| 4/20 | 6/11 | 5/21 | 3/12 | 0/18 | 3/18 | 0/18 | **21/118** |

Consecuencias, documentadas y **sin corregir** (el código no se ha tocado):

1. El mapeo solo admite la línea 2.5 (`providers/the_odds_api/mapping.py`). Con la referencia
   `pinnacle` > `betfair_ex_eu` (D2), el O/U 2.5 tiene referencia en 21 de 118 eventos. En el
   escaneo real, los 97 restantes salieron «sin referencia válida». La Bundesliga y la Champions
   no tuvieron ninguna. Ningún pick de la ejecución fue de totales.
2. `betfair_ex_eu` no ofrece `totals`, así que no sirve de segunda referencia para O/U.
3. Para tener 2.5 cuando la línea principal es otra, hay que usar `alternate_totals` (BACKLOG nº 5,
   B): por evento, no por liga. **NO VERIFICADO** si sale a cuenta o cuánto cuesta.
4. `h2h_lay` llega sin pedirlo y sin coste extra (`x-requests-last` = 2 igualmente). El cliente
   lo ignora sin aviso. Que ignorarlo sea lo correcto, no se ha estudiado.

### 13.5 Frescura de `pinnacle` y `betfair_ex_eu` (`last_update` del mercado)

| Liga | `pinnacle` h2h / totals (s) | `betfair_ex_eu` h2h (s) |
|---|---|---|
| LaLiga | 19 | 43 |
| Segunda | 17 | 15 |
| Premier | 3–4 | 1 |
| Serie A | 1 | 0 |
| Bundesliga | 6 | 23–24 |
| Ligue 1 | 4 | 3 |
| Champions | 5 | 24 |

- Todas por debajo de 1 minuto en esta captura, muy por debajo de `max_reference_age_minutes`
  (10 min). Para comparar, el resto de casas va de 0 s a 111 s (`williamhill` en LaLiga: 111 s).
- Dentro de cada liga, el `last_update` de una casa es **el mismo para todos los eventos**
  (mínimo, mediana y máximo coinciden salvo ±1 s). Parece una marca por casa y deporte, no por
  evento. Por tanto no demuestra que cada cuota concreta sea reciente. **NO VERIFICADO.**
- La nota del §3 («Odds are from public website which may incur a delay») no se contradice ni se
  confirma: una marca reciente no mide el retraso real de Pinnacle.
- **No verificado:** la frescura en otros días u horas, y cuánto tarda una cuota en cambiar de
  verdad.
- Aparece una antigüedad de **−1 s** (`last_update` posterior a `captured_at`): efecto de definir
  `captured_at` como el inicio del intento HTTP (ADR 006). Ver BACKLOG nº 14.

### 13.6 Qué sigue NO VERIFICADO

- Casas distintas de las 8 pedidas y cualquier feed .es (no se pidió `regions=`).
- El coste de `regions=eu,uk` (28 créditos), el de `alternate_totals` y el de BTTS (§11, punto 3).
- Los puntos 4–7 del §11 (OddsPapi, football-data.co.uk, DGOJ, comparación con webs .es).
- Liquidez y límites por cuota, y el límite de peticiones por segundo (se usó 1 por segundo sin
  recibir ningún 429).
- Si los términos de The Odds API permiten dejar sus respuestas reales en un repositorio público
  (el §3 dice «Prohibido revender o redistribuir los datos como producto»).

## 14. Verificación de nivel A de football-data.co.uk (Fase 2, 2026-10-29)

**Cómo se obtuvo.** Descargas directas con `curl` desde la máquina local, sin clave, el
2026-10-29 sobre las 09:40 UTC. Se bajaron unos 55 CSV de muestra (~7 MB, fuera de git) de las 6
ligas, y la página de datos, `notes.txt` y `disclaimer.php`. No se descargó el histórico entero:
la existencia del resto se comprobó con `HEAD`. Cada dato se cita con el fichero o la cabecera de
donde sale.

### 14.1 Acceso y estructura

| Aspecto | Observado |
|---|---|
| URL | `https://www.football-data.co.uk/mmz4281/2425/E0.csv` responde **302** con `location: https://football-data.co.uk/mmz4281/2425/E0.csv` (cuerpo vacío). Hay que seguir la redirección (`-L`) o usar el dominio sin `www` |
| Respuesta final | HTTP 200, `content-type: text/csv`; `E0` 24/25: 197 110 bytes, `last-modified: Sun, 25 May 2025 22:41:05 GMT` |
| Cabeceras de límite | `x-ws-ratelimit-limit: 1000` y `x-ws-ratelimit-remaining: 999` en las respuestas. Qué cuenta (por hora, por día…) y qué pasa al superarlo: **NO VERIFICADO** |
| Existencia | `HEAD` devuelve 200 para las **204** combinaciones (6 ligas × 34 temporadas, de 1993/94 a 2026/27). Solo se descargó y se leyó el contenido de las muestras |
| Codificación | UTF-8 con BOM en las temporadas recientes (`efbbbf` en 24/25 y 26/27), sin BOM en 12/13: decodificar con `utf-8-sig` |
| Fechas | `dd/mm/yy` en las muestras de 2012/13 y anteriores (`18/08/12`) y `dd/mm/yyyy` desde 2015/16; 2013/14 y 2014/15 sin muestrear. Hay columna `Time` en 24/25 (antes: NO VERIFICADO) |
| Filas por temporada | 24/25: E0 380, SP1 380, SP2 462. 25/26: E0 380, SP1 380, SP2 462, I1 380, D1 306, F1 306. 26/27 (en curso, hasta el 25–26/10/2026): E0 80, SP1 99, SP2 121, I1 80, D1 63, F1 72 |

**Cabecera de `E0` 24/25 (120 columnas):** `Div, Date, Time, HomeTeam, AwayTeam, FTHG, FTAG,
FTR, HTHG, HTAG, HTR, Referee, HS, AS, HST, AST, HF, AF, HC, AC, HY, AY, HR, AR` y luego las
cuotas: `B365H/D/A, BWH/D/A, BFH/D/A, PSH/D/A, WHH/D/A, 1XBH/D/A, MaxH/D/A, AvgH/D/A,
BFEH/D/A, B365>2.5, B365<2.5, P>2.5, P<2.5, Max>2.5, Max<2.5, Avg>2.5, Avg<2.5, BFE>2.5,
BFE<2.5, AHh, B365AHH/A, PAHH/A, MaxAHH/A, AvgAHH/A, BFEAHH/A` (apertura) y las mismas con «C»
(cierre): `B365CH/D/A, BWC*, BFC*, PSCH/PSCD/PSCA, WHC*, 1XBC*, MaxCH/D/A, AvgCH/D/A,
BFECH/BFECD/BFECA, B365C>2.5, B365C<2.5, PC>2.5, PC<2.5, MaxC>2.5, MaxC<2.5, AvgC>2.5,
AvgC<2.5, BFEC>2.5, BFEC<2.5, AHCh, …`. `SP1` y `SP2` de 24/25 traen 119 columnas: las mismas
sin `Referee`. Las columnas son por cuota, no por casa «viva»: que exista una columna no dice que
tenga datos (ver §14.2).

### 14.2 Cuotas de cierre de Pinnacle y Betfair Exchange (el punto crítico)

Porcentaje de partidos con la columna rellena (`PSCH` = Pinnacle 1X2 local de cierre; `BFECH` =
Betfair Exchange 1X2 local de cierre). `--` = la columna no existe en el fichero.

| Temporada | Ligas comprobadas | `PSH`/`PSCH` | `BFEH`/`BFECH` |
|---|---|---|---|
| 2010/11 y 2011/12 | las 6 | `--` | `--` |
| 2012/13 | las 6 | 100 % (Serie A 99 %) | `--` |
| 2013/14 a 2023/24 | `E0`: 12/13, 15/16, 18/19, 21/22 y 23/24 medidas (100 %); 19/20, 20/21 y 22/23 solo con la columna presente, relleno sin medir. Las 6 ligas en 2023/24 (100 %) | 100 % | `--` |
| 2024/25 | las 6 | 100 % | 100 % |
| 2025/26 | las 6 | **42–55 %** (E0 55, SP1 50, SP2 42–43, I1 53, D1 49, F1 50) | 92–95 % |
| 2026/27 (hasta el 26/10/2026) | las 6 | **la columna no existe** (114 columnas, sin `PS*` ni `P>2.5`) | 100 % (SP2: 94 % / 99 %) |

**Pinnacle en 2025/26, mes a mes** (las 6 ligas sumadas; partidos con `PSCH` / partidos):

| Mes | 2025-08 | 2025-09 | 2025-10 | 2025-11 | 2025-12 | 2026-01 | 2026-02 a 2026-05 |
|---|---|---|---|---|---|---|---|
| `PSCH` | 157/157 | 199/199 | 208/209 | 211/243 | 202/203 | 119/272 | **0** |

- La **última fecha de 2025/26 con `PSCH` es el 14/01/2026**; desde febrero de 2026 no hay ni
  `PSH` ni `PSCH` y en 2026/27 las columnas desaparecen. Esto precisa el punto 4 del §1 de la Fase 0, que lo
  daba por «desaparecen tras el 08/01/2026» [C]: ahora es nivel A.
- El sitio avisa (página de datos, nivel A): «Since 23/07/2025 Pinnacle's public API for odds
  delivery has become unreliable meaning their odds are systematically out of date relative to
  odds for other bookmakers, including both the pre-closing and closing odds. Consequently they
  should be used with caution […], and are no longer being included for the calculation of market
  average and maximum odds.» Que la columna esté rellena entre agosto y diciembre de 2025 **no
  prueba que la cuota sea buena**; su calidad ahí es NO VERIFICADO. El corte seguro para el CLV
  contra Pinnacle sigue siendo la temporada 2024/25, como decía PLAN §6.
- El sitio dice que el cierre de Pinnacle está «back to 2012/13» («Closing home-draw-away odds are
  also available for Pinnacle bookmaker only back to 2012/13»): coincide con lo observado.

**Betfair Exchange (`BFE*`).**
- Existe **solo desde 2024/25** (no hay `BFEH` ni `BFECH` en 2023/24 en ninguna de las 6 ligas).
  Hoy son **2 temporadas completas más la actual**: poco histórico para calibrar.
- 2025/26: `BFECH` casi completa hasta marzo de 2026 (237/237 en febrero, 219/219 en marzo) y
  parcial después: 160/233 en abril y 180/242 en mayo.
- Otro Betfair: `BFH/BFD/BFA` (y sus cierres `BFC*`) son «Betfair», no el exchange; las `BFD*` de
  la cabecera de 26/27 son **Betfred** según `notes.txt`. No confundir con `BFE*`.
- Cómo se mide el cierre (liquidez, momento) y si equivale al de Pinnacle: NO VERIFICADO.

**Fallback `Max*`/`Avg*` (media y máximo del mercado).**
- Columnas de cierre `MaxCH/D/A` y `AvgCH/D/A` (y `MaxC>2.5`, `AvgC>2.5`…) presentes desde
  **2019/20** en `E0`, con 100 % de relleno en las temporadas medidas (21/22, 23/24, 24/25, 25/26 y 26/27). En las
  otras 5 ligas, medido en 25/26 y 26/27 (100 %) y en 24/25 solo en SP1 y SP2; el resto, NO
  VERIFICADO.
- Según el sitio, desde el 23/07/2025 Pinnacle ya no entra en esas medias: hay una **ruptura de
  serie** entre antes y después de esa fecha. Vienen de Betbrain (y de Oddsportal desde 2019/20),
  es decir, un promedio de casas, no una referencia *sharp*.

### 14.3 Cobertura de ligas y temporadas

| Pregunta | Respuesta |
|---|---|
| ¿Las 6 ligas? | **Sí.** `E0` (Premier), `SP1` (LaLiga), `SP2` (Segunda), `I1` (Serie A), `D1` (Bundesliga) y `F1` (Ligue 1): 200 en las 34 temporadas, 1993/94 a 2026/27 |
| ¿Hasta cuándo atrás? | Resultados desde 1993/94 (`9394_E0`: 28 columnas). Cuotas de casas desde 2000/01 según el sitio; **con cierre de Pinnacle desde 2012/13** (observado en las 6 ligas) y Max/Avg de cierre desde 2019/20 (observado en `E0`) |
| ¿Estadísticas de partido? | Según el sitio, tiros, córners, faltas y tarjetas desde 2000/01 en las ligas principales |
| ¿Champions? | **No consta.** La página de datos no cita ninguna competición UEFA y su lista de ligas (Inglaterra, Escocia, Alemania, Italia, España, Francia, Países Bajos, Bélgica, Portugal, Turquía, Grecia y las «extra») no la incluye. Confirma el BACKLOG nº 2 |
| ¿Cuota de Ambos Marcan? | No hay columnas de BTTS en la cabecera de 24/25 (`E0`, `SP1`, `SP2`); el resto de temporadas, sin comprobar |

### 14.4 Términos de uso (importante)

- La página de datos dice: «What's more, it's all FREE, however its use is intended for private
  individuals only, NOT commerical [sic] or data training products using automated bots/scrapers/AI.»
- La página de descargo (`disclaimer.php`) es solo de responsabilidad («Football-Data cannot
  guarantee the correctness of information contained within […]»). No trata la licencia de los
  datos.
- **Qué implica para el proyecto: NO VERIFICADO, y es una decisión del usuario.** El proyecto es
  personal y no comercial, pero el módulo de descarga sería un script automatizado y los modelos
  se *entrenan* con esos datos. La frase prohíbe «data training products using automated
  bots/scrapers/AI» y no define «producto»: no puedo afirmar que un modelo estadístico propio de
  uso privado lo infrinja, ni que no. El menú del sitio tiene un enlace «Contact» (no se ha abierto)
  que sería la vía para preguntarlo.
- Alternativa que el propio sitio ofrece de pago: una API por suscripción con
  «TheStatsAPI»; sus condiciones y cobertura no se han revisado.

### 14.5 Qué sigue NO VERIFICADO

- La licencia real para entrenar modelos (14.4) y el límite de peticiones (14.1).
- La calidad de las cuotas de Pinnacle de agosto a diciembre de 2025 (14.2).
- Las columnas `Max*`/`Avg*` y `BFE*` en las otras 5 ligas antes de 2024/25.
- El contenido de las temporadas no muestreadas (solo se comprobó que existen).
- La actualización durante la temporada: cuándo se publica cada jornada y cuándo se rellenan las
  cuotas de cierre.

## 15. Verificación de nivel A del dataset `eatpizzanot/soccer-dataset` (Fase 2, 2026-10-29)

**Cómo se obtuvo.** Descarga directa desde Hugging Face el 2026-10-29: la API del dataset, su
`README.md`, `data_dictionary.md` y `QUALITY_REPORT.md`, y cinco Parquet (`fixtures`, `odds`,
`leagues`, `teams`, `league_catalogue`; ≈16 MB, en el scratchpad y fuera de git). Se leyeron con
`pyarrow` y `pandas` en un entorno temporal de `uv`, sin tocar las dependencias del proyecto. No se
ha escrito ningún cargador.

### 15.1 Ficha

| Dato | Observado |
|---|---|
| Identificador | `eatpizzanot/soccer-dataset`, público, sin acceso restringido (`gated: false`) |
| Revisión | `sha f0cbe86bee3f28cc4b803f735a5287968741c471`, `lastModified 2026-07-05T01:23:18Z` |
| Licencia | `license: cc-by-4.0` (ficha y etiqueta de la API). La ficha: «Licensed CC-BY-4.0; cite API-Football and football-data.co.uk» |
| Fuentes declaradas | «Sources: API-Football + football-data.co.uk» |
| Tamaños | `odds` 2 591 808 B · `fixtures` 12 938 933 B · `teams` 321 028 B · `league_catalogue` 39 623 B · `leagues` 8 240 B |
| Calidad declarada | «Gate: PASS — 54/54 checks passed» (`QUALITY_REPORT.md`, 2026-07-05) |
| Columnas | Las de los cinco Parquet **coinciden** con `data_dictionary.md`: `fixtures` (21), `odds` (9), `leagues` (7), `teams` (8) y `league_catalogue` (15) |

### 15.2 Ligas disponibles

Las 6 ligas y la Champions están en `leagues`:

| Competición | `leagues.id` | `fd_code` |
|---|---|---|
| Premier League | 1 | E0 |
| La Liga | 5 | SP1 |
| Segunda División | 6 | SP2 |
| Serie A | 7 | I1 |
| Ligue 1 | 9 | F1 |
| Bundesliga | 11 | D1 |
| UEFA Champions League | 89 | CUP-UCL |

La Champions **sí está**, lo que contradice el BACKLOG nº 2 (que lo decía de football-data.co.uk).
Resultados jugados de las 6 ligas desde el 2010-08-07.

### 15.3 Tabla `odds`

- **Solo 1X2:** `home_win`, `draw`, `away_win`, más `bookmaker`, `source` y `known_at`. **No hay
  O/U 2.5, ni Asian handicap, ni BTTS.** Una fila por casa y partido (hasta 3 por partido).
- **Casas en las 7 competiciones** (filas): Pinnacle 23 536 · Bet365 9 104 · Betfair 139 ·
  888sport 18 · Unibet 13 · 1xBet 12 · William Hill 1. En todo el dataset hay 86 filas de
  «Betfair Exchange» y 263 de «Maximum». No hay medias de mercado.
- **«96 %+ Pinnacle» (diccionario):** en filas, Pinnacle es el 84,8 % de todo el dataset y el 71,7 %
  de las 7 competiciones. En partidos jugados de las 6 ligas entre 2016/17 y 2024/25, el 96,3 %
  tiene Pinnacle (21 035 de 21 843).
- **Procedencia:** las cuotas de Pinnacle de esas 6 ligas son `API-Football-closing` (21 033
  filas) y 6 de `The-Odds-API`. Las 8 849 de Bet365 son `source = CSV` (football-data.co.uk).
- **`known_at`:** para las 32 823 filas de las 7 competiciones, `known_at − date_utc = 0` exacto.
  Es la hora del partido, **no una captura medida de la cuota**. Que sean cuotas de cierre es lo que
  declara el dataset, **NO VERIFICADO**.
- **Rango:** mínimo 1.01, máximo 201 en una selección; 364 filas fuera de la banda de overround
  [1.0, 1.25] (aviso del propio informe de calidad).

### 15.4 Partidos jugados y con cuota de Pinnacle (crudo, sin quitar duplicados)

Temporada con corte el 1 de agosto. «Jugados / con Pinnacle»:

| Temp. | Premier | LaLiga | Segunda | Serie A | Ligue 1 | Bundesliga |
|---|---|---|---|---|---|---|
| 2016/17 | 380 / 380 | 454 / 380 | 550 / 459 | 418 / 418 | 380 / 380 | 340 / 306 |
| 2017/18 | 380 / 380 | 454 / 380 | 625 / 461 | 418 / 418 | 380 / 380 | 306 / 306 |
| 2018/19 | 380 / 380 | 418 / 380 | 586 / 441 | 418 / 418 | 380 / 380 | 308 / 305 |
| 2019/20 | 380 / 380 | 418 / 391 | 542 / 461 | 407 / 407 | 279 / 279 | 308 / 306 |
| 2020/21 | 380 / 380 | 418 / 418 | 518 / 464 | 429 / 429 | 382 / 380 | 342 / 340 |
| 2021/22 | 380 / 380 | 418 / 418 | 510 / 507 | 418 / 418 | 382 / 380 | 342 / 340 |
| 2022/23 | 380 / 380 | 418 / 418 | 468 / 468 | 419 / 419 | 380 / 380 | 308 / 306 |
| 2023/24 | 380 / 380 | 418 / 418 | 468 / 465 | 418 / 418 | 308 / 308 | 308 / 308 |
| **2024/25** | **380 / 380** | **418 / 418** | **510 / 505** | **418 / 418** | **308 / 308** | **308 / 308** |
| 2025/26 | 380 / 272 | 409 / 281 | 556 / 327 | 410 / 331 | 310 / 253 | 308 / 245 |

- **Antes de 2016/17 no hay ninguna cuota:** 0 de 1 826 partidos por temporada en 2010/11 a
  2015/16, y la primera fecha con cuotas es el 2016-08-12.
- **2024/25 está completo para Pinnacle en 5 de las 6 ligas** (Premier, LaLiga, Serie A, Ligue 1 y
  Bundesliga); Segunda tiene 505 de 510 partidos (99,0 %).
- **Las cifras por encima de lo esperado no son partidos reales.** Una liga de 20 equipos tiene 380
  partidos y la Serie A y LaLiga salen con 418:
  - **Duplicados de entidad confirmados:** en LaLiga 2024/25 el club aparece como «Ath Bilbao»
    (`teams.id` 107) y «Athletic Club» (4643); el partido del 2024-08-15 está dos veces, una a las
    00:00 y otra a las 17:00, con el mismo resultado. El equipo 4643 y el 107 suman 38 partidos
    cada uno, y los otros 19 equipos, 40. Eso son 38 partidos duplicados (418 − 380).
  - Serie A (418) y LaLiga tienen el mismo exceso de 38 (hipótesis de la misma causa, **no
    comprobada** en la Serie A).
  - Segunda (510 frente a 462) y Bundesliga/Ligue 1 (+2) se explican en parte por promociones
    (no comprobado).
  - La Premier no tiene exceso en ninguna temporada.
- **2025/26:** los partidos con Pinnacle bajan mes a mes (seis ligas juntas, con Pinnacle /
  jugados): 169/170 en agosto, 217/219 en septiembre, 227/228 en octubre, 232/265 en noviembre,
  217/217 en diciembre, 217/295 en enero, 162/257 en febrero, 203/235 en marzo, 64/233 en abril,
  1/248 en mayo y 0/6 en junio de 2026. Todas son `API-Football-closing`. Su fiabilidad después del
  23/07/2025 es **NO VERIFICADO**.
- **Champions:** con Pinnacle desde 2020/21 (118/250, 106/214, 117/202, 123/225, 167/281 en
  2020/21 a 2024/25) y ninguno antes.
- **Horas:** 1 425 partidos de las 6 ligas en 2016/17–2024/25 tienen hora 00:00:00 (solo se conocía
  la fecha).

### 15.5 Qué sigue NO VERIFICADO

- Que el dataset pueda usarse para entrenar modelos sin conflicto con los términos de
  football-data.co.uk y de API-Football (la ficha solo dice CC-BY-4.0). Ver BACKLOG nº 19 y 23.
- Que el cierre de Pinnacle de API-Football coincida con el de football-data.co.uk (no se ha
  cruzado partido a partido) ni con el cierre real.
- La fiabilidad de las cuotas de Pinnacle de 2025/26.
- La causa de los excesos de partidos en Serie A, Segunda, Bundesliga y Ligue 1.
- Que el dataset no cambie: la revisión fijada es la de 2026-07-05.

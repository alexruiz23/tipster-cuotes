# Fase 0 — Verificación de proveedores de datos

**Fecha:** 2026-10-21 · **Estado:** completada con limitaciones (lee la §0 antes que nada).

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

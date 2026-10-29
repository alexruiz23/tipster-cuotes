# Backlog (fuera del alcance actual)

Ideas útiles detectadas durante el trabajo que no entran en la fase en curso. Cada una indica de
dónde sale y su nivel de verificación (A/B/C/NO VERIFICADO, como en la
[verificación de proveedores](fase-0/verificacion-proveedores.md)).

| # | Idea | Por qué | Verificación | Fase candidata |
|---|---|---|---|---|
| 1 | Evaluar odds-api.io (otra empresa, distinta de The Odds API) | Su directorio incluye Luckia ES, Retabet ES, Winamax ES y Bwin ES, que no aparecen en los proveedores revisados | C | 1b |
| 2 | Fuente de partidos europeos para la Champions (football-data.org con token, openfootball) | football-data.co.uk no parece cubrir la Champions, y sin partidos entre ligas el modelo no puede valorar esos cruces | C | 2+ |
| 3 | Ratings Elo entre ligas (ClubElo) | Alternativa para comparar equipos de ligas distintas | NO VERIFICADO | 2+ |
| 4 | xG de Understat | Mejoraría Dixon-Coles (FBref ya no publica xG) | Términos NO VERIFICADOS | 2+ |
| 5 | `alternate_totals` de The Odds API para obtener la línea 2.5 cuando la principal es otra | Más cobertura de O/U 2.5, pero se paga por evento | B | después de la F1 |
| 6 | Cuotas de Ambos Marcan de un proveedor con cobertura verificada en fútbol europeo | Hoy no hay ninguna fuente verificada (D5) | NO VERIFICADO | después de la 1b |
| 7 | Comparar a mano los feeds no-ES con sus webs .es | Cuantificar cuánto se desvían los feeds que se usan como aproximación (si D1 = a) | — | 1 |
| 8 | Liquidez y límites por cuota | La regla de descarte por liquidez no se puede aplicar con The Odds API; la API de Betfair exige credenciales | NO VERIFICADO | — |
| 9 | Revisar la normativa española de comunicaciones comerciales del juego (Real Decreto 958/2020) antes de publicar picks | Publicar recomendaciones (Telegram) podría considerarse publicidad del juego | NO VERIFICADO | 6 |
| 10 | Telegram, API y dashboard | Previsto como opcional | — | 6 |
| 11 | Tenis y baloncesto | Previsto como opcional | — | 6 |
| 12 | Bot de Telegram para notificaciones de picks y casas | El usuario quiere recibir por Telegram los picks y las casas. El token del bot se expuso por error en un chat y se revocó en BotFather: al implementarlo hay que crear uno nuevo y guardarlo solo en `.env`. Ver también la nº 9 (normativa) | — | 6 |
| 13 | Línea 2.5 de O/U sin referencia: Pinnacle da una sola línea por evento y es 2.5 solo en 21 de 118 eventos; `betfair_ex_eu` no da `totals` | Con el mapeo actual (solo 2.5) el O/U 2.5 no tiene referencia en 97 de 118 eventos y ningún pick del escaneo real fue de totales. Opciones: `alternate_totals` (nº 5), admitir la línea principal de cada evento, o dejar el O/U fuera hasta la F2. Datos en [verificación §13.4](fase-0/verificacion-proveedores.md) | A | decidir antes de la F2 |
| 14 | Antigüedad negativa («hace -1 s») cuando `provider_last_update` es posterior a `captured_at` | Efecto de definir `captured_at` como inicio del intento HTTP ([ADR 006](decisiones/006-hora-de-captura-y-antiguedad.md)). Visto en el escaneo real (Le Havre – PSG). Mostrar 0 o «<1 s»; no tocar el criterio de antigüedad sin decidirlo | A | 1 (cosmético) |
| 15 | `build-system.requires = ["uv-build>=0.11.32,<0.12.0"]` no incluye uv 0.13.6 | `uv` avisa en cada ejecución, pero funciona porque resuelve `uv-build` en un entorno aislado. Puede dar problemas en la F2 si se añaden dependencias con backend de compilación | A | 2 |
| 16 | La tabla de `scan` se trunca a 80 columnas | Con `COLUMNS=220` se lee; necesita unas 230. Si el informe de la F3 reutiliza ese render, arreglarlo antes (ya anotado en la precisión 7 del plan de la F1) | A | 3 |
| 17 | macOS 14: `uv run tipster` falla con `No module named 'tipster'` | Fallo del entorno local, no del proyecto: macOS marca como `hidden` el `.pth` editable del venv (`ls -lO`) y Python lo ignora. Se rodea con `PYTHONPATH=src uv run --no-sync tipster …`. `chflags nohidden` no basta: la marca reaparece | A | — |
| 18 | Los términos de The Odds API no permiten (o no está claro que permitan) redistribuir sus respuestas reales | El §3 de la verificación dice «Prohibido revender o redistribuir los datos como producto». Decisión del usuario (2026-10-29): la fixture real (LaLiga y Premier, ~100 KB, en `tests/fixtures/the_odds_api/real/`) vive solo en local y está en `.gitignore`; **no se puede distribuir**. Los tests de formato corren con la sintética y usan la real solo si existe. Si un día hace falta una fixture real en el repo, habría que pedir permiso al proveedor o fabricar una sintética con la misma estructura | NO VERIFICADO | — |

# tipster-dispatcher (Worker de Cloudflare)

Dispara el workflow **Cron** de GitHub Actions con puntualidad. Los cron de Actions llegan tarde o no
llegan (el 12/11/2026 solo se ejecutó 1 de unos 17 disparos programados, uno con casi 3 h de retraso), y un
`close` que llega tarde pierde el cierre del pick y, con él, su CLV. Un Cron Trigger de Cloudflare es
puntual y gratis. [ADR 013](../../docs/decisiones/013-nube-github-actions-r2.md).

Cada 15 minutos, en las franjas de partidos (`*/15 11-22 * * 0,2,3,5,6` y `*/15 17-21 * * 1`, UTC), hace
un `POST` a la API de GitHub (`workflow_dispatch`, `accion=auto`). El workflow decide por el estado de la
base qué toca; el Worker no sabe nada de picks, ni guarda nada, ni tiene URL pública.

Si el disparo falla (token caducado, repo mal escrito…), reintenta una vez si es un fallo pasajero y, si
persiste, te avisa por Telegram con la causa (como mucho una vez cada 6 h si le das acceso al bucket).

## Despliegue (una vez, desde tu Mac)

1. **Token de GitHub** (*Settings → Developer settings → Fine-grained personal access tokens*):
   solo el repositorio `alexruiz23/tipster-cuotes`, permiso **Actions: Read and write** (nada más;
   *Metadata: read* se añade solo) y caducidad de un año (apunta la fecha: cuando caduque, el Worker avisa).
2. **Bucket:** en `wrangler.toml` cambia `cambia-este-bucket` por el nombre de tu bucket de R2 (el de
   `R2_BUCKET_NAME`). Solo se usa para no repetir el aviso de fallo; si no lo quieres, borra el bloque
   `[[r2_buckets]]`.
3. **Instalar y desplegar:**
   ```bash
   cd cloudflare/dispatcher
   npm install
   npx wrangler login
   npx wrangler secret put GITHUB_TOKEN          # pega el token del paso 1
   npx wrangler secret put TELEGRAM_BOT_TOKEN    # opcional: el mismo bot de los avisos
   npx wrangler secret put TELEGRAM_CHAT_ID      # opcional
   npx wrangler deploy
   ```
4. **Comprobar:** en la pestaña *Actions* del repositorio deben aparecer ejecuciones de *Cron* con evento
   `workflow_dispatch` a los minutos :00, :15, :30 y :45, y en el panel de Cloudflare
   (*Workers → tipster-dispatcher → Logs*) ninguna línea de error. Para probarlo sin esperar:
   `npx wrangler dev --test-scheduled` y, en otra terminal,
   `curl "http://localhost:8787/__scheduled?cron=*/15+*+*+*+*"` (usa tus secretos con un `.dev.vars`).
5. **Quitar el cron de Actions** (después de comprobar el paso 4 durante un día): en
   `.github/workflows/cron.yml` comenta las dos líneas `- cron: "*/15 …"` del `close`. Si las dejas junto al
   Worker pagas los minutos dos veces (≈ 2 400 min/mes, por encima de los 2 000 gratis); solo con el Worker son
   ≈ 1 250. Los cron de `scan` y `settle` se quedan: no necesitan puntualidad.

## Mantenimiento

- **Tests:** `npm test` (Node 20+; no hace falta `npm install` para ellos).
- **Cambiar las franjas:** edita `crons` en `wrangler.toml` y `npx wrangler deploy`.
- **Parar:** `npx wrangler delete`, o quita los `crons` y vuelve a desplegar. Sin Worker y con el cron de
  Actions descomentado, todo sigue funcionando (más impuntual).
- **Qué no cubre:** si el propio Worker deja de ejecutarse no hay quien avise; el aviso de «scan parado»
  del tipster (8 días) y los cierres perdidos (`notify --alerts`) lo delatarían.

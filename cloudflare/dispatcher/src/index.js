// Dispara el workflow "Cron" de GitHub Actions (workflow_dispatch) con la puntualidad de un Cron
// Trigger de Cloudflare. El workflow decide por el estado de la base qué toca (auto), así que este
// Worker no sabe nada de picks: solo llama a la puerta cada 15 minutos en las franjas de partidos.
//
// Secretos (wrangler secret put): GITHUB_TOKEN (fine-grained, solo este repo, Actions: read/write),
// y opcionalmente TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID para avisar si el disparo falla.

const ALERT_KEY = "dispatcher/last-alert.json";
const ALERT_EVERY_MS = 6 * 3600 * 1000;
const RETRY_DELAY_MS = 2000;

const HINTS = {
  401: "el GITHUB_TOKEN no es válido o caducó",
  403: "el GITHUB_TOKEN no tiene permiso de Actions (read/write) sobre el repo, o hay límite de uso",
  404: "no se encuentra el repo o el workflow (¿el token no ve el repo? ¿GITHUB_REPO/WORKFLOW bien escritos?)",
  422: "GitHub rechaza la rama (REF) o las entradas; ¿cron.yml tiene workflow_dispatch en esa rama?",
};

export async function dispatchOnce(env, fetchFn) {
  const url = `https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/${env.WORKFLOW}/dispatches`;
  const res = await fetchFn(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "tipster-dispatcher",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: env.REF, inputs: { accion: "auto" } }),
  });
  if (res.status === 204) return { ok: true, status: 204 };
  const detail = (await res.text()).slice(0, 200);
  return { ok: false, status: res.status, detail };
}

// Un reintento si GitHub tuvo un fallo pasajero (5xx) o la red falló
export async function dispatch(env, fetchFn = fetch, sleep = (ms) => new Promise((r) => setTimeout(r, ms))) {
  let last;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      last = await dispatchOnce(env, fetchFn);
    } catch (err) {
      last = { ok: false, status: 0, detail: String(err).slice(0, 200) };
    }
    if (last.ok || (last.status !== 0 && last.status < 500)) return last;
    if (attempt === 0) await sleep(RETRY_DELAY_MS);
  }
  return last;
}

function describe(result) {
  const hint = HINTS[result.status] ?? (result.status === 0 ? "fallo de red" : "error de GitHub");
  return `Tipster: el Worker no pudo disparar el workflow (HTTP ${result.status}: ${hint}). ${result.detail ?? ""}`.trim();
}

// Con R2 limita el aviso a uno cada 6 h; sin R2 solo avisa en el primer minuto de cada hora
async function shouldAlert(env, now) {
  if (!env.BUCKET) return new Date(now).getUTCMinutes() < 15;
  const last = await env.BUCKET.get(ALERT_KEY);
  if (last) {
    const { at } = await last.json();
    if (now - at < ALERT_EVERY_MS) return false;
  }
  return true;
}

export async function alert(env, text, fetchFn = fetch, now = Date.now()) {
  if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID) return false;
  if (!(await shouldAlert(env, now))) return false;
  const res = await fetchFn(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text }),
  });
  if (res.ok && env.BUCKET) await env.BUCKET.put(ALERT_KEY, JSON.stringify({ at: now }));
  return res.ok;
}

export async function run(env, fetchFn = fetch, now = Date.now(), sleep) {
  const result = await dispatch(env, fetchFn, sleep);
  if (result.ok) return result;
  console.error(describe(result));
  try {
    await alert(env, describe(result), fetchFn, now);
  } catch (err) {
    console.error("no se pudo avisar por Telegram:", String(err));
  }
  return result;
}

export default {
  async scheduled(_event, env, ctx) {
    ctx.waitUntil(run(env));
  },
};

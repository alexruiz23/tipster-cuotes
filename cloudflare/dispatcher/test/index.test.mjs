import assert from "node:assert/strict";
import { test } from "node:test";
import { alert, dispatch, run } from "../src/index.js";

const ENV = { GITHUB_REPO: "o/r", WORKFLOW: "cron.yml", REF: "main", GITHUB_TOKEN: "tok" };
const NO_SLEEP = async () => {};
const res = (status, body = "") => ({ status, ok: status >= 200 && status < 300, text: async () => body });

function recorder(...answers) {
  const calls = [];
  const fn = async (url, init) => {
    calls.push({ url, init });
    const a = answers.shift();
    if (a instanceof Error) throw a;
    return a;
  };
  return { fn, calls };
}

function fakeBucket(initial) {
  const store = new Map(initial ? [["dispatcher/last-alert.json", JSON.stringify(initial)]] : []);
  return {
    store,
    get: async (k) => (store.has(k) ? { json: async () => JSON.parse(store.get(k)) } : null),
    put: async (k, v) => void store.set(k, v),
  };
}

test("dispara el workflow con la rama y accion=auto", async () => {
  const { fn, calls } = recorder(res(204));
  const r = await dispatch(ENV, fn, NO_SLEEP);
  assert.equal(r.ok, true);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://api.github.com/repos/o/r/actions/workflows/cron.yml/dispatches");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.headers.Authorization, "Bearer tok");
  assert.deepEqual(JSON.parse(calls[0].init.body), { ref: "main", inputs: { accion: "auto" } });
});

test("un 5xx se reintenta una vez y si el segundo sale bien no hay aviso", async () => {
  const gh = recorder(res(502, "bad gateway"), res(204));
  const tg = [];
  const fetchFn = (url, init) => (url.includes("telegram") ? (tg.push(url), res(200)) : gh.fn(url, init));
  const r = await run({ ...ENV, TELEGRAM_BOT_TOKEN: "t", TELEGRAM_CHAT_ID: "1" }, fetchFn, 0, NO_SLEEP);
  assert.equal(r.ok, true);
  assert.equal(gh.calls.length, 2);
  assert.equal(tg.length, 0);
});

test("un fallo de red se reintenta y, si persiste, devuelve status 0", async () => {
  const { fn, calls } = recorder(new Error("boom"), new Error("boom"));
  const r = await dispatch(ENV, fn, NO_SLEEP);
  assert.deepEqual([r.ok, r.status, calls.length], [false, 0, 2]);
});

test("un 401 no se reintenta y avisa por Telegram con la causa", async () => {
  const sent = [];
  const fetchFn = async (url, init) => {
    if (url.includes("telegram")) return sent.push(JSON.parse(init.body)), res(200);
    return res(401, '{"message":"Bad credentials"}');
  };
  const env = { ...ENV, TELEGRAM_BOT_TOKEN: "t", TELEGRAM_CHAT_ID: "42", BUCKET: fakeBucket() };
  const r = await run(env, fetchFn, 1_000, NO_SLEEP);
  assert.equal(r.status, 401);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].chat_id, "42");
  assert.match(sent[0].text, /GITHUB_TOKEN no es válido/);
});

test("con R2 el aviso no se repite antes de 6 horas, y sí después", async () => {
  const bucket = fakeBucket();
  const env = { ...ENV, TELEGRAM_BOT_TOKEN: "t", TELEGRAM_CHAT_ID: "1", BUCKET: bucket };
  let sent = 0;
  const fetchFn = async (url) => (url.includes("telegram") ? (sent++, res(200)) : res(403));
  await run(env, fetchFn, 0, NO_SLEEP);
  await run(env, fetchFn, 15 * 60 * 1000, NO_SLEEP);
  await run(env, fetchFn, 5 * 3600 * 1000, NO_SLEEP);
  assert.equal(sent, 1);
  await run(env, fetchFn, 6 * 3600 * 1000 + 1, NO_SLEEP);
  assert.equal(sent, 2);
});

test("sin R2 solo avisa en el primer cuarto de hora de cada hora", async () => {
  const env = { ...ENV, TELEGRAM_BOT_TOKEN: "t", TELEGRAM_CHAT_ID: "1" };
  const t = (min) => Date.UTC(2026, 10, 13, 12, min);
  let sent = 0;
  const fetchFn = async () => (sent++, res(200));
  assert.equal(await alert(env, "x", fetchFn, t(0)), true);
  assert.equal(await alert(env, "x", fetchFn, t(30)), false);
  assert.equal(sent, 1);
});

test("sin secretos de Telegram el fallo solo se registra y no lanza", async () => {
  const { fn } = recorder(res(404, "Not Found"));
  const r = await run(ENV, fn, 0, NO_SLEEP);
  assert.equal(r.status, 404);
});

test("si Telegram también falla, run no lanza", async () => {
  const fetchFn = async (url) => {
    if (url.includes("telegram")) throw new Error("sin red");
    return res(403);
  };
  const r = await run({ ...ENV, TELEGRAM_BOT_TOKEN: "t", TELEGRAM_CHAT_ID: "1" }, fetchFn, 0, NO_SLEEP);
  assert.equal(r.status, 403);
});

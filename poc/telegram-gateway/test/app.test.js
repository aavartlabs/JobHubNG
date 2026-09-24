import { test } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";

import { createApp } from "../src/app.js";
import { TelegramError, createBotApi } from "../src/bot-api.js";
import { createHandlers } from "../src/handlers.js";

const KEY = "gw-key";
const SECRET = "hook-secret";

function fakeBot(behaviour = {}) {
  const sent = [];
  return {
    sent,
    async sendMessage(chatId, text, extra) {
      if (behaviour.fail) throw behaviour.fail(sent.length);
      sent.push({ chatId, text, extra });
      return { message_id: sent.length };
    },
    async answerCallbackQuery() {},
  };
}

async function withApp(opts, run) {
  const app = createApp({ apiKey: KEY, webhookSecret: SECRET, log: { error() {} }, ...opts });
  const server = http.createServer(app);
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    await run(base);
  } finally {
    await new Promise((r) => server.close(r));
  }
}

const post = (base, path, body, headers = {}) =>
  fetch(`${base}${path}`, { method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify(body) });

const auth = (reply = "Your code: 123456") => {
  const calls = [];
  return { calls, async telegramStart(p) { calls.push(p); return { reply }; } };
};

test("/send needs the key and a valid chat id, then sends", async () => {
  const bot = fakeBot();
  await withApp({ botApi: bot, handlers: createHandlers({ auth: auth() }) }, async (base) => {
    assert.equal((await post(base, "/send", { chat_id: "1", text: "x" })).status, 401);
    assert.equal((await post(base, "/send", { chat_id: "abc", text: "x" }, { "x-api-key": KEY })).status, 400);
    assert.equal((await post(base, "/send", { chat_id: "1", text: " " }, { "x-api-key": KEY })).status, 400);
    const res = await post(base, "/send", { chat_id: 4242, text: "hello" }, { "x-api-key": KEY });
    assert.deepEqual([res.status, await res.json()], [200, { status: "sent", message_id: 1 }]);
    assert.deepEqual(bot.sent[0], { chatId: "4242", text: "hello", extra: {} });
  });
});

test("/send maps blocked, missing chat and other failures", async () => {
  const cases = [
    [new TelegramError("x", { status: 403, description: "Forbidden: bot was blocked by the user" }), 410, "blocked"],
    [new TelegramError("x", { status: 400, description: "Bad Request: chat not found" }), 404, "chat_not_found"],
    [new TelegramError("x", { status: 500, description: "oops" }), 502, "send_failed"],
    [new TelegramError("Telegram unreachable (TimeoutError)"), 503, "send_failed"],
  ];
  for (const [err, status, error] of cases) {
    await withApp({ botApi: fakeBot({ fail: () => err }), handlers: createHandlers({ auth: auth() }) }, async (base) => {
      const res = await post(base, "/send", { chat_id: "1", text: "x" }, { "x-api-key": KEY });
      assert.equal(res.status, status);
      assert.equal((await res.json()).error, error);
    });
  }
});

test("/send is disabled without a key", async () => {
  await withApp({ apiKey: "", botApi: fakeBot(), handlers: createHandlers({ auth: auth() }) }, async (base) => {
    assert.equal((await post(base, "/send", { chat_id: "1", text: "x" }, { "x-api-key": "" })).status, 503);
  });
});

test("webhook: wrong secret is refused; /start <token> goes to auth-service and replies once", async () => {
  const bot = fakeBot();
  const a = auth("Your JobsHub code: 654321");
  await withApp({ botApi: bot, handlers: createHandlers({ auth: a }) }, async (base) => {
    const update = { update_id: 7, message: { chat: { id: 4242, type: "private", username: "ada" }, text: "/start tok123" } };
    assert.equal((await post(base, "/webhook", update, { "X-Telegram-Bot-Api-Secret-Token": "nope" })).status, 401);
    assert.equal(bot.sent.length, 0);

    for (let i = 0; i < 2; i++) { // a redelivery of the same update is ignored
      const res = await post(base, "/webhook", update, { "X-Telegram-Bot-Api-Secret-Token": SECRET });
      assert.equal(res.status, 200);
    }
    assert.deepEqual(a.calls, [{ token: "tok123", chatId: "4242", username: "ada", firstName: "" }]);
    assert.deepEqual(bot.sent.map((s) => [s.chatId, s.text]), [["4242", "Your JobsHub code: 654321"]]);
  });
});

test("webhook: plain /start and any text get help with the chat id; a failing handler still 200s", async () => {
  const bot = fakeBot();
  const broken = { async telegramStart() { throw new Error("auth down"); } };
  await withApp({ botApi: bot, handlers: createHandlers({ auth: broken, siteUrl: "https://jobs.example" }) }, async (base) => {
    const h = { "X-Telegram-Bot-Api-Secret-Token": SECRET };
    const msg = (id, text) => ({ update_id: id, message: { chat: { id: 9, type: "private" }, text } });
    await post(base, "/webhook", msg(1, "/start"), h);
    await post(base, "/webhook", msg(2, "hello"), h);
    const res = await post(base, "/webhook", msg(3, "/start tok"), h);
    assert.equal(res.status, 200);
    assert.match(bot.sent[0].text, /sign up at https:\/\/jobs\.example/);
    assert.match(bot.sent[0].text, /chat id: 9/);
    assert.match(bot.sent[1].text, /JobsHub alerts bot/);
    assert.match(bot.sent[2].text, /something went wrong/);
  });
});

test("bot API errors never contain the token", async () => {
  const token = "123:very-secret";
  const failing = createBotApi({ token, fetchImpl: async (url) => { throw new TypeError(`fetch failed ${url}`); } });
  await assert.rejects(failing.sendMessage("1", "x"), (err) => !err.message.includes("very-secret"));
  const refused = createBotApi({
    token,
    fetchImpl: async () => new Response(JSON.stringify({ ok: false, description: "Unauthorized" }), { status: 401 }),
  });
  await assert.rejects(refused.sendMessage("1", "x"), (err) => err.status === 401 && !err.message.includes("very-secret"));
});

test("bot API truncates text to Telegram's limit and reports retry_after", async () => {
  let body;
  const api = createBotApi({
    token: "t",
    fetchImpl: async (url, init) => {
      body = JSON.parse(init.body);
      return new Response(JSON.stringify({ ok: false, description: "Too Many Requests", parameters: { retry_after: 3 } }), { status: 429 });
    },
  });
  await assert.rejects(api.sendMessage("1", "x".repeat(5000)), (err) => err.retryAfter === 3);
  assert.equal(body.text.length, 4096);
});

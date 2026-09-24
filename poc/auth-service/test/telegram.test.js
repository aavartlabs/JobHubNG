import { test } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import Database from "better-sqlite3";

import {
  CODE_TTL_MS,
  EXPIRED_LINK_REPLY,
  LINK_TTL_MS,
  MAX_CODE_ATTEMPTS,
  TelegramVerifyError,
  createTelegramInternalHandler,
  createTelegramStore,
  ensureTelegramChatIndex,
  maskEmail,
} from "../src/telegram.js";

const NOW = "2026-09-24T00:00:00.000Z";

function setup() {
  const db = new Database(":memory:");
  db.exec(`CREATE TABLE "user" ("id" text not null primary key, "email" text not null, "updatedAt" date not null,
    "telegramChatId" text, "telegramUsername" text, "telegramVerified" integer)`);
  db.prepare(`INSERT INTO "user" (id, email, updatedAt) VALUES ('u1', 'ada@example.com', ?), ('u2', 'bob@example.com', ?)`).run(NOW, NOW);
  let clock = Date.parse(NOW);
  const store = createTelegramStore({ db, botUsername: "JobsBot", now: () => clock });
  return { db, store, tick: (ms) => { clock += ms; } };
}

const tokenOf = (url) => new URL(url).searchParams.get("start");
const codeOf = (reply) => /code: ([0-9]{6})/.exec(reply)[1];
const user = (db, id) => db.prepare(`SELECT * FROM "user" WHERE id = ?`).get(id);
const failsWith = (fn, code) => assert.throws(fn, (err) => err instanceof TelegramVerifyError && err.code === code);

test("link -> /start -> code links the user's Telegram", () => {
  const { db, store } = setup();
  const url = store.createLink("u1");
  assert.match(url, /^https:\/\/t\.me\/JobsBot\?start=[A-Za-z0-9_-]{32}$/);
  const reply = store.start({ token: tokenOf(url), chatId: "4242", username: "ada" });
  assert.match(reply, /Never share it/);
  store.verify("u1", codeOf(reply));
  const u = user(db, "u1");
  assert.deepEqual([u.telegramChatId, u.telegramUsername, u.telegramVerified], ["4242", "ada", 1]);
  // Nothing left behind: link and code are both one-time.
  assert.equal(db.prepare("SELECT count(*) AS n FROM telegram_verification").get().n, 0);
});

test("a link works once, only the newest link works, and links expire", () => {
  const { store, tick } = setup();
  const first = tokenOf(store.createLink("u1"));
  const second = tokenOf(store.createLink("u1"));
  assert.equal(store.start({ token: first, chatId: "1" }), EXPIRED_LINK_REPLY);
  assert.notEqual(store.start({ token: second, chatId: "1" }), EXPIRED_LINK_REPLY);
  assert.equal(store.start({ token: second, chatId: "1" }), EXPIRED_LINK_REPLY);
  const late = tokenOf(store.createLink("u1"));
  tick(LINK_TTL_MS);
  assert.equal(store.start({ token: late, chatId: "1" }), EXPIRED_LINK_REPLY);
  assert.equal(store.start({ token: "made-up", chatId: "1" }), EXPIRED_LINK_REPLY);
});

test("wrong codes count, and the code is gone after too many", () => {
  const { db, store } = setup();
  const code = codeOf(store.start({ token: tokenOf(store.createLink("u1")), chatId: "1" }));
  const wrong = code === "000000" ? "111111" : "000000";
  for (let i = 1; i < MAX_CODE_ATTEMPTS; i++) failsWith(() => store.verify("u1", wrong), "INVALID_CODE");
  failsWith(() => store.verify("u1", wrong), "TOO_MANY_ATTEMPTS");
  failsWith(() => store.verify("u1", code), "CODE_EXPIRED"); // even the right one, now
  assert.equal(user(db, "u1").telegramVerified, null);
});

test("codes expire, and belong to the user whose link was used", () => {
  const { store, tick } = setup();
  const code = codeOf(store.start({ token: tokenOf(store.createLink("u1")), chatId: "1" }));
  failsWith(() => store.verify("u2", code), "CODE_EXPIRED"); // u2 has no pending code
  tick(CODE_TTL_MS);
  failsWith(() => store.verify("u1", code), "CODE_EXPIRED");
  failsWith(() => store.verify("u1", "abc"), "CODE_EXPIRED");
});

test("a Telegram already on another account gets no code, and is told which account", () => {
  const { db, store } = setup();
  store.verify("u1", codeOf(store.start({ token: tokenOf(store.createLink("u1")), chatId: "4242" })));
  const token = tokenOf(store.createLink("u2"));
  const reply = store.start({ token, chatId: "4242" });
  assert.match(reply, /already linked to the JobsHub account ad•••@example\.com/);
  assert.doesNotMatch(reply, /[0-9]{6}/);
  assert.equal(store.start({ token, chatId: "4242" }), EXPIRED_LINK_REPLY); // link used up
  failsWith(() => store.verify("u2", "123456"), "CODE_EXPIRED"); // no code was issued
  assert.equal(user(db, "u2").telegramVerified, null);
  // Re-linking the same account to the same chat is fine.
  store.verify("u1", codeOf(store.start({ token: tokenOf(store.createLink("u1")), chatId: "4242" })));
});

test("if the chat gets linked elsewhere after the code went out, verify refuses and names it", () => {
  const { db, store } = setup();
  const code = codeOf(store.start({ token: tokenOf(store.createLink("u2")), chatId: "4242" }));
  store.verify("u1", codeOf(store.start({ token: tokenOf(store.createLink("u1")), chatId: "4242" })));
  assert.throws(() => store.verify("u2", code), (err) => err.code === "TELEGRAM_IN_USE" && /ad•••@example\.com/.test(err.message));
  assert.equal(user(db, "u2").telegramVerified, null);
});

test("the database refuses a second account on the same chat", () => {
  const { db } = setup();
  assert.equal(ensureTelegramChatIndex(db), true);
  assert.equal(ensureTelegramChatIndex(db), true); // idempotent
  db.prepare(`UPDATE "user" SET "telegramChatId" = '4242' WHERE id = 'u1'`).run();
  assert.throws(() => db.prepare(`UPDATE "user" SET "telegramChatId" = '4242' WHERE id = 'u2'`).run(), /UNIQUE/);
  db.prepare(`UPDATE "user" SET "telegramChatId" = NULL WHERE id = 'u1'`).run(); // many unlinked is fine
  db.prepare(`UPDATE "user" SET "telegramChatId" = NULL WHERE id = 'u2'`).run();
});

test("existing duplicates don't stop startup: the index is skipped and reported", () => {
  const { db } = setup();
  db.prepare(`UPDATE "user" SET "telegramChatId" = '4242'`).run();
  const errors = [];
  assert.equal(ensureTelegramChatIndex(db, { error: (m) => errors.push(m) }), false);
  assert.match(errors[0], /duplicate/);
});

test("emails are masked to two characters and the domain", () => {
  assert.equal(maskEmail("someone@example.org"), "so•••@example.org");
  assert.equal(maskEmail("a@x.io"), "a•••@x.io");
  assert.equal(maskEmail("nodomain"), "another account");
});

async function withInternal(store, apiKey, run) {
  const handler = createTelegramInternalHandler({ store, apiKey });
  const server = http.createServer(async (req, res) => {
    if (!(await handler(req, res))) { res.writeHead(418); res.end(); }
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  try {
    await run(`http://127.0.0.1:${server.address().port}`);
  } finally {
    await new Promise((r) => server.close(r));
  }
}

test("internal /start needs its key and a chat id, and returns the bot's reply", async () => {
  const { store } = setup();
  const token = tokenOf(store.createLink("u1"));
  await withInternal(store, "k", async (base) => {
    const call = (body, key = "k") => fetch(`${base}/internal/telegram/start`, {
      method: "POST", headers: { "x-telegram-internal-key": key }, body: JSON.stringify(body),
    });
    assert.equal((await call({ token, chatId: "1" }, "wrong")).status, 401);
    assert.equal((await call({ token, chatId: "abc" })).status, 400);
    const res = await call({ token, chatId: "4242", username: "ada" });
    assert.equal(res.status, 200);
    assert.match((await res.json()).reply, /verification code: [0-9]{6}/);
    assert.equal((await fetch(`${base}/elsewhere`)).status, 418); // not ours: falls through
  });
  await withInternal(store, "", async (base) => {
    const res = await fetch(`${base}/internal/telegram/start`, { method: "POST", body: "{}" });
    assert.equal(res.status, 503);
  });
});

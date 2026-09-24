import { test } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import Database from "better-sqlite3";
import { createAdminHandler } from "../src/admin.js";
import { createTelegramStore } from "../src/telegram.js";

const KEY = "admin-test-key";

// Same DDL Better Auth's own migrate produced on the real deployment (user, session,
// account, verification) -- copied from pi09's auth.db, not hand-invented.
const SCHEMA = `
CREATE TABLE "user" ("id" text not null primary key, "name" text not null, "email" text not null unique, "emailVerified" integer not null, "image" text, "createdAt" date not null, "updatedAt" date not null, "phoneNumber" text unique, "phoneNumberVerified" integer, "telegramChatId" text, "telegramUsername" text, "telegramVerified" integer);
CREATE TABLE "session" ("id" text not null primary key, "expiresAt" date not null, "token" text not null unique, "createdAt" date not null, "updatedAt" date not null, "ipAddress" text, "userAgent" text, "userId" text not null references "user" ("id") on delete cascade);
CREATE TABLE "account" ("id" text not null primary key, "accountId" text not null, "providerId" text not null, "userId" text not null references "user" ("id") on delete cascade, "accessToken" text, "refreshToken" text, "idToken" text, "accessTokenExpiresAt" date, "refreshTokenExpiresAt" date, "scope" text, "password" text, "createdAt" date not null, "updatedAt" date not null);
CREATE TABLE "verification" ("id" text not null primary key, "identifier" text not null, "value" text not null, "expiresAt" date not null, "createdAt" date not null, "updatedAt" date not null);
`;

const FUTURE = "2099-01-01T00:00:00.000Z";
const PAST = "2000-01-01T00:00:00.000Z";
const NOW = "2026-09-23T00:00:00.000Z";

function seededDb() {
  const db = new Database(":memory:");
  db.exec(SCHEMA);
  const addUser = db.prepare(
    `INSERT INTO "user" (id, name, email, emailVerified, createdAt, updatedAt, telegramChatId, telegramUsername, telegramVerified)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  );
  addUser.run("u1", "Ada", "ada@example.com", 1, NOW, NOW, "4242", "ada", 1);
  addUser.run("u2", "Bob", "bob@example.com", 0, NOW, NOW, null, null, null);
  // Creates telegram_verification, as auth.js does at startup; a pending link for Bob.
  createTelegramStore({ db, botUsername: "JobsBot" }).createLink("u2");
  const addSession = db.prepare(
    `INSERT INTO "session" (id, expiresAt, token, createdAt, updatedAt, userId) VALUES (?, ?, ?, ?, ?, ?)`,
  );
  addSession.run("s1", FUTURE, "t1", NOW, NOW, "u1");
  addSession.run("s2", PAST, "t2", NOW, NOW, "u1");
  addSession.run("s3", FUTURE, "t3", NOW, NOW, "u2");
  db.prepare(
    `INSERT INTO "account" (id, accountId, providerId, userId, password, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?, ?, ?)`,
  ).run("a2", "u2", "credential", "u2", "hash", NOW, NOW);
  const addVerification = db.prepare(
    `INSERT INTO "verification" (id, identifier, value, expiresAt, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?, ?)`,
  );
  addVerification.run("v1", "email-verification-otp-bob@example.com", "123456:0", FUTURE, NOW, NOW);
  addVerification.run("v2", "+15550000009", "654321:0", FUTURE, NOW, NOW);
  return db;
}

async function withServer(db, run, apiKey = KEY) {
  const handler = createAdminHandler({ db, apiKey });
  const server = http.createServer(async (req, res) => {
    if (!(await handler(req, res))) {
      res.writeHead(418);
      res.end();
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    await run(base);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

function call(base, method, path, { body, key = KEY } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (key !== null) headers["x-admin-api-key"] = key;
  return fetch(base + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
}

test("leaves non-admin paths to the next handler", async () => {
  await withServer(seededDb(), async (base) => {
    const res = await fetch(`${base}/auth/get-session`);
    assert.equal(res.status, 418);
  });
});

test("rejects a missing or wrong key with 401", async () => {
  await withServer(seededDb(), async (base) => {
    assert.equal((await call(base, "GET", "/internal/admin/users", { key: null })).status, 401);
    assert.equal((await call(base, "GET", "/internal/admin/users", { key: "nope" })).status, 401);
  });
});

test("is disabled (503) when no admin key is configured", async () => {
  await withServer(
    seededDb(),
    async (base) => {
      assert.equal((await call(base, "GET", "/internal/admin/users", { key: "" })).status, 503);
    },
    "",
  );
});

test("lists users with booleans and a live-session count", async () => {
  await withServer(seededDb(), async (base) => {
    const res = await call(base, "GET", "/internal/admin/users");
    assert.equal(res.status, 200);
    const { users } = await res.json();
    const ada = users.find((u) => u.id === "u1");
    assert.deepEqual(
      { ...ada, createdAt: undefined, updatedAt: undefined },
      {
        id: "u1",
        name: "Ada",
        email: "ada@example.com",
        emailVerified: true,
        telegramChatId: "4242",
        telegramUsername: "ada",
        telegramVerified: true,
        activeSessions: 1,
        createdAt: undefined,
        updatedAt: undefined,
      },
    );
    const bob = users.find((u) => u.id === "u2");
    assert.equal(bob.emailVerified, false);
    assert.equal(bob.telegramVerified, false);
  });
});

test("updates only the provided fields", async () => {
  const db = seededDb();
  await withServer(db, async (base) => {
    const res = await call(base, "PATCH", "/internal/admin/users/u2", {
      body: { name: "Robert", emailVerified: true },
    });
    assert.equal(res.status, 200);
    const row = db.prepare(`SELECT * FROM "user" WHERE id = 'u2'`).get();
    assert.equal(row.name, "Robert");
    assert.equal(row.email, "bob@example.com");
    assert.equal(row.emailVerified, 1);
    assert.notEqual(row.updatedAt, NOW);
  });
});

test("telegramVerified:false unlinks Telegram; it can't be set true", async () => {
  const db = seededDb();
  await withServer(db, async (base) => {
    assert.equal((await call(base, "PATCH", "/internal/admin/users/u1", { body: { telegramVerified: false } })).status, 200);
    const row = db.prepare(`SELECT * FROM "user" WHERE id = 'u1'`).get();
    assert.deepEqual([row.telegramChatId, row.telegramUsername, row.telegramVerified], [null, null, 0]);
    assert.equal((await call(base, "PATCH", "/internal/admin/users/u2", { body: { telegramVerified: true } })).status, 400);
  });
});

test("rejects invalid field values with 400", async () => {
  await withServer(seededDb(), async (base) => {
    for (const body of [{ email: "not-an-email" }, { name: "" }, { emailVerified: "yes" }, { phoneNumber: "+15550000002" }, {}]) {
      assert.equal((await call(base, "PATCH", "/internal/admin/users/u1", { body })).status, 400, JSON.stringify(body));
    }
  });
});

test("a duplicate email is a 409, not a 500", async () => {
  await withServer(seededDb(), async (base) => {
    assert.equal((await call(base, "PATCH", "/internal/admin/users/u2", { body: { email: "ada@example.com" } })).status, 409);
  });
});

test("unknown user ids are 404", async () => {
  await withServer(seededDb(), async (base) => {
    assert.equal((await call(base, "PATCH", "/internal/admin/users/nope", { body: { name: "X" } })).status, 404);
    assert.equal((await call(base, "DELETE", "/internal/admin/users/nope")).status, 404);
    assert.equal((await call(base, "POST", "/internal/admin/users/nope/revoke-sessions")).status, 404);
  });
});

test("delete removes the user, its sessions, accounts and pending codes", async () => {
  const db = seededDb();
  await withServer(db, async (base) => {
    const res = await call(base, "DELETE", "/internal/admin/users/u2");
    assert.equal(res.status, 200);
    assert.equal(db.prepare(`SELECT count(*) AS n FROM "user" WHERE id = 'u2'`).get().n, 0);
    assert.equal(db.prepare(`SELECT count(*) AS n FROM "session" WHERE userId = 'u2'`).get().n, 0);
    assert.equal(db.prepare(`SELECT count(*) AS n FROM "account" WHERE userId = 'u2'`).get().n, 0);
    assert.equal(db.prepare(`SELECT count(*) AS n FROM "verification" WHERE id = 'v1'`).get().n, 0);
    assert.equal(db.prepare(`SELECT count(*) AS n FROM telegram_verification WHERE user_id = 'u2'`).get().n, 0);
    // Someone else's pending code is untouched.
    assert.equal(db.prepare(`SELECT count(*) AS n FROM "verification" WHERE id = 'v2'`).get().n, 1);
    assert.equal(db.prepare(`SELECT count(*) AS n FROM "user"`).get().n, 1);
  });
});

test("revoke-sessions deletes every session for that user only", async () => {
  const db = seededDb();
  await withServer(db, async (base) => {
    const res = await call(base, "POST", "/internal/admin/users/u1/revoke-sessions");
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { revoked: 2 });
    assert.equal(db.prepare(`SELECT count(*) AS n FROM "session" WHERE userId = 'u1'`).get().n, 0);
    assert.equal(db.prepare(`SELECT count(*) AS n FROM "session" WHERE userId = 'u2'`).get().n, 1);
  });
});

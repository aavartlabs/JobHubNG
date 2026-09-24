import crypto from "node:crypto";
import { APIError, createAuthEndpoint, sessionMiddleware } from "better-auth/api";

/**
 * Telegram as the account's second verified contact (after email), replacing the
 * WhatsApp mobile OTP.
 *
 *   1. Signed in, the user asks for a link: POST /auth/telegram/link -> a one-time
 *      t.me/<bot>?start=<token> URL (LINK_TTL).
 *   2. They press Start; telegram-gateway gets "/start <token>" and calls
 *      POST /internal/telegram/start here, which consumes the token and returns the
 *      bot's reply: a 6-digit code (CODE_TTL) bound to that user and that chat.
 *   3. They type the code into the site: POST /auth/telegram/verify {code} sets
 *      telegramChatId / telegramUsername / telegramVerified on their user.
 *
 * The code has to come back through the site session, so forwarding someone a link
 * can't attach their Telegram to your account. One Telegram chat belongs to at most
 * one account: a chat already linked elsewhere gets no code, just the (masked) email of
 * the account it's on, so a person who already has an account signs in to that one
 * instead of making another. verify() checks again, and a unique index
 * (ensureTelegramChatIndex) backs both. Tokens and codes are stored hashed.
 */

export const LINK_TTL_MS = 15 * 60 * 1000;
export const CODE_TTL_MS = 10 * 60 * 1000;
export const MAX_CODE_ATTEMPTS = 5;

const INTERNAL_PATH = "/internal/telegram/start";
const MAX_BODY_BYTES = 16 * 1024;

export const EXPIRED_LINK_REPLY =
  'That link has expired or was already used. On JobsHub, click "Connect Telegram" again for a fresh one.';

/** "so•••@example.org" -- enough for the owner to recognise, not to learn an address. */
export function maskEmail(email) {
  const [name, domain] = String(email ?? "").split("@");
  return domain ? `${name.slice(0, 2)}•••@${domain}` : "another account";
}

const inUseMessage = (email) =>
  `That Telegram is already linked to the JobsHub account ${maskEmail(email)}. ` +
  "Sign in with that account instead.";

/**
 * One account per Telegram chat, in the database itself. Called by server.js at
 * startup -- after Better Auth's migrate has added the column, which importing this
 * module (as the migrate CLI does) must not depend on. If existing rows already share
 * a chat, the index can't be built: that's reported and startup goes on, with the
 * checks in start()/verify() still in force.
 */
export function ensureTelegramChatIndex(db, log = console) {
  try {
    db.exec(`CREATE UNIQUE INDEX IF NOT EXISTS user_telegram_chat_unique
             ON "user" ("telegramChatId") WHERE "telegramChatId" IS NOT NULL`);
    return true;
  } catch (err) {
    log.error(`[auth-service] no unique index on telegramChatId (duplicate chats already linked?): ${err.message}`);
    return false;
  }
}

const hash = (value) => crypto.createHash("sha256").update(String(value)).digest("hex");

function sameHash(a, b) {
  const x = Buffer.from(a, "hex");
  const y = Buffer.from(b, "hex");
  return x.length === y.length && crypto.timingSafeEqual(x, y);
}

export class TelegramVerifyError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

export function createTelegramStore({ db, botUsername, now = () => Date.now() }) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS telegram_verification (
      kind        TEXT NOT NULL CHECK (kind IN ('link', 'code')),
      key         TEXT NOT NULL,   -- link: sha256(token); code: the user id
      user_id     TEXT NOT NULL,
      chat_id     TEXT,
      username    TEXT,
      code_hash   TEXT,
      attempts    INTEGER NOT NULL DEFAULT 0,
      expires_at  INTEGER NOT NULL, -- epoch ms
      PRIMARY KEY (kind, key)
    )
  `);
  const purge = db.prepare(`DELETE FROM telegram_verification WHERE expires_at <= ?`);
  const dropUserLinks = db.prepare(`DELETE FROM telegram_verification WHERE kind = 'link' AND user_id = ?`);
  const addLink = db.prepare(
    `INSERT INTO telegram_verification (kind, key, user_id, expires_at) VALUES ('link', ?, ?, ?)`,
  );
  const findLink = db.prepare(`SELECT * FROM telegram_verification WHERE kind = 'link' AND key = ?`);
  const dropLink = db.prepare(`DELETE FROM telegram_verification WHERE kind = 'link' AND key = ?`);
  const putCode = db.prepare(`
    INSERT INTO telegram_verification (kind, key, user_id, chat_id, username, code_hash, attempts, expires_at)
    VALUES ('code', @userId, @userId, @chatId, @username, @codeHash, 0, @expiresAt)
    ON CONFLICT (kind, key) DO UPDATE SET chat_id = excluded.chat_id, username = excluded.username,
      code_hash = excluded.code_hash, attempts = 0, expires_at = excluded.expires_at
  `);
  const findCode = db.prepare(`SELECT * FROM telegram_verification WHERE kind = 'code' AND key = ?`);
  const dropCode = db.prepare(`DELETE FROM telegram_verification WHERE kind = 'code' AND key = ?`);
  const countAttempt = db.prepare(
    `UPDATE telegram_verification SET attempts = attempts + 1 WHERE kind = 'code' AND key = ?`,
  );
  // Prepared on first use, not here: Better Auth's migrate CLI imports this module (via
  // auth.js) before it has added the telegram* columns these statements name.
  let userStatements;
  const users = () =>
    (userStatements ??= {
      chatOwner: db.prepare(`SELECT id, email FROM "user" WHERE "telegramChatId" = ? AND id != ?`),
      linkUser: db.prepare(`
        UPDATE "user" SET "telegramChatId" = @chatId, "telegramUsername" = @username,
          "telegramVerified" = 1, "updatedAt" = @updatedAt WHERE id = @userId
      `),
    });

  function createLink(userId) {
    if (!botUsername) throw new Error("TELEGRAM_BOT_USERNAME is not set");
    // 32 chars of [A-Za-z0-9_-]: what Telegram allows in a start parameter (max 64).
    const token = crypto.randomBytes(24).toString("base64url");
    db.transaction(() => {
      purge.run(now());
      dropUserLinks.run(userId); // only the newest link works
      addLink.run(hash(token), userId, now() + LINK_TTL_MS);
    })();
    return `https://t.me/${botUsername}?start=${token}`;
  }

  /** "/start <token>" from chat -> the text the bot should reply with. */
  function start({ token, chatId, username }) {
    purge.run(now());
    const link = typeof token === "string" && token ? findLink.get(hash(token)) : undefined;
    if (!link) return EXPIRED_LINK_REPLY;
    const owner = users().chatOwner.get(String(chatId), link.user_id);
    if (owner) {
      dropLink.run(link.key);
      return inUseMessage(owner.email);
    }
    const code = String(crypto.randomInt(0, 1_000_000)).padStart(6, "0");
    db.transaction(() => {
      dropLink.run(link.key);
      putCode.run({
        userId: link.user_id,
        chatId: String(chatId),
        username: username || null,
        codeHash: hash(code),
        expiresAt: now() + CODE_TTL_MS,
      });
    })();
    return (
      `Your JobsHub verification code: ${code}\n\n` +
      'Enter it on the JobsHub page where you clicked "Connect Telegram". It is valid for ' +
      `${CODE_TTL_MS / 60000} minutes. Never share it -- JobsHub will never ask you for it here.`
    );
  }

  /** Links the user's Telegram if `code` is right; throws TelegramVerifyError if not. */
  function verify(userId, code) {
    // The transaction returns the failure instead of throwing it: a throw inside would
    // roll back the attempt count and the code deletions along with everything else.
    const failure = db.transaction(() => {
      const row = findCode.get(userId);
      if (!row || row.expires_at <= now()) {
        if (row) dropCode.run(userId);
        return ["CODE_EXPIRED", 'That code has expired. Click "Connect Telegram" again.'];
      }
      if (!/^[0-9]{6}$/.test(String(code ?? "")) || !sameHash(hash(code), row.code_hash)) {
        if (row.attempts + 1 >= MAX_CODE_ATTEMPTS) {
          dropCode.run(userId);
          return ["TOO_MANY_ATTEMPTS", 'Too many wrong codes. Click "Connect Telegram" again.'];
        }
        countAttempt.run(userId);
        return ["INVALID_CODE", "Wrong code. Check the latest message from the bot."];
      }
      dropCode.run(userId);
      const owner = users().chatOwner.get(row.chat_id, userId);
      if (owner) return ["TELEGRAM_IN_USE", inUseMessage(owner.email)];
      users().linkUser.run({
        userId,
        chatId: row.chat_id,
        username: row.username,
        updatedAt: new Date(now()).toISOString(),
      });
      return null;
    })();
    if (failure) throw new TelegramVerifyError(...failure);
  }

  return { createLink, start, verify };
}

/**
 * Better Auth plugin: the user fields (added to "user" by the migrate CLI) and the two
 * session-only endpoints. Fields are input:false, so no sign-up or update-user call can
 * set them -- only verify() does.
 */
export function telegramPlugin(store) {
  return {
    id: "telegram",
    schema: {
      user: {
        fields: {
          // Not unique: SQLite can't ALTER TABLE ADD a UNIQUE column onto the existing
          // user table. verify() enforces one account per chat instead.
          telegramChatId: { type: "string", required: false, input: false, returned: true },
          telegramUsername: { type: "string", required: false, input: false, returned: true },
          telegramVerified: { type: "boolean", required: false, input: false, returned: true },
        },
      },
    },
    endpoints: {
      telegramLink: createAuthEndpoint(
        "/telegram/link",
        { method: "POST", use: [sessionMiddleware] },
        async (ctx) => ctx.json({ url: store.createLink(ctx.context.session.user.id) }),
      ),
      telegramVerify: createAuthEndpoint(
        "/telegram/verify",
        { method: "POST", use: [sessionMiddleware] },
        async (ctx) => {
          try {
            store.verify(ctx.context.session.user.id, ctx.body?.code);
          } catch (err) {
            if (err instanceof TelegramVerifyError) {
              throw APIError.from("BAD_REQUEST", { code: err.code, message: err.message });
            }
            throw err;
          }
          return ctx.json({ status: true });
        },
      ),
    },
  };
}

function sendJson(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

function keyMatches(provided, expected) {
  const a = Buffer.from(String(provided ?? ""));
  const b = Buffer.from(expected);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let raw = "";
    req.on("data", (chunk) => {
      raw += chunk;
      if (raw.length > MAX_BODY_BYTES) reject(new Error("body too large"));
    });
    req.on("end", () => {
      try {
        resolve(raw ? JSON.parse(raw) : {});
      } catch (err) {
        reject(err);
      }
    });
    req.on("error", reject);
  });
}

/**
 * POST /internal/telegram/start, for telegram-gateway only (header
 * x-telegram-internal-key). Outside /auth/*, like /internal/admin/*, so Flask's public
 * proxy can never reach it. Returns true if it handled the request.
 */
export function createTelegramInternalHandler({ store, apiKey = process.env.TELEGRAM_INTERNAL_API_KEY || "" }) {
  return async function handleTelegramInternal(req, res) {
    const url = new URL(req.url, "http://internal");
    if (url.pathname !== INTERNAL_PATH) return false;
    if (req.method !== "POST") {
      sendJson(res, 404, { error: "not found" });
      return true;
    }
    if (!apiKey) {
      sendJson(res, 503, { error: "disabled: TELEGRAM_INTERNAL_API_KEY is not set" });
      return true;
    }
    if (!keyMatches(req.headers["x-telegram-internal-key"], apiKey)) {
      sendJson(res, 401, { error: "unauthorized" });
      return true;
    }
    let body;
    try {
      body = await readJson(req);
    } catch {
      sendJson(res, 400, { error: "invalid JSON body" });
      return true;
    }
    if (!/^-?[0-9]{1,20}$/.test(String(body.chatId ?? ""))) {
      sendJson(res, 400, { error: "chatId must be a Telegram chat id" });
      return true;
    }
    sendJson(res, 200, { reply: store.start(body) });
    return true;
  };
}

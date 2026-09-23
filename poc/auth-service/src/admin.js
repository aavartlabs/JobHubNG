import crypto from "node:crypto";

/**
 * Internal admin API over Better Auth's own tables, for the Flask admin pages
 * (poc/jobhub_poc/webapp/admin.py). Lives under /internal/admin/*, deliberately
 * OUTSIDE Better Auth's basePath "/auth": Flask's public reverse proxy
 * (auth_proxy.py) only ever forwards /auth/*, and this service publishes no host
 * port, so nothing outside the jobhub Docker network can reach these routes. The
 * shared x-admin-api-key is defence in depth on top of that, not the only guard.
 *
 * Goes straight to SQLite rather than through Better Auth's admin plugin: that
 * plugin authorises by a role on a Better Auth user, but the admin identity here
 * is the Flask app's own app_users row, which Better Auth knows nothing about.
 */

const PREFIX = "/internal/admin/users";
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PHONE_RE = /^\+?[0-9]{7,15}$/;
// Better Auth's email-otp plugin keys pending codes as `${type}-otp-${email}`;
// the phone-number plugin keys them by the bare number.
const EMAIL_OTP_TYPES = ["sign-in", "email-verification", "forget-password"];
const MAX_BODY_BYTES = 16 * 1024;

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

/** Validates a PATCH body into column -> value pairs, or returns an error string. */
function parseUpdate(body) {
  if (!body || typeof body !== "object" || Array.isArray(body)) return { error: "body must be an object" };
  const set = {};
  if ("name" in body) {
    if (typeof body.name !== "string" || !body.name.trim()) return { error: "name must be a non-empty string" };
    set.name = body.name.trim();
  }
  if ("email" in body) {
    if (typeof body.email !== "string" || !EMAIL_RE.test(body.email.trim())) return { error: "invalid email" };
    set.email = body.email.trim().toLowerCase();
  }
  if ("phoneNumber" in body) {
    const phone = body.phoneNumber === null ? "" : body.phoneNumber;
    if (typeof phone !== "string" || (phone.trim() && !PHONE_RE.test(phone.trim()))) {
      return { error: "invalid phoneNumber" };
    }
    set.phoneNumber = phone.trim() || null;
  }
  for (const flag of ["emailVerified", "phoneNumberVerified"]) {
    if (flag in body) {
      if (typeof body[flag] !== "boolean") return { error: `${flag} must be a boolean` };
      set[flag] = body[flag] ? 1 : 0;
    }
  }
  if (Object.keys(set).length === 0) return { error: "nothing to update" };
  return { set };
}

export function createAdminHandler({ db, apiKey = process.env.ADMIN_API_KEY || "" }) {
  const listUsers = db.prepare(`
    SELECT u.id, u.name, u.email, u.emailVerified, u.phoneNumber, u.phoneNumberVerified,
           u.createdAt, u.updatedAt,
           (SELECT count(*) FROM "session" s WHERE s.userId = u.id AND s.expiresAt > ?) AS activeSessions
    FROM "user" u
    ORDER BY u.createdAt DESC
  `);
  const getUser = db.prepare(`SELECT * FROM "user" WHERE id = ?`);
  const deleteSessions = db.prepare(`DELETE FROM "session" WHERE userId = ?`);
  const deleteAccounts = db.prepare(`DELETE FROM "account" WHERE userId = ?`);
  const deleteVerification = db.prepare(`DELETE FROM "verification" WHERE identifier = ?`);
  const deleteUserRow = db.prepare(`DELETE FROM "user" WHERE id = ?`);

  const deleteUser = db.transaction((user) => {
    deleteSessions.run(user.id);
    deleteAccounts.run(user.id);
    for (const type of EMAIL_OTP_TYPES) deleteVerification.run(`${type}-otp-${user.email}`);
    if (user.phoneNumber) deleteVerification.run(user.phoneNumber);
    deleteUserRow.run(user.id);
  });

  function updateUser(id, set) {
    const columns = Object.keys(set);
    const assignments = columns.map((c) => `"${c}" = @${c}`).join(", ");
    db.prepare(`UPDATE "user" SET ${assignments}, "updatedAt" = @updatedAt WHERE id = @id`).run({
      ...set,
      updatedAt: new Date().toISOString(),
      id,
    });
  }

  /** Returns true if it handled the request, false to let the caller fall through. */
  return async function handleAdmin(req, res) {
    const url = new URL(req.url, "http://internal");
    if (url.pathname !== PREFIX && !url.pathname.startsWith(`${PREFIX}/`)) return false;

    if (!apiKey) {
      sendJson(res, 503, { error: "admin API disabled: ADMIN_API_KEY is not set" });
      return true;
    }
    if (!keyMatches(req.headers["x-admin-api-key"], apiKey)) {
      sendJson(res, 401, { error: "unauthorized" });
      return true;
    }

    const rest = url.pathname.slice(PREFIX.length).split("/").filter(Boolean).map(decodeURIComponent);

    if (rest.length === 0 && req.method === "GET") {
      const users = listUsers.all(new Date().toISOString()).map((u) => ({
        ...u,
        emailVerified: Boolean(u.emailVerified),
        phoneNumberVerified: Boolean(u.phoneNumberVerified),
      }));
      sendJson(res, 200, { users });
      return true;
    }

    const [id, action] = rest;
    const known = id ? getUser.get(id) : undefined;
    const route = `${req.method} ${action ?? ""}`;
    if (!["PATCH ", "DELETE ", "POST revoke-sessions"].includes(route) || rest.length > 2) {
      sendJson(res, 404, { error: "not found" });
      return true;
    }
    if (!known) {
      sendJson(res, 404, { error: "no such user" });
      return true;
    }

    if (route === "PATCH ") {
      let body;
      try {
        body = await readJson(req);
      } catch {
        sendJson(res, 400, { error: "invalid JSON body" });
        return true;
      }
      const { set, error } = parseUpdate(body);
      if (error) {
        sendJson(res, 400, { error });
        return true;
      }
      try {
        updateUser(id, set);
      } catch (err) {
        if (err.code === "SQLITE_CONSTRAINT_UNIQUE") {
          sendJson(res, 409, { error: "email or phone number already belongs to another user" });
          return true;
        }
        throw err;
      }
      sendJson(res, 200, { ok: true });
      return true;
    }

    if (route === "DELETE ") {
      deleteUser(known);
      sendJson(res, 200, { ok: true });
      return true;
    }

    const { changes } = deleteSessions.run(id);
    sendJson(res, 200, { revoked: changes });
    return true;
  };
}

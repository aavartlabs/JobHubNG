import http from "node:http";
import { toNodeHandler } from "better-auth/node";

import { createAdminHandler } from "./admin.js";
import { auth, db, telegramStore } from "./auth.js";
import { createTelegramInternalHandler, ensureTelegramChatIndex } from "./telegram.js";

const PORT = Number(process.env.PORT || 3200);

const authHandler = toNodeHandler(auth);
const adminHandler = createAdminHandler({ db });
const telegramHandler = createTelegramInternalHandler({ store: telegramStore });
// Here, not in auth.js: the migrate CLI imports auth.js before adding the column.
ensureTelegramChatIndex(db);

function sendJson(res, statusCode, body) {
  res.writeHead(statusCode, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

const server = http.createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/health") {
    sendJson(res, 200, { ready: true });
    return;
  }

  // /internal/admin/* -- see src/admin.js for why it is outside /auth/*.
  if (await adminHandler(req, res)) return;
  // /internal/telegram/start -- for telegram-gateway, see src/telegram.js.
  if (await telegramHandler(req, res)) return;

  // Everything else (basePath "/auth/*") is Better Auth's own router --
  // it 404s unmatched paths itself.
  await authHandler(req, res);
});

server.listen(PORT, () => {
  console.log(`[auth-service] listening on :${PORT}`);
});

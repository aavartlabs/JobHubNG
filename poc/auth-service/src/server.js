import http from "node:http";
import { toNodeHandler } from "better-auth/node";

import { auth } from "./auth.js";

const PORT = Number(process.env.PORT || 3200);

const authHandler = toNodeHandler(auth);

function sendJson(res, statusCode, body) {
  res.writeHead(statusCode, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

const server = http.createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/health") {
    sendJson(res, 200, { ready: true });
    return;
  }

  // Everything else (basePath "/auth/*") is Better Auth's own router --
  // it 404s unmatched paths itself.
  await authHandler(req, res);
});

server.listen(PORT, () => {
  console.log(`[auth-service] listening on :${PORT}`);
});

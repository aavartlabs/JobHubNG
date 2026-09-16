import http from "node:http";
import makeWASocket, { useMultiFileAuthState, DisconnectReason } from "baileys";
import qrcodeTerminal from "qrcode-terminal";
import pino from "pino";

import { toJid } from "./jid.js";
import { validateSendPayload } from "./validate.js";

const PORT = Number(process.env.PORT || 3100);
const API_KEY = process.env.WHATSAPP_GATEWAY_API_KEY || "";
const AUTH_DIR = process.env.AUTH_DIR || "./auth_info";

const logger = pino({ level: process.env.LOG_LEVEL || "warn" });

let sock = null;
let isReady = false;

async function connectWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  sock = makeWASocket({ auth: state, logger });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log("\n=== Scan this QR code with WhatsApp > Linked Devices > Link a Device ===\n");
      qrcodeTerminal.generate(qr, { small: true });
      console.log("\n(QR codes expire after ~60s; a new one is generated automatically if it does.)\n");
    }

    if (connection === "open") {
      isReady = true;
      console.log("[whatsapp-sender] connected and ready.");
    }

    if (connection === "close") {
      isReady = false;
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const loggedOut = statusCode === DisconnectReason.loggedOut;
      console.log(
        `[whatsapp-sender] connection closed (status ${statusCode}).`,
        loggedOut ? "Logged out -- delete AUTH_DIR and restart to re-pair." : "Reconnecting..."
      );
      if (!loggedOut) {
        connectWhatsApp().catch((err) => console.error("[whatsapp-sender] reconnect failed:", err));
      }
    }
  });
}

function sendJson(res, statusCode, body) {
  res.writeHead(statusCode, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let raw = "";
    req.on("data", (chunk) => { raw += chunk; });
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

const server = http.createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/health") {
    sendJson(res, 200, { ready: isReady });
    return;
  }

  if (req.method !== "POST" || req.url !== "/send") {
    sendJson(res, 404, { error: "not found" });
    return;
  }

  if (API_KEY && req.headers["x-api-key"] !== API_KEY) {
    sendJson(res, 401, { error: "unauthorized" });
    return;
  }

  let body;
  try {
    body = await readJsonBody(req);
  } catch {
    sendJson(res, 400, { error: "invalid JSON" });
    return;
  }

  const validated = validateSendPayload(body);
  if (!validated.valid) {
    sendJson(res, 400, { error: validated.error });
    return;
  }

  if (!isReady || !sock) {
    sendJson(res, 503, { error: "WhatsApp session not ready -- pair via QR first (see server logs)" });
    return;
  }

  try {
    await sock.sendMessage(toJid(validated.phone), { text: validated.message });
    sendJson(res, 200, { status: "sent" });
  } catch (err) {
    sendJson(res, 502, { error: String(err?.message || err) });
  }
});

connectWhatsApp().catch((err) => {
  console.error("[whatsapp-sender] failed to start WhatsApp connection:", err);
});

server.listen(PORT, () => {
  console.log(`[whatsapp-sender] listening on :${PORT}`);
});

import http from "node:http";
import makeWASocket, { useMultiFileAuthState, DisconnectReason } from "baileys";
import qrcodeTerminal from "qrcode-terminal";
import pino from "pino";

import { toJid } from "./jid.js";
import { validateSendPayload } from "./validate.js";
import { createAckTracker } from "./ack-tracker.js";
import { createSentMessageCache } from "./sent-message-cache.js";

const PORT = Number(process.env.PORT || 3100);
const API_KEY = process.env.WHATSAPP_GATEWAY_API_KEY || "";
const AUTH_DIR = process.env.AUTH_DIR || "./auth_info";
// Kept below the Python WhatsAppNotifier's HTTP timeout (20s) so a real
// timeout here always reaches the caller as a clean error, not a dropped
// connection.
const ACK_TIMEOUT_MS = Number(process.env.ACK_TIMEOUT_MS || 12000);

const logger = pino({ level: process.env.LOG_LEVEL || "warn" });

let sock = null;
let isReady = false;

// Survives across reconnects (connectWhatsApp() re-runs on every drop) --
// declared outside it so in-flight sends aren't orphaned by a socket swap.
const ackTracker = createAckTracker();
const sentMessageCache = createSentMessageCache();

async function connectWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  // Without a real getMessage, baileys can't answer WhatsApp's retry-receipt
  // protocol when a recipient's device fails to decrypt a message on the
  // first try -- the message is then stuck showing "Waiting for this
  // message" on their end, forever, since the retry can never be satisfied.
  sock = makeWASocket({ auth: state, logger, getMessage: sentMessageCache.getMessage });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("messages.update", (updates) => {
    for (const { key, update } of updates) {
      if (typeof update.status === "number" && key?.id) {
        ackTracker.settle(key.id, update.status);
      }
    }
  });

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
    const content = { text: validated.message };
    const sent = await sock.sendMessage(toJid(validated.phone), content);
    const msgId = sent?.key?.id;
    if (!msgId) {
      // No message id to track (shouldn't normally happen) -- report sent
      // but flag that delivery wasn't confirmed, rather than silently
      // claiming a guarantee we can't back up.
      sendJson(res, 200, { status: "sent", confirmed: false });
      return;
    }
    // Must be cached before we can possibly need it for a retry -- do this
    // before awaiting the ack, not after.
    sentMessageCache.remember(msgId, content);
    await ackTracker.waitForAck(msgId, ACK_TIMEOUT_MS);
    sendJson(res, 200, { status: "sent", confirmed: true });
  } catch (err) {
    // Covers both sock.sendMessage() throwing and the ack tracker timing
    // out/erroring -- either way WhatsApp never confirmed this message, so
    // callers must not treat it as delivered.
    sendJson(res, 502, { error: String(err?.message || err) });
  }
});

connectWhatsApp().catch((err) => {
  console.error("[whatsapp-sender] failed to start WhatsApp connection:", err);
});

server.listen(PORT, () => {
  console.log(`[whatsapp-sender] listening on :${PORT}`);
});

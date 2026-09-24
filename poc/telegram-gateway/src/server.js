import http from "node:http";

import { createApp } from "./app.js";
import { createBotApi } from "./bot-api.js";
import { createAuthClient, createHandlers } from "./handlers.js";

const PORT = Number(process.env.PORT || 3300);
const WEBHOOK_URL = process.env.TELEGRAM_WEBHOOK_URL || "";
const WEBHOOK_SECRET = process.env.TELEGRAM_WEBHOOK_SECRET || "";
// What the router handles: messages (commands, text) and inline-button taps.
const ALLOWED_UPDATES = ["message", "callback_query"];

// TELEGRAM_API_BASE: only for local runs against a fake Bot API.
const botApi = createBotApi({
  token: process.env.TELEGRAM_BOT_TOKEN,
  ...(process.env.TELEGRAM_API_BASE ? { baseUrl: process.env.TELEGRAM_API_BASE } : {}),
});
const auth = createAuthClient({
  baseUrl: process.env.AUTH_SERVICE_URL,
  apiKey: process.env.TELEGRAM_INTERNAL_API_KEY,
});
const app = createApp({
  botApi,
  handlers: createHandlers({ auth, siteUrl: process.env.SITE_URL }),
  services: { auth },
  apiKey: process.env.TELEGRAM_GATEWAY_API_KEY || "",
  webhookSecret: WEBHOOK_SECRET,
});

http.createServer(app).listen(PORT, () => {
  console.log(`[telegram-gateway] listening on :${PORT}`);
});

// Registering the webhook on every boot keeps Telegram pointed at the current URL and
// secret. Failing here isn't fatal: /send still works, only inbound messages wait.
if (WEBHOOK_URL && WEBHOOK_SECRET) {
  botApi
    .setWebhook(WEBHOOK_URL, WEBHOOK_SECRET, ALLOWED_UPDATES)
    .then(() => console.log(`[telegram-gateway] webhook set to ${WEBHOOK_URL}`))
    .catch((err) => console.error(`[telegram-gateway] setWebhook failed: ${err.message}`));
} else {
  console.warn("[telegram-gateway] TELEGRAM_WEBHOOK_URL / TELEGRAM_WEBHOOK_SECRET unset: not receiving messages");
}

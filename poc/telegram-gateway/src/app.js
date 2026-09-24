/**
 * The gateway's HTTP API.
 *
 *   GET  /health   -> { ready: true }
 *   POST /send     -> send one message. Header x-api-key. Body { chat_id, text, reply_markup? }.
 *                     200 { status: "sent", message_id } | 410 { error: "blocked" } (the user
 *                     blocked the bot) | 404 { error: "chat_not_found" } | 502/503 otherwise.
 *   POST /webhook  -> Telegram's updates, forwarded by Flask's /telegram/webhook. Header
 *                     X-Telegram-Bot-Api-Secret-Token must equal TELEGRAM_WEBHOOK_SECRET.
 *                     Always 200 once authenticated, even if a handler fails -- anything
 *                     else makes Telegram redeliver the same update over and over.
 */
import crypto from "node:crypto";

import { createRouter, createSeenUpdates, toEvent } from "./router.js";

const MAX_BODY_BYTES = 64 * 1024;
// A 429's retry_after up to this is waited out once; longer is the caller's problem.
const MAX_RETRY_WAIT_SECONDS = 10;

function sendJson(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

function secretMatches(provided, expected) {
  if (!expected) return false;
  const a = Buffer.from(String(provided ?? ""));
  const b = Buffer.from(expected);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let raw = "";
    let tooLarge = false;
    req.on("data", (chunk) => {
      raw += chunk;
      if (raw.length > MAX_BODY_BYTES) tooLarge = true;
    });
    req.on("end", () => {
      if (tooLarge) return reject(new Error("body too large"));
      try {
        resolve(raw ? JSON.parse(raw) : {});
      } catch (err) {
        reject(err);
      }
    });
    req.on("error", reject);
  });
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export function createApp({ botApi, handlers, services = {}, apiKey, webhookSecret, log = console }) {
  const route = createRouter(handlers);
  const firstTime = createSeenUpdates();

  async function send(chatId, text, extra) {
    try {
      return await botApi.sendMessage(chatId, text, extra);
    } catch (err) {
      if (err.status === 429 && err.retryAfter > 0 && err.retryAfter <= MAX_RETRY_WAIT_SECONDS) {
        await sleep(err.retryAfter * 1000);
        return botApi.sendMessage(chatId, text, extra);
      }
      throw err;
    }
  }

  async function handleSend(req, res) {
    if (!apiKey) return sendJson(res, 503, { error: "send disabled: TELEGRAM_GATEWAY_API_KEY is not set" });
    if (!secretMatches(req.headers["x-api-key"], apiKey)) return sendJson(res, 401, { error: "unauthorized" });
    let body;
    try {
      body = await readJson(req);
    } catch {
      return sendJson(res, 400, { error: "invalid JSON body" });
    }
    const chatId = String(body.chat_id ?? "").trim();
    if (!/^-?[0-9]{1,20}$/.test(chatId)) return sendJson(res, 400, { error: "chat_id must be a Telegram chat id" });
    if (typeof body.text !== "string" || !body.text.trim()) return sendJson(res, 400, { error: "text is required" });
    const extra = body.reply_markup && typeof body.reply_markup === "object" ? { reply_markup: body.reply_markup } : {};
    try {
      const sent = await send(chatId, body.text, extra);
      return sendJson(res, 200, { status: "sent", message_id: sent?.message_id ?? null });
    } catch (err) {
      if (err.status === 403) return sendJson(res, 410, { error: "blocked", detail: err.description });
      if (err.status === 400 && /chat not found/i.test(err.description)) {
        return sendJson(res, 404, { error: "chat_not_found" });
      }
      log.error(`[telegram-gateway] send to ${chatId} failed: ${err.message}`);
      return sendJson(res, err.status ? 502 : 503, { error: "send_failed", detail: err.message });
    }
  }

  async function handleWebhook(req, res) {
    if (!secretMatches(req.headers["x-telegram-bot-api-secret-token"], webhookSecret)) {
      return sendJson(res, 401, { error: "unauthorized" });
    }
    let update;
    try {
      update = await readJson(req);
    } catch {
      return sendJson(res, 200, { ok: true }); // unreadable: redelivering it won't help
    }
    const event = toEvent(update);
    if (event && firstTime(event.updateId)) {
      const ctx = {
        services,
        reply: (text, extra) => send(event.chat.id, text, extra),
        answerCallback: (text) => botApi.answerCallbackQuery(event.callbackId, text),
      };
      try {
        await route(event, ctx);
      } catch (err) {
        log.error(`[telegram-gateway] ${event.kind} ${event.command || event.action || ""} failed: ${err.message}`);
        await ctx.reply("Sorry, something went wrong. Please try again in a minute.").catch(() => {});
      }
    }
    return sendJson(res, 200, { ok: true });
  }

  return async function handle(req, res) {
    const path = new URL(req.url, "http://internal").pathname;
    if (req.method === "GET" && path === "/health") return sendJson(res, 200, { ready: true });
    if (req.method === "POST" && path === "/send") return handleSend(req, res);
    if (req.method === "POST" && path === "/webhook") return handleWebhook(req, res);
    return sendJson(res, 404, { error: "not found" });
  };
}

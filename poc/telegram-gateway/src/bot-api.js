/**
 * The few Telegram Bot API methods the gateway uses. The bot token is part of every
 * request URL, so no error from here ever carries the URL: callers log these errors.
 */
export class TelegramError extends Error {
  constructor(message, { status = 0, description = "", retryAfter = 0 } = {}) {
    super(message);
    this.name = "TelegramError";
    this.status = status;
    this.description = description;
    this.retryAfter = retryAfter;
  }
}

// Telegram's own cap on one message's text.
export const MAX_TEXT = 4096;

export function createBotApi({
  token,
  fetchImpl = fetch,
  baseUrl = "https://api.telegram.org",
  timeoutMs = 20000,
}) {
  if (!token) throw new Error("TELEGRAM_BOT_TOKEN is not set");

  async function call(method, params) {
    let res;
    try {
      res = await fetchImpl(`${baseUrl}/bot${token}/${method}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch (err) {
      throw new TelegramError(`Telegram unreachable (${err?.name || "error"})`);
    }
    let body = {};
    try {
      body = await res.json();
    } catch {
      // not JSON: handled as a failure below
    }
    if (!res.ok || !body.ok) {
      const description = String(body.description || "");
      throw new TelegramError(`Telegram ${method} failed: HTTP ${res.status} ${description}`.trim(), {
        status: res.status,
        description,
        retryAfter: Number(body.parameters?.retry_after || 0),
      });
    }
    return body.result;
  }

  return {
    sendMessage(chatId, text, extra = {}) {
      return call("sendMessage", {
        chat_id: chatId,
        text: String(text).slice(0, MAX_TEXT),
        disable_web_page_preview: true,
        ...extra,
      });
    },
    answerCallbackQuery(callbackQueryId, text) {
      return call("answerCallbackQuery", { callback_query_id: callbackQueryId, ...(text ? { text } : {}) });
    },
    setWebhook(url, secretToken, allowedUpdates) {
      return call("setWebhook", { url, secret_token: secretToken, allowed_updates: allowedUpdates });
    },
  };
}

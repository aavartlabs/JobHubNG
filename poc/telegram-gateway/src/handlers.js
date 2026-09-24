/**
 * What the bot does with what users send it. Today: account linking (/start <token> from
 * the site's "Connect Telegram" link) and help. Add new commands or button actions here
 * and register them in `createHandlers`' return value.
 */

export function createHandlers({ auth, siteUrl }) {
  const site = siteUrl || "the JobsHub website";

  const help = async (event, ctx) => {
    await ctx.reply(
      "This is the JobsHub alerts bot.\n\n" +
        `To get job alerts here, sign up at ${site} and connect Telegram when asked. ` +
        `Manage your alerts at ${siteUrl ? `${siteUrl}/alerts` : "the website"}.\n\n` +
        `Your Telegram chat id: ${event.chat.id}`,
    );
  };

  const start = async (event, ctx) => {
    if (!event.args) return help(event, ctx);
    // The payload is the one-time link token the site put in t.me/<bot>?start=<token>.
    // auth-service decides what it means and what to say back (a code, or "expired").
    const { reply } = await auth.telegramStart({
      token: event.args,
      chatId: event.chat.id,
      username: event.chat.username,
      firstName: event.chat.firstName,
    });
    await ctx.reply(reply);
  };

  return {
    commands: { start, help },
    actions: {},
    onText: help,
    onUnknownCommand: help,
  };
}

/** auth-service's internal Telegram API (auth-service/src/telegram.js). */
export function createAuthClient({ baseUrl, apiKey, fetchImpl = fetch, timeoutMs = 10000 }) {
  return {
    async telegramStart(payload) {
      if (!baseUrl || !apiKey) throw new Error("AUTH_SERVICE_URL / TELEGRAM_INTERNAL_API_KEY are not set");
      const res = await fetchImpl(`${baseUrl.replace(/\/+$/, "")}/internal/telegram/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-telegram-internal-key": apiKey },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(timeoutMs),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || typeof body.reply !== "string") {
        throw new Error(`auth-service /internal/telegram/start returned HTTP ${res.status}`);
      }
      return body;
    },
  };
}

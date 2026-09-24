# telegram-gateway

The one place JobsHub talks to Telegram. It holds the bot token; nothing else does.

- **Out:** `POST /send` (`x-api-key`), `{chat_id, text, reply_markup?}`. Alert digests,
  admin messages and account-linking codes all go through it. `410 blocked` means the
  user blocked the bot; `404 chat_not_found` means the chat id is wrong.
- **In:** Telegram posts updates to `https://<site>/telegram/webhook`; Flask forwards the
  raw body and the `X-Telegram-Bot-Api-Secret-Token` header to `POST /webhook` here, which
  checks the secret. The webhook is (re)registered with Telegram on every boot from
  `TELEGRAM_WEBHOOK_URL` + `TELEGRAM_WEBHOOK_SECRET`, so `getUpdates` no longer works for
  this bot.

## Handling what users send

`src/router.js` turns an update into one event (`command`, `text` or `callback` for an
inline-button tap with `callback_data` `"<action>:<arg>"`); `src/handlers.js` says what
happens. To add behaviour, add a command or an action there -- a handler gets
`(event, ctx)` with `ctx.reply(text, extra?)`, `ctx.answerCallback(text)` and
`ctx.services`. Only private chats are handled.

Today: `/start <token>` (from the site's "Connect Telegram" link) asks auth-service
(`/internal/telegram/start`) for the reply -- a 6-digit code, or "that link expired";
`/start`, `/help` or any text get help, including the user's chat id.

## Run and test

```bash
npm test                 # no network: fake bot API, fake auth-service
npm start                # needs the env in .env.example
```

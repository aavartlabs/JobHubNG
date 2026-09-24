# jobhub-auth-service

A small Node service (no framework, just `node:http`) that wraps
[Better Auth](https://www.better-auth.com) to provide real self-service
accounts -- email + password, with the email verified via OTP and Telegram
linked by a code the bot sends -- for JobHubNG. This replaces the single shared
demo login. It's a sibling of `poc/telegram-gateway/`, not part of the Flask app: Better Auth is
TypeScript-only, so this had to be its own Node service, called over HTTP by
the Flask app (a separate task) rather than embedded.

Own SQLite database (`auth.db`), separate from the Flask app's `jobhub.db`.
Own user table with `telegramChatId`/`telegramUsername`/`telegramVerified`
columns (added by this service's own Better Auth plugin, `src/telegram.js`).
Databases from before 2026-09-24 also still have `phoneNumber` /
`phoneNumberVerified` from the removed `phoneNumber` plugin (WhatsApp OTP);
nothing reads them. The Flask app's own user/session concepts are untouched
by this service.

## Where "email verified *and* Telegram linked" is enforced

**Not here.** This service will happily issue a session to a user who has
verified neither. The single enforcement point is the Flask app's
`login_required` (`poc/jobhub_poc/webapp/auth.py`), which checks
`emailVerified` **and** `telegramVerified` on the `get-session` response
of every gated request and redirects to `/verify` if either is false --
regardless of session state, so there is no window it misses.

An earlier version of this service also gated `POST /auth/sign-in/email` on
both flags, as belt-and-suspenders. That was removed: it permanently bricked
any account whose owner lost the post-signup session before finishing
verification (closed the tab, logged out, let it expire). Such a user could
not sign back in to resume -- the gate refused them -- and could not
re-register either, because the email already existed
(`USER_ALREADY_EXISTS_USE_ANOTHER_EMAIL`). The gate covered no attack
surface Flask's own check misses, since Flask is the only consumer of these
sessions (the Cloudflare Tunnel's ingress is fixed to `jobhub-web`, so
nothing else can reach this service at all), and it cost real accounts.

Note the corollary: an unverified user's session is real but useless -- the
only thing it can do is complete verification. If some future consumer ever
reads these sessions directly instead of going through Flask, it needs its
own equivalent check.

## Rate limiting

`src/auth.js` sets `rateLimit.enabled: true` explicitly rather than relying
on Better Auth's default (`enabled: isProduction`), because these endpoints
send real emails to unauthenticated, caller-supplied recipients -- "on
unless NODE_ENV says otherwise" is not a safe default to inherit. Limits are
per (client IP, path) over a rolling window: 5/60s on the email OTP *send*
endpoint and on `/telegram/link`, 10/60s on the verify endpoints and
sign-in, 5/60s on sign-up, and a deliberately generous 120/60s
global fallback (`/get-session` is hit once per gated Flask request, so a
tight global limit would throttle ordinary logged-in browsing rather than
abuse).

The client IP comes from `X-Forwarded-For`. Flask **strips** any inbound
`X-Forwarded-For`/`X-Real-IP`/`Forwarded` and sets a single value it derives
itself (`auth_proxy.py`, `auth.client_ip()`) -- otherwise a caller could
hand themselves a fresh bucket per request just by varying the header.

## API surface

Everything under `/auth/*` is Better Auth's own router (mounted via
`toNodeHandler`, `basePath: "/auth"`); this file lists only the paths this
project actually uses. `GET /health` is this service's own, not Better
Auth's.

- `GET /health` -> `{"ready": true}`
- `POST /auth/sign-up/email` `{email, password, name, ...}` -> `200` with a
  session cookie set and `{token, user}` in the body.
- `POST /auth/sign-in/email` `{email, password}` -> `200` with a session
  cookie, whether or not the user is verified (see above -- Flask, not this
  service, is the verification gate).
- `POST /auth/sign-out` -> `200 {"success": true}`, clears the session
  cookie. Requires a matching `Origin` header -- see below.
- `GET /auth/get-session` -> `{"session": {...}, "user": {...}}` when the
  request's cookie is a valid session, or literal `null` otherwise.
- `POST /auth/email-otp/send-verification-otp` `{email, type:
  "email-verification"}` -> `200 {"success": true}`. Triggers
  `src/email.js`'s `sendEmailOTP`.
- `POST /auth/email-otp/verify-email` `{email, otp}` -> `200` with the
  updated user (`emailVerified: true`) on success.
- `POST /auth/telegram/link` (session) -> `200 {"url":
  "https://t.me/<bot>?start=<token>"}`, a one-time link valid 15 minutes;
  only the newest one works. `TELEGRAM_BOT_USERNAME` names the bot.
- `POST /auth/telegram/verify` (session) `{code}` -> `200 {"status": true}`
  and the user's `telegramChatId`/`telegramUsername`/`telegramVerified` set;
  `400` with `code` `INVALID_CODE`, `CODE_EXPIRED`, `TOO_MANY_ATTEMPTS` (5) or
  `TELEGRAM_IN_USE` (that chat already belongs to another account; the message
  names it by masked email, e.g. `so•••@example.org`). A chat that's already
  linked elsewhere is caught earlier too: `/start` gets that message instead of
  a code. The database backs this with a partial unique index on
  `telegramChatId`, created at startup by `ensureTelegramChatIndex`.
- `POST /internal/telegram/start` -- **not** under `/auth/*`, so Flask's
  proxy can't reach it; only `telegram-gateway` calls it, with header
  `x-telegram-internal-key` = `TELEGRAM_INTERNAL_API_KEY`. `{token, chatId,
  username}` -> `200 {"reply": "..."}`: the text the bot sends back -- a
  6-digit code (10 minutes) bound to the link's user and that chat, or "that
  link expired". The code has to be typed back into the site under the same
  session, so forwarding someone a link can't attach their Telegram to your
  account.

The full session cookie name and `get-session` shape actually observed
during this task's manual verification are in the task report, not
duplicated here since they depend on `advanced.cookiePrefix` in
`src/auth.js`, which is the source of truth if it ever changes.

### Cookie-bearing `POST` requests need a matching `Origin` header

Better Auth's CSRF protection requires a valid `Origin` (or `Referer`)
header, checked against `TRUSTED_ORIGINS`, on any `POST` request that
carries the session cookie (confirmed for `/sign-out` and
`/telegram/verify`; `GET`
requests and cookie-less `POST`s like `/sign-up/email` are exempt). Browsers
send `Origin` automatically; a server-to-server caller (e.g. the Flask app)
must set it explicitly to a value listed in `TRUSTED_ORIGINS`, or these
calls fail with `403 MISSING_OR_NULL_ORIGIN`.

### The exact session cookie name depends on how this is reached

`advanced.cookiePrefix: "jobhub-auth"` in `src/auth.js` names the cookie
`jobhub-auth.session_token` -- but Better Auth prepends `__Secure-` to that
name (and sets the `Secure` attribute) whenever it treats the connection as
secure, making the real name `__Secure-jobhub-auth.session_token`. With
`BETTER_AUTH_URL` set -- which it always must be, see `.env.example` -- that
decision follows **that URL's scheme**, not `NODE_ENV`: an `https://` value
gives the prefixed name, an `http://` value the plain one, even with
`NODE_ENV=production` (which the Dockerfile sets). Confirmed by running this
service directly. This isn't something `src/auth.js` controls; whatever
consumes this cookie needs to match on how the service is actually reached
in that environment, which is why `poc/jobhub_poc/webapp/auth.py` checks
both names.

## Awaiting OTP sends is intentional

Better Auth's own docs recommend firing OTP emails without awaiting them, to
avoid timing attacks that could reveal whether an email is registered.
`src/email.js`'s `sendEmailOTP` deliberately does the opposite -- it awaits
the send and throws on failure, so a failed send is a clear error, not a
silent stuck state. Note that Better Auth's own `email-otp` plugin still
swallows (logs, doesn't propagate) a thrown error from
`send-verification-otp`'s HTTP response either way (its
`runInBackgroundOrAwait` always catches).

## One-time setup: Resend domain verification

`sendEmailOTP` (`src/email.js`) sends via [Resend](https://resend.com).
Resend requires the sending domain (whatever `RESEND_FROM_EMAIL`'s domain
is) to be verified in the Resend dashboard (SPF/DKIM DNS records) before it
will deliver mail from that address -- this is a one-time manual setup step
outside this repo, not something this service can do for you. Until that's
done (and a real `RESEND_API_KEY` exists), don't point this at production;
local dev and automated tests never make a real Resend call (see below).

## Local development

```bash
npm install
npm test          # unit tests -- mocked Resend client, Telegram linking against in-memory SQLite; no real network sends
npm start          # boots the real service on $PORT (default 3200)
```

`npm test` never sends a real email or Telegram message: `test/email.test.js`
injects a fake Resend client via `createEmailOTPSender`, and
`test/telegram.test.js` drives the linking store and the internal endpoint
against an in-memory SQLite database.

Before `npm start` will work against a fresh `AUTH_DB_PATH`, apply Better
Auth's schema migrations once:

```bash
npx --yes @better-auth/cli@1.4.21 migrate --yes
```

(`@better-auth/cli` is deliberately not a `package.json` dependency --
`better-auth`, `better-sqlite3`, `resend` are the only three this brief
calls for -- so it's invoked via `npx` here and baked into the Docker image
at build time instead of installed locally.)

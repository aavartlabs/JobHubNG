# jobhub-auth-service

A small Node service (no framework, just `node:http`) that wraps
[Better Auth](https://www.better-auth.com) to provide real self-service
accounts -- email + password, with both email and mobile verified via OTP --
for JobHubNG. This replaces the single shared demo login. It's a sibling of
`poc/whatsapp-sender/`, not part of the Flask app: Better Auth is
TypeScript-only, so this had to be its own Node service, called over HTTP by
the Flask app (a separate task) rather than embedded.

Own SQLite database (`auth.db`), separate from the Flask app's `jobhub.db`.
Own user table with `phoneNumber`/`phoneNumberVerified` columns (added by
Better Auth's `phoneNumber` plugin); the Flask app's own user/session
concepts are untouched by this service.

## Why both email *and* phone must be verified

Sign-in (`POST /auth/sign-in/email`) is blocked by `src/hooks.js` unless the
target user's `emailVerified` **and** `phoneNumberVerified` are both `true`.
This is belt-and-suspenders, not the only gate: Better Auth's
`emailAndPassword.autoSignIn` (on by default) means a brand-new user already
holds a session immediately after `POST /auth/sign-up/email`, before either
flag is set -- that session is what lets `phoneNumber.verify` attach a
verified phone number to it. The hook can't (and doesn't try to) block that
initial post-signup session; it only blocks *re*-authentication once that
session expires or the user logs out. The Flask app's own `login_required`
(a separate task) is what closes the remaining gap by checking both flags on
every gated request, not just at sign-in.

## API surface

Everything under `/auth/*` is Better Auth's own router (mounted via
`toNodeHandler`, `basePath: "/auth"`); this file lists only the paths this
project actually uses. `GET /health` is this service's own, not Better
Auth's.

- `GET /health` -> `{"ready": true}`
- `POST /auth/sign-up/email` `{email, password, name, ...}` -> `200` with a
  session cookie set and `{token, user}` in the body. **Don't pass
  `phoneNumber` here** -- see the "phone verification" note below.
- `POST /auth/sign-in/email` `{email, password}` -> `200` with a session
  cookie once both verification flags are `true`; `403
  EMAIL_AND_PHONE_VERIFICATION_REQUIRED` otherwise (see `src/hooks.js`).
- `POST /auth/sign-out` -> `200 {"success": true}`, clears the session
  cookie. Requires a matching `Origin` header -- see below.
- `GET /auth/get-session` -> `{"session": {...}, "user": {...}}` when the
  request's cookie is a valid session, or literal `null` otherwise.
- `POST /auth/email-otp/send-verification-otp` `{email, type:
  "email-verification"}` -> `200 {"success": true}`. Triggers
  `src/email.js`'s `sendEmailOTP`.
- `POST /auth/email-otp/verify-email` `{email, otp}` -> `200` with the
  updated user (`emailVerified: true`) on success.
- `POST /auth/phone-number/send-otp` `{phoneNumber}` -> `200 {"message":
  "code sent"}`. Triggers `src/phone.js`'s `sendPhoneOTP`.
- `POST /auth/phone-number/verify` `{phoneNumber, code, updatePhoneNumber:
  true}` -> `200` with the updated user (`phoneNumberVerified: true`) on
  success. **`updatePhoneNumber: true` and an active (cookie-bearing)
  session are both required** -- see below.

The full session cookie name and `get-session` shape actually observed
during this task's manual verification are in the task report, not
duplicated here since they depend on `advanced.cookiePrefix` in
`src/auth.js`, which is the source of truth if it ever changes.

### Phone verification only works if `phoneNumber` was *not* set at sign-up

`POST /auth/phone-number/verify` with `updatePhoneNumber: true` refuses to
attach a phone number that "already exists" on *any* user -- including the
current session's own user. If `phoneNumber` was already passed at
`/sign-up/email` time (Better Auth accepts it there, since the plugin adds
it as an unverified additional field), verification for that same number
will always fail with `400 PHONE_NUMBER_EXIST`, confirmed while testing this
service. Collect the phone number as a separate step after sign-up, then
verify it with `send-otp` + `verify`.

### Cookie-bearing `POST` requests need a matching `Origin` header

Better Auth's CSRF protection requires a valid `Origin` (or `Referer`)
header, checked against `TRUSTED_ORIGINS`, on any `POST` request that
carries the session cookie (confirmed for `/sign-out` and
`/phone-number/verify` during this task's manual verification; `GET`
requests and cookie-less `POST`s like `/sign-up/email` are exempt). Browsers
send `Origin` automatically; a server-to-server caller (e.g. the Flask app)
must set it explicitly to a value listed in `TRUSTED_ORIGINS`, or these
calls fail with `403 MISSING_OR_NULL_ORIGIN`.

### The exact session cookie name depends on how this is reached

`advanced.cookiePrefix: "jobhub-auth"` in `src/auth.js` names the cookie
`jobhub-auth.session_token` -- but Better Auth prepends `__Secure-` to that
name whenever the connection is treated as secure (an `https://` `BETTER_AUTH_URL`,
or `NODE_ENV=production`), making the real name
`__Secure-jobhub-auth.session_token`. This isn't something `src/auth.js`
controls directly; whatever consumes this cookie needs to match on how the
service is actually being reached in that environment.

## Awaiting OTP sends is intentional

Better Auth's own docs recommend firing OTP emails without awaiting them, to
avoid timing attacks that could reveal whether an email/phone number is
registered. `src/email.js`'s `sendEmailOTP` and `src/phone.js`'s
`sendPhoneOTP` deliberately do the opposite -- they await the send and throw
on failure. This project has a demonstrated real OTP-delivery failure mode
on the sibling WhatsApp gateway (see `tasks_all.md`'s T8): a failed send
must surface as a clear error, not a silent stuck state. Note that Better
Auth's own `email-otp` plugin still swallows (logs, doesn't propagate) a
thrown error from `send-verification-otp`'s HTTP response either way (its
`runInBackgroundOrAwait` always catches); the `phone-number` plugin's
`send-otp` does propagate a thrown error as an HTTP failure. See the task
report for the exact behavior confirmed for each.

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
npm test          # unit tests -- mocked Resend client, a local http stub standing in for whatsapp-sender; no real network sends
npm start          # boots the real service on $PORT (default 3200)
```

`npm test` never sends a real email or WhatsApp message: `test/email.test.js`
injects a fake Resend client via `createEmailOTPSender`, and
`test/phone.test.js` points `createPhoneOTPSender` at a local
`http.createServer` stub standing in for `whatsapp-sender`'s `/send`.

Before `npm start` will work against a fresh `AUTH_DB_PATH`, apply Better
Auth's schema migrations once:

```bash
npx --yes @better-auth/cli@1.4.21 migrate --yes
```

(`@better-auth/cli` is deliberately not a `package.json` dependency --
`better-auth`, `better-sqlite3`, `resend` are the only three this brief
calls for -- so it's invoked via `npx` here and baked into the Docker image
at build time instead of installed locally.)

# jobhub-whatsapp-sender

A small, hand-rolled Node service (no framework) that holds a WhatsApp Web
session via [baileys](https://www.npmjs.com/package/baileys) and exposes one
endpoint for sending a text message. This is what `WhatsAppNotifier` in
`jobhub_poc/alerts/notifier.py` calls when `NOTIFIER_BACKEND=whatsapp`.

Deliberately minimal: no REST framework, no database, no inbound message
handling, no group/contact management -- just enough to send outbound alert
texts. Baileys is pinned to `6.7.24` (the `legacy` npm dist-tag), not the
`7.0.0-rc*` release candidate, for reliability in a long-running session.

## API

- `GET /health` -> `{"ready": true|false}` -- whether the WhatsApp session is
  currently connected and able to send.
- `POST /send` (header `x-api-key: <WHATSAPP_GATEWAY_API_KEY>`, JSON body
  `{"phone": "+15551234567", "message": "..."}`) -> `200 {"status": "sent"}`
  on success, `503` if the session isn't paired/ready yet, `400` for a
  malformed request, `401` for a missing/wrong API key.

## One-time pairing (cannot be automated)

WhatsApp's Linked Devices flow requires scanning a QR code with the actual
phone that owns the number being paired. This is a deliberate design of
WhatsApp's own security model -- there is no way to script around it.

**Use a number you're willing to dedicate to this, not your personal or
business WhatsApp** -- the unofficial API this is built on isn't sanctioned
by WhatsApp, and automated sending can get an account flagged or
temporarily banned. Never run two independent deployments against the same
number; a second login will silently kick the first one.

1. Deploy the service (see below) and watch its logs:
   `docker logs -f jobhub-whatsapp`
2. A QR code renders directly in the log output. On the phone with the
   number you're dedicating: WhatsApp -> Settings -> Linked Devices ->
   Link a Device -> scan it.
3. Logs show `[whatsapp-sender] connected and ready.` once paired.
   `GET /health` now returns `{"ready": true}`.
4. The session is persisted to `AUTH_DIR` (bind-mounted outside the
   container, see `docker-compose.yml`), so restarts don't require
   re-pairing -- only an explicit logout does.
5. Switch the main app over by setting `NOTIFIER_BACKEND=whatsapp` in
   `~/jobhub-poc/.env` on pi09 (it's `console` until you do this on
   purpose). No code or container restart needed for the main app --
   `run_alerts.py` reads `NOTIFIER_BACKEND` fresh on every invocation.

## Local development

```bash
npm install
npm test          # pure-logic tests (jid formatting, payload validation) -- no live WhatsApp needed
npm start          # boots the real service, prints a QR to the terminal
```

import { APIError } from "better-auth/api";

const SENT_STATUS = "sent";
// whatsapp-sender's answer when the number has no WhatsApp account (src/server.js).
const NOT_ON_WHATSAPP = "not_on_whatsapp";
const E164 = /^\+[1-9][0-9]{6,14}$/;

/**
 * "+", a country code that never starts with 0, 7-15 digits in all (E.164) --
 * Better Auth's phoneNumberValidator, so a malformed number is a 400 before any
 * WhatsApp send. Same rule as the frontend's normalizePhone and Flask's
 * normalize_e164; the browser strips spaces/dashes before it gets here.
 */
export function isValidPhoneNumber(phoneNumber) {
  return typeof phoneNumber === "string" && E164.test(phoneNumber);
}

/**
 * Builds a `sendPhoneOTP(phoneNumber, code)` function bound to a
 * whatsapp-sender gateway URL/key. Mirrors
 * `jobhub_poc/alerts/notifier.py`'s `WhatsAppNotifier._deliver()` request
 * contract exactly: same gateway, same `POST {gatewayUrl}/send` shape, same
 * `x-api-key` header (sent only when a key is configured, matching that
 * Python code) -- so a single whatsapp-sender deployment serves both the
 * job-alert notifier and this OTP path unmodified.
 *
 * Stricter than notifier.py on the response side: that code only checks the
 * HTTP status code, but this also requires the JSON body's `status` field to
 * be `"sent"` (per this task's brief), since a wrong/missing body would
 * otherwise look like a delivered OTP.
 */
export function createPhoneOTPSender({
  gatewayUrl = process.env.WHATSAPP_GATEWAY_URL,
  apiKey = process.env.WHATSAPP_GATEWAY_API_KEY,
} = {}) {
  return async function sendPhoneOTP(phoneNumber, code) {
    if (!gatewayUrl) {
      throw new Error("WHATSAPP_GATEWAY_URL is not configured");
    }

    const message = `Your JobsHub verification code is ${code}.`;
    const headers = { "Content-Type": "application/json" };
    if (apiKey) {
      headers["x-api-key"] = apiKey;
    }

    const res = await fetch(`${gatewayUrl.replace(/\/+$/, "")}/send`, {
      method: "POST",
      headers,
      body: JSON.stringify({ phone: phoneNumber, message }),
    });

    let body = null;
    try {
      body = await res.json();
    } catch {
      // non-JSON or empty body -- treated as a failure below
    }

    if (body?.error === NOT_ON_WHATSAPP) {
      // The person's fault to fix, not a server failure: surface it as a 400 with a
      // message the verify page can show, instead of Better Auth's generic 500.
      throw APIError.from("BAD_REQUEST", {
        code: "NOT_ON_WHATSAPP",
        message: "That number isn't on WhatsApp. Check the country code and number.",
      });
    }
    if (!res.ok || body?.status !== SENT_STATUS) {
      const detail = body?.error ? `: ${body.error}` : "";
      throw new Error(`WhatsApp gateway did not confirm the OTP send (HTTP ${res.status}${detail})`);
    }
  };
}

export const sendPhoneOTP = createPhoneOTPSender();

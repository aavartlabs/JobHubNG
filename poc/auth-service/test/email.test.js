import { test } from "node:test";
import assert from "node:assert/strict";
import { createEmailOTPSender } from "../src/email.js";

function fakeResendClient({ error = null, data = { id: "email_123" } } = {}) {
  const calls = [];
  return {
    calls,
    emails: {
      send: async (payload) => {
        calls.push(payload);
        return error ? { data: null, error } : { data, error: null };
      },
    },
  };
}

test("resolves on a successful send", async () => {
  const client = fakeResendClient();
  const sendEmailOTP = createEmailOTPSender({ fromEmail: "noreply@jobhubng.test", client });
  await assert.doesNotReject(sendEmailOTP("user@example.com", "123456", "sign-in"));
  assert.equal(client.calls.length, 1);
});

test("sends the OTP-bearing message to the given recipient", async () => {
  const client = fakeResendClient();
  const sendEmailOTP = createEmailOTPSender({ fromEmail: "noreply@jobhubng.test", client });
  await sendEmailOTP("user@example.com", "654321", "email-verification");
  const [payload] = client.calls;
  assert.equal(payload.to, "user@example.com");
  assert.equal(payload.from, "noreply@jobhubng.test");
  assert.match(payload.text, /654321/);
});

test("throws when Resend returns an error response", async () => {
  const client = fakeResendClient({ error: { message: "domain not verified", statusCode: 403, name: "validation_error" } });
  const sendEmailOTP = createEmailOTPSender({ fromEmail: "noreply@jobhubng.test", client });
  await assert.rejects(sendEmailOTP("user@example.com", "123456", "sign-in"), /domain not verified/);
});

test("throws when RESEND_FROM_EMAIL is not configured, without calling Resend", async () => {
  const client = fakeResendClient();
  const sendEmailOTP = createEmailOTPSender({ fromEmail: "", client });
  await assert.rejects(sendEmailOTP("user@example.com", "123456", "sign-in"));
  assert.equal(client.calls.length, 0);
});

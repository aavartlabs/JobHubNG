import { test } from "node:test";
import assert from "node:assert/strict";
import { validateSendPayload } from "../src/validate.js";

test("valid payload passes", () => {
  const result = validateSendPayload({ phone: "+15551234567", message: "Hello" });
  assert.equal(result.valid, true);
});

test("missing phone is rejected", () => {
  const result = validateSendPayload({ message: "Hello" });
  assert.equal(result.valid, false);
  assert.match(result.error, /phone/);
});

test("missing message is rejected", () => {
  const result = validateSendPayload({ phone: "+15551234567" });
  assert.equal(result.valid, false);
  assert.match(result.error, /message/);
});

test("empty string message is rejected", () => {
  const result = validateSendPayload({ phone: "+15551234567", message: "   " });
  assert.equal(result.valid, false);
});

test("phone with too few digits is rejected", () => {
  const result = validateSendPayload({ phone: "12345", message: "Hello" });
  assert.equal(result.valid, false);
  assert.match(result.error, /valid number/);
});

test("non-object body is rejected", () => {
  const result = validateSendPayload(null);
  assert.equal(result.valid, false);
});

test("a country code starting with 0 is rejected (no such WhatsApp number exists)", () => {
  for (const phone of ["+019902065845", "019902065845"]) {
    const result = validateSendPayload({ phone, message: "Hello" });
    assert.equal(result.valid, false, phone);
  }
});

test("letters in the phone are rejected rather than silently stripped", () => {
  assert.equal(validateSendPayload({ phone: "+1555CALLNOW1", message: "Hello" }).valid, false);
});

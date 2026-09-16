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

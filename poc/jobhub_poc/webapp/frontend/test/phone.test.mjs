import { test } from "node:test";
import assert from "node:assert/strict";

import { normalizePhone } from "../src/phone.ts";

test("accepts international format and strips separators", () => {
  assert.deepEqual(normalizePhone("+91 99020 65845"), { ok: true, phone: "+919902065845" });
  assert.deepEqual(normalizePhone(" +1 (555) 123-4567 "), { ok: true, phone: "+15551234567" });
  assert.deepEqual(normalizePhone("+44.20.7946.0958"), { ok: true, phone: "+442079460958" });
});

test("rejects a number without a leading + country code", () => {
  // A bare national number would be read as some other country's number.
  for (const input of ["9902065845", "09902065845", "919902065845"]) {
    assert.equal(normalizePhone(input).ok, false, input);
  }
});

test("rejects a country code starting with 0 (the 2026-09-23 '+01...' OTP failure)", () => {
  assert.equal(normalizePhone("+019902065845").ok, false);
  assert.equal(normalizePhone("+0 9902065845").ok, false);
});

test("rejects too short, too long, letters and empty input", () => {
  for (const input of ["", "   ", "+1234", "+1234567890123456", "+91 99020 6584x", "+", "++919902065845"]) {
    assert.equal(normalizePhone(input).ok, false, JSON.stringify(input));
  }
});

test("every rejection carries a message a person can act on", () => {
  const result = normalizePhone("9902065845");
  assert.equal(result.ok, false);
  assert.match(result.error, /country code/i);
});

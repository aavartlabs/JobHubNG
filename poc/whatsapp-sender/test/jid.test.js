import { test } from "node:test";
import assert from "node:assert/strict";
import { toJid } from "../src/jid.js";

test("strips formatting characters and appends the whatsapp suffix", () => {
  assert.equal(toJid("+1 (555) 123-4567"), "15551234567@s.whatsapp.net");
});

test("passes through digits-only input unchanged", () => {
  assert.equal(toJid("919876543210"), "919876543210@s.whatsapp.net");
});

test("handles numeric input (not just strings)", () => {
  assert.equal(toJid(15551234567), "15551234567@s.whatsapp.net");
});

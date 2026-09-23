import { test } from "node:test";
import assert from "node:assert/strict";

import { isOnWhatsApp } from "../src/registered.js";

// Stand-in for Baileys' sock.onWhatsApp: it returns entries only for jids that
// have an account (it filters on `contact`), so "not on WhatsApp" is an empty list.
function fakeSock(result) {
  const calls = [];
  return {
    calls,
    async onWhatsApp(...jids) {
      calls.push(jids);
      if (result instanceof Error) throw result;
      return result;
    },
  };
}

test("true when WhatsApp reports the jid exists", async () => {
  const sock = fakeSock([{ jid: "15551234567@s.whatsapp.net", exists: true }]);
  assert.equal(await isOnWhatsApp(sock, "15551234567@s.whatsapp.net"), true);
  assert.deepEqual(sock.calls, [["15551234567@s.whatsapp.net"]]);
});

test("false for an empty or missing result", async () => {
  assert.equal(await isOnWhatsApp(fakeSock([]), "1@s.whatsapp.net"), false);
  assert.equal(await isOnWhatsApp(fakeSock(undefined), "1@s.whatsapp.net"), false);
  assert.equal(await isOnWhatsApp(fakeSock([{ jid: "x", exists: false }]), "1@s.whatsapp.net"), false);
});

test("propagates lookup failures instead of guessing either way", async () => {
  await assert.rejects(isOnWhatsApp(fakeSock(new Error("usync timeout")), "1@s.whatsapp.net"), /usync timeout/);
});

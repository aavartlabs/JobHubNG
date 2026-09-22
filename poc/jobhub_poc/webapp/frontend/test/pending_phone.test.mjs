import { test } from "node:test";
import assert from "node:assert/strict";

import {
  PENDING_PHONE_KEY,
  clearPendingPhone,
  readPendingPhone,
  resolvePhoneNumber,
  savePendingPhone,
} from "../src/pending_phone.ts";

/** Minimal stand-in for sessionStorage -- no DOM needed. */
function fakeStorage(initial = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: (key) => (key in data ? data[key] : null),
    setItem: (key, value) => {
      data[key] = String(value);
    },
    removeItem: (key) => {
      delete data[key];
    },
  };
}

/** Stands in for a browser that refuses storage access entirely (private mode, etc.). */
function throwingStorage() {
  return {
    getItem() {
      throw new DOMExceptionLike();
    },
    setItem() {
      throw new DOMExceptionLike();
    },
    removeItem() {
      throw new DOMExceptionLike();
    },
  };
}

class DOMExceptionLike extends Error {
  constructor() {
    super("SecurityError: storage access denied");
  }
}

test("prefers the phone number already on the account over anything stashed", () => {
  const storage = fakeStorage({ [PENDING_PHONE_KEY]: "+15550000000" });
  assert.equal(resolvePhoneNumber("+15551234567", storage), "+15551234567");
});

test("falls back to the stashed number when the account has none yet", () => {
  // The real post-registration case: send-otp does not write phoneNumber to the user
  // row, so get-session reports null right up until verification succeeds.
  const storage = fakeStorage({ [PENDING_PHONE_KEY]: "+15551234567" });
  assert.equal(resolvePhoneNumber(null, storage), "+15551234567");
  assert.equal(resolvePhoneNumber(undefined, storage), "+15551234567");
  assert.equal(resolvePhoneNumber("", storage), "+15551234567");
});

test("resolves to empty when neither source has a number", () => {
  assert.equal(resolvePhoneNumber(null, fakeStorage()), "");
  assert.equal(resolvePhoneNumber(null, null), "");
});

test("treats a whitespace-only value from either source as absent", () => {
  assert.equal(resolvePhoneNumber("   ", fakeStorage({ [PENDING_PHONE_KEY]: "  " })), "");
  assert.equal(resolvePhoneNumber("   ", fakeStorage({ [PENDING_PHONE_KEY]: "+15551234567" })), "+15551234567");
});

test("trims surrounding whitespace from a resolved number", () => {
  assert.equal(resolvePhoneNumber(" +15551234567 ", null), "+15551234567");
  assert.equal(resolvePhoneNumber(null, fakeStorage({ [PENDING_PHONE_KEY]: " +15551234567 " })), "+15551234567");
});

test("save then resolve round-trips the registration number", () => {
  const storage = fakeStorage();
  savePendingPhone(storage, " +919902065845 ");
  assert.equal(storage.data[PENDING_PHONE_KEY], "+919902065845");
  assert.equal(resolvePhoneNumber(null, storage), "+919902065845");
});

test("saving a blank number clears the key rather than storing an empty string", () => {
  const storage = fakeStorage({ [PENDING_PHONE_KEY]: "+15551234567" });
  savePendingPhone(storage, "   ");
  assert.equal(PENDING_PHONE_KEY in storage.data, false);
  assert.equal(readPendingPhone(storage), "");
});

test("clearing removes the stash, so a later visit resolves to empty", () => {
  const storage = fakeStorage({ [PENDING_PHONE_KEY]: "+15551234567" });
  clearPendingPhone(storage);
  assert.equal(PENDING_PHONE_KEY in storage.data, false);
  assert.equal(resolvePhoneNumber(null, storage), "");
});

test("a storage that throws on every access degrades to empty, never propagates", () => {
  const storage = throwingStorage();
  assert.equal(readPendingPhone(storage), "");
  assert.equal(resolvePhoneNumber(null, storage), "");
  assert.doesNotThrow(() => savePendingPhone(storage, "+15551234567"));
  assert.doesNotThrow(() => clearPendingPhone(storage));
});

test("a null storage is accepted everywhere without throwing", () => {
  assert.equal(readPendingPhone(null), "");
  assert.doesNotThrow(() => savePendingPhone(null, "+15551234567"));
  assert.doesNotThrow(() => clearPendingPhone(null));
});

import { test } from "node:test";
import assert from "node:assert/strict";
import { requireVerifiedForSignIn } from "../src/hooks.js";

function fakeCtx({ path, email, user }) {
  return {
    path,
    body: email === undefined ? {} : { email },
    context: {
      internalAdapter: {
        findUserByEmail: async () => (user ? { user, accounts: [] } : null),
      },
    },
  };
}

test("throws for a user who hasn't verified both email and phone", async () => {
  const ctx = fakeCtx({
    path: "/sign-in/email",
    email: "unverified@example.com",
    user: { emailVerified: true, phoneNumberVerified: false },
  });
  await assert.rejects(requireVerifiedForSignIn(ctx));
});

test("throws for a user who has verified neither", async () => {
  const ctx = fakeCtx({
    path: "/sign-in/email",
    email: "brandnew@example.com",
    user: { emailVerified: false, phoneNumberVerified: false },
  });
  await assert.rejects(requireVerifiedForSignIn(ctx));
});

test("does not throw for a fully verified user", async () => {
  const ctx = fakeCtx({
    path: "/sign-in/email",
    email: "verified@example.com",
    user: { emailVerified: true, phoneNumberVerified: true },
  });
  await assert.doesNotReject(requireVerifiedForSignIn(ctx));
});

test("does not throw for a path other than /sign-in/email, even for an unverified user", async () => {
  const ctx = fakeCtx({
    path: "/sign-up/email",
    email: "brandnew@example.com",
    user: { emailVerified: false, phoneNumberVerified: false },
  });
  await assert.doesNotReject(requireVerifiedForSignIn(ctx));
});

test("does not throw (and does not look up a user) when the body has no email", async () => {
  const ctx = fakeCtx({ path: "/sign-in/email", email: undefined, user: null });
  await assert.doesNotReject(requireVerifiedForSignIn(ctx));
});

test("does not throw for an unknown email -- let sign-in report invalid credentials itself", async () => {
  const ctx = fakeCtx({ path: "/sign-in/email", email: "nobody@example.com", user: null });
  await assert.doesNotReject(requireVerifiedForSignIn(ctx));
});

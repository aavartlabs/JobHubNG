import { APIError } from "better-auth/api";

// Only /sign-in/email is gated -- see README for why this is
// belt-and-suspenders rather than the sole guard. Better Auth's
// emailAndPassword.autoSignIn (default true) means a brand-new unverified
// user already holds a session right after /sign-up/email -- that session is
// needed so the phone-number plugin can verify a phone number against it,
// so this hook cannot (and does not try to) block that initial post-signup
// session. It only blocks *re*-authentication once that session expires or
// the user logs out. Flask's login_required (a separate task) closes the
// remaining gap by additionally checking both flags on every gated request.
const GATED_PATH = "/sign-in/email";

/**
 * `hooks.before` handler (wrap with `createAuthMiddleware` when wiring it
 * into `betterAuth({...})` -- see src/auth.js). Exported here as a plain
 * async function so it can be unit tested with a minimal fake `ctx`, without
 * going through Better Auth's middleware dispatch machinery.
 */
export async function requireVerifiedForSignIn(ctx) {
  if (ctx.path !== GATED_PATH) {
    return;
  }

  const email = ctx.body?.email;
  if (!email) {
    return;
  }

  const existing = await ctx.context.internalAdapter.findUserByEmail(email);
  const user = existing?.user;
  if (!user) {
    // Let sign-in's own credential check report "invalid email or
    // password" -- don't leak whether an account exists via a different
    // error here.
    return;
  }

  if (!user.emailVerified || !user.phoneNumberVerified) {
    throw new APIError("FORBIDDEN", {
      code: "EMAIL_AND_PHONE_VERIFICATION_REQUIRED",
      message: "Verify both your email and phone number before signing in.",
    });
  }
}

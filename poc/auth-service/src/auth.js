import path from "node:path";
import { fileURLToPath } from "node:url";
import Database from "better-sqlite3";
import { betterAuth } from "better-auth";
import { emailOTP, phoneNumber } from "better-auth/plugins";

import { sendEmailOTP } from "./email.js";
import { sendPhoneOTP } from "./phone.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Own SQLite file, separate from the main poc/ Flask app's jobhub.db --
// this service owns its own user/session/verification tables.
const DB_PATH = process.env.AUTH_DB_PATH || path.join(__dirname, "..", "auth.db");

const trustedOrigins = (process.env.TRUSTED_ORIGINS || "")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

export const auth = betterAuth({
  database: new Database(DB_PATH),
  basePath: "/auth",
  secret: process.env.BETTER_AUTH_SECRET,
  baseURL: process.env.BETTER_AUTH_URL,
  trustedOrigins,
  advanced: {
    // Confirmed (see README): the resulting session cookie is named
    // "jobhub-auth.session_token" over plain http/dev, or
    // "__Secure-jobhub-auth.session_token" once BETTER_AUTH_URL is https
    // (Better Auth's own secure-cookie prefixing follows the configured
    // baseURL's scheme, NOT NODE_ENV -- confirmed directly in
    // node_modules/better-auth/dist/cookies/index.mjs).
    cookiePrefix: "jobhub-auth",
  },
  emailAndPassword: {
    enabled: true,
    // Default is already true; explicit for the reason below.
    // A brand-new user holds a session immediately after /sign-up/email so
    // the phone-number plugin's /phone-number/verify (updatePhoneNumber:
    // true) has a session to attach the verified phone number to.
    autoSignIn: true,
  },
  // There is deliberately NO sign-in-time verification gate here. An earlier
  // version blocked /sign-in/email for users whose emailVerified /
  // phoneNumberVerified weren't both true; that permanently bricked any
  // account whose owner lost the post-signup session mid-verification (close
  // the tab, log out, let it expire) -- they could neither sign back in to
  // finish verifying nor re-register (USER_ALREADY_EXISTS). The Flask app's
  // login_required (poc/jobhub_poc/webapp/auth.py) already checks BOTH flags
  // on every gated request and redirects to /verify when either is false,
  // regardless of session state, and Flask is the only consumer of these
  // sessions (the Cloudflare Tunnel's ingress is fixed to jobhub-web, so
  // nothing else can reach this service). An unverified user signing in
  // therefore gets a session that can do nothing but finish verification.
  // If some future consumer ever reads these sessions directly, it needs its
  // own equivalent check.
  rateLimit: {
    // Explicitly on, rather than relying on Better Auth's default of
    // `enabled: isProduction` -- these endpoints trigger real WhatsApp and
    // email sends to arbitrary, caller-supplied recipients without
    // authentication, so "off unless NODE_ENV happens to be production" is
    // not a safe default to depend on.
    enabled: true,
    // Global fallback for any path without a more specific rule below or a
    // plugin rule of its own. Deliberately generous: /get-session is hit once
    // per gated Flask request, so a tight global limit would throttle normal
    // logged-in browsing, not abuse.
    window: 60,
    max: 120,
    // Applied last, overriding both Better Auth's built-in special rules and
    // the plugins' own (phone-number: 10/60s across /phone-number/*;
    // email-otp: 3/60s on send-verification-otp). Paths here are relative to
    // basePath, i.e. "/auth" is already stripped.
    customRules: {
      // Each call sends a real WhatsApp message to a caller-supplied number.
      "/phone-number/send-otp": { window: 60, max: 5 },
      // Verification attempts -- enough for a few fat-fingered codes, not
      // enough to brute-force a 6-digit OTP.
      "/phone-number/verify": { window: 60, max: 10 },
      // Each call sends a real email to a caller-supplied address.
      "/email-otp/send-verification-otp": { window: 60, max: 5 },
      "/email-otp/verify-email": { window: 60, max: 10 },
      "/sign-up/email": { window: 60, max: 5 },
      "/sign-in/email": { window: 60, max: 10 },
    },
  },
  plugins: [
    emailOTP({
      otpLength: 6,
      async sendVerificationOTP({ email, otp, type }) {
        await sendEmailOTP(email, otp, type);
      },
    }),
    phoneNumber({
      otpLength: 6,
      async sendOTP({ phoneNumber: number, code }) {
        await sendPhoneOTP(number, code);
      },
    }),
  ],
});

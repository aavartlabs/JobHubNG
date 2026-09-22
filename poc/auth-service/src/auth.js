import path from "node:path";
import { fileURLToPath } from "node:url";
import Database from "better-sqlite3";
import { betterAuth } from "better-auth";
import { createAuthMiddleware } from "better-auth/api";
import { emailOTP, phoneNumber } from "better-auth/plugins";

import { requireVerifiedForSignIn } from "./hooks.js";
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
    // "__Secure-jobhub-auth.session_token" once baseURL is https / the
    // service runs with NODE_ENV=production (Better Auth's own secure-cookie
    // prefixing, not something this file controls directly).
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
  hooks: {
    // Gate *re*-authentication on both verification flags -- see
    // src/hooks.js for why this can't (and doesn't try to) block the
    // initial post-signup session.
    before: createAuthMiddleware(requireVerifiedForSignIn),
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

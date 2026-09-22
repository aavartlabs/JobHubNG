import { Resend } from "resend";

const SUBJECTS = {
  "sign-in": "Your JobHubNG sign-in code",
  "email-verification": "Verify your JobHubNG email address",
  "forget-password": "Your JobHubNG password reset code",
  "change-email": "Confirm your new JobHubNG email address",
};

function subjectFor(type) {
  return SUBJECTS[type] || "Your JobHubNG verification code";
}

/**
 * Builds a `sendEmailOTP(email, otp, type)` function bound to a Resend
 * client. `client` can be injected for testing (anything with an
 * `emails.send()` method matching the Resend SDK's shape); production code
 * (src/auth.js, via the default export below) lets this construct a real
 * `Resend` client from RESEND_API_KEY/RESEND_FROM_EMAIL.
 *
 * Awaits the send and throws on failure -- a deliberate deviation from
 * Better Auth's generic "don't await OTP email sends, to avoid timing
 * attacks" advice. This project has a demonstrated real OTP-delivery
 * failure mode on its sibling WhatsApp gateway (see tasks_all.md's T8) --
 * failed sends must surface as a clear error, not a silent stuck state.
 */
export function createEmailOTPSender({
  apiKey = process.env.RESEND_API_KEY,
  fromEmail = process.env.RESEND_FROM_EMAIL,
  client,
} = {}) {
  // Built lazily, not at createEmailOTPSender() call time -- the `Resend`
  // constructor throws immediately if no API key is available (env or
  // arg), and this module is imported (via auth.js) by tooling like the
  // Better Auth migrate CLI that has no reason to need a real key.
  let resend = client ?? null;
  function getClient() {
    if (!resend) {
      resend = new Resend(apiKey);
    }
    return resend;
  }

  return async function sendEmailOTP(email, otp, type) {
    if (!fromEmail) {
      throw new Error("RESEND_FROM_EMAIL is not configured");
    }

    const { error } = await getClient().emails.send({
      from: fromEmail,
      to: email,
      subject: subjectFor(type),
      text: `Your JobHubNG verification code is ${otp}.`,
    });

    if (error) {
      throw new Error(`Resend failed to send OTP email: ${error.message}`);
    }
  };
}

export const sendEmailOTP = createEmailOTPSender();

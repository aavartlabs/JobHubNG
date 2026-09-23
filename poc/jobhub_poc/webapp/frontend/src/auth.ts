/* Vanilla-fetch helpers backing login.html/register.html/verify.html -- same
   plain-fetch-plus-DOM style as app.ts, no framework. Everything here talks to the
   /auth/* proxy (see auth_proxy.py) on this same origin, which byte-for-byte relays to
   poc/auth-service/'s own Better Auth router (see that service's README.md). */

import {
  type PendingPhoneStorage,
  clearPendingPhone,
  resolvePhoneNumber,
  savePendingPhone,
} from "./pending_phone";
import { normalizePhone } from "./phone";
import { getTurnstileToken } from "./turnstile";

interface AuthUser {
  id: string;
  email: string;
  name?: string;
  phoneNumber?: string | null;
  emailVerified: boolean;
  // Better Auth's own default before phone verification -- null, not false.
  phoneNumberVerified: boolean | null;
}

interface GetSessionResponse {
  session: unknown;
  user: AuthUser;
}

// How long to wait before offering an email-OTP resend. Better Auth's own
// send-verification-otp endpoint always returns 200 even if the underlying send failed
// (see poc/auth-service/README.md's "Awaiting OTP sends" note) -- there is no reliable
// way to detect a silent failure from the HTTP response, so this is a fixed timeout, not
// a response check.
const EMAIL_RESEND_DELAY_MS = 45_000;

/** sessionStorage, or null where the browser refuses to hand it over at all. */
function pendingPhoneStorage(): PendingPhoneStorage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

// Carries a failed first phone-code send from /register over to /verify, where the
// person can see it and correct the number -- otherwise it just never arrives, silently.
const PHONE_SEND_ERROR_KEY = "jobhub.phoneSendError";

const BOT_CHECK_FAILED = "Bot check failed or didn't load. Please try again.";

/** `action` marks a Turnstile-protected endpoint (see auth_proxy.py's
    _TURNSTILE_ACTIONS): a fresh token for it is sent as X-Turnstile-Token. */
async function postJson(
  path: string,
  body: unknown,
  action?: string,
): Promise<{ ok: boolean; status: number; data: any }> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (action) {
    try {
      headers["X-Turnstile-Token"] = await getTurnstileToken(action);
    } catch {
      return { ok: false, status: 0, data: { message: BOT_CHECK_FAILED } };
    }
  }
  let resp: Response;
  try {
    resp = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers,
      body: JSON.stringify(body),
    });
  } catch {
    return { ok: false, status: 0, data: null };
  }
  let data: any = null;
  try {
    data = await resp.json();
  } catch {
    data = null;
  }
  return { ok: resp.ok, status: resp.status, data };
}

async function getSession(): Promise<GetSessionResponse | null> {
  try {
    const resp = await fetch("/auth/get-session", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!resp.ok) return null;
    return (await resp.json()) as GetSessionResponse | null;
  } catch {
    return null;
  }
}

function showError(el: HTMLElement | null, message: string): void {
  if (!el) return;
  el.textContent = message;
  el.hidden = false;
}

function errorMessage(data: any, fallback: string): string {
  if (data && typeof data === "object") {
    if (typeof data.message === "string" && data.message) return data.message;
    if (typeof data.code === "string" && data.code) return data.code;
  }
  return fallback;
}

// ---- /login ----
function initLogin(): void {
  const form = document.getElementById("login-form") as HTMLFormElement | null;
  if (!form) return;
  const errorEl = document.getElementById("login-error");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (errorEl) errorEl.hidden = true;

    const email = (document.getElementById("login-email") as HTMLInputElement | null)?.value.trim() ?? "";
    const password = (document.getElementById("login-password") as HTMLInputElement | null)?.value ?? "";

    const { ok, data } = await postJson("/auth/sign-in/email", { email, password }, "login");
    if (!ok) {
      showError(errorEl, errorMessage(data, "Could not log in. Check your email and password."));
      return;
    }
    window.location.href = "/jobs";
  });
}

// ---- /register ----
function initRegister(): void {
  const form = document.getElementById("register-form") as HTMLFormElement | null;
  if (!form) return;
  const errorEl = document.getElementById("register-error");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (errorEl) errorEl.hidden = true;

    const name = (document.getElementById("register-name") as HTMLInputElement | null)?.value.trim() ?? "";
    const email = (document.getElementById("register-email") as HTMLInputElement | null)?.value.trim() ?? "";
    const password = (document.getElementById("register-password") as HTMLInputElement | null)?.value ?? "";
    const phone = normalizePhone(
      (document.getElementById("register-phone") as HTMLInputElement | null)?.value ?? "",
    );
    if (!phone.ok) {
      showError(errorEl, phone.error);
      return;
    }
    const phoneNumber = phone.phone;

    // 1. Sign up with email+password only -- deliberately NOT phoneNumber. Better Auth's
    // phone-number/verify later refuses to attach a number that "already exists" on any
    // user, including the requester's own just-created one (confirmed in Task 1). Sign-up
    // leaves us with an active session (autoSignIn), which the next two calls need.
    const signUp = await postJson("/auth/sign-up/email", { name, email, password }, "signup");
    if (!signUp.ok) {
      showError(errorEl, errorMessage(signUp.data, "Could not create your account."));
      return;
    }

    // 2. Stash the typed number BEFORE navigating away. /phone-number/send-otp does not
    // write it to the user row (only /phone-number/verify with updatePhoneNumber:true
    // does), so without this stash /verify has no number to verify against and every
    // attempt 400s with OTP_NOT_FOUND. See src/pending_phone.ts for the full reasoning.
    // /verify also renders an editable field prefilled from this, for the cases this
    // can't cover (a different tab/device, storage unavailable).
    savePendingPhone(pendingPhoneStorage(), phoneNumber);

    // 3 & 4. Trigger both OTP sends as separate steps, then move on to /verify
    // regardless of their outcome -- that page re-derives status from get-session and
    // offers its own resend affordances, so this is best-effort here.
    const phoneSend = await postJson("/auth/phone-number/send-otp", { phoneNumber }, "send_phone_otp");
    if (!phoneSend.ok) {
      try {
        window.sessionStorage.setItem(
          PHONE_SEND_ERROR_KEY,
          errorMessage(phoneSend.data, "We couldn't send a WhatsApp code to that number."),
        );
      } catch {
        // storage unavailable -- /verify still offers a resend
      }
    }
    await postJson("/auth/email-otp/send-verification-otp", { email, type: "email-verification" }, "send_email_otp");

    window.location.href = "/verify";
  });
}

// ---- /verify ----
function initVerify(): void {
  const statusEl = document.getElementById("verify-status");
  const emailSection = document.getElementById("email-section");
  const phoneSection = document.getElementById("phone-section");
  if (!statusEl || !emailSection || !phoneSection) return; // not on the verify page

  const continueEl = document.getElementById("verify-continue");
  const emailForm = document.getElementById("email-otp-form") as HTMLFormElement | null;
  const emailError = document.getElementById("email-error");
  const emailVerifiedMsg = document.getElementById("email-verified-msg");
  const resendEmailBtn = document.getElementById("resend-email-otp") as HTMLButtonElement | null;
  const phoneForm = document.getElementById("phone-otp-form") as HTMLFormElement | null;
  const phoneError = document.getElementById("phone-error");
  const phoneVerifiedMsg = document.getElementById("phone-verified-msg");
  const resendPhoneBtn = document.getElementById("resend-phone-otp") as HTMLButtonElement | null;
  // Visible and editable on purpose: the number may not be recoverable here at all (a
  // different tab or device, cleared storage, or a signed-back-in unverified user), in
  // which case typing it in is the only way to finish verification.
  const phoneInput = document.getElementById("phone-number-input") as HTMLInputElement | null;

  const storage = pendingPhoneStorage();

  let email = "";
  let emailDone = false;
  let phoneDone = false;

  /** The number to verify against: whatever is in the editable field right now,
      normalised, or null (with the reason shown) if it isn't a usable number. */
  function currentPhoneNumber(): string | null {
    const phone = normalizePhone(phoneInput?.value ?? "");
    if (!phone.ok) {
      showError(phoneError, phone.error);
      return null;
    }
    return phone.phone;
  }

  function maybeShowContinue(): void {
    if (emailDone && phoneDone && continueEl) continueEl.hidden = false;
  }

  function markEmailVerified(): void {
    emailDone = true;
    if (emailForm) emailForm.hidden = true;
    if (emailVerifiedMsg) emailVerifiedMsg.hidden = false;
    if (resendEmailBtn) resendEmailBtn.hidden = true;
    maybeShowContinue();
  }

  function markPhoneVerified(): void {
    phoneDone = true;
    if (phoneForm) phoneForm.hidden = true;
    if (phoneVerifiedMsg) phoneVerifiedMsg.hidden = false;
    if (resendPhoneBtn) resendPhoneBtn.hidden = true;
    // The number now lives on the account (verify + updatePhoneNumber wrote it there),
    // so the stash has done its job and shouldn't linger into a later registration.
    clearPendingPhone(storage);
    maybeShowContinue();
  }

  void (async () => {
    const sessionData = await getSession();
    if (!sessionData || !sessionData.user) {
      statusEl.textContent = "You're not signed in. ";
      const link = document.createElement("a");
      link.href = "/register";
      link.textContent = "Create an account";
      statusEl.append(link);
      return;
    }

    email = sessionData.user.email;
    // user.phoneNumber is still null until /phone-number/verify writes it, so the
    // registration-time stash is the normal source here -- see src/pending_phone.ts.
    if (phoneInput) phoneInput.value = resolvePhoneNumber(sessionData.user.phoneNumber, storage);
    statusEl.textContent = "Enter the codes sent to your email and phone to finish setting up your account.";
    emailSection.hidden = false;
    phoneSection.hidden = false;

    try {
      const sendError = window.sessionStorage.getItem(PHONE_SEND_ERROR_KEY);
      if (sendError) {
        window.sessionStorage.removeItem(PHONE_SEND_ERROR_KEY);
        showError(phoneError, `${sendError} Check the number below and use "Resend phone code".`);
      }
    } catch {
      // storage unavailable
    }

    if (sessionData.user.emailVerified) markEmailVerified();
    if (sessionData.user.phoneNumberVerified) markPhoneVerified();

    // We've SENT a code -- not confirmed it arrived (see the EMAIL_RESEND_DELAY_MS
    // comment above). Never claim delivery here; only offer a way to try again.
    if (!emailDone && resendEmailBtn) {
      window.setTimeout(() => {
        resendEmailBtn.hidden = false;
      }, EMAIL_RESEND_DELAY_MS);
    }
    if (!phoneDone && resendPhoneBtn) {
      resendPhoneBtn.hidden = false;
    }
  })();

  emailForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (emailError) emailError.hidden = true;
    const code = (document.getElementById("email-otp-code") as HTMLInputElement | null)?.value.trim() ?? "";

    const { ok, data } = await postJson("/auth/email-otp/verify-email", { email, otp: code });
    if (!ok) {
      showError(emailError, errorMessage(data, "That code didn't work. Check it and try again."));
      return;
    }
    markEmailVerified();
  });

  resendEmailBtn?.addEventListener("click", async () => {
    resendEmailBtn.disabled = true;
    resendEmailBtn.textContent = "Sending...";
    const { ok, data } = await postJson(
      "/auth/email-otp/send-verification-otp",
      { email, type: "email-verification" },
      "send_email_otp",
    );
    if (!ok) {
      showError(emailError, errorMessage(data, "Couldn't send a new code. Try again."));
      resendEmailBtn.textContent = "Resend email code";
      resendEmailBtn.disabled = false;
      return;
    }
    resendEmailBtn.textContent = "Code sent again -- resend email code";
    window.setTimeout(() => {
      resendEmailBtn.disabled = false;
    }, EMAIL_RESEND_DELAY_MS);
  });

  phoneForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (phoneError) phoneError.hidden = true;
    const phoneNumber = currentPhoneNumber();
    if (!phoneNumber) return;
    const code = (document.getElementById("phone-otp-code") as HTMLInputElement | null)?.value.trim() ?? "";

    const { ok, data } = await postJson("/auth/phone-number/verify", {
      phoneNumber,
      code,
      updatePhoneNumber: true,
    });
    if (!ok) {
      showError(phoneError, errorMessage(data, "That code didn't work. Check it and try again."));
      return;
    }
    markPhoneVerified();
  });

  resendPhoneBtn?.addEventListener("click", async () => {
    if (phoneError) phoneError.hidden = true;
    const phoneNumber = currentPhoneNumber();
    if (!phoneNumber) return;
    // Keep the stash in step with whatever the user actually typed, so a reload of
    // /verify prefills the number they just asked a code for, not a stale one.
    savePendingPhone(storage, phoneNumber);
    resendPhoneBtn.disabled = true;
    const { ok, data } = await postJson("/auth/phone-number/send-otp", { phoneNumber }, "send_phone_otp");
    resendPhoneBtn.disabled = false;
    if (!ok) {
      showError(phoneError, errorMessage(data, "Couldn't send a code to that number. Check it and try again."));
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initLogin();
  initRegister();
  initVerify();
});

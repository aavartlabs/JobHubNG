/* Vanilla-fetch helpers backing login.html/register.html/verify.html -- same
   plain-fetch-plus-DOM style as app.ts, no framework. Everything here talks to the
   /auth/* proxy (see auth_proxy.py) on this same origin, which byte-for-byte relays to
   poc/auth-service/'s own Better Auth router (see that service's README.md). */

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

async function postJson(path: string, body: unknown): Promise<{ ok: boolean; status: number; data: any }> {
  let resp: Response;
  try {
    resp = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
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

    const { ok, data } = await postJson("/auth/sign-in/email", { email, password });
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
    const phoneNumber = (document.getElementById("register-phone") as HTMLInputElement | null)?.value.trim() ?? "";

    // 1. Sign up with email+password only -- deliberately NOT phoneNumber. Better Auth's
    // phone-number/verify later refuses to attach a number that "already exists" on any
    // user, including the requester's own just-created one (confirmed in Task 1). Sign-up
    // leaves us with an active session (autoSignIn), which the next two calls need.
    const signUp = await postJson("/auth/sign-up/email", { name, email, password });
    if (!signUp.ok) {
      showError(errorEl, errorMessage(signUp.data, "Could not create your account."));
      return;
    }

    // 2 & 3. Trigger both OTP sends as separate steps, then move on to /verify
    // regardless of their outcome -- that page re-derives status from get-session and
    // offers its own resend affordances, so this is best-effort here.
    await postJson("/auth/phone-number/send-otp", { phoneNumber });
    await postJson("/auth/email-otp/send-verification-otp", { email, type: "email-verification" });

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

  let email = "";
  let phoneNumber = "";
  let emailDone = false;
  let phoneDone = false;

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
    phoneNumber = sessionData.user.phoneNumber ?? "";
    statusEl.textContent = "Enter the codes sent to your email and phone to finish setting up your account.";
    emailSection.hidden = false;
    phoneSection.hidden = false;

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
    await postJson("/auth/email-otp/send-verification-otp", { email, type: "email-verification" });
    resendEmailBtn.textContent = "Code sent again -- resend email code";
    window.setTimeout(() => {
      resendEmailBtn.disabled = false;
    }, EMAIL_RESEND_DELAY_MS);
  });

  phoneForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (phoneError) phoneError.hidden = true;
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
    resendPhoneBtn.disabled = true;
    await postJson("/auth/phone-number/send-otp", { phoneNumber });
    resendPhoneBtn.disabled = false;
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initLogin();
  initRegister();
  initVerify();
});

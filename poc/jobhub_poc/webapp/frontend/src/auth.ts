/* Vanilla-fetch helpers backing login.html/register.html/verify.html -- same
   plain-fetch-plus-DOM style as app.ts, no framework. Everything here talks to the
   /auth/* proxy (see auth_proxy.py) on this same origin, which byte-for-byte relays to
   poc/auth-service/'s own Better Auth router (see that service's README.md). */

import { safeNext, withNext } from "./nav";
import { getTurnstileToken } from "./turnstile";

interface AuthUser {
  id: string;
  email: string;
  name?: string;
  emailVerified: boolean;
  // Set only by POST /auth/telegram/verify (auth-service/src/telegram.js); null until then.
  telegramVerified: boolean | null;
  telegramUsername?: string | null;
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
  // On a phone the message (above the form) is often off-screen by now.
  el.scrollIntoView({ block: "center", behavior: "smooth" });
}

/** Disables the form's submit button and shows `label` on it while a request runs, so a
    tap visibly did something (the bot check + sign-up can take several seconds). Returns
    a function that puts the button back. */
function busy(form: HTMLFormElement, label: string): (next?: string) => void {
  const button = form.querySelector<HTMLButtonElement>('button[type="submit"]');
  if (!button) return () => {};
  const original = button.textContent ?? "";
  button.disabled = true;
  button.textContent = label;
  return (next?: string) => {
    if (next !== undefined) {
      button.textContent = next;
      return;
    }
    button.disabled = false;
    button.textContent = original;
  };
}

function errorMessage(data: any, fallback: string): string {
  if (data && typeof data === "object") {
    if (typeof data.message === "string" && data.message) return data.message;
    if (typeof data.code === "string" && data.code) return data.code;
  }
  return fallback;
}

/** `next` from this page's URL (e.g. /login?next=/jobs?job=12), unvalidated. */
function currentNext(): string | null {
  return new URLSearchParams(window.location.search).get("next");
}

/** Keeps `next` on the login <-> register cross-links, so switching pages mid-flow
    still returns the person to the job they were looking at. */
function carryNextOnLinks(): void {
  const next = currentNext();
  document.querySelectorAll<HTMLAnchorElement>('main a[href="/login"], main a[href="/register"]').forEach((a) => {
    a.href = withNext(a.getAttribute("href") ?? "/", next);
  });
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

    const done = busy(form, "Logging in…");
    const { ok, data } = await postJson("/auth/sign-in/email", { email, password }, "login");
    if (!ok) {
      done();
      showError(errorEl, errorMessage(data, "Could not log in. Check your email and password."));
      return;
    }
    window.location.href = safeNext(currentNext());
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

    // Sign-up leaves an active session (autoSignIn), which the email code and the
    // Telegram link on /verify both need.
    const done = busy(form, "Creating your account…");
    const signUp = await postJson("/auth/sign-up/email", { name, email, password }, "signup");
    if (!signUp.ok) {
      done();
      showError(errorEl, errorMessage(signUp.data, "Could not create your account."));
      return;
    }
    done("Emailing your code…");
    // Best-effort: /verify re-derives status from get-session and offers a resend.
    await postJson("/auth/email-otp/send-verification-otp", { email, type: "email-verification" }, "send_email_otp");
    window.location.href = withNext("/verify", currentNext());
  });
}

// ---- /verify ----
function initVerify(): void {
  const statusEl = document.getElementById("verify-status");
  const emailSection = document.getElementById("email-section");
  const telegramSection = document.getElementById("telegram-section");
  if (!statusEl || !emailSection || !telegramSection) return; // not on the verify page

  const continueEl = document.getElementById("verify-continue");
  const emailForm = document.getElementById("email-otp-form") as HTMLFormElement | null;
  const emailError = document.getElementById("email-error");
  const emailVerifiedMsg = document.getElementById("email-verified-msg");
  const resendEmailBtn = document.getElementById("resend-email-otp") as HTMLButtonElement | null;
  const telegramError = document.getElementById("telegram-error");
  const telegramVerifiedMsg = document.getElementById("telegram-verified-msg");
  const connectBtn = document.getElementById("telegram-connect") as HTMLButtonElement | null;
  const openLink = document.getElementById("telegram-open") as HTMLAnchorElement | null;
  const telegramForm = document.getElementById("telegram-otp-form") as HTMLFormElement | null;

  let email = "";
  let emailDone = false;

  // Only the email is required; Telegram is optional (it unlocks Telegram alerts).
  function maybeShowContinue(): void {
    if (!(emailDone && continueEl)) return;
    const link = continueEl.querySelector("a");
    if (link) link.href = safeNext(currentNext());
    continueEl.hidden = false;
  }

  function markEmailVerified(): void {
    emailDone = true;
    if (emailForm) emailForm.hidden = true;
    if (emailVerifiedMsg) emailVerifiedMsg.hidden = false;
    if (resendEmailBtn) resendEmailBtn.hidden = true;
    maybeShowContinue();
  }

  function markTelegramVerified(username?: string | null): void {
    for (const el of [connectBtn, openLink, telegramForm]) if (el) el.hidden = true;
    if (telegramVerifiedMsg) {
      telegramVerifiedMsg.textContent = username ? `Telegram connected (@${username}).` : "Telegram connected.";
      telegramVerifiedMsg.hidden = false;
    }
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
    statusEl.textContent = "Verify your email to finish setting up your account. Telegram is optional.";
    emailSection.hidden = false;
    telegramSection.hidden = false;

    if (sessionData.user.emailVerified) markEmailVerified();
    if (sessionData.user.telegramVerified) markTelegramVerified(sessionData.user.telegramUsername);

    // We've SENT a code -- not confirmed it arrived (see the EMAIL_RESEND_DELAY_MS
    // comment above). Never claim delivery here; only offer a way to try again.
    if (!emailDone && resendEmailBtn) {
      window.setTimeout(() => {
        resendEmailBtn.hidden = false;
      }, EMAIL_RESEND_DELAY_MS);
    }
  })();

  emailForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (emailError) emailError.hidden = true;
    const code = (document.getElementById("email-otp-code") as HTMLInputElement | null)?.value.trim() ?? "";

    const done = busy(emailForm, "Checking…");
    const { ok, data } = await postJson("/auth/email-otp/verify-email", { email, otp: code });
    done();
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

  // A one-time t.me link: pressing Start there makes the bot send a code, which comes
  // back here. Shown as a link rather than opened for them: a popup after an await is
  // usually blocked, and on a laptop they may want to open it on their phone.
  connectBtn?.addEventListener("click", async () => {
    if (telegramError) telegramError.hidden = true;
    connectBtn.disabled = true;
    const { ok, data } = await postJson("/auth/telegram/link", {});
    connectBtn.disabled = false;
    if (!ok || typeof data?.url !== "string") {
      showError(telegramError, errorMessage(data, "Couldn't create a Telegram link. Try again."));
      return;
    }
    if (openLink) {
      openLink.href = data.url;
      openLink.hidden = false;
    }
    connectBtn.textContent = "Get a new link";
    if (telegramForm) telegramForm.hidden = false;
  });

  telegramForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (telegramError) telegramError.hidden = true;
    const code = (document.getElementById("telegram-otp-code") as HTMLInputElement | null)?.value.trim() ?? "";
    const done = busy(telegramForm, "Checking…");
    const { ok, data } = await postJson("/auth/telegram/verify", { code });
    done();
    if (!ok) {
      showError(telegramError, errorMessage(data, "That code didn't work. Check it and try again."));
      return;
    }
    const refreshed = await getSession();
    markTelegramVerified(refreshed?.user?.telegramUsername);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  carryNextOnLinks();
  initLogin();
  initRegister();
  initVerify();
});

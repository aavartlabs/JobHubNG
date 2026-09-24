/* One fresh Cloudflare Turnstile token per protected /auth/* call. Tokens are
   single-use and each is bound to an action (signup, login, send_email_otp) that
   auth_proxy.py checks server-side, so a widget is rendered per
   request and removed once it has produced its token. "interaction-only" keeps it
   invisible unless Cloudflare actually wants the visitor to click something.

   Needs, on the page: <meta name="turnstile-sitekey">, a #turnstile-container element,
   and api.js loaded with ?render=explicit (see templates/_turnstile.html). */

interface TurnstileApi {
  render(container: HTMLElement, options: Record<string, unknown>): string | undefined;
  remove(widgetId: string): void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

const API_WAIT_MS = 15_000;
// Long enough for a visitor to notice and solve an interactive challenge.
const TOKEN_WAIT_MS = 120_000;

function waitForApi(): Promise<TurnstileApi> {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const poll = () => {
      if (window.turnstile) return resolve(window.turnstile);
      if (Date.now() - started > API_WAIT_MS) return reject(new Error("Turnstile failed to load"));
      window.setTimeout(poll, 100);
    };
    poll();
  });
}

export async function getTurnstileToken(action: string): Promise<string> {
  const sitekey = document.querySelector<HTMLMetaElement>('meta[name="turnstile-sitekey"]')?.content;
  const container = document.getElementById("turnstile-container");
  if (!sitekey || !container) throw new Error("Turnstile is not configured on this page");

  const api = await waitForApi();
  const slot = document.createElement("div");
  container.append(slot);

  let widgetId: string | undefined;
  try {
    return await new Promise<string>((resolve, reject) => {
      const timer = window.setTimeout(() => reject(new Error("Turnstile timed out")), TOKEN_WAIT_MS);
      const fail = (code?: unknown) => {
        window.clearTimeout(timer);
        reject(new Error(`Turnstile error ${String(code ?? "")}`.trim()));
      };
      widgetId = api.render(slot, {
        sitekey,
        action,
        appearance: "interaction-only",
        callback: (token: string) => {
          window.clearTimeout(timer);
          resolve(token);
        },
        // Cloudflare wants a click: close the phone keyboard and bring the widget into
        // view, or it sits below the fold while the button says "Creating…".
        "before-interactive-callback": () => {
          (document.activeElement as HTMLElement | null)?.blur();
          slot.scrollIntoView({ block: "center", behavior: "smooth" });
        },
        "error-callback": fail,
        "expired-callback": () => fail("expired"),
      });
    });
  } finally {
    if (widgetId !== undefined) api.remove(widgetId);
    slot.remove();
  }
}

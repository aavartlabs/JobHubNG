/* Post-login/signup navigation. `next` arrives in the URL, so it is attacker-controlled:
   only same-origin absolute paths are followed, anything else lands on /jobs. Pure, no
   DOM, tested under `node --test` (../test/nav.test.mjs). */

const DEFAULT_NEXT = "/jobs";

export function safeNext(raw: string | null | undefined): string {
  if (typeof raw !== "string") return DEFAULT_NEXT;
  // "/" but not "//" or "/\" (both protocol-relative in browsers), no control chars.
  if (!/^\/(?![/\\])/.test(raw) || /[\u0000-\u001f\u007f\\]/.test(raw)) return DEFAULT_NEXT;
  return raw;
}

/** `path` with `?next=` carried along, when there's a meaningful, safe next. */
export function withNext(path: string, next: string | null | undefined): string {
  const target = safeNext(next);
  return target === DEFAULT_NEXT ? path : `${path}?next=${encodeURIComponent(target)}`;
}

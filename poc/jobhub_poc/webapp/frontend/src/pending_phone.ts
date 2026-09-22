/* Where the mobile number typed at /register survives the navigation to /verify.

   Why this exists at all: Better Auth's POST /auth/phone-number/send-otp does NOT write
   the number to the user's row -- it only stores a verification row keyed by the number
   itself (confirmed against node_modules/better-auth/dist/plugins/phone-number/routes.mjs).
   Only POST /auth/phone-number/verify with updatePhoneNumber:true writes it to the user,
   and that call is the very one that needs the number as input. So between /register and
   /verify the number lives nowhere server-side, and get-session's user.phoneNumber is
   still null. Without persisting it client-side, every phone verification 400s with
   OTP_NOT_FOUND because it verifies against an empty identifier.

   Kept in its own module, free of DOM/browser globals, so it can be unit tested under
   `node --test` without a DOM (see ../test/pending_phone.test.mjs) -- same spirit as
   poc/whatsapp-sender/src/*.js's small, separately-tested pure modules. */

/** The subset of the Web Storage API this module uses. */
export interface PendingPhoneStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export const PENDING_PHONE_KEY = "jobhub.pendingPhone";

/** Trim, and treat a whitespace-only value as absent. */
function clean(value: string | null | undefined): string {
  return typeof value === "string" ? value.trim() : "";
}

/**
 * Resolve the phone number to verify against, in priority order:
 *   1. the number already recorded on the account (a verified/attached number),
 *   2. the number stashed at registration time in this tab's sessionStorage,
 *   3. "" -- nothing usable; the caller must ask the user to type it in.
 *
 * `storage` may be null (sessionStorage unavailable, e.g. a hardened/private context),
 * and any throw from it is treated as "nothing stored" rather than propagated.
 */
export function resolvePhoneNumber(
  sessionPhoneNumber: string | null | undefined,
  storage: PendingPhoneStorage | null,
): string {
  const fromSession = clean(sessionPhoneNumber);
  if (fromSession) return fromSession;
  return clean(readPendingPhone(storage));
}

/** Read the stashed number, tolerating an unavailable/throwing storage. */
export function readPendingPhone(storage: PendingPhoneStorage | null): string {
  if (!storage) return "";
  try {
    return clean(storage.getItem(PENDING_PHONE_KEY));
  } catch {
    return "";
  }
}

/**
 * Stash the number typed at registration. A blank value clears the key instead of
 * storing an empty string, so a later read can't resolve to "" and look like a hit.
 */
export function savePendingPhone(storage: PendingPhoneStorage | null, phoneNumber: string): void {
  if (!storage) return;
  const value = clean(phoneNumber);
  try {
    if (value) {
      storage.setItem(PENDING_PHONE_KEY, value);
    } else {
      storage.removeItem(PENDING_PHONE_KEY);
    }
  } catch {
    // Storage unavailable/full -- the editable field on /verify is the fallback.
  }
}

/** Drop the stash once the number is verified (it now lives on the account). */
export function clearPendingPhone(storage: PendingPhoneStorage | null): void {
  if (!storage) return;
  try {
    storage.removeItem(PENDING_PHONE_KEY);
  } catch {
    // Nothing to do -- a stale key is harmless, it's only ever a prefill hint.
  }
}

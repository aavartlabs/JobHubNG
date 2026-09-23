/* Mobile number normalisation for the auth pages. Pure, no DOM, unit tested under
   `node --test` (../test/phone.test.mjs).

   The number becomes a WhatsApp address, so it must be unambiguous: a leading "+",
   a country code (never starting with 0), 7-15 digits in all. A bare national number
   ("9902065845") or a "+0..." prefix would be sent to a different country's number or
   to no WhatsApp account at all -- the 2026-09-23 "code never arrived" failure.
   Same rule as auth-service's isValidPhoneNumber and the Flask alert form. */

export type PhoneResult = { ok: true; phone: string } | { ok: false; error: string };

const SEPARATORS = /[\s().-]/g;
const E164 = /^\+[1-9][0-9]{6,14}$/;

export function normalizePhone(input: string): PhoneResult {
  const compact = input.trim().replace(SEPARATORS, "");
  if (!compact) return { ok: false, error: "Enter your mobile number." };
  if (!compact.startsWith("+")) {
    return { ok: false, error: "Start with + and your country code, e.g. +91 98765 43210." };
  }
  if (!E164.test(compact)) {
    return {
      ok: false,
      error: "That doesn't look like a mobile number. Use + and your country code, e.g. +91 98765 43210.",
    };
  }
  return { ok: true, phone: compact };
}

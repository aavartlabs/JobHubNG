/**
 * Whether a jid has a WhatsApp account, via Baileys' sock.onWhatsApp (a USync
 * query). That call returns entries only for jids that exist, so an empty or
 * missing result means "no account".
 *
 * Why ask first: WhatsApp never server-acks a message to a number with no
 * account, so without this a send to a mistyped number just hangs for the
 * full ACK_TIMEOUT_MS and then fails with a vague timeout (the 2026-09-23
 * "+01..." OTP). Lookup errors are thrown, not guessed: the caller decides.
 */
export async function isOnWhatsApp(sock, jid) {
  const results = await sock.onWhatsApp(jid);
  return Array.isArray(results) && results.some((r) => r?.exists === true);
}

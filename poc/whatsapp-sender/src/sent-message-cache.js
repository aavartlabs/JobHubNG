/**
 * Remembers recently-sent message content so baileys can answer WhatsApp's
 * retry-receipt protocol.
 *
 * When a recipient's device can't decrypt a message on the first try, it
 * asks the sender to resend (this is what shows as "Waiting for this
 * message" on their end). Baileys calls the socket's `getMessage(key)` to
 * get that content back -- the installed version's default is
 * `async () => undefined` (see node_modules/baileys/lib/Defaults/index.js),
 * which means a retry can never be satisfied and the recipient is stuck
 * forever unless the socket is given a real getMessage.
 */
export function createSentMessageCache(maxEntries = 500) {
  const store = new Map(); // insertion order doubles as recency order

  function remember(msgId, message) {
    if (store.has(msgId)) store.delete(msgId);
    store.set(msgId, message);
    while (store.size > maxEntries) {
      store.delete(store.keys().next().value);
    }
  }

  async function getMessage(key) {
    return store.get(key.id);
  }

  return { remember, getMessage };
}

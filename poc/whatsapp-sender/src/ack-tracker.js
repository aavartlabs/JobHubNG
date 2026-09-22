/**
 * Tracks in-flight sends until baileys confirms WhatsApp's own servers
 * actually received the message. sock.sendMessage() resolving is not proof
 * of that -- it just means the message was handed to the socket, which is
 * not reliable when the underlying connection is flapping (see the repeated
 * 428/500/503 reconnects this gateway has hit in production).
 *
 * Mirrors proto.WebMessageInfo.Status from the installed baileys version:
 * ERROR=0, PENDING=1, SERVER_ACK=2, DELIVERY_ACK=3, READ=4, PLAYED=5.
 */
export const ACK_STATUS = { ERROR: 0, PENDING: 1, SERVER_ACK: 2 };

export function createAckTracker() {
  const pending = new Map();

  function waitForAck(msgId, timeoutMs) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        pending.delete(msgId);
        reject(new Error(`no delivery confirmation from WhatsApp within ${timeoutMs}ms`));
      }, timeoutMs);
      pending.set(msgId, { resolve, reject, timer });
    });
  }

  function settle(msgId, status) {
    const entry = pending.get(msgId);
    if (!entry) return;

    if (status === ACK_STATUS.ERROR) {
      clearTimeout(entry.timer);
      pending.delete(msgId);
      entry.reject(new Error("WhatsApp reported a delivery error for this message"));
    } else if (status >= ACK_STATUS.SERVER_ACK) {
      clearTimeout(entry.timer);
      pending.delete(msgId);
      entry.resolve(status);
    }
    // PENDING (1) is an interim state before WhatsApp's server has it --
    // leave the entry in place and wait for a later update or the timeout.
  }

  return { waitForAck, settle };
}

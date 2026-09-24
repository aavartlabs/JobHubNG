/**
 * Incoming Telegram updates -> one normalised event -> the handler registered for it.
 *
 * This is the extension point for anything users say or tap in Telegram: add a command
 * to `commands`, or an action to `actions` for inline-button taps (callback_data
 * "<action>:<arg>"). A handler gets the event and a context ({ reply, services }) and
 * may reply; whatever it returns is ignored. Only private chats are handled -- the bot
 * is never meant to sit in groups.
 */

/** A Telegram update as { kind, updateId, chat, ... }, or null if it isn't ours to handle. */
export function toEvent(update) {
  if (!update || typeof update !== "object") return null;
  const updateId = update.update_id;

  if (update.callback_query) {
    const cq = update.callback_query;
    const chat = cq.message?.chat;
    if (!chat || chat.type !== "private") return null;
    const [action, ...rest] = String(cq.data || "").split(":");
    return {
      kind: "callback",
      updateId,
      chat: chatOf(chat, cq.from),
      callbackId: cq.id,
      action,
      arg: rest.join(":"),
    };
  }

  const message = update.message;
  if (!message || message.chat?.type !== "private") return null;
  const text = typeof message.text === "string" ? message.text.trim() : "";
  const chat = chatOf(message.chat, message.from);
  const command = /^\/([A-Za-z0-9_]+)(?:@[A-Za-z0-9_]+)?(?:\s+([\s\S]*))?$/.exec(text);
  if (command) {
    return { kind: "command", updateId, chat, command: command[1].toLowerCase(), args: (command[2] || "").trim(), text };
  }
  return { kind: "text", updateId, chat, text };
}

function chatOf(chat, from) {
  return {
    id: String(chat.id),
    username: chat.username || from?.username || "",
    firstName: chat.first_name || from?.first_name || "",
  };
}

export function createRouter({ commands = {}, actions = {}, onText, onUnknownCommand }) {
  return async function route(event, ctx) {
    if (event.kind === "command") {
      const handler = commands[event.command] || onUnknownCommand;
      if (handler) await handler(event, ctx);
      return;
    }
    if (event.kind === "callback") {
      const handler = actions[event.action];
      if (handler) await handler(event, ctx);
      else await ctx.answerCallback("That button no longer works.");
      return;
    }
    if (onText) await onText(event, ctx);
  };
}

/** Remembers the last `size` update ids, so Telegram's redeliveries are handled once. */
export function createSeenUpdates(size = 1000) {
  const seen = new Set();
  return function firstTime(updateId) {
    if (updateId === undefined || updateId === null) return true;
    if (seen.has(updateId)) return false;
    seen.add(updateId);
    if (seen.size > size) seen.delete(seen.values().next().value);
    return true;
  };
}

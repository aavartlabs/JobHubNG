import { test } from "node:test";
import assert from "node:assert/strict";

import { createRouter, createSeenUpdates, toEvent } from "../src/router.js";

const chat = { id: 4242, type: "private", username: "ada", first_name: "Ada" };

test("commands are parsed with args, bot mentions stripped", () => {
  const e = toEvent({ update_id: 1, message: { chat, text: "/start@AavartJobsAlert_bot  abc-DEF_123 " } });
  assert.deepEqual(e, {
    kind: "command", updateId: 1, chat: { id: "4242", username: "ada", firstName: "Ada" },
    command: "start", args: "abc-DEF_123", text: "/start@AavartJobsAlert_bot  abc-DEF_123",
  });
});

test("plain text and button taps become events; groups and junk are ignored", () => {
  assert.equal(toEvent({ update_id: 2, message: { chat, text: "hi" } }).kind, "text");
  const cb = toEvent({ update_id: 3, callback_query: { id: "cq1", data: "pause:17", message: { chat } } });
  assert.deepEqual([cb.kind, cb.action, cb.arg, cb.callbackId], ["callback", "pause", "17", "cq1"]);
  assert.equal(toEvent({ update_id: 4, message: { chat: { id: -1, type: "group" }, text: "/start" } }), null);
  assert.equal(toEvent({ update_id: 5, edited_message: {} }), null);
  assert.equal(toEvent(null), null);
});

test("router dispatches commands, text, actions and unknowns", async () => {
  const calls = [];
  const route = createRouter({
    commands: { start: async (e) => calls.push(["start", e.args]) },
    actions: { pause: async (e) => calls.push(["pause", e.arg]) },
    onText: async (e) => calls.push(["text", e.text]),
    onUnknownCommand: async (e) => calls.push(["unknown", e.command]),
  });
  const ctx = { answerCallback: async (t) => calls.push(["answer", t]) };
  await route({ kind: "command", command: "start", args: "x" }, ctx);
  await route({ kind: "command", command: "nope", args: "" }, ctx);
  await route({ kind: "text", text: "hello" }, ctx);
  await route({ kind: "callback", action: "pause", arg: "17" }, ctx);
  await route({ kind: "callback", action: "gone", arg: "" }, ctx);
  assert.deepEqual(calls, [
    ["start", "x"], ["unknown", "nope"], ["text", "hello"], ["pause", "17"], ["answer", "That button no longer works."],
  ]);
});

test("seen updates are handled once and the memory is bounded", () => {
  const firstTime = createSeenUpdates(2);
  assert.equal(firstTime(1), true);
  assert.equal(firstTime(1), false);
  firstTime(2);
  firstTime(3);
  assert.equal(firstTime(1), true); // evicted, so seen as new again
});

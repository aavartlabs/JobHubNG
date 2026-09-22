import { test } from "node:test";
import assert from "node:assert/strict";
import { createAckTracker, ACK_STATUS } from "../src/ack-tracker.js";

test("resolves once a SERVER_ACK status arrives for the message id", async () => {
  const tracker = createAckTracker();
  const pending = tracker.waitForAck("abc", 1000);
  tracker.settle("abc", ACK_STATUS.SERVER_ACK);
  await assert.doesNotReject(pending);
});

test("resolves on a later status too (e.g. DELIVERY_ACK)", async () => {
  const tracker = createAckTracker();
  const pending = tracker.waitForAck("abc", 1000);
  tracker.settle("abc", 3); // DELIVERY_ACK
  await assert.doesNotReject(pending);
});

test("ignores PENDING status and keeps waiting for a later update", async () => {
  const tracker = createAckTracker();
  const pending = tracker.waitForAck("abc", 1000);
  tracker.settle("abc", ACK_STATUS.PENDING);
  tracker.settle("abc", ACK_STATUS.SERVER_ACK);
  await assert.doesNotReject(pending);
});

test("rejects on ERROR status", async () => {
  const tracker = createAckTracker();
  const pending = tracker.waitForAck("abc", 1000);
  tracker.settle("abc", ACK_STATUS.ERROR);
  await assert.rejects(pending);
});

test("rejects after the timeout if no status ever arrives", async () => {
  const tracker = createAckTracker();
  const pending = tracker.waitForAck("abc", 20);
  await assert.rejects(pending);
});

test("settling an unknown message id is a no-op, not a throw", () => {
  const tracker = createAckTracker();
  assert.doesNotThrow(() => tracker.settle("never-tracked", ACK_STATUS.SERVER_ACK));
});

test("a settled entry doesn't fire again on a later stray update", async () => {
  const tracker = createAckTracker();
  const pending = tracker.waitForAck("abc", 1000);
  tracker.settle("abc", ACK_STATUS.SERVER_ACK);
  await pending;
  // second update for the same id after it already resolved -- must not throw
  assert.doesNotThrow(() => tracker.settle("abc", ACK_STATUS.ERROR));
});

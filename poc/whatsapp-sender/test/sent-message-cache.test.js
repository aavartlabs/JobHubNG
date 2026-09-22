import { test } from "node:test";
import assert from "node:assert/strict";
import { createSentMessageCache } from "../src/sent-message-cache.js";

test("returns the remembered message for a known id", async () => {
  const cache = createSentMessageCache();
  cache.remember("id1", { text: "hello" });
  const msg = await cache.getMessage({ id: "id1" });
  assert.deepEqual(msg, { text: "hello" });
});

test("returns undefined for an unknown id", async () => {
  const cache = createSentMessageCache();
  const msg = await cache.getMessage({ id: "unknown" });
  assert.equal(msg, undefined);
});

test("evicts the oldest entry once maxEntries is exceeded", async () => {
  const cache = createSentMessageCache(2);
  cache.remember("a", { text: "1" });
  cache.remember("b", { text: "2" });
  cache.remember("c", { text: "3" });
  assert.equal(await cache.getMessage({ id: "a" }), undefined);
  assert.deepEqual(await cache.getMessage({ id: "b" }), { text: "2" });
  assert.deepEqual(await cache.getMessage({ id: "c" }), { text: "3" });
});

test("re-remembering an id refreshes its recency instead of duplicating it", async () => {
  const cache = createSentMessageCache(2);
  cache.remember("a", { text: "1" });
  cache.remember("b", { text: "2" });
  cache.remember("a", { text: "1-updated" }); // touching "a" again should make "b" the oldest
  cache.remember("c", { text: "3" }); // should evict "b", not "a"
  assert.deepEqual(await cache.getMessage({ id: "a" }), { text: "1-updated" });
  assert.equal(await cache.getMessage({ id: "b" }), undefined);
  assert.deepEqual(await cache.getMessage({ id: "c" }), { text: "3" });
});

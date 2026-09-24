import { test } from "node:test";
import assert from "node:assert/strict";

import { isPlainClick, nextRowIndex, selectionUrl } from "../src/split.ts";

test("selectionUrl sets sel, keeps the list's params, drops the hash", () => {
  assert.equal(selectionUrl("https://x.example/jobs", "7"), "/jobs?sel=7");
  assert.equal(selectionUrl("https://x.example/jobs?q=sre&page=2#job-3", "9"), "/jobs?q=sre&page=2&sel=9");
  assert.equal(selectionUrl("https://x.example/jobs?sel=1&q=a", "2"), "/jobs?sel=2&q=a");
});

test("nextRowIndex steps and stops at the ends", () => {
  assert.equal(nextRowIndex(0, 1, 3), 1);
  assert.equal(nextRowIndex(2, 1, 3), 2);
  assert.equal(nextRowIndex(0, -1, 3), 0);
  assert.equal(nextRowIndex(0, 1, 0), -1);
});

test("only plain left clicks are taken over", () => {
  const plain = { button: 0, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false };
  assert.equal(isPlainClick(plain), true);
  for (const change of [{ button: 1 }, { ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true }]) {
    assert.equal(isPlainClick({ ...plain, ...change }), false, JSON.stringify(change));
  }
});

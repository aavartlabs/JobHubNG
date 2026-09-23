import { test } from "node:test";
import assert from "node:assert/strict";

import { postedLabel, POSTED_WITHIN_OPTIONS } from "../src/jobs_query.ts";

const NOW = new Date("2026-09-23T12:00:00Z");

test("uses the posted date when there is one", () => {
  assert.equal(postedLabel("2026-09-23T09:00:00+00:00", "2026-09-23T10:00:00+00:00", NOW), "today");
  assert.equal(postedLabel("2026-09-22T00:00:00+00:00", "2026-09-23T10:00:00+00:00", NOW), "1d ago");
  assert.equal(postedLabel("2026-09-17T00:00:00+00:00", "2026-09-23T10:00:00+00:00", NOW), "6d ago");
  assert.equal(postedLabel("2026-09-02T00:00:00+00:00", "2026-09-23T10:00:00+00:00", NOW), "3w ago");
  assert.equal(postedLabel("2026-07-01T00:00:00+00:00", "2026-09-23T10:00:00+00:00", NOW), "2mo ago");
});

test("falls back to when we first saw it, and says so", () => {
  assert.equal(postedLabel(null, "2026-09-20T00:00:00+00:00", NOW), "seen 3d ago");
});

test("garbage in, empty label out", () => {
  assert.equal(postedLabel("nope", "also nope", NOW), "");
});

test("posted-within options match the API's accepted values", () => {
  assert.deepEqual(POSTED_WITHIN_OPTIONS.map((o) => o.days), [0, 1, 3, 7, 30]);
});

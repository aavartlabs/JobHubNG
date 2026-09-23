import { test } from "node:test";
import assert from "node:assert/strict";

import { safeNext, withNext } from "../src/nav.ts";

test("same-origin paths pass through", () => {
  assert.equal(safeNext("/jobs?job=12"), "/jobs?job=12");
  assert.equal(safeNext("/alerts"), "/alerts");
});

test("anything that could leave the site falls back to /jobs", () => {
  for (const bad of [
    null, "", "jobs", "https://evil.example", "//evil.example", "/\\evil.example",
    "\\\\evil.example", "javascript:alert(1)", "/jobs\nLocation: x", " /jobs",
  ]) {
    assert.equal(safeNext(bad), "/jobs", JSON.stringify(bad));
  }
});

test("withNext appends an encoded next only when it is safe and not the default", () => {
  assert.equal(withNext("/verify", "/jobs?job=12"), "/verify?next=%2Fjobs%3Fjob%3D12");
  assert.equal(withNext("/verify", "https://evil.example"), "/verify");
  assert.equal(withNext("/verify", "/jobs"), "/verify");
});

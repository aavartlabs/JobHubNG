import { test } from "node:test";
import assert from "node:assert/strict";

import { savedAction, savedLabel } from "../src/saving.ts";

test("save and unsave swap in the form action", () => {
  assert.equal(savedAction("https://x.example/jobs/7/save", true), "https://x.example/jobs/7/unsave");
  assert.equal(savedAction("/jobs/7/unsave", false), "/jobs/7/save");
  assert.equal(savedAction("/jobs/7/save", false), "/jobs/7/save");
});

test("the label flips but keeps the job title", () => {
  assert.equal(savedLabel("Save job: SRE", true), "Saved: SRE");
  assert.equal(savedLabel("Saved: SRE", false), "Save job: SRE");
});

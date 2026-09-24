import { test } from "node:test";
import assert from "node:assert/strict";

import { isJobsListReferrer } from "../src/back.ts";

const ORIGIN = "https://jobs.example";

test("the jobs list, with or without filters or a row anchor, counts", () => {
  for (const ref of [`${ORIGIN}/jobs`, `${ORIGIN}/jobs/`, `${ORIGIN}/jobs?title=sre&page=3`, `${ORIGIN}/jobs?page=2#job-9`]) {
    assert.equal(isJobsListReferrer(ref, ORIGIN), true, ref);
  }
});

test("job pages, other pages, other sites and junk don't", () => {
  for (const ref of ["", "not a url", `${ORIGIN}/jobs/12`, `${ORIGIN}/alerts`, "https://evil.example/jobs", "http://jobs.example/jobs"]) {
    assert.equal(isJobsListReferrer(ref, ORIGIN), false, ref);
  }
});

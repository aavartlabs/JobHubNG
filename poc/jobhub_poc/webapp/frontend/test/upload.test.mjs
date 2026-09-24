import { test } from "node:test";
import assert from "node:assert/strict";

import { fileTooLargeMessage, uploadPercent } from "../src/upload.ts";

test("upload percent is whole, clamped, and 0 when the size is unknown", () => {
  assert.equal(uploadPercent(512, 1024), 50);
  assert.equal(uploadPercent(1, 3), 33);
  assert.equal(uploadPercent(5000, 1024), 100);
  assert.equal(uploadPercent(10, 0), 0);
});

test("names both sizes in MB", () => {
  assert.equal(fileTooLargeMessage(6.2 * 1024 * 1024, 5 * 1024 * 1024),
    "That file is 6.2 MB; the limit is 5 MB. Try a smaller PDF or a DOCX.");
});

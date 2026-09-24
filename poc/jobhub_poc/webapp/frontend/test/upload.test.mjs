import { test } from "node:test";
import assert from "node:assert/strict";

import { fileTooLargeMessage } from "../src/upload.ts";

test("names both sizes in MB", () => {
  assert.equal(fileTooLargeMessage(6.2 * 1024 * 1024, 5 * 1024 * 1024),
    "That file is 6.2 MB; the limit is 5 MB. Try a smaller PDF or a DOCX.");
});

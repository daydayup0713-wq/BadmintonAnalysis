import assert from "node:assert/strict";
import test from "node:test";

import { importResultsUrl, stageName } from "./task-actions.ts";

test("labels an uploaded external job as waiting for results", () => {
  assert.equal(stageName("awaiting_results"), "等待导入分析结果");
});

test("builds the external import endpoint", () => {
  assert.equal(
    importResultsUrl("http://127.0.0.1:8000", "job-1"),
    "http://127.0.0.1:8000/api/jobs/job-1/results/import",
  );
});

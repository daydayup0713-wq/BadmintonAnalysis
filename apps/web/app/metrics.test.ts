import assert from "node:assert/strict";
import test from "node:test";

import {
  buildLandingMarkers,
  buildSpatialHeatmapCells,
  buildTimelineHeatmapSegments,
  buildQualityIssueKey,
  buildRallyClipDownload,
  currentVideoFrame,
  formatCandidateMetric,
  formatRecoveryMetrics,
  navigationKeyForPath,
  projectCourtRatio,
  selectAnalysisJobId,
  selectOriginalView,
  selectShuttleTrail,
  slotLabel,
  toggleOverlayLayer,
} from "./metrics.ts";

test("marks recovery metrics as missing evidence when summaries omit them", () => {
  assert.deepEqual(formatRecoveryMetrics(undefined), {
    returnRate: "missing_evidence",
    averageLatency: "missing_evidence",
  });
});

test("formats measured recovery metrics without changing their values", () => {
  assert.deepEqual(
    formatRecoveryMetrics({
      excursion_count: 4,
      completed_returns: 3,
      return_rate: 0.75,
      average_latency_seconds: 1.25,
    }),
    {
      returnRate: "75%",
      averageLatency: "1.25 s",
    },
  );
});

test("builds a downloadable rally clip URL from a Windows export path", () => {
  assert.deepEqual(
    buildRallyClipDownload(
      "http://127.0.0.1:8000",
      "job-1",
      String.raw`D:\exports\rallies\rally 001.mp4`,
    ),
    {
      name: "rally 001.mp4",
      href: "http://127.0.0.1:8000/api/jobs/job-1/exports/rallies/rally%20001.mp4",
    },
  );
});

test("builds stable unique keys for quality issues with duplicate codes", () => {
  const first = {
    code: "SHUTTLE_COVERAGE_LOW",
    message: "rally-1 coverage is below 80%",
    severity: "warning",
  };
  const second = {
    code: "SHUTTLE_COVERAGE_LOW",
    message: "rally-2 coverage is below 80%",
    severity: "warning",
  };

  const firstKey = buildQualityIssueKey(first, 0);
  const secondKey = buildQualityIssueKey(second, 1);

  assert.equal(firstKey, buildQualityIssueKey(first, 0));
  assert.notEqual(firstKey, secondKey);
});

test("selects the newest reviewable or completed analysis job", () => {
  assert.equal(
    selectAnalysisJobId([
      {
        id: "new-demo-review",
        stage: "review_required",
        source_path: String.raw`D:\repo\res\videos\test1\test1.mp4`,
      },
      {
        id: "real-completed",
        stage: "completed",
        source_path: String.raw`D:\repo\data\uploads\real.mp4`,
      },
    ]),
    "real-completed",
  );
  assert.equal(
    selectAnalysisJobId([{ id: "uploaded-only", stage: "uploaded" }]),
    undefined,
  );
});

test("turns overlay layers on independently and restores the original view", () => {
  const original = selectOriginalView();
  const skeleton = toggleOverlayLayer(original, "skeleton");
  const combined = toggleOverlayLayer(skeleton, "trajectory");

  assert.deepEqual(original, {
    skeleton: false,
    trajectory: false,
    landing: false,
  });
  assert.deepEqual(combined, {
    skeleton: true,
    trajectory: true,
    landing: false,
  });
  assert.deepEqual(selectOriginalView(), original);
});

test("selects the current frame and a bounded visible shuttle trail", () => {
  assert.equal(currentVideoFrame(1.26, 50, 750), 63);
  assert.equal(currentVideoFrame(20, 50, 750), 749);
  assert.deepEqual(
    selectShuttleTrail(
      [
        { frame: 60, x: 10, y: 20, visible: true },
        { frame: 61, x: 0, y: 0, visible: false },
        { frame: 62, x: 12, y: 22, visible: true },
        { frame: 63, x: 13, y: 23, visible: true },
        { frame: 64, x: 14, y: 24, visible: true },
      ],
      63,
      2,
    ),
    [
      { frame: 62, x: 12, y: 22, visible: true },
      { frame: 63, x: 13, y: 23, visible: true },
    ],
  );
});

test("projects normalized landing zones and assigns their display frames", () => {
  assert.deepEqual(
    projectCourtRatio(
      [
        [100, 100],
        [300, 100],
        [80, 200],
        [320, 200],
        [50, 400],
        [350, 400],
      ],
      0.5,
      0.5,
    ),
    { x: 200, y: 250 },
  );
  assert.deepEqual(
    buildLandingMarkers(
      [
        {
          id: "shot-10",
          hit_frame: 10,
          rally_id: "rally-1",
          landing_zone: { x_ratio: 0.25, y_ratio: 0.75, zone: "bottom-mid-left" },
        },
        {
          id: "shot-20",
          hit_frame: 20,
          rally_id: "rally-1",
          landing_zone: { x_ratio: 0.75, y_ratio: 0.25, zone: "top-mid-right" },
        },
      ],
      [{ id: "rally-1", end_frame: 40 }],
    ),
    [
      {
        id: "shot-10",
        frame: 19,
        x_ratio: 0.25,
        y_ratio: 0.75,
        zone: "bottom-mid-left",
      },
      {
        id: "shot-20",
        frame: 40,
        x_ratio: 0.75,
        y_ratio: 0.25,
        zone: "top-mid-right",
      },
    ],
  );
});

test("maps real routes to the active top navigation item", () => {
  assert.equal(navigationKeyForPath("/analysis"), "analysis");
  assert.equal(navigationKeyForPath("/tasks/job-1"), "tasks");
  assert.equal(navigationKeyForPath("/athletes"), "athletes");
});

test("uses court-slot labels instead of claiming stable athlete identity", () => {
  assert.equal(slotLabel("top"), "上半场槽位");
  assert.equal(slotLabel("bottom"), "下半场槽位");
  assert.equal(slotLabel("unknown"), "未知槽位");
});

test("formats candidate metrics without presenting missing evidence as zero", () => {
  assert.deepEqual(
    formatCandidateMetric(4.84, "m/s", "missing_evidence"),
    {
      value: "4.84 m/s",
      evidence: "2D候选 · 缺少人工GT",
    },
  );
  assert.deepEqual(
    formatCandidateMetric(null, "m", "missing_evidence"),
    {
      value: "证据不足",
      evidence: "有效轨迹不足",
    },
  );
});

test("builds bounded spatial and timeline heatmap render data", () => {
  const spatial = buildSpatialHeatmapCells([
    [0, 50, 100],
    [25, 0, 75],
  ]);
  const timeline = buildTimelineHeatmapSegments([
    {
      start_seconds: 0,
      end_seconds: 0.5,
      intensity_index: 80,
      event_count: 1,
      low_confidence_count: 1,
    },
  ]);

  assert.equal(spatial.length, 6);
  assert.deepEqual(spatial.at(-1), {
    row: 1,
    column: 2,
    intensity: 75,
    opacity: 0.75,
  });
  assert.deepEqual(timeline[0], {
    startSeconds: 0,
    endSeconds: 0.5,
    intensity: 80,
    opacity: 0.52,
    eventCount: 1,
  });
});

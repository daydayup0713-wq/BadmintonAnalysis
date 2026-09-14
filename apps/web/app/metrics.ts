export type RecoveryMetric = {
  excursion_count: number;
  completed_returns: number;
  return_rate: number;
  average_latency_seconds: number | null;
};

export type OverlayLayer = "skeleton" | "trajectory" | "landing";

export type OverlayLayers = Record<OverlayLayer, boolean>;

export type NavigationKey = "analysis" | "tasks" | "athletes";

export type TimelineHeatmapBin = {
  start_seconds: number;
  end_seconds: number;
  intensity_index: number;
  event_count: number;
  low_confidence_count: number;
};

export type ShuttleTrailPoint = {
  frame: number;
  x: number;
  y: number;
  visible: boolean;
};

export type LandingMarker = {
  id: string;
  frame: number;
  x_ratio: number;
  y_ratio: number;
  zone: string;
};

export function selectOriginalView(): OverlayLayers {
  return {
    skeleton: false,
    trajectory: false,
    landing: false,
  };
}

export function navigationKeyForPath(pathname: string): NavigationKey {
  if (pathname.startsWith("/tasks")) return "tasks";
  if (pathname.startsWith("/athletes")) return "athletes";
  return "analysis";
}

export function slotLabel(side: "top" | "bottom" | "unknown") {
  if (side === "top") return "上半场槽位";
  if (side === "bottom") return "下半场槽位";
  return "未知槽位";
}

export function formatCandidateMetric(
  value: number | null | undefined,
  unit: string,
  validationStatus: string,
) {
  if (value === null || value === undefined) {
    return {
      value: "证据不足",
      evidence: "有效轨迹不足",
    };
  }
  return {
    value: `${value} ${unit}`.trim(),
    evidence:
      validationStatus === "missing_evidence"
        ? "2D候选 · 缺少人工GT"
        : "已验证",
  };
}

export function buildSpatialHeatmapCells(matrix: number[][]) {
  return matrix.flatMap((row, rowIndex) =>
    row.map((value, columnIndex) => {
      const intensity = Math.min(Math.max(value, 0), 100);
      return {
        row: rowIndex,
        column: columnIndex,
        intensity,
        opacity: intensity / 100,
      };
    }),
  );
}

export function buildTimelineHeatmapSegments(bins: TimelineHeatmapBin[]) {
  return bins.map((bin) => {
    const intensity = Math.min(Math.max(bin.intensity_index, 0), 100);
    const confidenceMultiplier =
      bin.low_confidence_count > 0 && bin.event_count > 0 ? 0.65 : 1;
    return {
      startSeconds: bin.start_seconds,
      endSeconds: bin.end_seconds,
      intensity,
      opacity: (intensity / 100) * confidenceMultiplier,
      eventCount: bin.event_count,
    };
  });
}

export function toggleOverlayLayer(
  layers: OverlayLayers,
  layer: OverlayLayer,
): OverlayLayers {
  return {
    ...layers,
    [layer]: !layers[layer],
  };
}

export function currentVideoFrame(
  currentTimeSeconds: number,
  fps: number,
  totalFrames: number,
) {
  if (fps <= 0 || totalFrames <= 0) return 0;
  return Math.min(
    Math.max(Math.round(currentTimeSeconds * fps), 0),
    totalFrames - 1,
  );
}

export function selectShuttleTrail<T extends ShuttleTrailPoint>(
  points: T[],
  currentFrame: number,
  maxLength = 14,
) {
  const limit = Math.max(maxLength, 0);
  if (limit === 0 || points.length === 0) return [];
  let low = 0;
  let high = points.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (points[middle].frame <= currentFrame) low = middle + 1;
    else high = middle;
  }
  const trail: T[] = [];
  for (let index = low - 1; index >= 0 && trail.length < limit; index -= 1) {
    const point = points[index];
    if (point.visible && (point.x !== 0 || point.y !== 0)) {
      trail.push(point);
    }
  }
  return trail.reverse();
}

export function projectCourtRatio(
  courtPoints: number[][],
  xRatio: number,
  yRatio: number,
) {
  if (courtPoints.length !== 6) return null;
  const topLeft = courtPoints[0];
  const topRight = courtPoints[1];
  const bottomLeft = courtPoints[4];
  const bottomRight = courtPoints[5];
  if (
    !topLeft ||
    !topRight ||
    !bottomLeft ||
    !bottomRight
  ) {
    return null;
  }
  const leftX = topLeft[0] + (bottomLeft[0] - topLeft[0]) * yRatio;
  const rightX = topRight[0] + (bottomRight[0] - topRight[0]) * yRatio;
  return {
    x: leftX + (rightX - leftX) * xRatio,
    y: topLeft[1] + (bottomLeft[1] - topLeft[1]) * yRatio,
  };
}

export function buildLandingMarkers(
  shots: Array<{
    id: string;
    hit_frame: number;
    rally_id?: string;
    landing_zone?: {
      x_ratio?: number;
      y_ratio?: number;
      zone?: string;
    } | null;
  }>,
  rallies: Array<{ id: string; end_frame: number }>,
): LandingMarker[] {
  const rallyEnds = new Map(
    rallies.map((rally) => [rally.id, rally.end_frame]),
  );
  const ordered = [...shots].sort((left, right) => left.hit_frame - right.hit_frame);
  return ordered.flatMap((shot, index) => {
    const landing = shot.landing_zone;
    if (
      !landing ||
      typeof landing.x_ratio !== "number" ||
      typeof landing.y_ratio !== "number"
    ) {
      return [];
    }
    const nextShot = ordered
      .slice(index + 1)
      .find((candidate) => candidate.rally_id === shot.rally_id);
    const rallyEnd = shot.rally_id
      ? rallyEnds.get(shot.rally_id)
      : undefined;
    const frame = nextShot
      ? nextShot.hit_frame - 1
      : rallyEnd ?? shot.hit_frame;
    return [
      {
        id: shot.id,
        frame,
        x_ratio: landing.x_ratio,
        y_ratio: landing.y_ratio,
        zone: landing.zone ?? "unknown",
      },
    ];
  });
}

export function buildQualityIssueKey(
  issue: { code: string; message: string; severity: string },
  index: number,
) {
  return `${issue.code}:${issue.severity}:${issue.message}:${index}`;
}

export function selectAnalysisJobId(
  jobs: Array<{ id: string; stage: string; source_path?: string }>,
) {
  const eligible = jobs.filter(
    (job) => job.stage === "review_required" || job.stage === "completed",
  );
  const uploaded = eligible.find((job) =>
    job.source_path?.replaceAll("\\", "/").includes("/data/uploads/"),
  );
  return uploaded?.id ?? eligible[0]?.id;
}

export function formatRecoveryMetrics(recovery?: RecoveryMetric) {
  if (!recovery) {
    return {
      returnRate: "missing_evidence",
      averageLatency: "missing_evidence",
    };
  }
  return {
    returnRate: `${Math.round(recovery.return_rate * 100)}%`,
    averageLatency:
      recovery.average_latency_seconds === null
        ? "missing_evidence"
        : `${recovery.average_latency_seconds} s`,
  };
}

export function buildRallyClipDownload(
  apiUrl: string,
  jobId: string,
  clipPath: string,
) {
  const name = clipPath.split(/[\\/]/).at(-1) ?? clipPath;
  return {
    name,
    href: `${apiUrl}/api/jobs/${jobId}/exports/rallies/${encodeURIComponent(name)}`,
  };
}

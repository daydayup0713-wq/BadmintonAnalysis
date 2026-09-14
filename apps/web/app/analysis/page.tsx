"use client";

import { type RefObject, useEffect, useMemo, useRef, useState } from "react";

import {
  buildSpatialHeatmapCells,
  buildTimelineHeatmapSegments,
  buildLandingMarkers,
  buildRallyClipDownload,
  currentVideoFrame,
  formatCandidateMetric,
  formatRecoveryMetrics,
  projectCourtRatio,
  selectAnalysisJobId,
  selectOriginalView,
  selectShuttleTrail,
  slotLabel,
  toggleOverlayLayer,
  type OverlayLayer,
  type OverlayLayers,
  type RecoveryMetric,
} from "../metrics";

type Job = {
  id: string;
  stage: string;
  progress: number;
  source_path: string;
};

type Rally = {
  id: string;
  start_frame: number;
  end_frame: number;
  start_timestamp_us: number;
  confidence: number;
  winner_candidate?: "top" | "bottom" | "unknown";
  outcome_reason?: string;
  phase_transitions?: Array<{
    player: "top" | "bottom";
    from_phase: "attack" | "defense";
    to_phase: "attack" | "defense";
  }>;
};

type Hit = {
  frame: number;
  timestamp_us: number;
  player: "top" | "bottom" | "unknown";
  confidence: number;
};

type Shot = {
  id: string;
  hit_frame: number;
  timestamp_us: number;
  rally_id?: string;
  player: "top" | "bottom" | "unknown";
  label: string;
  confidence: number;
  origin: "external" | "interpolated" | "human";
  hitter_phase?: "attack" | "neutral" | "unknown";
  opponent_phase?: "defense" | "neutral";
  landing_zone?: {
    in_court: boolean;
    court_side: "top" | "bottom";
    lateral: "left" | "center" | "right";
    longitudinal: "front" | "mid" | "rear";
    zone: string;
    x_ratio?: number;
    y_ratio?: number;
  } | null;
};

type PoseFrame = {
  frame: number;
  top_keypoints: number[][] | null;
  bottom_keypoints: number[][] | null;
};

type PosePayload = {
  frames: PoseFrame[];
};

type ShuttlePoint = {
  frame: number;
  x: number;
  y: number;
  visible: boolean;
  confidence: number;
  origin: "external" | "interpolated";
};

type ShuttlePayload = {
  points: ShuttlePoint[];
};

type PlayerMetric = {
  distance_m: number | null;
  average_speed_mps: number | null;
  max_effective_speed_mps: number | null;
  trajectory_valid_ratio: number;
  validation_status: "missing_evidence" | "pass";
  quality_label: string;
  heatmap: number[][];
  track: Array<{
    frame: number;
    x_m: number;
    y_m: number;
    speed_mps: number;
    valid: boolean;
  }>;
  recovery?: RecoveryMetric;
  diagnostics: {
    raw_distance_m: number;
    raw_max_speed_mps: number;
    rejected_segment_count: number;
    valid_segment_count: number;
    total_segment_count: number;
  };
};

type SwingPlayerMetric = {
  hit_count: number;
  low_confidence_hit_count: number;
  average_intensity_index: number | null;
  peak_intensity_index: number | null;
  validation_status: "missing_evidence" | "pass";
  quality_label: string;
  spatial_heatmap: number[][];
  timeline_heatmap: Array<{
    start_seconds: number;
    end_seconds: number;
    intensity_index: number;
    event_count: number;
    low_confidence_count: number;
  }>;
};

type ExportResult = {
  json: string;
  shots_csv: string;
  movement_csv: string;
  pdf: string;
  video: string;
  rally_clips: string[];
};

type Summary = {
  job: Job;
  video: {
    fps: number;
    width: number;
    height: number;
    total_frames: number;
    duration_seconds?: number;
  } | null;
  calibration: {
    court_points: number[][];
  } | null;
  rallies: Rally[];
  hits: Hit[];
  shots: Shot[];
  metrics: {
    available: boolean;
    missing_evidence: string[];
    players: {
      top: PlayerMetric;
      bottom: PlayerMetric;
    };
    biomechanics?: {
      top: {
        max_wrist_acceleration_px_s2: number;
        start_step_candidates: number[];
        lunge_candidates: number[];
      };
      bottom: {
        max_wrist_acceleration_px_s2: number;
        start_step_candidates: number[];
        lunge_candidates: number[];
      };
    };
    swings?: {
      top: SwingPlayerMetric;
      bottom: SwingPlayerMetric;
    };
  } | null;
  review: {
    status?: string;
    issue_count?: number;
    missing_evidence?: string[];
  };
};

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

const SKELETON_EDGES = [
  [0, 1],
  [0, 2],
  [1, 3],
  [2, 4],
  [5, 6],
  [5, 7],
  [7, 9],
  [6, 8],
  [8, 10],
  [5, 11],
  [6, 12],
  [11, 12],
  [11, 13],
  [13, 15],
  [12, 14],
  [14, 16],
] as const;

const shotNames: Record<string, string> = {
  smash: "杀球",
  drive: "平抽",
  clear_or_lift: "高远 / 挑球",
  net_or_drop: "网前 / 吊球",
  drop_or_push: "吊推",
  unknown: "待判定",
};

function formatTime(timestampUs: number) {
  const seconds = timestampUs / 1_000_000;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

function MiniCourt({ player }: { player?: PlayerMetric }) {
  const points = player?.track.filter((point) => point.valid) ?? [];
  const sampled = points.filter((_, index) => index % 18 === 0).slice(-42);
  return (
    <div className="miniCourt" aria-label="场上槽位跑位图">
      <div className="courtLine centerLine" />
      <div className="courtLine serviceTop" />
      <div className="courtLine serviceBottom" />
      {sampled.map((point, index) => (
        <span
          className="trackPoint"
          key={`${point.frame}-${index}`}
          style={{
            left: `${(point.x_m / 6.1) * 100}%`,
            top: `${(point.y_m / 13.4) * 100}%`,
            opacity: 0.18 + (index / Math.max(sampled.length, 1)) * 0.8,
          }}
        />
      ))}
      {sampled.length > 0 && (
        <span
          className="currentPoint"
          style={{
            left: `${(sampled.at(-1)!.x_m / 6.1) * 100}%`,
            top: `${(sampled.at(-1)!.y_m / 13.4) * 100}%`,
          }}
        />
      )}
    </div>
  );
}

function SwingHeatmaps({ swing }: { swing?: SwingPlayerMetric }) {
  const spatial = buildSpatialHeatmapCells(swing?.spatial_heatmap ?? []);
  const timeline = buildTimelineHeatmapSegments(
    swing?.timeline_heatmap ?? [],
  );
  return (
    <div className="swingHeatmaps">
      <div>
        <div className="heatmapHeading">
          <strong>场地挥拍强度</strong>
          <span>位置 × 相对指数</span>
        </div>
        <div className="strengthCourt" aria-label="场地挥拍强度热力图">
          {spatial.map((cell) => (
            <span
              key={`${cell.row}-${cell.column}`}
              style={{
                gridColumn: cell.column + 1,
                gridRow: cell.row + 1,
                backgroundColor: `rgba(239, 141, 73, ${cell.opacity})`,
              }}
              title={`强度 ${cell.intensity}`}
            />
          ))}
        </div>
      </div>
      <div>
        <div className="heatmapHeading">
          <strong>时间强度热力带</strong>
          <span>每 0.5 秒</span>
        </div>
        <div className="strengthTimeline" aria-label="时间挥拍强度热力带">
          {timeline.map((segment) => (
            <span
              key={`${segment.startSeconds}-${segment.endSeconds}`}
              style={{
                backgroundColor: `rgba(239, 141, 73, ${segment.opacity})`,
              }}
              title={`${segment.startSeconds.toFixed(1)}s · 强度 ${segment.intensity} · ${segment.eventCount} 次`}
            />
          ))}
        </div>
        <p className="heatmapNote">
          颜色表示当前视频内的相对挥拍强度；低置信击球降低透明度。
        </p>
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  unit,
  accent,
}: {
  label: string;
  value: string | number;
  unit?: string;
  accent?: boolean;
}) {
  return (
    <article className={`metricCard ${accent ? "accent" : ""}`}>
      <span>{label}</span>
      <strong>
        {value}
        {unit && <small>{unit}</small>}
      </strong>
    </article>
  );
}

function Skeleton({
  keypoints,
  className,
}: {
  keypoints: number[][] | null;
  className: string;
}) {
  if (!keypoints || keypoints.length !== 17) return null;
  return (
    <g className={className}>
      {SKELETON_EDGES.map(([first, second]) => (
        <line
          key={`${first}-${second}`}
          x1={keypoints[first][0]}
          y1={keypoints[first][1]}
          x2={keypoints[second][0]}
          y2={keypoints[second][1]}
        />
      ))}
      {keypoints.map(([x, y], index) => (
        <circle cx={x} cy={y} key={index} r="4" />
      ))}
    </g>
  );
}

function VideoOverlay({
  videoRef,
  summary,
  posePayload,
  shuttlePayload,
  layers,
}: {
  videoRef: RefObject<HTMLVideoElement | null>;
  summary: Summary;
  posePayload: PosePayload | null;
  shuttlePayload: ShuttlePayload | null;
  layers: OverlayLayers;
}) {
  const [currentFrame, setCurrentFrame] = useState(0);
  const fps = summary.video?.fps ?? 0;
  const totalFrames = summary.video?.total_frames ?? 0;
  const width = summary.video?.width ?? 1920;
  const height = summary.video?.height ?? 1080;

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    let callbackId: number | null = null;
    const update = () => {
      setCurrentFrame(currentVideoFrame(video.currentTime, fps, totalFrames));
    };
    const updateWithNextFrame = () => {
      update();
      if (typeof video.requestVideoFrameCallback === "function") {
        callbackId = video.requestVideoFrameCallback(updateWithNextFrame);
      }
    };
    update();
    video.addEventListener("seeked", update);
    video.addEventListener("timeupdate", update);
    if (typeof video.requestVideoFrameCallback === "function") {
      callbackId = video.requestVideoFrameCallback(updateWithNextFrame);
    }
    return () => {
      video.removeEventListener("seeked", update);
      video.removeEventListener("timeupdate", update);
      if (
        callbackId !== null &&
        typeof video.cancelVideoFrameCallback === "function"
      ) {
        video.cancelVideoFrameCallback(callbackId);
      }
    };
  }, [fps, totalFrames, videoRef]);

  const poseByFrame = useMemo(
    () =>
      new Map(
        (posePayload?.frames ?? []).map((frame) => [frame.frame, frame]),
      ),
    [posePayload],
  );
  const shuttlePoints = useMemo(
    () => shuttlePayload?.points ?? [],
    [shuttlePayload],
  );
  const trail = useMemo(
    () => selectShuttleTrail(shuttlePoints, currentFrame),
    [currentFrame, shuttlePoints],
  );
  const landingMarkers = useMemo(
    () => buildLandingMarkers(summary.shots, summary.rallies),
    [summary.rallies, summary.shots],
  );
  const pose = poseByFrame.get(currentFrame);
  const courtPoints = summary.calibration?.court_points ?? [];

  if (!layers.skeleton && !layers.trajectory && !layers.landing) return null;

  return (
    <svg
      aria-label="视频分析叠加层"
      className="videoOverlay"
      data-frame={currentFrame}
      preserveAspectRatio="xMidYMid meet"
      viewBox={`0 0 ${width} ${height}`}
    >
      {layers.skeleton && pose && (
        <>
          <Skeleton className="skeleton top" keypoints={pose.top_keypoints} />
          <Skeleton
            className="skeleton bottom"
            keypoints={pose.bottom_keypoints}
          />
        </>
      )}
      {layers.trajectory && (
        <g className="shuttleTrail">
          {trail.map((point, index) => (
            <circle
              className={point.origin === "interpolated" ? "interpolated" : ""}
              cx={point.x}
              cy={point.y}
              key={`${point.frame}-${index}`}
              opacity={
                0.25 + 0.75 * ((index + 1) / Math.max(trail.length, 1))
              }
              r={Math.max(
                4,
                10 * ((index + 1) / Math.max(trail.length, 1)),
              )}
            />
          ))}
        </g>
      )}
      {layers.landing && (
        <g className="landingMarkers">
          {landingMarkers.map((marker) => {
            const point = projectCourtRatio(
              courtPoints,
              marker.x_ratio,
              marker.y_ratio,
            );
            if (!point) return null;
            const isRecent = Math.abs(currentFrame - marker.frame) <= fps;
            return (
              <g
                className={isRecent ? "recent" : ""}
                key={marker.id}
                transform={`translate(${point.x} ${point.y})`}
              >
                <circle r={isRecent ? 18 : 12} />
                <line x1="-8" x2="8" y1="-8" y2="8" />
                <line x1="-8" x2="8" y1="8" y2="-8" />
                <title>{marker.zone}</title>
              </g>
            );
          })}
        </g>
      )}
    </svg>
  );
}

export default function Home() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [posePayload, setPosePayload] = useState<PosePayload | null>(null);
  const [shuttlePayload, setShuttlePayload] =
    useState<ShuttlePayload | null>(null);
  const [overlayLayers, setOverlayLayers] =
    useState<OverlayLayers>(selectOriginalView);
  const [activeRally, setActiveRally] = useState(0);
  const [activePlayer, setActivePlayer] = useState<"top" | "bottom">("bottom");
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null);
  const [exports, setExports] = useState<ExportResult | null>(null);
  const [status, setStatus] = useState("连接分析服务");
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setStatus("加载分析任务");
        const jobsResponse = await fetch(`${API_URL}/api/jobs`);
        const jobs: Job[] = jobsResponse.ok ? await jobsResponse.json() : [];
        const requestedJobId = new URLSearchParams(
          window.location.search,
        ).get("job");
        let jobId = requestedJobId ?? selectAnalysisJobId(jobs);
        if (!jobId) {
          const bootstrap = await fetch(`${API_URL}/api/demo/bootstrap`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
          });
          if (!bootstrap.ok) throw new Error("无法创建合成分析示例");
          const payload = await bootstrap.json();
          jobId = payload.job.id;
        }
        const response = await fetch(`${API_URL}/api/jobs/${jobId}/summary`);
        if (!response.ok) throw new Error("分析摘要读取失败");
        const payload = await response.json();
        if (!cancelled) {
          setSummary(payload);
          setStatus("等待人工复核");
        }
        const [poseResponse, shuttleResponse] = await Promise.all([
          fetch(`${API_URL}/api/jobs/${jobId}/results/pose_tracking`),
          fetch(`${API_URL}/api/jobs/${jobId}/results/shuttle_tracking`),
        ]);
        if (!cancelled && poseResponse.ok && shuttleResponse.ok) {
          setPosePayload(await poseResponse.json());
          setShuttlePayload(await shuttleResponse.json());
        } else if (!cancelled) {
          setStatus("分析已加载，视频叠加数据不可用");
        }
      } catch (error) {
        if (!cancelled) {
          setStatus(error instanceof Error ? error.message : "服务不可用");
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedRally = summary?.rallies[activeRally];
  const selectedPlayer = summary?.metrics?.players[activePlayer];
  const selectedBiomechanics =
    summary?.metrics?.biomechanics?.[activePlayer];
  const selectedSwing = summary?.metrics?.swings?.[activePlayer];
  const recoveryDisplay = formatRecoveryMetrics(selectedPlayer?.recovery);
  const distanceDisplay = formatCandidateMetric(
    selectedPlayer?.distance_m,
    "m",
    selectedPlayer?.validation_status ?? "missing_evidence",
  );
  const maxSpeedDisplay = formatCandidateMetric(
    selectedPlayer?.max_effective_speed_mps,
    "m/s",
    selectedPlayer?.validation_status ?? "missing_evidence",
  );
  const averageSpeedDisplay = formatCandidateMetric(
    selectedPlayer?.average_speed_mps,
    "m/s",
    selectedPlayer?.validation_status ?? "missing_evidence",
  );
  const rallyShots = useMemo(() => {
    if (!selectedRally || !summary) return [];
    return summary.shots.filter(
      (shot) =>
        shot.hit_frame >= selectedRally.start_frame &&
        shot.hit_frame <= selectedRally.end_frame,
    );
  }, [selectedRally, summary]);
  const selectedShot = rallyShots.find(
    (shot) => shot.id === selectedShotId,
  );
  const overlayAvailability: Record<OverlayLayer, boolean> = {
    skeleton: Boolean(posePayload?.frames.length),
    trajectory: Boolean(
      shuttlePayload?.points.length,
    ),
    landing: Boolean(
      summary &&
        summary.calibration?.court_points.length === 6 &&
        buildLandingMarkers(summary.shots, summary.rallies).length > 0,
    ),
  };

  async function reviseShot(
    fieldName: "label" | "player",
    newValue: string,
  ) {
    if (!summary || !selectedShot) return;
    const oldValue = selectedShot[fieldName];
    if (oldValue === newValue) return;
    setStatus("保存人工修订");
    const response = await fetch(`${API_URL}/api/revisions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_id: summary.job.id,
        entity_type: "shot",
        entity_id: selectedShot.id,
        field_name: fieldName,
        old_value: oldValue,
        new_value: newValue,
        reason: "网页分析台人工复核",
      }),
    });
    if (!response.ok) {
      setStatus("修订保存失败");
      return;
    }
    const refreshed = await fetch(
      `${API_URL}/api/jobs/${summary.job.id}/summary`,
    );
    setSummary(await refreshed.json());
    setStatus("人工修订已保存");
  }

  async function createExports() {
    if (!summary) return;
    setStatus("正在生成导出文件");
    const response = await fetch(
      `${API_URL}/api/jobs/${summary.job.id}/exports`,
      { method: "POST" },
    );
    if (!response.ok) {
      const error = await response.json().catch(() => null);
      setStatus(error?.detail ?? "导出失败");
      return;
    }
    setExports(await response.json());
    setStatus("导出文件已生成");
  }

  return (
    <main>
      <section className="pageHeader">
        <div>
          <p className="eyebrow">比赛分析 / {summary?.job.id.slice(-8) ?? "本地任务"}</p>
          <h1>双人回合与跑位复核</h1>
          <p className="subline">
            原始结果保留外部提供方置信度，所有低于门槛的结论进入人工审核。
          </p>
        </div>
        <div className="headerActions">
          <span className="statusPill">{status}</span>
          <button className="secondaryButton" onClick={createExports}>
            导出数据
          </button>
          <button className="primaryButton" onClick={createExports}>
            生成分析视频
          </button>
        </div>
      </section>
      {exports && summary && (
        <section className="exportBar">
          <span>导出完成</span>
          {[
            ["JSON", "json"],
            ["击球 CSV", "shots.csv"],
            ["跑位 CSV", "movement.csv"],
            ["PDF", "report.pdf"],
            ["叠加视频", "video.mp4"],
          ].map(([label, artifact]) => (
            <a
              href={`${API_URL}/api/jobs/${summary.job.id}/exports/${artifact}`}
              key={artifact}
            >
              {label}
            </a>
          ))}
          {exports.rally_clips.map((clipPath, index) => {
            const clip = buildRallyClipDownload(
              API_URL,
              summary.job.id,
              clipPath,
            );
            return (
              <a href={clip.href} key={clip.name}>
                回合剪辑 {index + 1}
              </a>
            );
          })}
          <small>{exports.rally_clips.length} 个回合剪辑已生成</small>
        </section>
      )}

      <section className="workspace">
        <div className="videoColumn">
          <div className="videoStage">
            {summary ? (
              <>
                <video
                  controls
                  preload="metadata"
                  ref={videoRef}
                  src={`${API_URL}/api/jobs/${summary.job.id}/video`}
                />
                <VideoOverlay
                  layers={overlayLayers}
                  posePayload={posePayload}
                  shuttlePayload={shuttlePayload}
                  summary={summary}
                  videoRef={videoRef}
                />
              </>
            ) : (
              <div className="videoPlaceholder">
                <span className="loader" />
                正在装载本地视频
              </div>
            )}
            <div className="videoHud topHud">
              <button
                aria-pressed={
                  !overlayLayers.skeleton &&
                  !overlayLayers.trajectory &&
                  !overlayLayers.landing
                }
                onClick={() => setOverlayLayers(selectOriginalView())}
              >
                原片
              </button>
              {(
                [
                  ["skeleton", "骨架"],
                  ["trajectory", "球轨迹"],
                  ["landing", "落点"],
                ] as Array<[OverlayLayer, string]>
              ).map(([layer, label]) => (
                <button
                  aria-pressed={overlayLayers[layer]}
                  disabled={!overlayAvailability[layer]}
                  key={layer}
                  onClick={() =>
                    setOverlayLayers((current) =>
                      toggleOverlayLayer(current, layer),
                    )
                  }
                  title={
                    overlayAvailability[layer]
                      ? `切换${label}叠加层`
                      : `${label}数据不可用`
                  }
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="confidenceLegend">
              <span><i className="good" />可信</span>
              <span><i className="review" />待复核</span>
            </div>
          </div>

          <div className="timelinePanel">
            <div className="timelineHeader">
              <div>
                <strong>回合时间轴</strong>
                <span>{summary?.rallies.length ?? 0} 个有效回合</span>
              </div>
              <span>击球候选 {summary?.hits.length ?? 0}</span>
            </div>
            <div className="timeline">
              <div className="timelineRail" />
              {summary?.rallies.map((rally, index) => {
                const total = summary.video?.total_frames ?? 1;
                return (
                  <button
                    key={rally.start_frame}
                    className={`rallyBlock ${activeRally === index ? "selected" : ""}`}
                    style={{
                      left: `${(rally.start_frame / total) * 100}%`,
                      width: `${Math.max(
                        ((rally.end_frame - rally.start_frame) / total) * 100,
                        4,
                      )}%`,
                    }}
                    onClick={() => setActiveRally(index)}
                    title={`回合 ${index + 1}`}
                  />
                );
              })}
              {summary?.hits.map((hit) => (
                <i
                  key={`${hit.frame}-${hit.player}`}
                  className={`hitMark ${hit.confidence < 0.7 ? "low" : ""}`}
                  style={{
                    left: `${(hit.frame / (summary.video?.total_frames ?? 1)) * 100}%`,
                  }}
                />
              ))}
            </div>
            <div className="rallyTabs">
              {summary?.rallies.map((rally, index) => (
                <button
                  className={activeRally === index ? "active" : ""}
                  key={rally.start_frame}
                  onClick={() => setActiveRally(index)}
                >
                  <span>R{String(index + 1).padStart(2, "0")}</span>
                  {formatTime(rally.start_timestamp_us ?? 0)}
                </button>
              ))}
            </div>
          </div>
        </div>

        <aside className="insightPanel">
          <div className="panelTitle">
            <div>
              <p className="eyebrow">当前回合</p>
              <h2>R{String(activeRally + 1).padStart(2, "0")}</h2>
            </div>
            <span className="reviewBadge">需复核</span>
          </div>
          <div className="outcomeCandidate">
            <span>回合胜方候选</span>
            <strong>
              {selectedRally?.winner_candidate === "top"
                ? slotLabel("top")
                : selectedRally?.winner_candidate === "bottom"
                  ? slotLabel("bottom")
                  : "待判定"}
            </strong>
            <small>{selectedRally?.outcome_reason ?? "等待轨迹分析"}</small>
          </div>

          <div className="playerSwitch">
            <button
              className={activePlayer === "top" ? "active" : ""}
              onClick={() => setActivePlayer("top")}
            >
              {slotLabel("top")}
            </button>
            <button
              className={activePlayer === "bottom" ? "active" : ""}
              onClick={() => setActivePlayer("bottom")}
            >
              {slotLabel("bottom")}
            </button>
          </div>

          <MiniCourt player={selectedPlayer} />

          <div className="compactMetrics">
            <div>
              <span>跑动距离</span>
              <strong>{distanceDisplay.value}</strong>
              <small>{distanceDisplay.evidence}</small>
            </div>
            <div>
              <span>最高有效速度 P95</span>
              <strong>{maxSpeedDisplay.value}</strong>
              <small>{maxSpeedDisplay.evidence}</small>
            </div>
            <div>
              <span>平均有效速度</span>
              <strong>{averageSpeedDisplay.value}</strong>
              <small>{averageSpeedDisplay.evidence}</small>
            </div>
            <div>
              <span>击球次数</span>
              <strong>{selectedSwing?.hit_count ?? 0} 次</strong>
              <small>
                低置信 {selectedSwing?.low_confidence_hit_count ?? 0} 次
              </small>
            </div>
            <div>
              <span>平均挥拍强度</span>
              <strong>
                {selectedSwing?.average_intensity_index ?? "证据不足"}
              </strong>
              <small>0–100 视频内相对指数</small>
            </div>
            <div>
              <span>峰值挥拍强度</span>
              <strong>{selectedSwing?.peak_intensity_index ?? "证据不足"}</strong>
              <small>非牛顿力值</small>
            </div>
          </div>
          <SwingHeatmaps swing={selectedSwing} />
          <div className="recoveryStrip">
            <span>回中成功率 <strong>{recoveryDisplay.returnRate}</strong></span>
            <span>平均回中耗时 <strong>{recoveryDisplay.averageLatency}</strong></span>
            <span>
              攻防转换{" "}
              <strong>
                {selectedRally?.phase_transitions?.filter(
                  (transition) => transition.player === activePlayer,
                ).length ?? 0} 次
              </strong>
            </span>
          </div>
          <details className="diagnosticsPanel">
            <summary>原始诊断数据</summary>
            <p>
              原始距离 {selectedPlayer?.diagnostics.raw_distance_m ?? "—"} m ·
              原始单帧峰值{" "}
              {selectedPlayer?.diagnostics.raw_max_speed_mps ?? "—"} m/s ·
              剔除片段{" "}
              {selectedPlayer?.diagnostics.rejected_segment_count ?? "—"}
            </p>
            <p>
              二维手腕峰值加速度{" "}
              {selectedBiomechanics?.max_wrist_acceleration_px_s2 ?? "—"} px/s² ·
              启动步逐帧候选{" "}
              {selectedBiomechanics?.start_step_candidates.length ?? "—"} ·
              弓步逐帧候选{" "}
              {selectedBiomechanics?.lunge_candidates.length ?? "—"}
            </p>
            <small>以上为未验证诊断量，不用于主界面结论。</small>
          </details>

          <div className="shotList">
            <div className="sectionLabel">
              <span>击球序列</span>
              <span>{rallyShots.length} 次</span>
            </div>
            {rallyShots.slice(0, 7).map((shot, index) => (
              <button
                className={`shotRow ${selectedShotId === shot.id ? "selected" : ""}`}
                key={shot.id}
                onClick={() => setSelectedShotId(shot.id)}
              >
                <span className={`shotIndex ${shot.player}`}>{index + 1}</span>
                <span>
                  <strong>{shotNames[shot.label] ?? shot.label}</strong>
                  <small>
                    {formatTime(shot.timestamp_us)}
                    {shot.landing_zone
                      ? ` · ${shot.landing_zone.longitudinal}/${shot.landing_zone.lateral}`
                      : " · 落点待判定"}
                    {shot.hitter_phase ? ` · ${shot.hitter_phase}` : ""}
                  </small>
                </span>
                <em className={shot.confidence < 0.7 ? "low" : ""}>
                  {shot.origin === "human"
                    ? "人工"
                    : `${Math.round(shot.confidence * 100)}%`}
                </em>
              </button>
            ))}
          </div>
          {selectedShot && (
            <div className="correctionPanel">
              <div className="sectionLabel">
                <span>人工校正</span>
                <span>{selectedShot.id}</span>
              </div>
              <span className="correctionLabel">击球方</span>
              <div className="correctionButtons">
                {(["top", "bottom", "unknown"] as const).map((player) => (
                  <button
                    className={selectedShot.player === player ? "active" : ""}
                    key={player}
                    onClick={() => reviseShot("player", player)}
                  >
                    {player === "top"
                      ? "上方"
                      : player === "bottom"
                        ? "下方"
                        : "未知"}
                  </button>
                ))}
              </div>
              <span className="correctionLabel">粗球种</span>
              <div className="correctionButtons shotTypes">
                {Object.entries(shotNames).map(([value, label]) => (
                  <button
                    className={selectedShot.label === value ? "active" : ""}
                    key={value}
                    onClick={() => reviseShot("label", value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </aside>
      </section>

      <section className="overview">
        <div className="sectionHeading">
          <div>
            <p className="eyebrow">全场概览</p>
            <h2>运动负荷与结果质量</h2>
          </div>
          <span>口径：球场米制坐标 / 外部结果原始置信度</span>
        </div>
        <div className="metricGrid">
          <MetricCard
            label="有效回合"
            value={summary?.rallies.length ?? "—"}
            unit="局段"
          />
          <MetricCard
            label="击球候选"
            value={summary?.hits.length ?? "—"}
            unit="次"
          />
          <MetricCard
            label="平台指标"
            value={summary?.metrics?.available ? "可计算" : "证据不足"}
            accent
          />
          <MetricCard
            label="待复核问题"
            value={summary?.review.issue_count ?? "—"}
            unit="项"
            accent
          />
        </div>
        <div className="qualityPanel">
          <div>
            <p className="eyebrow">质量门禁</p>
            <h3>不以插值结果掩盖原始轨迹缺失</h3>
            <p>
              外部结果缺少必要证据时，球种、击球方和姿态指标只作为候选结论展示，不以插值掩盖缺失。
            </p>
          </div>
          <div className="issueList">
            {summary?.review.missing_evidence?.map((evidence, index) => (
              <div key={`${evidence}:${index}`}>
                <i />
                <span>
                  <strong>{evidence}</strong>
                  <small>需要外部结果或人工证据</small>
                </span>
              </div>
            )) ?? <span>等待分析结果</span>}
          </div>
        </div>
      </section>
    </main>
  );
}

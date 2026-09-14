import { useEffect, useState } from "react";
import Taro, { useRouter } from "@tarojs/taro";
import { ScrollView, Text, View } from "@tarojs/components";
import "./index.scss";

type Summary = {
  rallies: Array<{
    start_frame: number;
    end_frame: number;
    start_timestamp_us: number;
    winner_candidate?: "top" | "bottom" | "unknown";
    phase_transitions?: Array<{ player: string }>;
  }>;
  shots: Array<{
    hit_frame: number;
    timestamp_us: number;
    player: string;
    label: string;
    confidence: number;
    origin?: "external" | "human";
    hitter_phase?: string;
    landing_zone?: {
      longitudinal: string;
      lateral: string;
    } | null;
  }>;
  review: {
    quality_issues?: Array<{ code: string; message: string }>;
  };
};

const API_URL = "http://127.0.0.1:8000";

function formatTime(timestampUs: number) {
  const seconds = timestampUs / 1_000_000;
  return `${Math.floor(seconds / 60)}:${String(
    Math.floor(seconds % 60),
  ).padStart(2, "0")}`;
}

export default function Rallies() {
  const router = useRouter();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [active, setActive] = useState(0);

  useEffect(() => {
    if (!router.params.jobId) return;
    Taro.request<Summary>({
      url: `${API_URL}/api/jobs/${router.params.jobId}/summary`,
    }).then((response) => setSummary(response.data));
  }, [router.params.jobId]);

  const rally = summary?.rallies[active];
  const shots =
    summary?.shots.filter(
      (shot) =>
        rally &&
        shot.hit_frame >= rally.start_frame &&
        shot.hit_frame <= rally.end_frame,
    ) ?? [];

  return (
    <View className="page">
      <View className="summaryCard">
        <Text className="eyebrow">当前任务</Text>
        <Text className="summaryTitle">关键回合信息流</Text>
        <Text className="summaryCopy">
          小程序仅展示结果。低置信击球方、球种和姿态指标需在网页端逐帧复核。
        </Text>
        <View className="summaryStats">
          <View><Text>{summary?.rallies.length ?? "—"}</Text><Text>回合</Text></View>
          <View><Text>{summary?.shots.length ?? "—"}</Text><Text>击球</Text></View>
          <View>
            <Text>{summary?.review.quality_issues?.length ?? "—"}</Text>
            <Text>问题</Text>
          </View>
        </View>
      </View>

      <ScrollView scrollX className="rallyStrip">
        <View className="rallyStripInner">
          {summary?.rallies.map((item, index) => (
            <View
              className={`rallyTab ${active === index ? "active" : ""}`}
              key={item.start_frame}
              onClick={() => setActive(index)}
            >
              <Text>R{String(index + 1).padStart(2, "0")}</Text>
              <Text>{formatTime(item.start_timestamp_us)}</Text>
            </View>
          ))}
        </View>
      </ScrollView>

      <View className="sectionTitle">
        <Text>击球序列</Text>
        <Text>{shots.length} 次</Text>
      </View>
      <View className="rallyOutcome">
        <View>
          <Text>胜方候选</Text>
          <Text>
            {rally?.winner_candidate === "top"
              ? "上方运动员"
              : rally?.winner_candidate === "bottom"
                ? "下方运动员"
                : "待复核"}
          </Text>
        </View>
        <View>
          <Text>攻防转换</Text>
          <Text>{rally?.phase_transitions?.length ?? 0} 次</Text>
        </View>
      </View>
      <View className="shotFeed">
        {shots.map((shot, index) => (
          <View className="shotCard" key={`${shot.hit_frame}-${index}`}>
            <Text className={`playerTag ${shot.player}`}>
              {shot.player === "top" ? "上方" : shot.player === "bottom" ? "下方" : "未知"}
            </Text>
            <View className="shotMain">
              <Text className="shotType">{shot.label}</Text>
              <Text className="shotTime">
                {formatTime(shot.timestamp_us)}
                {shot.landing_zone
                  ? ` · ${shot.landing_zone.longitudinal}/${shot.landing_zone.lateral}`
                  : ""}
                {shot.hitter_phase ? ` · ${shot.hitter_phase}` : ""}
              </Text>
            </View>
            <Text className={`confidence ${shot.confidence < 0.7 ? "low" : ""}`}>
              {shot.origin === "human"
                ? "人工"
                : `${Math.round(shot.confidence * 100)}%`}
            </Text>
          </View>
        ))}
      </View>

      <View className="qualitySection">
        <View className="sectionTitle">
          <Text>质量提示</Text>
          <Text>必须复核</Text>
        </View>
        {summary?.review.quality_issues?.map((issue) => (
          <View className="issueCard" key={issue.code}>
            <View className="issueDot" />
            <View>
              <Text className="issueCode">{issue.code}</Text>
              <Text className="issueMessage">{issue.message}</Text>
            </View>
          </View>
        ))}
      </View>
    </View>
  );
}

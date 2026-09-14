import { useEffect, useState } from "react";
import Taro from "@tarojs/taro";
import { Button, Text, View } from "@tarojs/components";
import "./index.scss";

type Job = {
  id: string;
  stage: string;
  progress: number;
  source_path: string;
};

const API_URL = "http://127.0.0.1:8000";

const stageName: Record<string, string> = {
  uploaded: "等待处理",
  awaiting_results: "等待导入分析结果",
  validating: "校验视频",
  transcoding: "生成代理视频",
  calibrating: "标定场地",
  segmenting: "拆分回合",
  pose_tracking: "分析姿态",
  shuttle_tracking: "追踪羽毛球",
  event_detection: "识别击球",
  metrics: "计算指标",
  review_required: "等待复核",
  rendering: "生成视频",
  completed: "已完成",
  failed: "处理失败",
};

export default function Index() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  async function loadJobs() {
    try {
      const response = await Taro.request<Job[]>({
        url: `${API_URL}/api/jobs`,
      });
      setJobs(response.data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadJobs();
  }, []);

  async function createDemo() {
    setLoading(true);
    await Taro.request({
      url: `${API_URL}/api/demo/bootstrap`,
      method: "POST",
      data: {},
    });
    await loadJobs();
  }

  return (
    <View className="page">
      <View className="hero">
        <View className="brandLine">
          <Text className="brandMark">BA</Text>
          <Text>BADMINTONANALYSIS</Text>
        </View>
        <Text className="heroTitle">把长视频变成可复核的比赛信息</Text>
        <Text className="heroCopy">
          查看任务进度、关键回合与低置信提示。完整校正在网页分析台完成。
        </Text>
        <Button className="heroButton" onClick={createDemo} loading={loading}>
          创建合成分析示例
        </Button>
      </View>

      <View className="sectionHeader">
        <View>
          <Text className="eyebrow">任务中心</Text>
          <Text className="sectionTitle">最近分析</Text>
        </View>
        <Text className="count">{jobs.length} 个任务</Text>
      </View>

      <View className="jobList">
        {jobs.map((job, index) => (
          <View
            className="jobCard"
            key={job.id}
            onClick={() =>
              Taro.navigateTo({
                url: `/pages/rallies/index?jobId=${job.id}`,
              })
            }
          >
            <View className="jobTop">
              <Text className="jobIndex">A{String(index + 1).padStart(2, "0")}</Text>
              <Text className={`stage ${job.stage === "failed" ? "failed" : ""}`}>
                {stageName[job.stage] ?? job.stage}
              </Text>
            </View>
            <Text className="jobTitle">
              {job.source_path.split(/[\\/]/).pop() ?? "比赛视频"}
            </Text>
            <Text className="jobId">{job.id.slice(-12)}</Text>
            <View className="progressTrack">
              <View
                className="progressValue"
                style={{ width: `${Math.max(job.progress * 100, 4)}%` }}
              />
            </View>
            <View className="jobBottom">
              <Text>{Math.round(job.progress * 100)}%</Text>
              <Text>查看回合 →</Text>
            </View>
          </View>
        ))}
        {!loading && jobs.length === 0 && (
          <View className="empty">
            <Text>还没有分析任务</Text>
            <Text>先创建合成示例，或从网页端上传并导入分析结果。</Text>
          </View>
        )}
      </View>
    </View>
  );
}

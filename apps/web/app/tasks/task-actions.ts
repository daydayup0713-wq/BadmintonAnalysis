export const stageNames: Record<string, string> = {
  uploaded: "已上传",
  awaiting_results: "等待导入分析结果",
  metrics: "指标计算",
  review_required: "待人工复核",
  rendering: "生成导出",
  completed: "已完成",
  failed: "失败",
  retrying: "重试中",
  canceled: "已取消",
};

export function stageName(stage: string) {
  return stageNames[stage] ?? stage;
}

export function importResultsUrl(apiUrl: string, jobId: string) {
  return `${apiUrl.replace(/\/$/, "")}/api/jobs/${encodeURIComponent(jobId)}/results/import`;
}

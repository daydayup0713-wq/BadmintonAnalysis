"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { importResultsUrl, stageName } from "./task-actions";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

type Job = {
  id: string;
  source_path: string;
  stage: string;
  progress: number;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
  checkpoint: Record<string, unknown>;
};

function fileName(path: string) {
  return path.split(/[\\/]/).at(-1) ?? path;
}

export default function TasksPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [title, setTitle] = useState("");
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [resultFile, setResultFile] = useState<File | null>(null);
  const [importJobId, setImportJobId] = useState("");
  const [status, setStatus] = useState("读取任务");
  const waitingJobs = useMemo(
    () => jobs.filter((job) => job.stage === "awaiting_results"),
    [jobs],
  );

  const loadJobs = useCallback(async () => {
    const response = await fetch(`${API_URL}/api/jobs`, { cache: "no-store" });
    if (!response.ok) throw new Error("任务列表读取失败");
    const payload: Job[] = await response.json();
    setJobs(payload);
    setImportJobId((current) => {
      if (payload.some((job) => job.id === current && job.stage === "awaiting_results")) {
        return current;
      }
      return payload.find((job) => job.stage === "awaiting_results")?.id ?? "";
    });
    setStatus("任务状态已同步");
  }, []);

  useEffect(() => {
    loadJobs().catch((error) => setStatus(error.message));
    const timer = window.setInterval(() => {
      loadJobs().catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [loadJobs]);

  async function upload(event: React.FormEvent) {
    event.preventDefault();
    if (!videoFile || !title.trim()) return;
    setStatus("正在上传视频");
    const body = new FormData();
    body.append("file", videoFile);
    const response = await fetch(
      `${API_URL}/api/uploads?title=${encodeURIComponent(title.trim())}`,
      { method: "POST", body },
    );
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      setStatus(payload?.detail ?? "上传失败");
      return;
    }
    setTitle("");
    setVideoFile(null);
    setImportJobId(payload.job.id);
    setStatus("上传完成，等待导入外部分析结果");
    await loadJobs();
  }

  async function importResults(event: React.FormEvent) {
    event.preventDefault();
    if (!resultFile || !importJobId) return;
    setStatus("正在校验并导入分析结果");
    let body: unknown;
    try {
      body = JSON.parse(await resultFile.text());
    } catch {
      setStatus("JSON 文件格式无效");
      return;
    }
    const response = await fetch(importResultsUrl(API_URL, importJobId), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      setStatus(payload?.detail ?? "结果导入失败");
      return;
    }
    setResultFile(null);
    setStatus("结果已导入，可进入分析工作台复核");
    await loadJobs();
  }

  return (
    <main className="managementPage">
      <section className="managementHeader">
        <div>
          <p className="eyebrow">任务</p>
          <h1>外部结果导入与分析任务</h1>
          <p>先上传原始视频，再导入符合平台契约的 JSON 结果。</p>
        </div>
        <span className="statusPill">{status}</span>
      </section>

      <form className="uploadBar" onSubmit={upload}>
        <label>
          场次名称
          <input
            maxLength={200}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="例如：周一单打训练"
            required
            value={title}
          />
        </label>
        <label>
          比赛视频
          <input
            accept=".mp4,.mov,.mkv,.avi"
            onChange={(event) => setVideoFile(event.target.files?.[0] ?? null)}
            required
            type="file"
          />
        </label>
        <button className="primaryButton" type="submit">上传视频</button>
      </form>

      <form className="uploadBar" onSubmit={importResults}>
        <label>
          等待结果的任务
          <select
            onChange={(event) => setImportJobId(event.target.value)}
            required
            value={importJobId}
          >
            <option value="">请选择任务</option>
            {waitingJobs.map((job) => (
              <option key={job.id} value={job.id}>
                {fileName(job.source_path)} · {job.id.slice(-8)}
              </option>
            ))}
          </select>
        </label>
        <label>
          外部分析 JSON
          <input
            accept=".json,application/json"
            onChange={(event) => setResultFile(event.target.files?.[0] ?? null)}
            required
            type="file"
          />
        </label>
        <button className="primaryButton" type="submit">导入分析结果</button>
      </form>

      <section className="dataSection">
        <div className="sectionHeading compact">
          <div>
            <h2>全部任务</h2>
            <p>{jobs.length} 个平台任务</p>
          </div>
        </div>
        <div className="dataTable taskTable">
          <div className="dataRow dataHead">
            <span>视频</span><span>阶段</span><span>进度</span>
            <span>更新时间</span><span>操作</span>
          </div>
          {jobs.map((job) => (
            <div className="dataRow" key={job.id}>
              <span>
                <strong>{fileName(job.source_path)}</strong>
                <small>{job.id}</small>
                {job.error_message && <em>{job.error_message}</em>}
              </span>
              <span>
                <i className={`stageDot ${job.stage}`} />
                {stageName(job.stage)}
              </span>
              <span className="progressCell">
                <b style={{ width: `${Math.round(job.progress * 100)}%` }} />
                <small>{Math.round(job.progress * 100)}%</small>
              </span>
              <span>{new Date(job.updated_at).toLocaleString("zh-CN")}</span>
              <span className="rowActions">
                {job.stage === "awaiting_results" && (
                  <button onClick={() => setImportJobId(job.id)} type="button">
                    选择导入
                  </button>
                )}
                {["review_required", "completed"].includes(job.stage) && (
                  <Link href={`/analysis?job=${job.id}`}>进入分析</Link>
                )}
              </span>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}

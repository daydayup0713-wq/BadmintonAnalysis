"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

type Athlete = {
  id: string;
  name: string;
  handedness?: string | null;
  created_at: string;
};

type AthleteDetail = Athlete & {
  sessions: Array<{
    id: string;
    title: string;
    slot: "top" | "bottom";
    created_at: string;
  }>;
  jobs: Array<{
    id: string;
    stage: string;
    source_path: string;
    updated_at: string;
  }>;
};

export default function AthletesPage() {
  const [athletes, setAthletes] = useState<Athlete[]>([]);
  const [selected, setSelected] = useState<AthleteDetail | null>(null);
  const [name, setName] = useState("");
  const [handedness, setHandedness] = useState("right");
  const [identityStatus, setIdentityStatus] = useState("missing_evidence");
  const [status, setStatus] = useState("读取运动员档案");

  const load = useCallback(async () => {
    const [athletesResponse, acceptanceResponse] = await Promise.all([
      fetch(`${API_URL}/api/athletes`, { cache: "no-store" }),
      fetch(`${API_URL}/api/evaluation/acceptance`, { cache: "no-store" }),
    ]);
    if (!athletesResponse.ok) throw new Error("运动员列表读取失败");
    const nextAthletes: Athlete[] = await athletesResponse.json();
    setAthletes(nextAthletes);
    if (acceptanceResponse.ok) {
      const acceptance = await acceptanceResponse.json();
      setIdentityStatus(
        acceptance.metrics?.identity_frame_accuracy?.status ??
          "missing_evidence",
      );
    }
    setStatus("档案已同步");
    if (!selected && nextAthletes[0]) {
      await selectAthlete(nextAthletes[0].id);
    }
  }, [selected]);

  useEffect(() => {
    load().catch((error) => setStatus(error.message));
  }, [load]);

  async function selectAthlete(id: string) {
    const response = await fetch(`${API_URL}/api/athletes/${id}`, {
      cache: "no-store",
    });
    if (!response.ok) {
      setStatus("运动员详情读取失败");
      return;
    }
    setSelected(await response.json());
  }

  async function createAthlete(event: React.FormEvent) {
    event.preventDefault();
    const response = await fetch(`${API_URL}/api/athletes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim(), handedness }),
    });
    if (!response.ok) {
      setStatus("运动员创建失败");
      return;
    }
    const athlete = await response.json();
    setName("");
    setStatus("运动员档案已创建");
    await load();
    await selectAthlete(athlete.id);
  }

  return (
    <main className="managementPage">
      <section className="managementHeader">
        <div>
          <p className="eyebrow">运动员</p>
          <h1>档案与场次关联</h1>
          <p>档案只保存明确身份；低置信视频仍按场上槽位展示。</p>
        </div>
        <span className="statusPill">{status}</span>
      </section>

      <form className="athleteCreate" onSubmit={createAthlete}>
        <label>
          姓名
          <input
            maxLength={100}
            onChange={(event) => setName(event.target.value)}
            required
            value={name}
          />
        </label>
        <label>
          持拍手
          <select
            onChange={(event) => setHandedness(event.target.value)}
            value={handedness}
          >
            <option value="right">右手</option>
            <option value="left">左手</option>
            <option value="unknown">未知</option>
          </select>
        </label>
        <button className="primaryButton" type="submit">
          创建档案
        </button>
      </form>

      <section className="athleteWorkspace">
        <div className="athleteList">
          <div className="sectionHeading compact">
            <div>
              <h2>运动员</h2>
              <p>{athletes.length} 个档案</p>
            </div>
          </div>
          {athletes.map((athlete) => (
            <button
              className={selected?.id === athlete.id ? "active" : ""}
              key={athlete.id}
              onClick={() => selectAthlete(athlete.id)}
            >
              <span>{athlete.name.slice(0, 1)}</span>
              <strong>{athlete.name}</strong>
              <small>
                {athlete.handedness === "left"
                  ? "左手"
                  : athlete.handedness === "right"
                    ? "右手"
                    : "持拍手未知"}
              </small>
            </button>
          ))}
        </div>

        <div className="athleteDetail">
          {selected ? (
            <>
              <div className="detailTitle">
                <div>
                  <p className="eyebrow">档案详情</p>
                  <h2>{selected.name}</h2>
                </div>
                <span>{selected.sessions.length} 个关联场次</span>
              </div>
              {identityStatus !== "pass" && (
                <div className="evidenceWarning">
                  <strong>跨场次表现汇总暂不可用</strong>
                  <p>
                    身份逐帧准确率尚无达到 98% 的人工 GT
                    证据，系统不会把上下半场槽位数据自动归入该运动员。
                  </p>
                </div>
              )}
              <div className="detailColumns">
                <section>
                  <h3>关联场次</h3>
                  {selected.sessions.map((session) => (
                    <div className="plainListRow" key={session.id}>
                      <span>
                        <strong>{session.title}</strong>
                        <small>
                          {session.slot === "top"
                            ? "上半场登记"
                            : "下半场登记"}
                        </small>
                      </span>
                      <time>
                        {new Date(session.created_at).toLocaleDateString("zh-CN")}
                      </time>
                    </div>
                  ))}
                </section>
                <section>
                  <h3>分析任务</h3>
                  {selected.jobs.map((job) => (
                    <div className="plainListRow" key={job.id}>
                      <span>
                        <strong>{job.stage}</strong>
                        <small>{job.id}</small>
                      </span>
                      {["review_required", "completed"].includes(job.stage) && (
                        <Link href={`/analysis?job=${job.id}`}>查看</Link>
                      )}
                    </div>
                  ))}
                </section>
              </div>
            </>
          ) : (
            <div className="emptyState">选择或创建一个运动员档案。</div>
          )}
        </div>
      </section>
    </main>
  );
}

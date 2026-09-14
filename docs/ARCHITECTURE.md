# 架构

```text
外部分析提供方 ── JSON ──┐
上传视频 ────────────────┼──> FastAPI ──> SQLite
Next.js / Taro ──────────┘        │
                                  ├── 平台指标与缺失证据判断
                                  ├── 人工修订记录
                                  └── JSON / CSV / PDF / 视频导出
```

## 边界

- `importing.py`：严格校验提供方身份、视频元数据、17 点姿态、帧范围和置信度；归一化为 `external` 来源。
- `repository.py`：SQLite 任务、结果、checkpoint 与只追加的人工修订。
- `metrics.py`、`biomechanics.py`、`tactics.py`：仅基于已经导入的证据计算二维候选指标。
- `api.py`：上传、导入、摘要、修订和导出 HTTP API。
- `apps/web`：完整导入与复核工作台。
- `apps/mini`：轻量任务/回合查看。

当前树没有视频检测或训练执行路径。`POST /api/jobs/{id}/run` 只返回 `409 external_results_required`，用于向旧客户端明确说明迁移方式。

## 状态机

```text
uploaded -> awaiting_results -> metrics -> review_required
                                      -> rendering -> completed
```

异常可进入 `failed`；导出恢复沿用 `retrying`。外部导入 checkpoint 记录 `provider`、`provider_version` 和 `imported: true`。

## 数据原则

- 未检测到的人员关键点使用 `null`；空数组表示无事件，不得补造。
- 导入数据来源固定为 `external`，人工修改来源为 `human`。
- 所有置信度必须在 `[0, 1]`，所有关键点坐标必须为有限数。
- 指标证据不足时返回 `missing_evidence`，不把缺失值显示为 0。
- SQLite 适合单机；多实例部署应换为生产数据库和对象存储。

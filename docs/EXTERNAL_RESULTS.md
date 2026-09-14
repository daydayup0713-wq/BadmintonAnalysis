# 外部分析结果 JSON 契约

平台通过 `POST /api/jobs/{job_id}/results/import` 接收 UTF-8 JSON。顶层字段严格校验，未知字段会被拒绝。

## 最小完整请求

下面的请求完全合法，但由于没有姿态、球轨迹和事件证据，任务会进入 `review_required`，指标标记为不可用。

```json
{
  "provider": "your-analysis-service",
  "provider_version": "2026.09",
  "video": {
    "fps": 30,
    "width": 1920,
    "height": 1080,
    "total_frames": 300,
    "duration_seconds": 10
  },
  "court_points": null,
  "net_points": null,
  "rallies": [],
  "poses": [],
  "shuttle": [],
  "hits": [],
  "shots": []
}
```

包含场地、双方 17 点姿态、球轨迹、两个击球和球种的可运行完整示例见 `services/api/courtvision/fixtures/synthetic-demo.json`。

## 字段约束

| 字段 | 约束 |
|---|---|
| `provider` / `provider_version` | 必填，去除首尾空白后非空，最多 100 字符 |
| `video.fps` | 大于 0 |
| `video.width` / `height` / `total_frames` | 正整数 |
| `video.duration_seconds` | 大于 0 |
| `court_points` | `null` 或恰好 6 个有限 `[x, y]` 点 |
| `net_points` | `null` 或恰好 4 个有限 `[x, y]` 点 |
| `poses[].frame` | `0 <= frame < total_frames` |
| `poses[].top_keypoints` / `bottom_keypoints` | `null` 或恰好 17 个有限 `[x, y]` 点 |
| 任意 `confidence` | 0 到 1（含边界） |
| 任意帧字段 | 必须落在视频帧范围内 |

推荐事件字段：

- `rallies[]`：`id`、`start_frame`、`end_frame`、`start_timestamp_us`、`end_timestamp_us`、`confidence`。
- `shuttle[]`：`frame`、`timestamp_us`、`x`、`y`、`visible`、`confidence`。
- `hits[]`：`frame`、`timestamp_us`、`player`（`top|bottom|unknown`）、`confidence`。
- `shots[]`：`id`、`hit_frame`、`timestamp_us`、`player`、`label`、`confidence`。

所有导入结果会记录 `origin: "external"` 以及提供方身份。平台不补造缺失姿态、轨迹、击球或球种；缺失项写入 `review_required.missing_evidence`。

## PowerShell 导入示例

```powershell
$jobId = "job_xxx"
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/jobs/$jobId/results/import" `
  -ContentType "application/json; charset=utf-8" `
  -InFile ".\analysis-result.json"
```

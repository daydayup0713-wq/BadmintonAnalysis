# API 契约

默认地址：`http://127.0.0.1:8000`。交互式 OpenAPI 文档：`/docs`。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/health` | 平台健康与分析模式 |
| POST/GET | `/api/athletes` | 创建/列出运动员 |
| GET | `/api/athletes/{id}` | 运动员、场次与任务 |
| POST/GET | `/api/sessions` | 创建/列出场次 |
| POST | `/api/jobs` | 用已有视频路径创建等待导入的任务 |
| POST | `/api/uploads` | 上传视频并创建等待导入的任务 |
| GET | `/api/jobs` | 列出任务 |
| GET | `/api/jobs/{id}` | 任务状态与 checkpoint |
| POST | `/api/jobs/{id}/results/import` | 导入外部结果 |
| GET | `/api/jobs/{id}/results/{kind}` | 读取某类保存结果 |
| GET | `/api/jobs/{id}/summary` | 聚合分析摘要 |
| POST | `/api/revisions` | 追加人工修订 |
| POST | `/api/jobs/{id}/exports` | 创建或读取导出 |
| GET | `/api/jobs/{id}/exports/{artifact}` | 下载导出文件 |
| POST | `/api/demo/bootstrap` | 创建人工合成示例 |

健康响应：

```json
{
  "status": "ok",
  "service": "BadmintonAnalysis",
  "analysis_mode": "external_results"
}
```

导入请求见 [EXTERNAL_RESULTS.md](EXTERNAL_RESULTS.md)。成功导入返回 summary，`job.stage` 为 `review_required`；校验失败返回 422，状态不允许导入返回 409。兼容端点 `/api/jobs/{id}/run` 始终返回：

```json
{"detail": "external_results_required"}
```

结果种类包括 `external_import`、`validating`、`calibrating`、`segmenting`、`pose_tracking`、`shuttle_tracking`、`event_detection`、`metrics`、`review_required` 与 `rendering`。

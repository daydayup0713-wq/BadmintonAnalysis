# 测试与验收

## 自动化

```powershell
.\.venv\Scripts\python.exe -m pytest
npm test -w @badminton-analysis/web
npm run web:build
npm run mini:build
```

Python 测试覆盖：导入校验与持久化、任务状态机、API、SQLite、二维指标、生物力学候选、战术、人工修订、JSON/CSV/PDF/媒体导出和仓库发布边界。

## 发布门禁

- 当前树不存在内置模型源码、权重、训练数据集、训练脚本与历史生成结果。
- 合成 fixture 能通过同一个导入端点到达 `review_required`。
- 空证据导入不会生成虚假击球、球种、姿态或轨迹。
- Web 构建路由不包含 `/models`；小程序构建成功。
- `.venv`、`node_modules`、构建产物、SQLite 与缓存不得进入 Git。
- `NOTICE.md` 必须明确说明保留的旧 Git 提交可能包含已从当前树删除的内容。

媒体测试需要 `ffmpeg`、`ffprobe`、NumPy 与 OpenCV。项目不设 GPU/CUDA 验收项。

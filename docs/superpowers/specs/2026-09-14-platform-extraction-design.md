# BadmintonAnalysis 平台独立仓库设计

## 目标

从现有 CourtVision / SoloShuttlePose 工程中保留分析平台，移除当前工作树中的开源检测模型实现、模型权重、训练数据和模型生成结果，并把可独立运行的平台提交到 `https://github.com/daydayup0713-wq/BadmintonAnalysis`。

目标仓库必须保留当前 SoloShuttlePose 仓库的完整 Git 历史。模型相关内容只从最终分支的最新工作树删除，不重写历史，也不声称这些内容从历史提交中消失。

## 选择的方案

采用“通用分析结果导入平台”方案：保留 Web、小程序、FastAPI、SQLite、指标计算、战术分析、人工复核、导出和视频叠加；移除内置检测引擎；增加与模型无关的 JSON 结果导入入口和合成演示数据。

未采用以下方案：

1. 仅保留静态前端。实现最少，但任务管理、审核、导出和后端指标能力会丢失。
2. 保留原 GPU Worker 接口但删除权重。平台表面完整，实际任务会在运行时失败，交付语义不清晰。

选择通用导入方案后，平台仍可端到端运行，但“从原始视频生成检测结果”明确属于外部分析提供方的责任。

## Git 与目标仓库策略

- 以 `D:\New_Badminton\SoloShuttlePose` 的现有 Git 历史为基础创建平台分支。
- 保留现有 `origin`，新增名为 `badminton-analysis` 的远端指向目标仓库。
- 目标仓库当前 `main` 只有占位 README。拉取该提交并使用允许无关历史的合并，使目标仓库原提交和 SoloShuttlePose 历史都保留。
- 不使用历史重写，不使用 `git filter-repo`，不声称旧提交中已删除模型。
- 最终将平台分支推送为目标仓库 `main`。

## 保留范围

### 前端

- `apps/web`：分析工作台、任务列表、运动员、模型无关的结果可视化、人工修订和导出入口。
- `apps/mini`：任务、关键回合和复核结果展示。
- 删除产品文案中的 SoloShuttlePose、TrackNet、Keypoint R-CNN 和本地模型声明。

### 后端平台

- FastAPI 应用与 CORS 配置。
- SQLite 仓库、任务状态、断点字段和版本化结果。
- 数据契约、运动员身份稳定、移动指标、生物力学指标、战术派生、质量提示。
- JSON/CSV/PDF 导出与已有视频叠加渲染。
- 人工修订、审核和验收证据计算。

### 通用输入

- 保留以标准化关键点、球轨迹、回合和击球事件为输入的数据结构。
- 新增导入 API，把外部算法输出写入既有结果表，再运行平台侧指标、战术和质量计算。
- 导入数据必须显式提供 `provider` 和 `provider_version`；平台不假设提供方使用哪种模型。
- 增加纯手工构造的合成演示结果，不包含比赛视频、模型输出或上游数据集内容。

## 删除范围

最终工作树删除以下内容：

- `src/models`、`src/tools`、`src/reprocess` 和旧根目录 `main.py`。
- `src/models/weights` 中全部权重。
- `ShuttleSet` 训练数据、训练脚本和后端训练模块。
- `services/api/courtvision/model_registry.py`。
- `services/api/courtvision/local_runtime.py`。
- `services/api/courtvision/gpu_pipeline.py`。
- `services/api/courtvision/worker.py`。
- 只用于读取上游历史产物的 `adapters.py` 和 `legacy_pipeline.py`。
- `videos`、`res`、`data`、`exports`、`logs`、`draft`、`references` 中的模型输入、输出和历史结果。
- GPU/PyTorch/NVIDIA 专用依赖、Windows GPU 安装说明与脚本。
- 对应的模型注册、GPU 流水线、本地运行时、Legacy 导入和 ShuttleSet 训练测试。

生成目录如 `.venv`、`node_modules`、`.next`、`dist`、`__pycache__` 和 egg-info 不提交。

## API 与数据流

### 创建任务

平台继续接受视频上传并创建任务，但上传结束后进入 `awaiting_results`，不会自动启动内置 Worker。

### 导入外部结果

新增 `POST /api/jobs/{job_id}/results/import`。请求体包含：

- 提供方标识与版本。
- 视频元数据。
- 场地与球网几何数据，可为空。
- 回合集合。
- 每帧双方 17 点姿态，可为空。
- 羽毛球轨迹点，可为空。
- 击球候选和置信度，可为空。

后端验证帧号、时间范围、坐标、置信度和实体引用。验证通过后，将原始导入数据标记为 `external` 来源，运行平台侧身份、跑位、生物力学、战术和质量计算，最后进入 `review_required` 或 `completed`。

### 合成演示

`POST /api/demo/bootstrap` 改为加载仓库内的合成 JSON fixture。该 fixture 由确定性坐标构造，只用于展示平台界面和导出能力，并在 API 与界面中标记为 `synthetic_demo`。

### 前端

任务页提供两个入口：

1. 上传视频，获得等待外部结果的任务。
2. 为指定任务导入标准 JSON。

分析工作台继续读取原有 summary 结构，因此图表、时间轴、姿态叠加和审核界面不需要更换数据模型。

## 错误处理

- 上传后尝试启动分析时，不再静默调用缺失模型；API 返回明确的 `external_results_required` 状态。
- 导入 JSON 缺字段、引用不存在、帧范围越界或置信度不合法时返回 422，并包含字段级错误。
- 外部结果不完整时保留可用数据，并通过质量门禁标记缺失项，不伪造轨迹、姿态或球种。
- 导出视频需要原始视频和 FFmpeg；缺失时返回可操作的错误，JSON/CSV/PDF 导出仍可使用。

## 文档与声明

根 README 改名并描述 BadmintonAnalysis 平台，不再把仓库描述为内置 SoloShuttlePose 检测产品。

新增 `NOTICE.md`，明确：

- 当前工作树不包含 SoloShuttlePose、TrackNet、Keypoint R-CNN 等开源模型实现和权重。
- 当前工作树不包含 ShuttleSet 数据和历史模型生成结果。
- Git 历史按用户要求保留，因此旧提交仍可能包含上述内容；需要完全清除历史时必须另行执行历史重写。
- 本仓库只负责接收标准化分析结果、计算平台指标、支持复核并展示或导出。

新增平台运行说明，覆盖 Python、Node、FFmpeg、安装、启动、合成演示、外部 JSON 契约和故障排查。平台运行不要求 CUDA、PyTorch 或 NVIDIA GPU。

## 测试与验收

- 先为模型无关的 API 健康信息、合成演示和外部结果导入写失败测试，再实现。
- 删除模型专用测试后，剩余 Python 测试全部通过。
- `rg` 扫描最终工作树，除 `NOTICE.md` 的历史声明外，不出现 SoloShuttlePose、TrackNet、ShuttleSet、模型权重路径或 GPU Worker 产品文案。
- `npm run web:build` 和 `npm run mini:build` 通过。
- 在临时数据目录启动 API，合成演示能生成 summary，外部 JSON fixture 能导入并进入可查看状态。
- `git status` 只包含预期的平台拆分变更。
- 推送后通过 `git ls-remote` 验证目标 `main` 指向本地最终提交。

## 完成标准

目标仓库 `main` 同时满足：保留原仓库 Git 历史；最新工作树不分发开源模型、权重、训练数据或模型结果；平台可以在无 GPU 的干净电脑上启动；合成演示和外部结果导入可用；README 与 NOTICE 对能力边界和历史保留给出明确说明。

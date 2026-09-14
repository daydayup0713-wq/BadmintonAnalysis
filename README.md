# BadmintonAnalysis

BadmintonAnalysis 是一个面向羽毛球视频分析结果的本地平台：它接收视频和第三方分析 JSON，保存回合、姿态、球轨迹、击球与球种信息，并提供指标计算、人工复核和导出能力。

当前工作树不包含任何内置检测模型、模型权重、训练数据集或历史模型生成结果，也不需要 NVIDIA GPU、CUDA、PyTorch 或 TorchVision。分析结果由你选择的外部系统生成，再按平台契约导入。

## 功能

- FastAPI + SQLite：任务、结果、修订、摘要与导出 API。
- Next.js：视频上传、JSON 导入、回合/姿态/轨迹展示、人工修订和导出。
- Taro：微信小程序任务与回合查看。
- 平台指标：二维跑位、回中、相对挥拍强度、战术候选与缺失证据提示。
- 合成示例：仓库自带人工构造的 JSON，可在没有视频和外部服务时体验分析界面。

## Windows 一键启动

干净电脑请先安装 Git、Python 3.10–3.12、Node.js LTS 和 FFmpeg，然后在 PowerShell 中运行：

```powershell
git clone https://github.com/daydayup0713-wq/BadmintonAnalysis.git
cd BadmintonAnalysis
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows\setup.ps1
.\scripts\windows\start.ps1
```

浏览器打开 <http://127.0.0.1:3000>；API 文档位于 <http://127.0.0.1:8000/docs>。完整安装与故障排查见 [Windows 干净机部署](docs/WINDOWS_SETUP.md)。

## 使用流程

1. 在“任务”页上传原始视频。
2. 使用外部分析服务生成符合 [外部结果契约](docs/EXTERNAL_RESULTS.md) 的 JSON。
3. 为等待中的任务选择 JSON 并导入。
4. 在“分析工作台”复核低置信结果、追加人工修订并生成 JSON、CSV、PDF、叠加视频和回合剪辑。

无需外部结果时，可直接在网页或小程序点击“创建合成分析示例”。合成数据文件位于 `services/api/courtvision/fixtures/synthetic-demo.json`，不来自比赛视频、数据集或历史推理输出。

## 开发与验证

```powershell
.\.venv\Scripts\python.exe -m pytest
npm test -w @badminton-analysis/web
npm run web:build
npm run mini:build
```

媒体叠加和回合剪辑需要系统命令 `ffmpeg`、`ffprobe`，Python 侧使用 NumPy 与 OpenCV；这些用于平台渲染，不执行检测或推理。

## 文档

- [Windows 干净机部署](docs/WINDOWS_SETUP.md)
- [外部结果 JSON 契约](docs/EXTERNAL_RESULTS.md)
- [架构](docs/ARCHITECTURE.md)
- [API 契约](docs/API_CONTRACTS.md)
- [测试与验收](docs/TEST_AND_ACCEPTANCE.md)
- [移除内容与 Git 历史说明](NOTICE.md)

## 重要限制

- 平台不会从视频自动生成姿态、轨迹、击球或球种；必须导入外部结果。
- 单目二维指标只作为候选分析，不等同于经过标定的三维运动学或医学结论。
- 缺少证据时接口会返回 `missing_evidence`，不会用插值或默认值伪造结论。
- 默认部署面向单机本地使用；公网部署前必须增加鉴权、上传限制、恶意文件检测和生产数据库。

许可与历史边界见 [NOTICE.md](NOTICE.md) 和 [LICENSE](LICENSE)。

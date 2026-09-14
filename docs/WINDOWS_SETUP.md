# Windows 干净机部署与运行

适用环境：Windows 10/11 x64。无需 NVIDIA GPU 或 CUDA。

## 1. 安装系统软件

以普通用户打开 PowerShell：

```powershell
winget install --exact --id Git.Git
winget install --exact --id Python.Python.3.11
winget install --exact --id OpenJS.NodeJS.LTS
winget install --exact --id Gyan.FFmpeg
```

全部安装完成后关闭并重新打开 PowerShell，确认：

```powershell
git --version
py -3.11 --version
node --version
npm --version
ffmpeg -version
ffprobe -version
```

## 2. 下载完整源码并安装

```powershell
git clone https://github.com/daydayup0713-wq/BadmintonAnalysis.git
cd BadmintonAnalysis
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows\setup.ps1
```

脚本会在项目内创建 `.venv`，执行 `pip install -e .[dev]`，再用 `npm ci` 安装锁定的 Web 与小程序依赖，不会修改系统 Python 包。

## 3. 启动

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows\start.ps1
```

脚本打开两个可见 PowerShell 窗口：

- Web：<http://127.0.0.1:3000>
- API：<http://127.0.0.1:8000>
- API 文档：<http://127.0.0.1:8000/docs>

关闭两个窗口或分别按 `Ctrl+C` 即可停止服务。

## 4. 首次体验

1. 打开 Web 后进入“分析工作台”，系统会在没有可复核任务时创建人工合成示例。
2. 实际使用时进入“任务”，先上传视频，再选择等待中的任务导入外部 JSON。
3. JSON 格式见 [EXTERNAL_RESULTS.md](EXTERNAL_RESULTS.md)。

## 5. 单独启动与构建

```powershell
.\scripts\windows\start-api.ps1
.\scripts\windows\start-web.ps1
npm run mini:build
```

小程序产物在 `apps\mini\dist`，用微信开发者工具打开 `apps\mini`。

## 常见问题

- `py -3.11` 找不到：重新安装 Python，并勾选加入 PATH；也可执行 `.\scripts\windows\setup.ps1 -PythonExe C:\path\python.exe`。
- `ffmpeg` 找不到：重新执行 Winget 命令，关闭所有终端后再打开。
- PowerShell 禁止脚本：仅对当前窗口执行 `Set-ExecutionPolicy -Scope Process Bypass`。
- `npm ci` 失败：确认网络可访问 npm registry，删除不完整的 `node_modules` 后重试安装脚本。
- 端口占用：停止占用 3000 或 8000 端口的程序，或分别编辑启动脚本端口。
- 叠加视频失败：先运行 `.\scripts\windows\check-environment.ps1`，重点确认 OpenCV、NumPy、FFmpeg 和 FFprobe。
- 页面没有自动分析：这是预期行为。当前树不执行视频检测，必须导入外部结果或使用合成示例。

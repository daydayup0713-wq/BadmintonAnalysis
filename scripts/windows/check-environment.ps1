[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$LASTEXITCODE = 0
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

foreach ($command in @("node", "npm", "ffmpeg", "ffprobe")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $command"
    }
}
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw ".venv is missing. Run .\scripts\windows\setup.ps1 first."
}

& ffmpeg -version | Select-Object -First 1
if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed." }
& ffprobe -version | Select-Object -First 1
if ($LASTEXITCODE -ne 0) { throw "ffprobe failed." }

$pythonCheck = @'
import cv2
import fastapi
import numpy
import reportlab
import uvicorn
from courtvision.main import app
assert app.title == "BadmintonAnalysis API"
print("OpenCV:", cv2.__version__)
print("NumPy:", numpy.__version__)
print("API:", app.title)
'@
& $PythonExe -c $pythonCheck
if ($LASTEXITCODE -ne 0) { throw "Python/API import check failed." }

if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot "node_modules\next\package.json"))) {
    throw "Web dependencies are missing. Run setup.ps1 first."
}
Write-Host "All environment checks passed." -ForegroundColor Green

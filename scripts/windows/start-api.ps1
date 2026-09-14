[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw ".venv is missing. Run .\scripts\windows\setup.ps1 first."
}
Set-Location $ProjectRoot
Write-Host "BadmintonAnalysis API: http://127.0.0.1:8000" -ForegroundColor Green
& $PythonExe -m uvicorn courtvision.main:app --host 127.0.0.1 --port 8000

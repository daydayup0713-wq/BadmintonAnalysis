[CmdletBinding()]
param([switch]$SkipCheck)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $SkipCheck) {
    & (Join-Path $PSScriptRoot "check-environment.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Environment check failed." }
}

$ApiScript = Join-Path $PSScriptRoot "start-api.ps1"
$WebScript = Join-Path $PSScriptRoot "start-web.ps1"
$ApiArguments = "-NoExit -ExecutionPolicy Bypass -File `"$ApiScript`""
$WebArguments = "-NoExit -ExecutionPolicy Bypass -File `"$WebScript`""
Start-Process -FilePath "powershell.exe" -ArgumentList $ApiArguments -WorkingDirectory $ProjectRoot
Start-Sleep -Seconds 2
Start-Process -FilePath "powershell.exe" -ArgumentList $WebArguments -WorkingDirectory $ProjectRoot

Write-Host "BadmintonAnalysis is starting in two PowerShell windows." -ForegroundColor Green
Write-Host "Web:      http://127.0.0.1:3000"
Write-Host "API:      http://127.0.0.1:8000"
Write-Host "API docs: http://127.0.0.1:8000/docs"

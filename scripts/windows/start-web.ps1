[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot "node_modules\next\package.json"))) {
    throw "Web dependencies are missing. Run .\scripts\windows\setup.ps1 first."
}
Write-Host "BadmintonAnalysis Web: http://127.0.0.1:3000" -ForegroundColor Green
& npm run web:dev

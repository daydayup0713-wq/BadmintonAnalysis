[CmdletBinding()]
param([string]$PythonExe = "")

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$VenvRoot = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"

function Assert-Command([string]$Name, [string]$Hint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name was not found. $Hint"
    }
}

function Resolve-CompatiblePython {
    $candidates = @()
    if ($PythonExe) {
        $candidates += [pscustomobject]@{ Executable = $PythonExe; Prefix = @() }
    }
    else {
        $candidates += [pscustomobject]@{ Executable = "py"; Prefix = @("-3.11") }
        $candidates += [pscustomobject]@{ Executable = "python"; Prefix = @() }
    }
    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Executable -ErrorAction SilentlyContinue)) { continue }
        $prefix = @($candidate.Prefix)
        $supported = & $candidate.Executable @prefix -c "import sys; print(sys.version_info.major, 10 <= sys.version_info.minor <= 12)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $supported -eq "3 True") { return $candidate }
    }
    throw "Python 3.10-3.12 x64 was not found. Install Python 3.11 and reopen PowerShell."
}

Write-Host "[1/4] Checking prerequisites..." -ForegroundColor Cyan
Assert-Command "node" "Install the Node.js LTS x64 release."
Assert-Command "npm" "Install the Node.js LTS x64 release."
Assert-Command "ffmpeg" "Run: winget install --exact --id Gyan.FFmpeg"
Assert-Command "ffprobe" "Run: winget install --exact --id Gyan.FFmpeg"
$python = Resolve-CompatiblePython

Write-Host "[2/4] Creating .venv..." -ForegroundColor Cyan
if (-not (Test-Path -LiteralPath $VenvPython)) {
    $prefix = @($python.Prefix)
    & $python.Executable @prefix -m venv $VenvRoot
    if ($LASTEXITCODE -ne 0) { throw "Failed to create .venv." }
}

Push-Location $ProjectRoot
try {
    Write-Host "[3/4] Installing Python platform dependencies..." -ForegroundColor Cyan
    & $VenvPython -m pip install --upgrade pip setuptools wheel
    if ($LASTEXITCODE -ne 0) { throw "pip bootstrap failed." }
    & $VenvPython -m pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }

    Write-Host "[4/4] Installing locked web dependencies..." -ForegroundColor Cyan
    & npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
}
finally { Pop-Location }

& (Join-Path $PSScriptRoot "check-environment.ps1")
if ($LASTEXITCODE -ne 0) { throw "Environment verification failed." }
Write-Host "Setup completed. Run .\scripts\windows\start.ps1" -ForegroundColor Green

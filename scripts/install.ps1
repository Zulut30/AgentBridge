param(
    [string]$Python = "python",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if ($Force -and (Test-Path ".venv")) {
    Remove-Item -LiteralPath ".venv" -Recurse -Force
}

if (-not (Test-Path $VenvPython)) {
    & $Python -m venv .venv
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

if (-not (Test-Path "agentbridge.yaml")) {
    Copy-Item "examples\agentbridge.yaml" "agentbridge.yaml"
}

& $VenvPython -m app.tools.doctor

Write-Host ""
Write-Host "AgentBridge installed."
Write-Host "Run: .\scripts\run.ps1"
Write-Host "Check: .\scripts\check.ps1"

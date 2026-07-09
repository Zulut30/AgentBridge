param(
    [switch]$Server,
    [switch]$Cursor
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

& $Python -m unittest discover -s tests

$Files = Get-ChildItem -Recurse -Filter *.py |
    Where-Object { $_.FullName -notmatch "\\.venv\\" } |
    ForEach-Object { $_.FullName }
& $Python -m py_compile @Files

$DoctorArgs = @()
if ($Server) {
    $DoctorArgs += "--server"
}
if ($Cursor) {
    $DoctorArgs += "--cursor"
}

& $Python -m app.tools.doctor @DoctorArgs

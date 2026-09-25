# ralph/afk.ps1 -- middle-rung afk loop (allowlist via .claude/settings.json)
# Launch: powershell -ExecutionPolicy Bypass -File .\ralph\afk.ps1 [-MaxIterations 2] [-Model opus]
# Each iteration is a fresh `claude -p` process. UV_NO_SYNC=1 inside every iteration: `uv run`
# never installs or syncs, so an unattended run can never pull a package (25 Sep 2026).
param(
    [int]$MaxIterations  = 2,
    [int]$TimeoutMinutes = 40,
    [int]$MaxTurns       = 150,
    [string]$Model       = "",
    [string]$LogDir      = ""
)
$ErrorActionPreference = "Stop"
$RepoRoot   = Split-Path -Parent $PSScriptRoot
$PromptFile = Join-Path $PSScriptRoot "prompt.md"
if (-not (Test-Path $PromptFile)) { throw "prompt.md not found" }
if (-not $LogDir) {
    foreach ($d in (Get-PSDrive -PSProvider FileSystem)) {
        $p = Join-Path $d.Root "My Drive"
        if (Test-Path $p) { $LogDir = Join-Path $p "Matt Pocock Workflow\afk-logs"; break }
    }
    if (-not $LogDir) {
        $m = Join-Path $env:USERPROFILE "My Drive"
        if (Test-Path $m) { $LogDir = Join-Path $m "Matt Pocock Workflow\afk-logs" }
        else { $LogDir = Join-Path $RepoRoot "work\afk-logs"; Write-Warning "Drive not found - local logs only" }
    }
}
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$modelArg = ""
if ($Model) { $modelArg = " --model $Model" }
Write-Host "Logs -> $LogDir"
Write-Host "Model -> $(if ($Model) { $Model } else { 'default' }); UV_NO_SYNC=1 in every iteration"
$fails = 0
for ($i = 1; $i -le $MaxIterations; $i++) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $log   = Join-Path $LogDir "afk-$stamp-iter$i.log"
    Write-Host "=== iteration $i/$MaxIterations -> $log ==="
    $inner = "`$env:UV_NO_SYNC='1'; Set-Location '$RepoRoot'; Get-Content -Raw '$PromptFile' | " +
             "claude -p --permission-mode acceptEdits$modelArg --max-turns $MaxTurns --verbose *>> '$log'"
    $proc = Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-Command",$inner `
            -WorkingDirectory $RepoRoot -PassThru -WindowStyle Hidden
    if (-not $proc.WaitForExit($TimeoutMinutes * 60 * 1000)) {
        taskkill /PID $($proc.Id) /T /F | Out-Null
        Add-Content $log "`n=== TIMEOUT $TimeoutMinutes min - tree killed ==="
        Write-Host "iteration ${i}: TIMEOUT"; $fails++
    } elseif ($proc.ExitCode -ne 0) {
        Add-Content $log "`n=== exit $($proc.ExitCode) ==="
        Write-Host "iteration ${i}: exit $($proc.ExitCode)"; $fails++
    } else {
        Write-Host "iteration ${i}: OK"; $fails = 0
    }
    if ($fails -ge 2) { Write-Host "Two consecutive failures - stopping."; break }
    Start-Sleep -Seconds 30
}
Write-Host "afk loop finished."

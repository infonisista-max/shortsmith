# ralph/afk.ps1 -- middle-rung afk loop (allowlist via .claude/settings.json)
# Launch: powershell -ExecutionPolicy Bypass -File .\ralph\afk.ps1 [-MaxIterations 2] [-Model opus]
# Each iteration is a fresh `claude -p` process. UV_NO_SYNC=1 inside every iteration: `uv run`
# never installs or syncs, so an unattended run can never pull a package (25 Sep 2026).
# Item 43 (26 Sep 2026): the live log is written LOCALLY (work\afk-logs) and copied to Drive at the
# end of each iteration, so Drive sync never sits on the live-write path. The timeout branch waits
# for the killed tree to release its handles; every harness note retries and never throws; a
# timeout that leaves a dirty tree stops the loop for a supervised rescue (once.ps1) instead of an
# unattended re-pick of the ticket that just outran the clock.
param(
    [int]$MaxIterations  = 2,
    [int]$TimeoutMinutes = 40,
    [int]$MaxTurns       = 150,
    [string]$Model       = "",
    [string]$LogDir      = ""      # Drive copy target; auto-discovered when empty
)
$ErrorActionPreference = "Stop"
$RepoRoot   = Split-Path -Parent $PSScriptRoot
$PromptFile = Join-Path $PSScriptRoot "prompt.md"
if (-not (Test-Path $PromptFile)) { throw "prompt.md not found" }

# Live logs: local, never on a synced drive.
$LocalDir = Join-Path $RepoRoot "work\afk-logs"
New-Item -ItemType Directory -Path $LocalDir -Force | Out-Null

# Drive: copy target only.
$DriveDir = $LogDir
if (-not $DriveDir) {
    foreach ($d in (Get-PSDrive -PSProvider FileSystem)) {
        $p = Join-Path $d.Root "My Drive"
        if (Test-Path $p) { $DriveDir = Join-Path $p "Matt Pocock Workflow\afk-logs"; break }
    }
    if (-not $DriveDir) {
        $m = Join-Path $env:USERPROFILE "My Drive"
        if (Test-Path $m) { $DriveDir = Join-Path $m "Matt Pocock Workflow\afk-logs" }
    }
}
if ($DriveDir) {
    try { New-Item -ItemType Directory -Path $DriveDir -Force | Out-Null }
    catch { Write-Warning "Drive log dir unusable ($($_.Exception.Message)) - local logs only"; $DriveDir = "" }
} else { Write-Warning "Drive not found - local logs only" }

function Write-Note([string]$Path, [string]$Text) {
    # Append a harness note. Retries a locked file, never throws. Unicode matches the child's *>> encoding.
    for ($try = 1; $try -le 5; $try++) {
        try { Add-Content -Path $Path -Value $Text -Encoding Unicode; return }
        catch { Start-Sleep -Seconds 2 }
    }
    Write-Warning "could not write note to ${Path}: $Text"
}

function Copy-ToDrive([string]$Path) {
    if (-not $DriveDir) { return }
    for ($try = 1; $try -le 3; $try++) {
        try { Copy-Item -Path $Path -Destination $DriveDir -Force; return }
        catch { Start-Sleep -Seconds 5 }
    }
    Write-Warning "could not copy $Path to Drive - local copy kept"
}

$modelArg = ""
if ($Model) { $modelArg = " --model $Model" }
Write-Host "Live logs -> $LocalDir"
Write-Host "Drive copy -> $(if ($DriveDir) { $DriveDir } else { 'none' })"
Write-Host "Model -> $(if ($Model) { $Model } else { 'default' }); UV_NO_SYNC=1 in every iteration"
$fails = 0
for ($i = 1; $i -le $MaxIterations; $i++) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $log   = Join-Path $LocalDir "afk-$stamp-iter$i.log"
    Write-Host "=== iteration $i/$MaxIterations -> $log ==="
    $inner = "`$env:UV_NO_SYNC='1'; Set-Location '$RepoRoot'; Get-Content -Raw '$PromptFile' | " +
             "claude -p --permission-mode acceptEdits$modelArg --max-turns $MaxTurns --verbose *>> '$log'"
    $proc = Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-Command",$inner `
            -WorkingDirectory $RepoRoot -PassThru -WindowStyle Hidden
    $stopAfter = $false
    if (-not $proc.WaitForExit($TimeoutMinutes * 60 * 1000)) {
        try { taskkill /PID $($proc.Id) /T /F | Out-Null } catch { }
        $proc.WaitForExit(15000) | Out-Null      # let the tree die and release the log handle
        Start-Sleep -Seconds 3
        Write-Note $log "`n=== TIMEOUT $TimeoutMinutes min - tree killed ==="
        Write-Host "iteration ${i}: TIMEOUT"; $fails++
        try { $dirty = git -C $RepoRoot status --porcelain } catch { $dirty = "unknown" }
        if ($dirty) {
            Write-Note $log "=== tree dirty after timeout - loop stopped for a supervised rescue ==="
            Write-Host "TIMEOUT left a dirty tree - stopping. Rescue by ceremony (once.ps1) before relaunching."
            $stopAfter = $true
        }
    } elseif ($proc.ExitCode -ne 0) {
        Write-Note $log "`n=== exit $($proc.ExitCode) ==="
        Write-Host "iteration ${i}: exit $($proc.ExitCode)"; $fails++
    } else {
        Write-Host "iteration ${i}: OK"; $fails = 0
    }
    Copy-ToDrive $log
    if ($stopAfter) { break }
    if ($fails -ge 2) { Write-Host "Two consecutive failures - stopping."; break }
    Start-Sleep -Seconds 30
}
Write-Host "afk loop finished."

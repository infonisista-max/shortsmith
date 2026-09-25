# once.ps1 - ONE interactive Claude Code session (HITL ceremony). PowerShell port of ralph/once.sh.
# Launch from the repo root:
#   powershell -ExecutionPolicy Bypass -File .\ralph\once.ps1 [-Ticket 050] [-Model opus]
# -Ticket names the HITL ticket for this session (prompt.md "Session discipline": HITL tickets
#   are worked only when the launch message names them). Omit it for review/board sessions.
# -Model  = fable | opus | sonnet | full model name. Omit to use the CLI default.
# Permission mode: acceptEdits (route B, 25 Sep 2026). File edits are auto-approved EXCEPT paths
#   listed under permissions.ask / permissions.deny in .claude/settings.json; every shell command
#   outside the allow list still prompts. Deny rules beat the mode.
# UV_NO_SYNC=1: `uv run` never installs or syncs; the operator installs in his own shell (uv add).
param(
    [string]$Ticket = "",
    [string]$Model  = ""
)
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
$env:UV_NO_SYNC = "1"

$msg = "Read ralph/prompt.md."
if ($Ticket) { $msg += " This session is the HITL ceremony for ticket $Ticket; work that ticket only." }
$msg += " Propose your task selection and plan first, and wait for my go before implementing."

$claudeArgs = @("--permission-mode", "acceptEdits")
if ($Model) { $claudeArgs += @("--model", $Model) }
$claudeArgs += $msg

Write-Host "once.ps1: repo=$RepoRoot ticket=$(if ($Ticket) { $Ticket } else { '-' }) model=$(if ($Model) { $Model } else { 'default' }) UV_NO_SYNC=1"
& claude @claudeArgs

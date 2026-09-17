# once.ps1 — PowerShell equivalent of Matt Pocock's ralph/once.sh
# (ADDITION for Windows. Matt's original is once.sh, which also works in Git Bash on Windows.)
#
# What it does: builds ONE prompt out of (a) the last 5 commits, (b) every open issue file,
# (c) ralph/prompt.md — then launches an interactive Claude Code session with that prompt.
# This is the HUMAN-IN-THE-LOOP version: you watch one iteration, learn how the agent behaves,
# and tune ralph/prompt.md before ever running it unattended.
#
# Run from the repo root:   .\ralph\once.ps1

$issueFiles = Get-ChildItem -Path "issues/*.md" -File -ErrorAction SilentlyContinue
if ($issueFiles) {
  $issues = ($issueFiles | ForEach-Object { Get-Content $_.FullName -Raw }) -join "`n"
} else {
  $issues = "No issues found"
}

$commitLines = git log -n 5 --format="%H%n%ad%n%B---" --date=short 2>$null
if ($commitLines) { $commits = ($commitLines -join "`n") } else { $commits = "No commits found" }

$prompt = Get-Content "ralph/prompt.md" -Raw

# --permission-mode acceptEdits = file edits are auto-approved, but every shell command
# (npm test, git commit, ...) still asks you. That is exactly what you want while learning.
claude --permission-mode acceptEdits "Previous commits: $commits Issues: $issues $prompt"

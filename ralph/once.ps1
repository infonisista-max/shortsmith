# once.ps1 - PowerShell equivalent of Matt Pocock's ralph/once.sh (HITL version).
# Launches ONE interactive Claude Code session. The agent reads ralph/prompt.md,
# the issues, and git log itself - nothing is stuffed into the command line.
# --permission-mode acceptEdits: file edits auto-approved, every shell command still prompts.
# Run from the repo root:   .\ralph\once.ps1

claude --permission-mode acceptEdits "Read ralph/prompt.md. Propose your task selection and plan first, and wait for my go before implementing."

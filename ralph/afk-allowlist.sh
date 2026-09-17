#!/bin/bash
# afk-allowlist.sh — ADDITION (not in Matt's repo). Level-B AFK loop for machines WITHOUT Docker.
#
# Matt's afk.sh runs Claude inside a Docker sandbox so a runaway agent cannot touch your machine.
# This script is the safer middle step between once.sh (fully supervised) and afk.sh (sandboxed):
# it runs unattended, but the agent may ONLY run the shell commands listed in --allowedTools.
# Anything else (curl, rm -rf, npm install, pushing to GitHub...) is DENIED, not asked.
#
# Trade-off you are accepting: the agent still has real write access to this repo's files.
# So: run it on a git branch, in a repo you have pushed to GitHub, with no secrets in the tree.
#
# Requirements: Git Bash (ships with Git for Windows), jq (winget install jqlang.jq), Claude Code.
# Usage from repo root:   ./ralph/afk-allowlist.sh 5      # run up to 5 iterations
set -eo pipefail

if [ -z "$1" ]; then
  echo "Usage: $0 <iterations>"
  exit 1
fi

# jq filter to extract streaming text from assistant messages (same as Matt's afk.sh)
stream_text='select(.type == "assistant").message.content[]? | select(.type == "text").text // empty | gsub("\n"; "\r\n") | . + "\r\n\n"'
# jq filter to extract final result
final_result='select(.type == "result").result // empty'

for ((i=1; i<=$1; i++)); do
  tmpfile=$(mktemp)
  trap "rm -f $tmpfile" EXIT

  commits=$(git log -n 5 --format="%H%n%ad%n%B---" --date=short 2>/dev/null || echo "No commits found")
  issues=$(cat issues/*.md 2>/dev/null || echo "No issues found")
  prompt=$(cat ralph/prompt.md)

  echo "===== Ralph iteration $i of $1 ====="

  # The prompt goes FIRST as a positional argument so it cannot be swallowed by --allowedTools.
  # Edit the allowlist to match YOUR project's feedback-loop commands (see ralph/prompt.md).
  claude -p "Previous commits: $commits Issues: $issues $prompt" \
    --verbose \
    --output-format stream-json \
    --permission-mode acceptEdits \
    --allowedTools \
      "Bash(uv run:*)" \
      "Bash(ffprobe:*)" \
      "Bash(ffmpeg:*)" \
      "Bash(git add:*)" \
      "Bash(git commit:*)" \
      "Bash(git status:*)" \
      "Bash(git diff:*)" \
      "Bash(git log:*)" \
      "Bash(mv issues/:*)" \
      "Bash(mkdir:*)" \
  | grep --line-buffered '^{' \
  | tee "$tmpfile" \
  | jq --unbuffered -rj "$stream_text"

  result=$(jq -r "$final_result" "$tmpfile")

  if [[ "$result" == *"<promise>NO MORE TASKS</promise>"* ]]; then
    echo "Ralph complete after $i iterations."
    exit 0
  fi
done

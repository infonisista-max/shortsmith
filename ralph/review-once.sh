#!/bin/bash
# review-once.sh — ADDITION (not in Matt's workshop repo).
#
# Implements what Matt described in the Q&A: an automated code review of the LAST commit,
# run in a FRESH context (so the reviewer is in the smart zone, not the implementer's dumb zone),
# with the coding standards PUSHED to the reviewer (the implementer only PULLS them via skills).
#
# It is read-only for the reviewer: no edits, no commits. It writes its findings to
# reviews/review-<shortsha>.md so you can turn real findings into new kanban tickets. (Kept OUT of issues/ so the Ralph loop does not mistake it for a ticket.)
#
# Usage from repo root:   ./ralph/review-once.sh
set -eo pipefail

mkdir -p reviews
sha=$(git rev-parse --short HEAD)
diff=$(git show --stat --patch HEAD)
standards=$(cat .claude/skills/tdd/SKILL.md .claude/skills/tdd/tests.md .claude/skills/tdd/deep-modules.md 2>/dev/null || echo "No standards files found")

claude -p "You are a senior code reviewer working in a fresh context.

CODING STANDARDS (pushed to you — enforce them):
$standards

COMMIT UNDER REVIEW ($sha):
$diff

Review for: (1) tests that test behaviour through public interfaces, not implementation;
(2) shallow modules or scattered logic that should be a deep module; (3) bugs, unhandled
edge cases, security problems; (4) anything that violates the standards above.
Do NOT edit files. Output a concise markdown review with a severity for each finding
(BLOCKER / SHOULD-FIX / NIT) and, for each BLOCKER or SHOULD-FIX, a one-line suggested ticket title." \
  --permission-mode plan \
  > "reviews/review-$sha.md"

echo "Review written to reviews/review-$sha.md"
